# -*- coding: utf-8 -*-
"""
===================================
CryptoFetcher - 加密货币数据源 (Priority 1)
===================================

数据来源（优先级）：
1. CoinGecko (免费，无需API Key) - 首选
2. Binance 公开API (免费，无需API Key) - 第二选择
3. CCXT (需要安装库) - 第三选择
4. QVeris API (需要API Key) - 最后备选

特点：多数据源 fallback，支持主流加密货币
定位：为系统添加 BTC、ETH 等加密货币的数据支持
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
import requests

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS, _is_crypto_code
from .realtime_types import UnifiedRealtimeQuote, RealtimeSource

logger = logging.getLogger(__name__)

# 默认支持的加密货币符号
DEFAULT_CRYPTO_SYMBOLS = [
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "ADA",
    "DOGE",
    "DOT",
    "MATIC",
    "LTC",
    "SHIB",
    "AVAX",
    "LINK",
    "ATOM",
    "UNI",
    "XMR",
    "ETC",
    "BCH",
    "NEAR",
    "APT",
    "ARB",
    "OP",
    "INJ",
    "FIL",
    "VET",
    "HBAR",
    "ICP",
]

# 加密货币名称映射 (Symbol -> Name)
CRYPTO_NAMES = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "BNB": "BNB",
    "SOL": "Solana",
    "XRP": "XRP",
    "ADA": "Cardano",
    "DOGE": "Dogecoin",
    "DOT": "Polkadot",
    "MATIC": "Polygon",
    "LTC": "Litecoin",
    "SHIB": "Shiba Inu",
    "AVAX": "Avalanche",
    "LINK": "Chainlink",
    "ATOM": "Cosmos",
    "UNI": "Uniswap",
}

# Symbol -> CoinGecko ID 映射
COINGECKO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LTC": "litecoin",
    "SHIB": "shiba-inu",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "ATOM": "cosmos",
    "UNI": "uniswap",
    "XMR": "monero",
    "ETC": "ethereum-classic",
    "BCH": "bitcoin-cash",
    "NEAR": "near",
    "APT": "aptos",
    "ARB": "arbitrum",
    "OP": "optimism",
    "INJ": "injective-protocol",
    "FIL": "filecoin",
    "VET": "vechain",
    "HBAR": "hedera-hashgraph",
    "ICP": "internet-computer",
}


class CryptoFetcher(BaseFetcher):
    """
    加密货币数据源实现

    优先级：1（高优先级）
    数据来源：CoinGecko -> Binance -> CCXT -> QVeris

    关键策略：
    - 首选免费的 CoinGecko API（无需密钥）
    - CoinGecko 失败时回退到 Binance 公开 API
    - Binance 失败时回退到 CCXT
    - CCXT 失败时回退到 QVeris（需 API Key）
    - 自动转换加密货币代码格式
    """

    name = "CryptoFetcher"
    priority = int(os.getenv("CRYPTO_PRIORITY", "1"))

    # API 配置
    COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
    BINANCE_BASE_URL = "https://api.binance.com/api/v3"
    QVERIS_BASE_URL = "https://qveris.ai/api/v1"
    REQUEST_TIMEOUT = 15

    # 速率限制（CoinGecko 免费版限制）
    _last_coingecko_request = 0
    COINGECKO_MIN_INTERVAL = 1.5  # 每次请求最小间隔（秒）

    def __init__(self, exchange: str = "binance"):
        """
        初始化 CryptoFetcher

        Args:
            exchange: CCXT 备用交易所名称，默认 binance
        """
        self.exchange_name = exchange
        self._exchange = None
        self._ccxt = None

        # QVeris 配置（最后备选）
        self.qveris_api_key = os.getenv("QVERIS_API_KEY")
        self._qveris_available = bool(self.qveris_api_key)

        # CoinGecko API Key（可选，有则速率限制更宽松）
        self.coingecko_api_key = os.getenv("COINGECKO_API_KEY")

        logger.info(
            "[CryptoFetcher] 数据源优先级: CoinGecko(免费) -> Binance(免费) -> CCXT -> QVeris"
        )

    # ==================== CoinGecko API (首选，免费) ====================

    def _fetch_via_coingecko(
        self, stock_code: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        通过 CoinGecko API 获取数据（首选，免费无需密钥）

        Args:
            stock_code: 加密货币代码 (BTC, ETH 等)
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            DataFrame 或 None
        """
        try:
            # 获取 CoinGecko ID
            coin_id = self._get_coingecko_id(stock_code)
            if not coin_id:
                logger.debug(f"[CoinGecko] 无法映射 {stock_code} 到 CoinGecko ID")
                return None

            # 速率限制
            self._rate_limit_coingecko()

            # 计算天数
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            days = (end_dt - start_dt).days + 1

            # CoinGecko OHLC API 只接受特定 days 值: 1, 7, 14, 30, 90, 180, 365
            # 需要将请求的 days 向上取整到最近的有效值
            VALID_COINGECKO_DAYS = [1, 7, 14, 30, 90, 180, 365]
            api_days = days
            for valid_days in VALID_COINGECKO_DAYS:
                if valid_days >= days:
                    api_days = valid_days
                    break
            else:
                api_days = 365  # 默认最大值

            # CoinGecko OHLC 接口限制最大 90 天（免费版）
            if days > 90:
                logger.debug(f"[CoinGecko] 请求天数 {days} 超过 90 天限制，分段获取")
                return self._fetch_coingecko_extended(coin_id, start_date, end_date)

            # 调用 OHLC 接口
            url = f"{self.COINGECKO_BASE_URL}/coins/{coin_id}/ohlc"
            params = {"vs_currency": "usd", "days": str(api_days)}

            if self.coingecko_api_key:
                params["x_cg_demo_api_key"] = self.coingecko_api_key

            logger.debug(f"[CoinGecko] 请求 {coin_id} OHLC, days={days}")
            resp = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT)

            if resp.status_code == 429:
                logger.warning("[CoinGecko] 速率限制，稍后重试")
                time.sleep(2)
                return None

            if resp.status_code != 200:
                logger.debug(f"[CoinGecko] HTTP {resp.status_code}: {resp.text[:100]}")
                return None

            data = resp.json()

            if not data:
                logger.debug(f"[CoinGecko] 无数据返回")
                return None

            # 转换为 DataFrame
            # CoinGecko OHLC 格式: [timestamp, open, high, low, close]
            # 注意：CoinGecko OHLC 不返回 volume 数据
            df = pd.DataFrame(
                data, columns=["timestamp", "open", "high", "low", "close"]
            )
            df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.drop(columns=["timestamp"])
            df["volume"] = 0  # CoinGecko OHLC 不提供 volume，设为 0

            # 过滤日期范围
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]

            if df.empty:
                return None

            logger.info(f"[CoinGecko] 获取成功: {stock_code} {len(df)} 条记录")
            return df

        except Exception as e:
            logger.debug(f"[CoinGecko] 获取失败: {e}")
            return None

    def _fetch_coingecko_extended(
        self, coin_id: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        分段获取超过 90 天的数据
        """
        all_dfs = []
        current_start = datetime.strptime(start_date, "%Y-%m-%d")
        final_end = datetime.strptime(end_date, "%Y-%m-%d")

        while current_start < final_end:
            current_end = min(current_start + timedelta(days=90), final_end)

            self._rate_limit_coingecko()

            # CoinGecko OHLC API 只接受特定 days 值，分段请求统一使用 90
            url = f"{self.COINGECKO_BASE_URL}/coins/{coin_id}/ohlc"
            params = {"vs_currency": "usd", "days": "90"}

            if self.coingecko_api_key:
                params["x_cg_demo_api_key"] = self.coingecko_api_key

            try:
                resp = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    if data:
                        df = pd.DataFrame(
                            data, columns=["timestamp", "open", "high", "low", "close"]
                        )
                        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
                        df = df.drop(columns=["timestamp"])
                        df["volume"] = 0  # CoinGecko OHLC 不提供 volume
                        all_dfs.append(df)
            except Exception as e:
                logger.debug(f"[CoinGecko] 分段获取失败: {e}")

            current_start = current_end + timedelta(days=1)

        if not all_dfs:
            return None

        result = pd.concat(all_dfs, ignore_index=True)
        result = result.drop_duplicates(subset=["date"])
        result = result.sort_values("date")

        return result

    def _get_realtime_quote_via_coingecko(
        self, stock_code: str
    ) -> Optional[UnifiedRealtimeQuote]:
        """通过 CoinGecko 获取实时行情（免费）"""
        try:
            coin_id = self._get_coingecko_id(stock_code)
            if not coin_id:
                return None

            self._rate_limit_coingecko()

            url = f"{self.COINGECKO_BASE_URL}/simple/price"
            params = {
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            }

            if self.coingecko_api_key:
                params["x_cg_demo_api_key"] = self.coingecko_api_key

            resp = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT)

            if resp.status_code != 200:
                return None

            data = resp.json()
            if coin_id not in data:
                return None

            coin_data = data[coin_id]
            base_symbol = self._extract_base_symbol(stock_code)

            return UnifiedRealtimeQuote(
                code=stock_code.upper(),
                name=CRYPTO_NAMES.get(base_symbol, base_symbol),
                source=RealtimeSource.CRYPTO,
                price=self._safe_float(coin_data.get("usd")),
                change_pct=self._safe_float(coin_data.get("usd_24h_change")),
                volume=self._safe_int(coin_data.get("usd_24h_vol")),
                total_mv=self._safe_float(coin_data.get("usd_market_cap")),
            )

        except Exception as e:
            logger.debug(f"[CoinGecko] 实时行情失败: {e}")
            return None

    def _get_coingecko_id(self, stock_code: str) -> Optional[str]:
        """获取 CoinGecko ID"""
        symbol = stock_code.strip().upper()
        # 移除常见后缀
        for suffix in ["USDT", "USDC", "USD", "BUSD"]:
            if symbol.endswith(suffix):
                symbol = symbol[: -len(suffix)]
                break
        return COINGECKO_ID_MAP.get(symbol)

    def _rate_limit_coingecko(self):
        """CoinGecko 速率限制"""
        elapsed = time.time() - self._last_coingecko_request
        if elapsed < self.COINGECKO_MIN_INTERVAL:
            time.sleep(self.COINGECKO_MIN_INTERVAL - elapsed)
        self._last_coingecko_request = time.time()

    # ==================== Binance API (第二选择，免费) ====================

    def _fetch_via_binance(
        self, stock_code: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        通过 Binance 公开 API 获取数据（免费，无需密钥）

        Args:
            stock_code: 加密货币代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame 或 None
        """
        try:
            symbol = self._to_binance_symbol(stock_code)

            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

            all_klines = []
            current_ts = start_ts

            while current_ts < end_ts:
                url = f"{self.BINANCE_BASE_URL}/klines"
                params = {
                    "symbol": symbol,
                    "interval": "1d",
                    "startTime": current_ts,
                    "endTime": end_ts,
                    "limit": 500,  # Binance 单次最大 1000
                }

                resp = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT)

                if resp.status_code == 429:
                    logger.warning("[Binance] 速率限制，等待...")
                    time.sleep(2)
                    continue

                if resp.status_code != 200:
                    logger.debug(
                        f"[Binance] HTTP {resp.status_code}: {resp.text[:100]}"
                    )
                    break

                klines = resp.json()
                if not klines:
                    break

                all_klines.extend(klines)
                last_ts = klines[-1][0]
                if last_ts <= current_ts:
                    break
                current_ts = last_ts + 86400000  # +1 day in ms
                time.sleep(0.1)  # 避免速率限制

            if not all_klines:
                logger.debug(f"[Binance] 无数据返回: {symbol}")
                return None

            # Binance kline 格式: [open_time, open, high, low, close, volume, ...]
            df = pd.DataFrame(
                all_klines,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_volume",
                    "trades",
                    "taker_buy_base",
                    "taker_buy_quote",
                    "ignore",
                ],
            )

            df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df[["date", "open", "high", "low", "close", "volume"]]
            df[["open", "high", "low", "close", "volume"]] = df[
                ["open", "high", "low", "close", "volume"]
            ].astype(float)

            # 过滤日期范围
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]

            if df.empty:
                return None

            logger.info(f"[Binance] 获取成功: {stock_code} {len(df)} 条记录")
            return df

        except Exception as e:
            logger.debug(f"[Binance] 获取失败: {e}")
            return None

    def _get_realtime_quote_via_binance(
        self, stock_code: str
    ) -> Optional[UnifiedRealtimeQuote]:
        """通过 Binance 获取实时行情"""
        try:
            symbol = self._to_binance_symbol(stock_code)
            base_symbol = self._extract_base_symbol(stock_code)

            # 获取 ticker
            url = f"{self.BINANCE_BASE_URL}/ticker/24hr"
            params = {"symbol": symbol}
            resp = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT)

            if resp.status_code != 200:
                return None

            data = resp.json()

            return UnifiedRealtimeQuote(
                code=stock_code.upper(),
                name=CRYPTO_NAMES.get(base_symbol, base_symbol),
                source=RealtimeSource.CRYPTO,
                price=self._safe_float(data.get("lastPrice")),
                change_pct=self._safe_float(data.get("priceChangePercent")),
                change_amount=self._safe_float(data.get("priceChange")),
                volume=self._safe_int(data.get("volume")),
                amount=self._safe_float(data.get("quoteVolume")),
                open_price=self._safe_float(data.get("openPrice")),
                high=self._safe_float(data.get("highPrice")),
                low=self._safe_float(data.get("lowPrice")),
                pre_close=self._safe_float(data.get("prevClosePrice")),
            )

        except Exception as e:
            logger.debug(f"[Binance] 实时行情失败: {e}")
            return None

    def _to_binance_symbol(self, stock_code: str) -> str:
        """转换为 Binance symbol 格式 (如 BTCUSDT)"""
        code = stock_code.strip().upper()
        for suffix in ["USDT", "USDC", "USD", "BUSD"]:
            if code.endswith(suffix):
                code = code[: -len(suffix)]
                break
        code = code.replace("-", "")
        return f"{code}USDT"

    # ==================== QVeris API (最后备选) ====================

    def _get_headers(self) -> Dict[str, str]:
        """获取 QVeris API 请求头"""
        return {
            "Authorization": f"Bearer {self.qveris_api_key}",
            "Content-Type": "application/json",
        }

    def _search_qveris_tool(self, query: str, limit: int = 5) -> Dict:
        """搜索 QVeris 工具"""
        import httpx

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{self.QVERIS_BASE_URL}/search",
                    headers=self._get_headers(),
                    json={"query": query, "limit": limit},
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.debug(f"[CryptoFetcher] QVeris 搜索失败: {e}")
            return {}

    def _execute_qveris_tool(
        self, tool_id: str, search_id: str, parameters: Dict[str, Any]
    ) -> Dict:
        """执行 QVeris 工具"""
        import httpx

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{self.QVERIS_BASE_URL}/tools/execute",
                    params={"tool_id": tool_id},
                    headers=self._get_headers(),
                    json={
                        "search_id": search_id,
                        "parameters": parameters,
                        "max_response_size": 20480,
                    },
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.debug(f"[CryptoFetcher] QVeris 执行失败: {e}")
            return {"success": False, "error_message": str(e)}

    def _fetch_via_qveris(
        self, stock_code: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """通过 QVeris 获取数据（最后备选）"""
        if not self._qveris_available:
            return None

        try:
            logger.debug(f"[CryptoFetcher] 通过 QVeris 获取 {stock_code} 数据")

            search_result = self._search_qveris_tool(
                "cryptocurrency historical price OHLC candlestick bitcoin ethereum",
                limit=5,
            )

            if not search_result.get("results"):
                logger.debug("[CryptoFetcher] QVeris 未找到合适的工具")
                return None

            search_id = search_result.get("search_id", "")

            for tool in search_result.get("results", []):
                tool_id = tool.get("tool_id")

                params = {
                    "symbol": stock_code.upper(),
                    "start_date": start_date,
                    "end_date": end_date,
                    "interval": "daily",
                }

                result = self._execute_qveris_tool(tool_id, search_id, params)

                if result.get("success"):
                    data = result.get("result", {}).get("data", {})

                    if isinstance(data, list) and len(data) > 0:
                        df = pd.DataFrame(data)
                        logger.info(
                            f"[CryptoFetcher] QVeris 获取成功: {len(df)} 条记录"
                        )
                        return df
                    elif isinstance(data, dict):
                        for key in ["data", "items", "bars", "candles"]:
                            if key in data and isinstance(data[key], list):
                                df = pd.DataFrame(data[key])
                                logger.info(
                                    f"[CryptoFetcher] QVeris 获取成功: {len(df)} 条记录"
                                )
                                return df

            return None

        except Exception as e:
            logger.debug(f"[CryptoFetcher] QVeris 获取失败: {e}")
            return None

    def _get_realtime_quote_via_qveris(
        self, stock_code: str
    ) -> Optional[UnifiedRealtimeQuote]:
        """通过 QVeris 获取实时行情"""
        if not self._qveris_available:
            return None

        try:
            search_result = self._search_qveris_tool(
                "cryptocurrency real-time price quote bitcoin ethereum", limit=5
            )

            if not search_result.get("results"):
                return None

            search_id = search_result.get("search_id", "")

            for tool in search_result.get("results", []):
                tool_id = tool.get("tool_id")

                result = self._execute_qveris_tool(
                    tool_id, search_id, {"symbol": stock_code.upper()}
                )

                if result.get("success"):
                    data = result.get("result", {}).get("data", {})

                    if isinstance(data, dict):
                        base_symbol = self._extract_base_symbol(stock_code)
                        return UnifiedRealtimeQuote(
                            code=stock_code.upper(),
                            name=CRYPTO_NAMES.get(base_symbol, base_symbol),
                            source=RealtimeSource.QVERIS,
                            price=self._safe_float(
                                data.get("price") or data.get("last")
                            ),
                            change_pct=self._safe_float(
                                data.get("change_pct") or data.get("changePercent")
                            ),
                            change_amount=self._safe_float(
                                data.get("change") or data.get("changeAmount")
                            ),
                            volume=self._safe_int(data.get("volume")),
                            amount=self._safe_float(
                                data.get("amount") or data.get("turnover")
                            ),
                            open_price=self._safe_float(data.get("open")),
                            high=self._safe_float(data.get("high")),
                            low=self._safe_float(data.get("low")),
                            pre_close=self._safe_float(
                                data.get("prev_close") or data.get("previousClose")
                            ),
                            total_mv=self._safe_float(data.get("market_cap")),
                        )

            return None

        except Exception as e:
            logger.debug(f"[CryptoFetcher] QVeris 实时行情失败: {e}")
            return None

    # ==================== CCXT (第三选择) ====================

    def _get_ccxt(self):
        """导入并返回 ccxt 模块"""
        import ccxt

        return ccxt

    def _get_exchange(self) -> Any:
        """获取交易所实例（CCXT）"""
        if self._exchange is None:
            ccxt = self._get_ccxt()
            exchange_class = getattr(ccxt, self.exchange_name, None)
            if exchange_class is None:
                raise DataFetchError(f"不支持的交易所: {self.exchange_name}")
            self._exchange = exchange_class(
                {
                    "enableRateLimit": True,
                    "timeout": 30000,
                }
            )
        return self._exchange

    def _fetch_via_ccxt(
        self, stock_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """通过 CCXT 获取数据"""
        exchange = self._get_exchange()
        symbol = self._to_ccxt_symbol(stock_code)

        logger.debug(f"[CryptoFetcher] 通过 CCXT 获取 {symbol} 数据")

        try:
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

            all_ohlcv = []
            current_ts = start_ts

            while current_ts < end_ts:
                ohlcv = exchange.fetch_ohlcv(
                    symbol, timeframe="1d", since=current_ts, limit=1000
                )

                if not ohlcv:
                    break

                all_ohlcv.extend(ohlcv)
                last_ts = ohlcv[-1][0]
                if last_ts <= current_ts:
                    break
                current_ts = last_ts + 86400000
                time.sleep(0.1)

            if not all_ohlcv:
                raise DataFetchError(f"未获取到 {symbol} 的数据")

            df = pd.DataFrame(
                all_ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )

            df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]

            logger.info(f"[CryptoFetcher] CCXT 获取成功: {len(df)} 条记录")
            return df

        except Exception as e:
            if isinstance(e, DataFetchError):
                raise
            raise DataFetchError(f"获取加密货币数据失败: {e}") from e

    def _get_realtime_quote_via_ccxt(
        self, stock_code: str
    ) -> Optional[UnifiedRealtimeQuote]:
        """通过 CCXT 获取实时行情"""
        try:
            exchange = self._get_exchange()
            symbol = self._to_ccxt_symbol(stock_code)
            base_symbol = self._extract_base_symbol(stock_code)

            ticker = exchange.fetch_ticker(symbol)
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe="1d", limit=2)

            prev_close = None
            if len(ohlcv) >= 2:
                prev_close = ohlcv[-2][4]

            current_price = ticker.get("last", ticker.get("close", 0))

            change_pct = None
            change_amount = None
            if prev_close and prev_close > 0:
                change_amount = current_price - prev_close
                change_pct = (change_amount / prev_close) * 100

            return UnifiedRealtimeQuote(
                code=stock_code.upper(),
                name=CRYPTO_NAMES.get(base_symbol, base_symbol),
                source=RealtimeSource.CRYPTO,
                price=current_price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4)
                if change_amount is not None
                else None,
                volume=int(ticker.get("baseVolume", 0) or 0),
                amount=ticker.get("quoteVolume"),
                open_price=ticker.get("open"),
                high=ticker.get("high"),
                low=ticker.get("low"),
                pre_close=prev_close,
                total_mv=ticker.get("marketCap"),
            )

        except Exception as e:
            logger.debug(f"[CryptoFetcher] CCXT 实时行情失败: {e}")
            return None

    def _to_ccxt_symbol(self, stock_code: str) -> str:
        """转换加密货币代码为 CCXT 格式"""
        code = stock_code.strip().upper()
        if "/" in code:
            return code
        for suffix in ["USDT", "USDC", "USD", "BUSD"]:
            if code.endswith(suffix):
                code = code[: -len(suffix)]
                break
        code = code.replace("-", "")
        return f"{code}/USDT"

    def _extract_base_symbol(self, stock_code: str) -> str:
        """提取基础符号"""
        code = stock_code.strip().upper()
        for suffix in ["USDT", "USDC", "USD", "BUSD"]:
            if code.endswith(suffix):
                code = code[: -len(suffix)]
                break
        return code.replace("-", "")

    # ==================== 主入口方法 ====================

    def _fetch_raw_data(
        self, stock_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        获取原始数据

        优先级: CoinGecko -> Binance -> CCXT -> QVeris
        """
        errors = []

        # 1. CoinGecko (首选，免费)
        df = self._fetch_via_coingecko(stock_code, start_date, end_date)
        if df is not None and not df.empty:
            return df
        errors.append("CoinGecko")

        # 2. Binance (第二选择，免费)
        df = self._fetch_via_binance(stock_code, start_date, end_date)
        if df is not None and not df.empty:
            return df
        errors.append("Binance")

        # 3. CCXT (第三选择)
        try:
            df = self._fetch_via_ccxt(stock_code, start_date, end_date)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.debug(f"[CryptoFetcher] CCXT 失败: {e}")
        errors.append("CCXT")

        # 4. QVeris (最后备选)
        if self._qveris_available:
            df = self._fetch_via_qveris(stock_code, start_date, end_date)
            if df is not None and not df.empty:
                return df
        errors.append("QVeris")

        raise DataFetchError(f"所有数据源均失败 ({', '.join(errors)}): {stock_code}")

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取实时行情

        优先级: CoinGecko -> Binance -> CCXT -> QVeris
        """
        if not _is_crypto_code(stock_code):
            return None

        # 1. CoinGecko (首选)
        quote = self._get_realtime_quote_via_coingecko(stock_code)
        if quote:
            return quote

        # 2. Binance
        quote = self._get_realtime_quote_via_binance(stock_code)
        if quote:
            return quote

        # 3. CCXT
        try:
            quote = self._get_realtime_quote_via_ccxt(stock_code)
            if quote:
                return quote
        except Exception:
            pass

        # 4. QVeris
        if self._qveris_available:
            quote = self._get_realtime_quote_via_qveris(stock_code)
            if quote:
                return quote

        return None

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """标准化数据格式"""
        df = df.copy()

        # 处理可能的列名
        column_mapping = {
            "Date": "date",
            "Time": "date",
            "timestamp": "date",
            "datetime": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Vol": "volume",
            "Amount": "amount",
            "Turnover": "amount",
        }
        df = df.rename(columns=column_mapping)

        # 确保日期格式
        if "date" in df.columns:
            if not pd.api.types.is_string_dtype(df["date"]):
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        # 计算涨跌幅
        if "close" in df.columns:
            df["pct_chg"] = df["close"].pct_change() * 100
            df["pct_chg"] = df["pct_chg"].fillna(0).round(2)

        # 计算成交额
        if (
            "amount" not in df.columns
            and "close" in df.columns
            and "volume" in df.columns
        ):
            df["amount"] = df["close"] * df["volume"]

        df["code"] = stock_code

        keep_cols = ["code"] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]

        return df

    def _safe_float(self, val: Any) -> Optional[float]:
        try:
            if val is None:
                return None
            return float(val)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, val: Any) -> Optional[int]:
        try:
            if val is None:
                return None
            return int(float(val))
        except (ValueError, TypeError):
            return None

    def get_supported_cryptos(self) -> List[str]:
        """获取支持的加密货币列表"""
        return DEFAULT_CRYPTO_SYMBOLS.copy()

    def get_crypto_trending(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取热门加密货币行情"""
        results = []
        for symbol in DEFAULT_CRYPTO_SYMBOLS[:limit]:
            quote = self.get_realtime_quote(symbol)
            if quote:
                results.append(quote.to_dict())
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    fetcher = CryptoFetcher()

    print("\n=== BTC Realtime Quote ===")
    quote = fetcher.get_realtime_quote("BTC")
    if quote:
        print(f"Price: ${quote.price:,.2f}")
        print(f"Source: {quote.source.value}")

    print("\n=== BTC Historical Data (7 days) ===")
    from datetime import datetime, timedelta

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    df = fetcher.fetch_daily_data("BTC", start_date=start_date, end_date=end_date)
    if df is not None and not df.empty:
        print(f"Got {len(df)} records")
        print(df.tail())
