# -*- coding: utf-8 -*-
"""
===================================
LLM 模型池管理器 (LLMModelPool)
===================================

设计目标：
1. 支持多个模型配置（逗号分隔）
2. 随机选择模型 - 负载均衡
3. 健康状态追踪 - 自动降级失败的模型
4. 失败重试 - 切换到其他模型

使用场景：
- 阿里云百炼等 OpenAI 兼容平台
- 多模型共用一个 API Key 和 Base URL
- 在 GitHub Actions Secrets 中配置 OPENAI_MODEL=qwen-turbo,qwen-plus,qwen-max
"""

import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Dict, List, Optional, Any, Tuple

import litellm

logger = logging.getLogger(__name__)


class ModelSelectionMode(Enum):
    """模型选择模式"""

    RANDOM = "random"  # 随机选择（推荐）
    SEQUENTIAL = "sequential"  # 顺序选择
    LEAST_LATENCY = "least_latency"  # 选择延迟最低的


@dataclass(slots=True)
class ModelHealth:
    """模型健康状态（内存优化：使用 slots=True）"""

    name: str
    health_score: float = 1.0  # 健康分数 0-1
    failure_count: int = 0  # 连续失败次数
    success_count: int = 0  # 成功次数
    avg_latency: float = 0  # 平均延迟（秒）
    total_requests: int = 0  # 总请求数
    last_error: Optional[str] = None  # 最后一次错误


@dataclass(slots=True)
class ModelPoolConfig:
    """模型池配置（内存优化：使用 slots=True）"""

    selection_mode: ModelSelectionMode = ModelSelectionMode.RANDOM
    health_decay: float = 0.1  # 失败时健康分衰减
    health_recovery: float = 0.05  # 成功时健康分恢复
    min_health_score: float = 0.1  # 最低健康分数
    latency_weight: float = 0.3  # 延迟权重（用于 least_latency 模式）


