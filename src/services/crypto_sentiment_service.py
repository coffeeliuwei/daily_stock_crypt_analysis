# -*- coding: utf-8 -*-
"""
===================================
加密货币情绪服务
===================================

通过 QVeris API 获取加密货币恐惧贪婪指数
"""

import logging
from typing import Optional, Dict, Any

import httpx

from data_provider.utils import get_http_client

logger = logging.getLogger(__name__)

# QVeris API 配置
QVERIS_BASE_URL = "https://qveris.ai/api/v1"
QVERIS_TIMEOUT = 30  # 秒


class CryptoSentimentService:
    """
    加密货币情绪服务

    通过 QVeris API 获取：
    - 恐惧贪婪指数 (Fear & Greed Index)
    - 历史情绪数据
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化服务

        Args:
            api_key: QVeris API Key（可选，默认从环境变量读取）
        """
        self._api_key = api_key
        self._qveris_available = False

        # 尝试初始化 QVeris
        try:
            import os

            self._api_key = api_key or os.environ.get("QVERIS_API_KEY")
            if self._api_key:
                self._qveris_available = True
                logger.info("[CryptoSentimentService] QVeris API 已配置")
            else:
                logger.warning("[CryptoSentimentService] QVERIS_API_KEY 未配置")
        except Exception as e:
            logger.warning(f"[CryptoSentimentService] 初始化失败: {e}")

    @property
    def is_available(self) -> bool:
        """服务是否可用"""
        return self._qveris_available

    def get_fear_greed_index(self, limit: int = 1) -> Optional[Dict[str, Any]]:
        """
        获取恐惧贪婪指数

        Args:
            limit: 获取最近 N 天的数据（默认 1 天）

        Returns:
            {
                "value": 45,  # 当前指数值 (0-100)
                "classification": "Fear",  # 分类
                "timestamp": "2024-01-15",
                "trend": "decreasing"  # 趋势（如有历史数据）
            }
        """
        if not self._qveris_available:
            return self._get_fallback_data()

        try:
            # 使用 REST API 调用 QVeris
            # 搜索恐惧贪婪指数工具
            search_result = self._search_tool(
                "crypto fear greed index bitcoin sentiment", limit=5
            )

            if not search_result.get("results"):
                logger.warning("[CryptoSentimentService] 未找到恐惧贪婪指数工具")
                return self._get_fallback_data()

            search_id = search_result.get("search_id", "")

            # 执行第一个匹配的工具
            for tool in search_result.get("results", []):
                tool_id = tool.get("tool_id")

                if "fear_greed" in tool_id.lower() or "sentiment" in tool_id.lower():
                    result = self._execute_tool(tool_id, search_id, {"limit": limit})

                    if result.get("success"):
                        data = result.get("result", {}).get("data", {})
                        return self._parse_fear_greed_data(data)

            return self._get_fallback_data()

        except Exception as e:
            logger.warning(f"[CryptoSentimentService] 获取恐惧贪婪指数失败: {e}")
            return self._get_fallback_data()

    def _parse_fear_greed_data(self, data: Any) -> Optional[Dict[str, Any]]:
        """解析恐惧贪婪指数数据"""
        try:
            if isinstance(data, dict):
                # Alternative.me 格式
                if "data" in data:
                    items = data.get("data", [])
                    if items:
                        latest = items[0] if isinstance(items, list) else items
                        value = int(latest.get("value", 50))
                        return {
                            "value": value,
                            "classification": self._classify_fear_greed(value),
                            "timestamp": latest.get("time_until_update"),
                            "raw_data": items if len(items) > 1 else None,
                        }

                # 其他格式
                value = data.get("value") or data.get("fear_greed_index") or 50
                return {
                    "value": int(value),
                    "classification": self._classify_fear_greed(int(value)),
                    "raw_data": data,
                }

            return self._get_fallback_data()

        except Exception as e:
            logger.warning(f"[CryptoSentimentService] 解析数据失败: {e}")
            return self._get_fallback_data()

    def _classify_fear_greed(self, value: int) -> str:
        """根据指数值分类情绪"""
        if value <= 25:
            return "Extreme Fear"
        elif value <= 45:
            return "Fear"
        elif value <= 55:
            return "Neutral"
        elif value <= 75:
            return "Greed"
        else:
            return "Extreme Greed"

    def _get_fallback_data(self) -> Dict[str, Any]:
        """返回默认数据（当 API 不可用时）"""
        return {
            "value": None,
            "classification": "Unknown",
            "error": "API not available",
        }

    def _get_headers(self) -> Dict[str, str]:
        """获取 API 请求头"""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _search_tool(self, query: str, limit: int = 5) -> Dict:
        """
        搜索可用的工具

        Args:
            query: 搜索查询
            limit: 返回数量限制

        Returns:
            搜索结果
        """
        try:
            client = get_http_client()
            if client:
                response = client.post(
                    f"{QVERIS_BASE_URL}/search",
                    headers=self._get_headers(),
                    json={"query": query, "limit": limit},
                )
            else:
                with httpx.Client(timeout=QVERIS_TIMEOUT) as temp_client:
                    response = temp_client.post(
                        f"{QVERIS_BASE_URL}/search",
                        headers=self._get_headers(),
                        json={"query": query, "limit": limit},
                    )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"[CryptoSentimentService] 搜索工具失败: {e}")
            return {}

    def _execute_tool(
        self,
        tool_id: str,
        search_id: str,
        parameters: Dict[str, Any],
        max_response_size: int = 20480,
    ) -> Dict:
        """
        执行工具调用

        Args:
            tool_id: 工具 ID
            search_id: 搜索 ID
            parameters: 参数
            max_response_size: 最大响应大小

        Returns:
            执行结果
        """
        try:
            client = get_http_client()
            if client:
                response = client.post(
                    f"{QVERIS_BASE_URL}/tools/execute",
                    params={"tool_id": tool_id},
                    headers=self._get_headers(),
                    json={
                        "search_id": search_id,
                        "parameters": parameters,
                        "max_response_size": max_response_size,
                    },
                )
            else:
                with httpx.Client(timeout=QVERIS_TIMEOUT) as temp_client:
                    response = temp_client.post(
                        f"{QVERIS_BASE_URL}/tools/execute",
                        params={"tool_id": tool_id},
                        headers=self._get_headers(),
                        json={
                            "search_id": search_id,
                            "parameters": parameters,
                            "max_response_size": max_response_size,
                        },
                    )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"[CryptoSentimentService] 执行工具失败: {e}")
            return {"success": False, "error_message": str(e)}

    def get_sentiment_trend(self, days: int = 7) -> Optional[Dict[str, Any]]:
        """
        获取情绪趋势

        Args:
            days: 获取最近 N 天的数据

        Returns:
            {
                "current": 45,
                "average": 42,
                "trend": "increasing",  # increasing, decreasing, stable
                "history": [...]
            }
        """
        result = self.get_fear_greed_index(limit=days)

        if not result or result.get("error"):
            return None

        raw_data = result.get("raw_data", [])
        if not raw_data or len(raw_data) < 2:
            return result

        values = [
            int(item.get("value", 50)) for item in raw_data if isinstance(item, dict)
        ]

        if len(values) < 2:
            return result

        current = values[0]
        previous = values[-1]
        average = sum(values) / len(values)

        if current > previous + 5:
            trend = "increasing"
        elif current < previous - 5:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "current": current,
            "previous": previous,
            "average": round(average, 1),
            "trend": trend,
            "history": raw_data,
        }
