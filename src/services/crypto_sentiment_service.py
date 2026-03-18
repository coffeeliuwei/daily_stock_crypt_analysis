# -*- coding: utf-8 -*-
"""
===================================
加密货币情绪服务
===================================

通过 QVeris API 获取加密货币恐惧贪婪指数
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


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
            from qveris import search_tools, execute_tool

            # 搜索恐惧贪婪指数工具
            search_result = search_tools(
                query="crypto fear greed index bitcoin sentiment", limit=5
            )

            if not search_result.get("results"):
                logger.warning("[CryptoSentimentService] 未找到恐惧贪婪指数工具")
                return self._get_fallback_data()

            search_id = search_result.get("search_id", "")

            # 执行第一个匹配的工具
            for tool in search_result.get("results", []):
                tool_id = tool.get("tool_id")

                if "fear_greed" in tool_id.lower() or "sentiment" in tool_id.lower():
                    result = execute_tool(
                        tool_id=tool_id,
                        search_id=search_id,
                        params_to_tool=f'{{"limit": {limit}}}',
                    )

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
