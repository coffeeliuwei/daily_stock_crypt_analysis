# -*- coding: utf-8 -*-
"""
===================================
加密货币新闻获取服务
===================================

通过多种 API 获取加密货币相关新闻和情绪分析：
- QVeris API（主源，需 API Key）
- Free Crypto News API（免费，无需 Key）
- Alternative.me Fear & Greed Index（免费，无需 Key）
- RSS 中文新闻源（免费，无需 Key）
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from xml.etree import ElementTree

import httpx
import requests

logger = logging.getLogger(__name__)

# QVeris API 配置
QVERIS_BASE_URL = "https://qveris.ai/api/v1"
QVERIS_TIMEOUT = 30  # 秒

# 免费 API 配置
FREE_CRYPTO_NEWS_URL = "https://cryptocurrency.cv/api/news"
FEAR_GREED_URL = "https://api.alternative.me/fng/"

# 中文 RSS 新闻源
CHINESE_RSS_SOURCES = {
    "odaily": {
        "name": "Odaily 星球日报",
        "url": "https://www.odaily.news/rss",
        "priority": 1,
    },
    "jinse": {
        "name": "金色财经",
        "url": "https://www.jinse.com/rss",
        "priority": 2,
    },
    "8btc": {
        "name": "巴比特",
        "url": "https://www.8btc.com/rss",
        "priority": 3,
    },
    "panews": {
        "name": "PANews",
        "url": "https://panewslab.com/zh/rss",
        "priority": 4,
    },
    "blockbeats": {
        "name": "区块律动",
        "url": "https://www.theblockbeats.info/rss",
        "priority": 5,
    },
}


class CryptoNewsFetcher:
    """
    加密货币新闻获取服务

    支持多种数据源（按优先级）：
    1. QVeris API（主源，需 API Key）
    2. Free Crypto News API（免费，无需 Key，200+ 新闻源）
    3. 中文 RSS 新闻源（免费，无需 Key）
    4. Alternative.me Fear & Greed Index（免费，无需 Key）

    使用方式：
        fetcher = CryptoNewsFetcher()  # 无需 API Key 也可工作
        news = fetcher.fetch_crypto_news("BTC", "Bitcoin")
        fg = fetcher.fetch_fear_greed_index()
        chinese = fetcher.fetch_chinese_news("ETH")
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
        """服务是否可用（免费源始终可用）"""
        return True  # 免费源始终可用

    @property
    def is_premium_available(self) -> bool:
        """高级 API（QVeris）是否可用"""
        return self._qveris_available

    def fetch_crypto_news(
        self, symbol: str, name: str = "", limit: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        获取加密货币新闻

        优先级（免费源优先）：
        1. Free Crypto News API（免费，无需 Key）
        2. 中文 RSS 新闻源（免费，无需 Key）
        3. QVeris API（需 API Key）
        4. Alternative.me Fear & Greed Index（免费，无需 Key）

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
        # 1. 尝试 Free Crypto News API（免费）
        news = self._fetch_free_crypto_news(symbol, limit)
        if news and news.get("news"):
            return news

        # 2. 尝试中文 RSS 新闻源（免费）
        rss_news = self._fetch_rss_news(symbol, name, limit)
        if rss_news and rss_news.get("news"):
            return rss_news

        # 3. 尝试 QVeris API（需 Key）
        if self._qveris_available:
            qveris_news = self._fetch_qveris_news(symbol, name, limit)
            if qveris_news and qveris_news.get("news"):
                return qveris_news

        # 4. 获取恐惧贪婪指数作为情绪参考（免费）
        fg_data = self._fetch_fear_greed_index()
        if fg_data:
            sentiment = self._map_fear_greed_to_sentiment(fg_data["value"])
            return {
                "symbol": symbol,
                "news": [],
                "sentiment": sentiment,
                "fear_greed_index": fg_data,
                "key_events": self._get_key_events_hint(),
                "news_count": 0,
                "source": "alternative.me",
            }

        # 5. 最终 fallback
        return {
            "symbol": symbol,
            "news": [],
            "sentiment": "neutral",
            "key_events": self._get_key_events_hint(),
            "news_count": 0,
            "source": "none",
        }

    def _fetch_qveris_news(
        self, symbol: str, name: str, limit: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        从 QVeris API 获取新闻（需 API Key）
        """
        try:
            # 搜索新闻工具
            search_result = self._search_tool(
                "cryptocurrency news sentiment bitcoin ethereum blockchain", limit=5
            )

            if not search_result.get("results"):
                logger.warning("[CryptoNewsFetcher] QVeris: 未找到新闻工具")
                return None

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
                        parsed = self._parse_news_data(data, symbol)
                        if parsed.get("news"):
                            parsed["source"] = "qveris"
                            return parsed

            return None

        except Exception as e:
            logger.warning(f"[CryptoNewsFetcher] QVeris 获取新闻失败: {e}")
            return None

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
            return None

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

    def _get_key_events_hint(self) -> List[str]:
        """返回建议关注的关键事件提示"""
        return [
            "建议关注美联储议息会议及利率决议",
            "关注 BTC/ETH ETF 资金流向",
            "留意监管政策动态",
        ]

    def _fetch_free_crypto_news(
        self, symbol: str, limit: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        从 Free Crypto News API 获取新闻（无需 API Key）

        API 文档: https://cryptocurrency.cv/api/news
        支持分类过滤：bitcoin, ethereum, defi, nft, trading 等
        """
        try:
            # 根据币种选择分类
            symbol_upper = symbol.upper().replace("USDT", "").replace("USD", "")
            category_map = {
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "SOL": "solana",
            }
            category = category_map.get(symbol_upper, "")

            # 构建请求 URL
            if category:
                url = f"{FREE_CRYPTO_NEWS_URL}?limit={limit}&category={category}"
            else:
                url = f"{FREE_CRYPTO_NEWS_URL}?limit={limit}"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()

            articles = data.get("articles", [])
            if not articles:
                return None

            # 过滤相关新闻
            symbol_upper = symbol.upper().replace("USDT", "").replace("USD", "")
            keywords = self.CRYPTO_KEYWORDS.get(
                symbol_upper, [symbol_lower := symbol.lower()]
            )

            filtered_news = []
            for article in articles:
                title = article.get("title", "").lower()
                description = article.get("description", "")
                summary = description.lower() if description else ""
                text = f"{title} {summary}"

                # 检查是否与目标币种相关
                if any(kw in text for kw in keywords) or symbol_upper == "CRYPTO":
                    filtered_news.append(
                        {
                            "title": article.get("title", ""),
                            "summary": (description[:500] if description else ""),
                            "source": article.get("source", "Unknown"),
                            "time": article.get("pubDate", ""),
                            "url": article.get("link", ""),
                            "sentiment": "neutral",
                        }
                    )

            if not filtered_news:
                # 如果没有过滤到相关新闻，返回前几条作为市场动态
                filtered_news = [
                    {
                        "title": a.get("title", ""),
                        "summary": (
                            a.get("description", "")[:500]
                            if a.get("description")
                            else ""
                        ),
                        "source": a.get("source", "Unknown"),
                        "time": a.get("pubDate", ""),
                        "url": a.get("link", ""),
                        "sentiment": "neutral",
                    }
                    for a in articles[:5]
                ]

            return {
                "symbol": symbol,
                "news": filtered_news,
                "sentiment": self._analyze_sentiment(filtered_news),
                "key_events": self._extract_key_events(filtered_news),
                "news_count": len(filtered_news),
                "source": "cryptocurrency.cv",
            }

        except Exception as e:
            logger.warning(f"[CryptoNews] Free Crypto News API failed: {e}")
            return None

    def _fetch_fear_greed_index(self) -> Optional[Dict[str, Any]]:
        """
        从 Alternative.me 获取恐惧贪婪指数（无需 API Key）

        API 文档: https://alternative.me/crypto/api/
        """
        try:
            url = f"{FEAR_GREED_URL}?limit=1"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("data"):
                fg = data["data"][0]
                return {
                    "value": int(fg["value"]),
                    "classification": fg["value_classification"],
                    "timestamp": fg["timestamp"],
                    "update_time": datetime.fromtimestamp(
                        int(fg["timestamp"])
                    ).strftime("%Y-%m-%d %H:%M"),
                }

        except Exception as e:
            logger.warning(f"[CryptoNews] Fear & Greed API failed: {e}")
            return None

    def _fetch_rss_news(
        self, symbol: str, name: str, limit: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        从中文 RSS 新闻源获取新闻

        支持：Odaily 星球日报、金色财经、巴比特、PANews、区块律动
        """
        all_news = []
        symbol_upper = symbol.upper().replace("USDT", "").replace("USD", "")
        keywords = self.CRYPTO_KEYWORDS.get(symbol_upper, [])
        if name:
            keywords.append(name.lower())

        for source_id, source_info in CHINESE_RSS_SOURCES.items():
            try:
                news_items = self._parse_rss_feed(
                    source_info["url"],
                    source_info["name"],
                    keywords,
                    limit=2,  # 每个源最多取2条
                )
                all_news.extend(news_items)
            except Exception as e:
                logger.debug(
                    f"[CryptoNews] RSS {source_info['name']} fetch failed: {e}"
                )
                continue

        if not all_news:
            return None

        # 按时间排序，取最新的
        all_news.sort(key=lambda x: x.get("time", ""), reverse=True)
        all_news = all_news[:limit]

        return {
            "symbol": symbol,
            "news": all_news,
            "sentiment": self._analyze_sentiment(all_news),
            "key_events": self._extract_key_events(all_news),
            "news_count": len(all_news),
            "source": "rss_chinese",
        }

    def _parse_rss_feed(
        self, url: str, source_name: str, keywords: List[str], limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        解析 RSS 订阅源

        Args:
            url: RSS 订阅地址
            source_name: 来源名称
            keywords: 关键词过滤列表
            limit: 返回数量限制

        Returns:
            新闻列表
        """
        news_items = []
        try:
            response = requests.get(
                url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()

            root = ElementTree.fromstring(response.content)

            # RSS 2.0 格式
            for item in root.findall(".//item")[: limit * 3]:  # 多取一些用于过滤
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubDate")
                description = item.find("description")

                if title is None:
                    continue

                title_text = title.text or ""
                desc_text = description.text if description is not None else ""

                # 关键词过滤
                text = f"{title_text} {desc_text}".lower()
                if keywords and not any(kw in text for kw in keywords):
                    continue

                news_items.append(
                    {
                        "title": title_text,
                        "summary": desc_text[:500] if desc_text else "",
                        "source": source_name,
                        "time": pub_date.text if pub_date is not None else "",
                        "url": link.text if link is not None else "",
                        "sentiment": "neutral",
                    }
                )

                if len(news_items) >= limit:
                    break

        except Exception as e:
            logger.debug(f"[CryptoNews] RSS parse error for {source_name}: {e}")

        return news_items

    def _map_fear_greed_to_sentiment(self, value: int) -> str:
        """
        将恐惧贪婪指数映射为情绪

        Args:
            value: 0-100 的恐惧贪婪指数

        Returns:
            情绪字符串: positive/negative/neutral
        """
        if value <= 25:
            return "negative"  # Extreme Fear - 可能是买入机会，但情绪负面
        elif value <= 45:
            return "negative"  # Fear
        elif value <= 55:
            return "neutral"
        elif value <= 75:
            return "positive"  # Greed
        else:
            return "positive"  # Extreme Greed

    def _analyze_sentiment(self, news_items: List[Dict]) -> str:
        """
        简单情绪分析（基于关键词）

        Args:
            news_items: 新闻列表

        Returns:
            情绪字符串
        """
        positive_words = [
            "bullish",
            "surge",
            "rally",
            "gain",
            "up",
            "high",
            "突破",
            "上涨",
            "利好",
            "增持",
            "adopt",
            "approval",
            "突破",
            "创新高",
        ]
        negative_words = [
            "bearish",
            "crash",
            "drop",
            "fall",
            "down",
            "low",
            "暴跌",
            "下跌",
            "利空",
            "监管",
            "ban",
            "hack",
            "暴跌",
            "暴跌",
        ]

        positive_count = 0
        negative_count = 0

        for item in news_items:
            title = item.get("title", "").lower()
            summary = item.get("summary", "").lower()
            text = f"{title} {summary}"

            positive_count += sum(1 for w in positive_words if w in text)
            negative_count += sum(1 for w in negative_words if w in text)

        if positive_count > negative_count * 1.3:
            return "positive"
        elif negative_count > positive_count * 1.3:
            return "negative"
        return "neutral"

    def fetch_fear_greed_index(self) -> Optional[Dict[str, Any]]:
        """
        公开方法：获取恐惧贪婪指数

        Returns:
            {
                "value": 0-100,
                "classification": "Extreme Fear/Fear/Neutral/Greed/Extreme Greed",
                "timestamp": "...",
                "update_time": "YYYY-MM-DD HH:MM"
            }
        """
        return self._fetch_fear_greed_index()

    def fetch_chinese_news(
        self, symbol: str = "CRYPTO", limit: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        公开方法：获取中文新闻

        Args:
            symbol: 币种代码（如 BTC, ETH）
            limit: 获取数量

        Returns:
            新闻数据字典
        """
        return self._fetch_rss_news(symbol, "", limit)

    def fetch_market_news(self, limit: int = 10) -> Optional[Dict[str, Any]]:
        """
        获取加密货币市场整体新闻

        Args:
            limit: 获取新闻数量

        Returns:
            市场新闻和情绪分析
        """
        return self.fetch_crypto_news("CRYPTO", "Cryptocurrency Market", limit)
