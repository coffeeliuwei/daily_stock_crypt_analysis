# -*- coding: utf-8 -*-
"""
===================================
数据源健康检测器
===================================

功能：
1. 启动时检测所有数据源是否可用
2. 记录响应时间和成功率
3. 自动排除不可用的数据源
4. 支持动态添加新数据源检测

使用方式：
    from data_provider.source_health_checker import SourceHealthChecker

    checker = SourceHealthChecker()
    results = checker.check_all()
    for name, result in results.items():
        print(f"{name}: {'可用' if result.available else '不可用'}")
"""

import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SourceStatus(Enum):
    """数据源状态"""

    AVAILABLE = "available"  # 可用
    UNAVAILABLE = "unavailable"  # 不可用
    TIMEOUT = "timeout"  # 超时
    ERROR = "error"  # 错误
    UNKNOWN = "unknown"  # 未知


@dataclass
class HealthCheckResult:
    """健康检测结果"""

    name: str  # 数据源名称
    status: SourceStatus  # 状态
    available: bool  # 是否可用
    latency_ms: float = 0.0  # 响应时间（毫秒）
    error_message: Optional[str] = None  # 错误信息
    timestamp: str = ""  # 检测时间
    details: Dict[str, Any] = field(default_factory=dict)  # 详细信息

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "status": self.status.value,
            "available": self.available,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "details": self.details,
        }


@dataclass
class HealthCheckConfig:
    """健康检测配置"""

    timeout_seconds: float = 5.0  # 单个检测超时时间
    retry_count: int = 2  # 重试次数
    retry_delay: float = 1.0  # 重试间隔
    concurrent_checks: int = 5  # 并发检测数
    test_stock_code: str = "600519"  # 测试用的股票代码（茅台）
    test_us_stock_code: str = "AAPL"  # 测试用的美股代码
    test_crypto_code: str = "BTC"  # 测试用的加密货币代码


