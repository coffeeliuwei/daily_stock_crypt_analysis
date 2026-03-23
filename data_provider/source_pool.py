# -*- coding: utf-8 -*-
"""
===================================
数据源池管理器 (DataSourcePool)
===================================

设计目标：
1. 随机选择数据源 - 避免单一数据源过载
2. 互斥访问 - 同一时间同一数据源只有一个请求
3. 健康状态追踪 - 自动降级失败的数据源
4. 冷却机制 - 连续失败后自动冷却

使用场景：
- 批量分析股票时，多并发从池中获取数据源
- 每个并发随机选择可用数据源，避免集中访问
"""

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class SourceSelectionMode(Enum):
    """数据源选择模式"""

    RANDOM = "random"  # 加权随机选择（推荐）
    ROUND_ROBIN = "round_robin"  # 轮询
    PRIORITY = "priority"  # 按优先级顺序（原有逻辑）


@dataclass
class SourceHealth:
    """数据源健康状态"""

    name: str
    health_score: float = 1.0  # 健康分数 0-1
    failure_count: int = 0  # 连续失败次数
    success_count: int = 0  # 成功次数
    last_failure_time: float = 0  # 最后失败时间
    cooldown_until: float = 0  # 冷却结束时间
    avg_latency: float = 0  # 平均延迟（秒）
    total_requests: int = 0  # 总请求数


@dataclass
class SourcePoolConfig:
    """数据源池配置"""

    selection_mode: SourceSelectionMode = SourceSelectionMode.RANDOM
    failure_threshold: int = 3  # 连续失败次数触发冷却
    cooldown_seconds: float = 300  # 冷却时间（秒）
    health_decay: float = 0.15  # 失败时健康分衰减
    health_recovery: float = 0.05  # 成功时健康分恢复
    min_health_score: float = 0.1  # 最低健康分数
    max_lock_wait_seconds: float = 5.0  # 最大等待锁时间


