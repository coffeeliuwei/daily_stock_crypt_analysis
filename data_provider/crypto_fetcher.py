# -*- coding: utf-8 -*-
"""
===================================
CryptoFetcher - 加密货币数据源 (Priority 1)
===================================

数据来源：QVeris API（首选）-> CCXT（备用）
特点：统一 API 网关，支持主流加密货币
定位：为系统添加 BTC、ETH 等加密货币的数据支持

关键策略：
1. 首选 QVeris API 获取加密货币数据
2. QVeris 不可用时回退到 CCXT/Binance
3. 自动将 BTC、ETH 等符号转换为标准格式
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd

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

# 加密货币名称映射
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


class CryptoFetcher(BaseFetcher):
    """
    加密货币数据源实现

    优先级：1（高优先级）
    数据来源：QVeris（首选）-> CCXT（备用）

    关键策略：
    - 首选 QVeris API 获取数据
    - QVeris 不可用时回退到 CCXT
    - 自动转换加密货币代码格式
    """

    name = "CryptoFetcher"
    priority = int(os.getenv("CRYPTO_PRIORITY", "1"))

    # QVeris API 配置
    QVERIS_BASE_URL = "https://qveris.ai/api/v1"
    QVERIS_TIMEOUT = 30

    def __init__(self, exchange: str = "binance"):
        """
        初始化 CryptoFetcher

        Args:
            exchange: 备用交易所名称，默认 binance
        """
        self.exchange_name = exchange
        self._exchange = None
        self._ccxt = None

        # QVeris 配置
        self.qveris_api_key = os.getenv("QVERIS_API_KEY")
        self._qveris_available = bool(self.qveris_api_key)

        if self._qveris_available:
            logger.info("[CryptoFetcher] QVeris API 已配置，作为首选数据源")
        else:
            logger.info("[CryptoFetcher] QVeris API 未配置，使用 CCXT 作为数据源")

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
            with httpx.Client(timeout=self.QVERIS_TIMEOUT) as client:
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
            with httpx.Client(timeout=self.QVERIS_TIMEOUT) as client:
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

    def _get_exchange(self) -> Any:
        """获取交易所实例（CCXT 备用）"""
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
        ccxt_symbol = self._to_ccxt_symbol(stock_code)
        return ccxt_symbol.split("/")[0]

    def _fetch_via_qveris(
        self, stock_code: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        通过 QVeris 获取数据（首选）

        Returns:
            DataFrame 或 None（失败时）
        """
        if not self._qveris_available:
            return None

        try:
            logger.debug(f"[CryptoFetcher] 通过 QVeris 获取 {stock_code} 数据")

            # 搜索加密货币历史数据工具
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

    def _fetch_via_ccxt(
        self, stock_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        通过 CCXT 获取数据（备用）
        """
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

    def _fetch_raw_data(
        self, stock_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        获取原始数据（首选 QVeris，备用 CCXT）
        """
        # 1. 首选：QVeris
        if self._qveris_available:
            df = self._fetch_via_qveris(stock_code, start_date, end_date)
            if df is not None and not df.empty:
                return df
            logger.info("[CryptoFetcher] QVeris 获取失败，回退到 CCXT")

        # 2. 备用：CCXT
        return self._fetch_via_ccxt(stock_code, start_date, end_date)

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

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """获取实时行情（首选 QVeris，备用 CCXT）"""
        if not _is_crypto_code(stock_code):
            return None

        # 首选 QVeris
        if self._qveris_available:
            quote = self._get_realtime_quote_via_qveris(stock_code)
            if quote:
                return quote
            logger.debug("[CryptoFetcher] QVeris 实时行情失败，回退到 CCXT")

        # 备用 CCXT
        return self._get_realtime_quote_via_ccxt(stock_code)

    def _get_realtime_quote_via_qveris(
        self, stock_code: str
    ) -> Optional[UnifiedRealtimeQuote]:
        """通过 QVeris 获取实时行情"""
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
            logger.warning(f"[CryptoFetcher] CCXT 获取 {stock_code} 实时行情失败: {e}")
            return None

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

    print("\n=== BTC 实时行情 ===")
    quote = fetcher.get_realtime_quote("BTC")
    if quote:
        print(f"价格: ${quote.price:,.2f}")
        print(f"来源: {quote.source.value}")