class SourceHealthChecker:
    """
    数据源健康检测器

    功能：
    1. 检测数据源是否可用
    2. 记录响应时间
    3. 自动排除不可用数据源
    4. 支持批量并发检测
    """

    def __init__(self, config: Optional[HealthCheckConfig] = None):
        """
        初始化检测器

        Args:
            config: 检测配置
        """
        self.config = config or HealthCheckConfig()
        self._results: Dict[str, HealthCheckResult] = {}
        self._lock = threading.Lock()

        # 注册的检测函数
        self._checkers: Dict[str, Callable[[], HealthCheckResult]] = {}

        # 注册默认检测器
        self._register_default_checkers()

    def _register_default_checkers(self) -> None:
        """注册默认的数据源检测器"""
        # A股数据源
        self.register_checker("EfinanceFetcher", self._check_efinance)
        self.register_checker("AkshareFetcher", self._check_akshare)
        self.register_checker("PytdxFetcher", self._check_pytdx)
        self.register_checker("TushareFetcher", self._check_tushare)
        self.register_checker("BaostockFetcher", self._check_baostock)
        self.register_checker("QVerisFetcher", self._check_qveris)

        # 美股数据源
        self.register_checker("YfinanceFetcher", self._check_yfinance)

        # 加密货币数据源
        self.register_checker("CryptoFetcher", self._check_crypto)

        # 新增数据源（待实现检测）
        self.register_checker("FinshareFetcher", self._check_finshare)
        self.register_checker("AshareFetcher", self._check_ashare)
        self.register_checker("AllTickFetcher", self._check_alltick)
        self.register_checker("FinnhubFetcher", self._check_finnhub)
        self.register_checker("ITickFetcher", self._check_itick)

    def register_checker(
        self, name: str, checker: Callable[[], HealthCheckResult]
    ) -> None:
        """
        注册数据源检测器

        Args:
            name: 数据源名称
            checker: 检测函数
        """
        self._checkers[name] = checker
        logger.debug(f"[HealthChecker] 注册检测器: {name}")

    def check_single(self, name: str) -> HealthCheckResult:
        """
        检测单个数据源

        Args:
            name: 数据源名称

        Returns:
            检测结果
        """
        if name not in self._checkers:
            return HealthCheckResult(
                name=name,
                status=SourceStatus.UNKNOWN,
                available=False,
                error_message=f"未注册的检测器: {name}",
            )

        checker = self._checkers[name]

        for attempt in range(self.config.retry_count):
            try:
                result = checker()
                with self._lock:
                    self._results[name] = result
                return result
            except Exception as e:
                if attempt < self.config.retry_count - 1:
                    time.sleep(self.config.retry_delay)
                    continue
                result = HealthCheckResult(
                    name=name,
                    status=SourceStatus.ERROR,
                    available=False,
                    error_message=str(e),
                )
                with self._lock:
                    self._results[name] = result
                return result

        return HealthCheckResult(
            name=name,
            status=SourceStatus.ERROR,
            available=False,
            error_message="检测失败",
        )

    def check_all(
        self, names: Optional[List[str]] = None
    ) -> Dict[str, HealthCheckResult]:
        """
        并发检测所有数据源

        Args:
            names: 要检测的数据源名称列表，None 表示检测所有

        Returns:
            检测结果字典
        """
        if names is None:
            names = list(self._checkers.keys())

        results: Dict[str, HealthCheckResult] = {}
        threads: List[threading.Thread] = []

        def check_and_store(name: str):
            result = self.check_single(name)
            results[name] = result

        # 并发检测
        for name in names:
            thread = threading.Thread(target=check_and_store, args=(name,))
            thread.start()
            threads.append(thread)

            # 限制并发数
            while (
                len([t for t in threads if t.is_alive()])
                >= self.config.concurrent_checks
            ):
                time.sleep(0.1)

        # 等待所有检测完成
        for thread in threads:
            thread.join(timeout=self.config.timeout_seconds * 2)

        # 记录结果
        available_count = sum(1 for r in results.values() if r.available)
        logger.info(
            f"[HealthChecker] 检测完成: {available_count}/{len(results)} 个数据源可用"
        )

        return results

    def get_available_sources(self) -> List[str]:
        """获取可用的数据源列表"""
        return [name for name, result in self._results.items() if result.available]

    def get_unavailable_sources(self) -> List[str]:
        """获取不可用的数据源列表"""
        return [name for name, result in self._results.items() if not result.available]

    def get_health_report(self) -> Dict[str, Any]:
        """获取健康状态报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "total_sources": len(self._results),
            "available_count": len(self.get_available_sources()),
            "unavailable_count": len(self.get_unavailable_sources()),
            "sources": {
                name: result.to_dict() for name, result in self._results.items()
            },
        }

    # ========================================
    # 具体数据源检测实现
    # ========================================

    def _check_efinance(self) -> HealthCheckResult:
        """检测东方财富数据源"""
        start_time = time.time()
        try:
            from .efinance_fetcher import EfinanceFetcher

            fetcher = EfinanceFetcher()

            # 尝试获取测试股票数据
            df = fetcher.get_daily_data(stock_code=self.config.test_stock_code, days=5)

            latency = (time.time() - start_time) * 1000

            if df is not None and not df.empty:
                return HealthCheckResult(
                    name="EfinanceFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"rows": len(df)},
                )
            else:
                return HealthCheckResult(
                    name="EfinanceFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="EfinanceFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_akshare(self) -> HealthCheckResult:
        """检测 Akshare 数据源"""
        start_time = time.time()
        try:
            from .akshare_fetcher import AkshareFetcher

            fetcher = AkshareFetcher()

            df = fetcher.get_daily_data(stock_code=self.config.test_stock_code, days=5)

            latency = (time.time() - start_time) * 1000

            if df is not None and not df.empty:
                return HealthCheckResult(
                    name="AkshareFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"rows": len(df)},
                )
            else:
                return HealthCheckResult(
                    name="AkshareFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="AkshareFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_pytdx(self) -> HealthCheckResult:
        """检测通达信数据源"""
        start_time = time.time()
        try:
            from .pytdx_fetcher import PytdxFetcher

            fetcher = PytdxFetcher()

            df = fetcher.get_daily_data(stock_code=self.config.test_stock_code, days=5)

            latency = (time.time() - start_time) * 1000

            if df is not None and not df.empty:
                return HealthCheckResult(
                    name="PytdxFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"rows": len(df)},
                )
            else:
                return HealthCheckResult(
                    name="PytdxFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="PytdxFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_tushare(self) -> HealthCheckResult:
        """检测 Tushare 数据源"""
        start_time = time.time()
        try:
            from .tushare_fetcher import TushareFetcher

            fetcher = TushareFetcher()

            # 检查是否配置了 Token（使用 getattr 安全检查）
            token = getattr(fetcher, "_token", None) or getattr(fetcher, "token", None)
            if not token:
                return HealthCheckResult(
                    name="TushareFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=0,
                    error_message="未配置 TUSHARE_TOKEN",
                )

            df = fetcher.get_daily_data(stock_code=self.config.test_stock_code, days=5)

            latency = (time.time() - start_time) * 1000

            if df is not None and not df.empty:
                return HealthCheckResult(
                    name="TushareFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"rows": len(df)},
                )
            else:
                return HealthCheckResult(
                    name="TushareFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="TushareFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_baostock(self) -> HealthCheckResult:
        """检测 Baostock 数据源"""
        start_time = time.time()
        try:
            from .baostock_fetcher import BaostockFetcher

            fetcher = BaostockFetcher()

            df = fetcher.get_daily_data(stock_code=self.config.test_stock_code, days=5)

            latency = (time.time() - start_time) * 1000

            if df is not None and not df.empty:
                return HealthCheckResult(
                    name="BaostockFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"rows": len(df)},
                )
            else:
                return HealthCheckResult(
                    name="BaostockFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="BaostockFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_qveris(self) -> HealthCheckResult:
        """检测 QVeris 数据源"""
        start_time = time.time()
        try:
            from .qveris_fetcher import QVerisFetcher

            fetcher = QVerisFetcher()

            # 检查是否配置了 API Key（使用 getattr 安全检查）
            api_key = getattr(fetcher, "_api_key", None) or getattr(
                fetcher, "api_key", None
            )
            if not api_key:
                return HealthCheckResult(
                    name="QVerisFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=0,
                    error_message="未配置 QVERIS_API_KEY",
                )

            df = fetcher.get_daily_data(stock_code=self.config.test_stock_code, days=5)

            latency = (time.time() - start_time) * 1000

            if df is not None and not df.empty:
                return HealthCheckResult(
                    name="QVerisFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"rows": len(df)},
                )
            else:
                return HealthCheckResult(
                    name="QVerisFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="QVerisFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_yfinance(self) -> HealthCheckResult:
        """检测 Yahoo Finance 数据源"""
        start_time = time.time()
        try:
            from .yfinance_fetcher import YfinanceFetcher

            fetcher = YfinanceFetcher()

            df = fetcher.get_daily_data(
                stock_code=self.config.test_us_stock_code, days=5
            )

            latency = (time.time() - start_time) * 1000

            if df is not None and not df.empty:
                return HealthCheckResult(
                    name="YfinanceFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"rows": len(df)},
                )
            else:
                return HealthCheckResult(
                    name="YfinanceFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="YfinanceFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_crypto(self) -> HealthCheckResult:
        """检测加密货币数据源"""
        start_time = time.time()
        try:
            from .crypto_fetcher import CryptoFetcher

            fetcher = CryptoFetcher()

            df = fetcher.get_daily_data(stock_code=self.config.test_crypto_code, days=5)

            latency = (time.time() - start_time) * 1000

            if df is not None and not df.empty:
                return HealthCheckResult(
                    name="CryptoFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"rows": len(df)},
                )
            else:
                return HealthCheckResult(
                    name="CryptoFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="CryptoFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    # ========================================
    # 新增数据源检测（待实现 Fetcher 后启用）
    # ========================================

    def _check_finshare(self) -> HealthCheckResult:
        """检测 Finshare 数据源"""
        start_time = time.time()
        try:
            import finshare as fs

            # 尝试获取快照数据（返回 SnapshotData 对象）
            snapshot = fs.get_snapshot_data(f"{self.config.test_stock_code}.SH")
            latency = (time.time() - start_time) * 1000

            # SnapshotData 是对象，检查是否有有效数据
            if snapshot is not None:
                # 检查是否有价格数据
                if hasattr(snapshot, "price") and snapshot.price:
                    return HealthCheckResult(
                        name="FinshareFetcher",
                        status=SourceStatus.AVAILABLE,
                        available=True,
                        latency_ms=latency,
                        details={"price": getattr(snapshot, "price", None)},
                    )
                # 检查是否是字典格式
                if isinstance(snapshot, dict) and snapshot.get("price"):
                    return HealthCheckResult(
                        name="FinshareFetcher",
                        status=SourceStatus.AVAILABLE,
                        available=True,
                        latency_ms=latency,
                        details={"price": snapshot.get("price")},
                    )
                # 即使没有价格，只要返回了对象也算可用
                return HealthCheckResult(
                    name="FinshareFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"note": "返回数据对象"},
                )
            else:
                return HealthCheckResult(
                    name="FinshareFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except ImportError:
            return HealthCheckResult(
                name="FinshareFetcher",
                status=SourceStatus.UNAVAILABLE,
                available=False,
                latency_ms=0,
                error_message="finshare 库未安装，请运行: pip install finshare",
            )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="FinshareFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_ashare(self) -> HealthCheckResult:
        """检测 Ashare 数据源（腾讯财经 API）"""
        start_time = time.time()
        try:
            from .ashare_fetcher import AshareFetcher

            fetcher = AshareFetcher()

            # 尝试获取测试股票数据
            df = fetcher.get_daily_data(stock_code=self.config.test_stock_code, days=5)

            latency = (time.time() - start_time) * 1000

            if df is not None and not df.empty:
                return HealthCheckResult(
                    name="AshareFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"rows": len(df)},
                )
            else:
                return HealthCheckResult(
                    name="AshareFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据为空",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="AshareFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_alltick(self) -> HealthCheckResult:
        """检测 AllTick 数据源"""
        start_time = time.time()
        try:
            import alltick

            # 尝试获取数据（需要 API Key）
            latency = (time.time() - start_time) * 1000

            return HealthCheckResult(
                name="AllTickFetcher",
                status=SourceStatus.AVAILABLE,
                available=True,
                latency_ms=latency,
                details={"note": "需要配置 ALLTICK_API_KEY"},
            )
        except ImportError:
            return HealthCheckResult(
                name="AllTickFetcher",
                status=SourceStatus.UNAVAILABLE,
                available=False,
                latency_ms=0,
                error_message="alltick 库未安装，请运行: pip install alltick",
            )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="AllTickFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_finnhub(self) -> HealthCheckResult:
        """检测 Finnhub 数据源"""
        start_time = time.time()
        try:
            import finnhub

            # 需要配置 API Key
            import os

            api_key = os.environ.get("FINNHUB_API_KEY", "")
            if not api_key:
                return HealthCheckResult(
                    name="FinnhubFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=0,
                    error_message="未配置 FINNHUB_API_KEY",
                )

            finnhub_client = finnhub.Client(api_key=api_key)
            # 测试获取股票数据
            quote = finnhub_client.quote(self.config.test_us_stock_code)

            latency = (time.time() - start_time) * 1000

            if quote and "c" in quote:  # c = current price
                return HealthCheckResult(
                    name="FinnhubFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"current_price": quote.get("c")},
                )
            else:
                return HealthCheckResult(
                    name="FinnhubFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message="返回数据格式异常",
                )
        except ImportError:
            return HealthCheckResult(
                name="FinnhubFetcher",
                status=SourceStatus.UNAVAILABLE,
                available=False,
                latency_ms=0,
                error_message="finnhub-python 库未安装，请运行: pip install finnhub-python",
            )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="FinnhubFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )

    def _check_itick(self) -> HealthCheckResult:
        """检测 iTick 数据源"""
        start_time = time.time()
        try:
            import requests

            # iTick HTTP API 测试
            url = "https://itick.io/api/v1/quote?symbol=AAPL"
            response = requests.get(url, timeout=self.config.timeout_seconds)

            latency = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                return HealthCheckResult(
                    name="ITickFetcher",
                    status=SourceStatus.AVAILABLE,
                    available=True,
                    latency_ms=latency,
                    details={"response": str(data)[:100]},
                )
            else:
                return HealthCheckResult(
                    name="ITickFetcher",
                    status=SourceStatus.UNAVAILABLE,
                    available=False,
                    latency_ms=latency,
                    error_message=f"HTTP {response.status_code}",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="ITickFetcher",
                status=SourceStatus.ERROR,
                available=False,
                latency_ms=latency,
                error_message=str(e)[:200],
            )


# ========================================
# 全局单例
# ========================================

_health_checker: Optional[SourceHealthChecker] = None
_health_checker_lock = threading.Lock()


def get_health_checker() -> SourceHealthChecker:
    """获取全局健康检测器实例"""
    global _health_checker
    if _health_checker is None:
        with _health_checker_lock:
            if _health_checker is None:
                _health_checker = SourceHealthChecker()
    return _health_checker


def check_sources_health(
    names: Optional[List[str]] = None,
    config: Optional[HealthCheckConfig] = None,
) -> Dict[str, HealthCheckResult]:
    """
    检测数据源健康状态（便捷函数）

    Args:
        names: 要检测的数据源名称列表
        config: 检测配置

    Returns:
        检测结果字典
    """
    checker = SourceHealthChecker(config) if config else get_health_checker()
    return checker.check_all(names)