class DataSourcePool:
    """
    数据源池管理器

    核心功能：
    1. 管理多个数据源实例
    2. 提供线程安全的数据源获取/释放
    3. 追踪每个数据源的健康状态
    4. 支持加权随机选择

    使用方式：
        pool = DataSourcePool(fetchers, config)

        # 获取数据源
        result = pool.acquire_fetcher()
        if result:
            fetcher, lock = result
            try:
                data = fetcher.get_daily_data(code)
                pool.release_fetcher(fetcher.name, success=True)
            except Exception:
                pool.release_fetcher(fetcher.name, success=False)
    """

    def __init__(
        self,
        fetchers: List[Any],  # List[BaseFetcher]
        config: Optional[SourcePoolConfig] = None,
    ):
        """
        初始化数据源池

        Args:
            fetchers: 数据源实例列表
            config: 池配置
        """
        self._fetchers = list(fetchers)
        self._config = config or SourcePoolConfig()

        # 每个数据源一个锁（可重入锁，支持同一线程多次获取）
        self._locks: Dict[str, RLock] = {f.name: RLock() for f in fetchers}

        # 健康状态追踪
        self._health: Dict[str, SourceHealth] = {
            f.name: SourceHealth(name=f.name) for f in fetchers
        }

        # 全局锁（用于健康状态更新等操作）
        self._global_lock = RLock()

        # 轮询索引（用于 round_robin 模式）
        self._round_robin_index = 0

        # 统计
        self._total_acquires = 0
        self._total_releases = 0

        logger.info(
            f"DataSourcePool initialized with {len(fetchers)} fetchers: "
            f"{[f.name for f in fetchers]}"
        )

    def acquire_fetcher(
        self,
        exclude_names: Optional[List[str]] = None,
        prefer_names: Optional[List[str]] = None,
    ) -> Optional[Tuple[Any, RLock]]:
        """
        获取一个可用的数据源（带锁）

        Args:
            exclude_names: 排除的数据源名称列表
            prefer_names: 优先选择的数据源名称列表

        Returns:
            (fetcher, lock) 或 None（所有数据源都不可用）
        """
        exclude_names = exclude_names or []

        with self._global_lock:
            self._total_acquires += 1

            # 获取可用数据源列表
            available = self._get_available_fetchers(exclude_names)

            if not available:
                logger.warning(
                    f"[DataSourcePool] No available fetchers "
                    f"(excluded: {exclude_names}, all in cooldown or locked)"
                )
                return None

            # 根据选择模式选择数据源
            selected = self._select_fetcher(available, prefer_names)

            if selected is None:
                return None

            # 尝试获取锁（非阻塞）
            lock = self._locks[selected.name]
            if lock.acquire(blocking=False):
                logger.debug(
                    f"[DataSourcePool] Acquired fetcher: {selected.name} "
                    f"(health: {self._health[selected.name].health_score:.2f})"
                )
                return (selected, lock)

            # 锁被占用，尝试其他数据源
            for fetcher in available:
                if fetcher.name == selected.name:
                    continue
                lock = self._locks[fetcher.name]
                if lock.acquire(blocking=False):
                    logger.debug(
                        f"[DataSourcePool] Acquired fetcher (fallback): {fetcher.name}"
                    )
                    return (fetcher, lock)

            logger.warning(
                f"[DataSourcePool] All {len(available)} available fetchers are locked"
            )
            return None

    def release_fetcher(
        self, name: str, success: bool, latency: Optional[float] = None
    ) -> None:
        """
        释放数据源并更新健康状态

        Args:
            name: 数据源名称
            success: 是否成功
            latency: 请求延迟（秒）
        """
        with self._global_lock:
            self._total_releases += 1
            health = self._health.get(name)

            if health is None:
                logger.warning(f"[DataSourcePool] Unknown fetcher: {name}")
                return

            health.total_requests += 1

            if success:
                health.failure_count = 0
                health.success_count += 1
                health.health_score = min(
                    1.0, health.health_score + self._config.health_recovery
                )
                if latency:
                    # 更新平均延迟（指数移动平均）
                    health.avg_latency = 0.7 * health.avg_latency + 0.3 * latency
                logger.debug(
                    f"[DataSourcePool] Released {name}: success, "
                    f"health={health.health_score:.2f}"
                )
            else:
                health.failure_count += 1
                health.last_failure_time = time.time()
                health.health_score = max(
                    self._config.min_health_score,
                    health.health_score - self._config.health_decay,
                )

                # 检查是否需要冷却
                if health.failure_count >= self._config.failure_threshold:
                    health.cooldown_until = time.time() + self._config.cooldown_seconds
                    logger.warning(
                        f"[DataSourcePool] {name} entering cooldown for "
                        f"{self._config.cooldown_seconds}s "
                        f"(failures: {health.failure_count})"
                    )

                logger.debug(
                    f"[DataSourcePool] Released {name}: failed, "
                    f"health={health.health_score:.2f}, "
                    f"failures={health.failure_count}"
                )

            # 释放锁
            lock = self._locks.get(name)
            if lock and lock._is_owned():
                lock.release()

    def _get_available_fetchers(self, exclude_names: List[str]) -> List[Any]:
        """获取当前可用的数据源列表"""
        now = time.time()
        available = []

        for fetcher in self._fetchers:
            if fetcher.name in exclude_names:
                continue

            health = self._health[fetcher.name]

            # 检查是否在冷却中
            if health.cooldown_until > now:
                continue

            available.append(fetcher)

        return available

    def _select_fetcher(
        self, available: List[Any], prefer_names: Optional[List[str]] = None
    ) -> Optional[Any]:
        """根据选择模式选择数据源"""
        if not available:
            return None

        prefer_names = prefer_names or []

        if self._config.selection_mode == SourceSelectionMode.RANDOM:
            # 加权随机选择
            weights = [self._health[f.name].health_score for f in available]
            return random.choices(available, weights=weights, k=1)[0]

        elif self._config.selection_mode == SourceSelectionMode.ROUND_ROBIN:
            # 轮询
            self._round_robin_index = (self._round_robin_index + 1) % len(available)
            return available[self._round_robin_index]

        elif self._config.selection_mode == SourceSelectionMode.PRIORITY:
            # 按优先级（原有逻辑，fetcher 列表已按优先级排序）
            # 优先选择 prefer_names 中的
            for name in prefer_names:
                for f in available:
                    if f.name == name:
                        return f
            return available[0]

        return available[0]

    def get_health_report(self) -> Dict[str, Any]:
        """获取健康状态报告"""
        with self._global_lock:
            return {
                name: {
                    "health_score": h.health_score,
                    "failure_count": h.failure_count,
                    "success_count": h.success_count,
                    "total_requests": h.total_requests,
                    "avg_latency": h.avg_latency,
                    "in_cooldown": h.cooldown_until > time.time(),
                }
                for name, h in self._health.items()
            }

    def reset_health(self, name: Optional[str] = None) -> None:
        """重置健康状态"""
        with self._global_lock:
            if name:
                if name in self._health:
                    self._health[name] = SourceHealth(name=name)
                    logger.info(f"[DataSourcePool] Reset health for {name}")
            else:
                for n in self._health:
                    self._health[n] = SourceHealth(name=n)
                logger.info("[DataSourcePool] Reset health for all fetchers")

    def get_fetcher_names(self) -> List[str]:
        """获取所有数据源名称"""
        return [f.name for f in self._fetchers]

    @property
    def stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._global_lock:
            return {
                "total_fetchers": len(self._fetchers),
                "total_acquires": self._total_acquires,
                "total_releases": self._total_releases,
            }


# 全局数据源池实例（延迟初始化）
_global_pool: Optional[DataSourcePool] = None
_pool_lock = RLock()


def get_source_pool(
    fetchers: Optional[List[Any]] = None,
    config: Optional[SourcePoolConfig] = None,
    force_new: bool = False,
) -> DataSourcePool:
    """
    获取全局数据源池实例

    Args:
        fetchers: 数据源列表（首次调用时必须提供）
        config: 池配置
        force_new: 是否强制创建新实例

    Returns:
        DataSourcePool 实例
    """
    global _global_pool

    with _pool_lock:
        if _global_pool is None or force_new:
            if fetchers is None:
                raise ValueError("First call to get_source_pool must provide fetchers")
            _global_pool = DataSourcePool(fetchers, config)
        return _global_pool


def reset_source_pool() -> None:
    """重置全局数据源池"""
    global _global_pool

    with _pool_lock:
        _global_pool = None
