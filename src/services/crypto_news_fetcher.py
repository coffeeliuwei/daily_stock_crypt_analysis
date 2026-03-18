# -*- coding: utf-8 -*-
"""
===================================
加密货币新闻获取服务
===================================

通过 QVeris API 获取加密货币相关新闻和情绪分析
"""

import logging
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

# QVeris API 配置
QVERIS_BASE_URL = "https://qveris.ai/api/v1"
QVERIS_TIMEOUT = 30  # 秒


class CryptoNewsFetcher:
    """
    加密货币新闻获取服务

    通过 QVeris API 获取：
    - 加密货币相关新闻
    - 新闻情绪分析
    - 市场热点
    """

    # 加密货币关键词映射
    CRYPTO_KEYWORDS = {
        "BTC": ["bitcoin", "btc", "比特币"],
        "ETH": ["ethereum", "eth", "以太坊"],
        "BNB": ["binance", "bnb", "币安币"],
        "SOL": ["solana", "sol"],
        "XRP": ["ripple", "xrp", "瑞波币"],
    }

    # 加密货币相关主题
    CRYPTO_TOPICS = [
        "blockchain",
        "cryptocurrency",
        "defi",
        "nft",
        "web3",
        "bitcoin etf",
        "ethereum upgrade",
        "crypto regulation",
        "sec crypto",
    ]

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化服务

        Args:
            api_key: QVeris API Key（可选，默认从环境变量读取）
        """
        self._api_key = api_key
        self._qveris_available = False

        try:
            import os

            self._api_key = api_key or os.environ.get("QVERIS_API_KEY")
            if self._api_key:
                self._qveris_available = True
                logger.info("[CryptoNewsFetcher] QVeris API 已配置")
            else:
                logger.warning("[CryptoNewsFetcher] QVERIS_API_KEY 未配置")
        except Exception as e:
            logger.warning(f"[CryptoNewsFetcher] 初始化失败: {e}")

    @property
    def is_available(self) -> bool:
        """服务是否可用"""
        return self._qveris_available

    def fetch_crypto_news(
        self, symbol: str, name: str = "", limit: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        获取加密货币新闻

        Args:
            symbol: 加密货币代码（如 BTC）
            name: 加密货币名称（如 Bitcoin）
            limit: 获取新闻数量

        Returns:
            {
                "news": [...],
                "sentiment": "positive/negative/neutral",
                "key_events": [...],
            }
        """
        if not self._qveris_available:
            return self._get_fallback_news(symbol, name)

        try:
            # 使用 REST API 调用 QVeris
            # 搜索新闻工具
            search_result = self._search_tool(
                "cryptocurrency news sentiment bitcoin ethereum blockchain", limit=5
            )

            if not search_result.get("results"):
                logger.warning("[CryptoNewsFetcher] 未找到新闻工具")
                return self._get_fallback_news(symbol, name)

            search_id = search_result.get("search_id", "")

            # 执行新闻搜索
            for tool in search_result.get("results", []):
                tool_id = tool.get("tool_id")

                if "news" in tool_id.lower() or "sentiment" in tool_id.lower():
                    # 构建参数
                    params = {
                        "tickers": f"CRYPTO:{symbol}",
                        "topics": "blockchain",
                        "limit": limit,
                        "sort": "LATEST",
                    }

                    result = self._execute_tool(tool_id, search_id, params)

                    if result.get("success"):
                        data = result.get("result", {}).get("data", {})
                        return self._parse_news_data(data, symbol)

            return self._get_fallback_news(symbol, name)

        except Exception as e:
            logger.warning(f"[CryptoNewsFetcher] 获取新闻失败: {e}")
            return self._get_fallback_news(symbol, name)

    def _build_search_keywords(self, symbol: str, name: str) -> List[str]:
        """构建搜索关键词"""
        keywords = []

        # 从映射获取关键词
        symbol_upper = symbol.upper().replace("USDT", "").replace("USD", "")
        if symbol_upper in self.CRYPTO_KEYWORDS:
            keywords.extend(self.CRYPTO_KEYWORDS[symbol_upper])

        # 添加名称
        if name:
            keywords.append(name.lower())

        # 添加通用关键词
        keywords.extend(["cryptocurrency", "crypto"])

        return list(set(keywords))

    def _parse_news_data(self, data: Any, symbol: str) -> Dict[str, Any]:
        """解析新闻数据"""
        try:
            news_items = []
            sentiment_scores = []

            if isinstance(data, dict):
                # Alpha Vantage 格式
                feed = data.get("feed", [])
                for item in feed[:10]:
                    news_items.append(
                        {
                            "title": item.get("title", ""),
                            "summary": item.get("summary", "")[:500]
                            if item.get("summary")
                            else "",
                            "source": item.get("source", ""),
                            "time": item.get("time_published", ""),
                            "url": item.get("url", ""),
                            "sentiment": item.get("overall_sentiment_label", "neutral"),
                        }
                    )
                    # 记录情绪分数
                    score = item.get("overall_sentiment_score", 0)
                    if score:
                        sentiment_scores.append(score)

            # 计算整体情绪
            overall_sentiment = "neutral"
            if sentiment_scores:
                avg_score = sum(sentiment_scores) / len(sentiment_scores)
                if avg_score > 0.15:
                    overall_sentiment = "positive"
                elif avg_score < -0.15:
                    overall_sentiment = "negative"

            # 提取关键事件
            key_events = self._extract_key_events(news_items)

            return {
                "symbol": symbol,
                "news": news_items,
                "sentiment": overall_sentiment,
                "key_events": key_events,
                "news_count": len(news_items),
            }

        except Exception as e:
            logger.warning(f"[CryptoNewsFetcher] 解析新闻失败: {e}")
            return self._get_fallback_news(symbol, "")

    def _extract_key_events(self, news_items: List[Dict]) -> List[str]:
        """从新闻中提取关键事件"""
        events = []
        keywords = [
            "etf",
            "upgrade",
            "fork",
            "listing",
            "regulation",
            "sec",
            "lawsuit",
            "hack",
            "adoption",
        ]

        for item in news_items:
            title = item.get("title", "").lower()
            summary = item.get("summary", "").lower()
            text = f"{title} {summary}"

            for kw in keywords:
                if kw in text:
                    events.append(f"{kw.title()}: {item.get('title', '')[:80]}")
                    break

        return events[:5]

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
            with httpx.Client(timeout=QVERIS_TIMEOUT) as client:
                response = client.post(
                    f"{QVERIS_BASE_URL}/search",
                    headers=self._get_headers(),
                    json={"query": query, "limit": limit},
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.warning(f"[CryptoNewsFetcher] 搜索工具失败: {e}")
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
            with httpx.Client(timeout=QVERIS_TIMEOUT) as client:
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
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.warning(f"[CryptoNewsFetcher] 执行工具失败: {e}")
            return {"success": False, "error_message": str(e)}

    def _get_fallback_news(self, symbol: str, name: str) -> Dict[str, Any]:
        """返回默认数据（当 API 不可用时）"""
        return {
            "symbol": symbol,
            "news": [],
            "sentiment": "unknown",
            "key_events": [],
            "news_count": 0,
            "error": "News API not available",
        }

    def fetch_market_news(self, limit: int = 10) -> Optional[Dict[str, Any]]:
        """
        获取加密货币市场整体新闻

        Args:
            limit: 获取新闻数量

        Returns:
            市场新闻和情绪分析
        """
        return self.fetch_crypto_news("CRYPTO", "Cryptocurrency Market", limit)