class LLMModelPool:
    """
    LLM 模型池管理器

    核心功能：
    1. 管理多个模型
    2. 提供线程安全的模型选择
    3. 追踪每个模型的健康状态
    4. 支持加权随机选择

    使用方式：
        pool = LLMModelPool(
            models=["qwen-turbo", "qwen-plus", "qwen-max"],
            api_key="your-api-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        # 调用模型
        response, model_used, usage = pool.call(messages=[...])
    """

    def __init__(
        self,
        models: List[str],
        api_key: str,
        base_url: Optional[str] = None,
        config: Optional[ModelPoolConfig] = None,
    ):
        """
        初始化模型池

        Args:
            models: 模型名称列表（如 ["qwen-turbo", "qwen-plus", "qwen-max"]）
            api_key: API Key
            base_url: API Base URL（阿里云百炼等兼容平台需要设置）
            config: 池配置
        """
        if not models:
            raise ValueError("models list cannot be empty")

        self._models = models
        self._api_key = api_key
        self._base_url = base_url
        self._config = config or ModelPoolConfig()

        # 健康状态追踪
        self._health: Dict[str, ModelHealth] = {m: ModelHealth(name=m) for m in models}

        # 全局锁
        self._lock = RLock()

        # 统计
        self._total_calls = 0
        self._total_success = 0
        self._total_failures = 0

        # 格式化模型名称（添加 openai/ 前缀以兼容 LiteLLM）
        self._formatted_models = self._format_models(models)

        logger.info(
            f"LLMModelPool initialized with {len(models)} models: "
            f"{models}, selection_mode: {self._config.selection_mode.value}"
        )

    def _format_models(self, models: List[str]) -> List[str]:
        """
        格式化模型名称以兼容 LiteLLM

        LiteLLM 需要 provider/model 格式，对于 OpenAI 兼容 API，
        使用 openai/ 前缀
        """
        formatted = []
        for m in models:
            if "/" not in m:
                formatted.append(f"openai/{m}")
            else:
                formatted.append(m)
        return formatted

    def select_model(self) -> str:
        """
        根据选择模式选择一个模型

        Returns:
            格式化后的模型名称（包含 openai/ 前缀）
        """
        with self._lock:
            available = [
                m
                for m in self._formatted_models
                if self._health[self._get_original_name(m)].health_score >= 0.1
            ]

            if not available:
                # 所有模型都不健康，仍然返回第一个（尝试恢复）
                logger.warning(
                    "[LLMModelPool] All models have low health, using first model"
                )
                return self._formatted_models[0]

            if self._config.selection_mode == ModelSelectionMode.RANDOM:
                # 加权随机选择
                weights = [
                    self._health[self._get_original_name(m)].health_score
                    for m in available
                ]
                return random.choices(available, weights=weights, k=1)[0]

            elif self._config.selection_mode == ModelSelectionMode.LEAST_LATENCY:
                # 选择延迟最低的
                latencies = [
                    self._health[self._get_original_name(m)].avg_latency
                    for m in available
                ]
                min_idx = latencies.index(min(latencies))
                return available[min_idx]

            else:  # SEQUENTIAL
                # 顺序选择第一个健康的
                return available[0]

    def _get_original_name(self, formatted_name: str) -> str:
        """获取原始模型名称（去除前缀）"""
        if formatted_name.startswith("openai/"):
            return formatted_name[7:]
        return formatted_name

    def call(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 8192,
        **kwargs,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        调用模型（自动选择 + 失败重试）

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数传递给 litellm.completion

        Returns:
            Tuple[str, str, Dict]: (响应文本, 使用的模型, usage 信息)

        Raises:
            Exception: 所有模型都失败时抛出
        """
        tried_models = set()
        last_error = None

        while len(tried_models) < len(self._formatted_models):
            model = self.select_model()
            original_name = self._get_original_name(model)

            if model in tried_models:
                # 已尝试过所有可用模型
                break

            tried_models.add(model)
            call_start = time.time()

            try:
                self._total_calls += 1

                call_kwargs: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "api_key": self._api_key,
                }

                if self._base_url:
                    call_kwargs["base_url"] = self._base_url

                call_kwargs.update(kwargs)

                logger.debug(f"[LLMModelPool] Calling model: {original_name}")

                response = litellm.completion(**call_kwargs)

                if (
                    response
                    and response.choices
                    and response.choices[0].message.content
                ):
                    latency = time.time() - call_start
                    self._total_success += 1

                    # 更新健康状态
                    with self._lock:
                        health = self._health[original_name]
                        health.failure_count = 0
                        health.success_count += 1
                        health.total_requests += 1
                        health.health_score = min(
                            1.0, health.health_score + self._config.health_recovery
                        )
                        health.avg_latency = 0.7 * health.avg_latency + 0.3 * latency

                    usage: Dict[str, Any] = {}
                    if response.usage:
                        usage = {
                            "prompt_tokens": response.usage.prompt_tokens or 0,
                            "completion_tokens": response.usage.completion_tokens or 0,
                            "total_tokens": response.usage.total_tokens or 0,
                        }

                    logger.info(
                        f"[LLMModelPool] Model {original_name} succeeded: "
                        f"latency={latency:.2f}s, tokens={usage.get('total_tokens', 0)}"
                    )

                    return (response.choices[0].message.content, original_name, usage)

                raise ValueError("LLM returned empty response")

            except Exception as e:
                latency = time.time() - call_start
                self._total_failures += 1
                last_error = e

                # 更新健康状态
                with self._lock:
                    health = self._health[original_name]
                    health.failure_count += 1
                    health.total_requests += 1
                    health.last_error = str(e)
                    health.health_score = max(
                        self._config.min_health_score,
                        health.health_score - self._config.health_decay,
                    )
                    health.avg_latency = 0.7 * health.avg_latency + 0.3 * latency

                logger.warning(
                    f"[LLMModelPool] Model {original_name} failed: {e}, "
                    f"health_score={self._health[original_name].health_score:.2f}"
                )

                continue

        # 所有模型都失败
        error_msg = (
            f"All {len(tried_models)} model(s) in pool failed. Last error: {last_error}"
        )
        logger.error(f"[LLMModelPool] {error_msg}")
        raise Exception(error_msg)

    def get_health_report(self) -> Dict[str, Any]:
        """获取健康状态报告"""
        with self._lock:
            return {
                name: {
                    "health_score": h.health_score,
                    "failure_count": h.failure_count,
                    "success_count": h.success_count,
                    "total_requests": h.total_requests,
                    "avg_latency": h.avg_latency,
                    "last_error": h.last_error,
                }
                for name, h in self._health.items()
            }

    def reset_health(self, model_name: Optional[str] = None) -> None:
        """重置健康状态"""
        with self._lock:
            if model_name:
                if model_name in self._health:
                    self._health[model_name] = ModelHealth(name=model_name)
                    logger.info(f"[LLMModelPool] Reset health for {model_name}")
            else:
                for name in self._health:
                    self._health[name] = ModelHealth(name=name)
                logger.info("[LLMModelPool] Reset health for all models")

    @property
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "models": self._models,
                "total_calls": self._total_calls,
                "total_success": self._total_success,
                "total_failures": self._total_failures,
                "success_rate": (
                    self._total_success / self._total_calls
                    if self._total_calls > 0
                    else 0
                ),
            }


# 全局模型池实例（延迟初始化）
_global_pool: Optional[LLMModelPool] = None
_pool_lock = RLock()


def get_model_pool(
    models: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    config: Optional[ModelPoolConfig] = None,
    force_new: bool = False,
) -> LLMModelPool:
    """
    获取全局模型池实例

    Args:
        models: 模型列表（首次调用时必须提供）
        api_key: API Key
        base_url: Base URL
        config: 池配置
        force_new: 是否强制创建新实例

    Returns:
        LLMModelPool 实例
    """
    global _global_pool

    with _pool_lock:
        if _global_pool is None or force_new:
            if not models or not api_key:
                raise ValueError(
                    "First call to get_model_pool must provide models and api_key"
                )
            _global_pool = LLMModelPool(models, api_key, base_url, config)
        return _global_pool


def reset_model_pool() -> None:
    """重置全局模型池"""
    global _global_pool

    with _pool_lock:
        _global_pool = None


def create_model_pool_from_config() -> Optional[LLMModelPool]:
    """
    从配置创建模型池

    读取 Config 中的 openai_model_pool, openai_api_key, openai_base_url

    Returns:
        LLMModelPool 实例，如果配置不足则返回 None
    """
    from src.config import get_config

    config = get_config()

    models = config.openai_model_pool
    api_key = config.openai_api_key
    base_url = config.openai_base_url

    if not models or len(models) == 0:
        logger.debug("[LLMModelPool] No models configured in openai_model_pool")
        return None

    if not api_key:
        logger.debug("[LLMModelPool] No API key configured")
        return None

    # 读取选择模式配置
    mode_str = getattr(config, "model_selection_mode", "random").lower()
    mode_map = {
        "random": ModelSelectionMode.RANDOM,
        "sequential": ModelSelectionMode.SEQUENTIAL,
        "least_latency": ModelSelectionMode.LEAST_LATENCY,
    }
    selection_mode = mode_map.get(mode_str, ModelSelectionMode.RANDOM)

    pool_config = ModelPoolConfig(selection_mode=selection_mode)

    return LLMModelPool(models, api_key, base_url, pool_config)
