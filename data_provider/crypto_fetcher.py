# -*- coding: utf-8 -*-
"""
===================================
CryptoFetcher - 加密货币数据源 (Priority 1)
===================================

数据来源（优先级）：
1. Hyperliquid 公开API (免费，无需API Key，无区域限制) - 首选
2. Bybit 公开API (免费，无需API Key，可能在云环境被 Cloudflare 屏蔽) - 第二选择
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


class CryptoFetcher(BaseFetcher):
    """
    加密货币数据源实现

    优先级：1（高优先级）
    数据来源：Hyperliquid -> Bybit -> CCXT -> QVeris

    关键策略：
    - 首选 Hyperliquid（无区域限制，稳定可靠）
    - Hyperliquid 失败时回退到 Bybit（可能在云环境被 Cloudflare 屏蔽）
    - Bybit 失败时回退到 CCXT
    - CCXT 失败时回退到 QVeris（需 API Key）
    - 自动转换加密货币代码格式
    """

    name = "CryptoFetcher"
    priority = int(os.getenv("CRYPTO_PRIORITY", "1"))

    # API 配置
    # Bybit API（无区域限制，首选）
    BYBIT_BASE_URL = "https://api.bybit.com/v5"
    # Hyperliquid API（无区域限制，免费）
    HYPERLIQUID_BASE_URL = "https://api.hyperliquid.xyz"
    QVERIS_BASE_URL = "https://qveris.ai/api/v1"
    REQUEST_TIMEOUT = 15

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

        logger.info(
            "[CryptoFetcher] 数据源优先级: Hyperliquid(无区域限制) -> Bybit -> CCXT -> QVeris"
        )

    # ==================== Bybit API (首选，无区域限制) ====================

    def _fetch_via_bybit(
        self, stock_code: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        通过 Bybit API 获取数据（免费，无区域限制，首选数据源）

        Bybit API 特点：
        - 无区域限制，可从中国访问
        - 免费，无需 API Key 获取公开数据
        - 高速率限制（60 req/sec）
        - 支持最多 1000 条/请求

        Args:
            stock_code: 加密货币代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame 或 None
        """
        try:
            symbol = self._to_bybit_symbol(stock_code)
            logger.debug(f"[Bybit] 映射 {stock_code} -> {symbol}")

            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
            logger.debug(f"[Bybit] 时间范围: {start_date} ~ {end_date}")

            all_klines = []
            current_ts = start_ts
            request_count = 0

            while current_ts < end_ts:
                url = f"{self.BYBIT_BASE_URL}/market/kline"
                params = {
                    "category": "spot",
                    "symbol": symbol,
                    "interval": "D",  # Daily
                    "start": current_ts,
                    "end": end_ts,
                    "limit": 1000,  # Bybit 最大 1000
                }

                request_count += 1
                logger.debug(f"[Bybit] 请求 #{request_count}: symbol={symbol}")
                resp = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT)

                if resp.status_code == 429:
                    logger.warning("[Bybit] 速率限制 (429)，等待...")
                    time.sleep(2)
                    continue

                if resp.status_code != 200:
                    logger.warning(
                        f"[Bybit] HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    break

                data = resp.json()
                if data.get("retCode", -1) != 0:
                    logger.warning(f"[Bybit] API 错误: {data.get('retMsg', 'Unknown')}")
                    break

                klines = data.get("result", {}).get("list", [])
                if not klines:
                    logger.debug(f"[Bybit] 返回空数据，停止分页")
                    break

                all_klines.extend(klines)
                logger.debug(
                    f"[Bybit] 本次返回 {len(klines)} 条，累计 {len(all_klines)} 条"
                )

                # Bybit klines 按 startTime 倒序排列，最早在最后
                # 格式: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
                oldest_ts = min(int(k[0]) for k in klines)
                if oldest_ts <= current_ts:
                    break
                current_ts = oldest_ts - 86400000  # 向前移动
                time.sleep(0.1)

            if not all_klines:
                logger.warning(f"[Bybit] 无数据返回: symbol={symbol}")
                return None

            # Bybit kline 格式: [startTime, open, high, low, close, volume, turnover]
            # 注意: 数据是倒序的，需要反转
            all_klines.sort(key=lambda x: int(x[0]))

            df = pd.DataFrame(
                all_klines,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "turnover",
                ],
            )

            df["date"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms")
            df = df[["date", "open", "high", "low", "close", "volume"]]
            df[["open", "high", "low", "close", "volume"]] = df[
                ["open", "high", "low", "close", "volume"]
            ].astype(float)

            # 过滤日期范围
            original_count = len(df)
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
            logger.debug(f"[Bybit] 日期过滤: {original_count} -> {len(df)} 条")

            if df.empty:
                logger.warning(
                    f"[Bybit] 过滤后无数据，日期范围: {start_date} ~ {end_date}"
                )
                return None

            logger.info(f"[Bybit] 获取成功: {stock_code} {len(df)} 条记录")
            return df

        except Exception as e:
            logger.warning(f"[Bybit] 获取失败: {type(e).__name__}: {e}")
            import traceback

            logger.debug(f"[Bybit] 堆栈: {traceback.format_exc()}")
            return None

    def _get_realtime_quote_via_bybit(
        self, stock_code: str
    ) -> Optional[UnifiedRealtimeQuote]:
        """通过 Bybit 获取实时行情"""
        try:
            symbol = self._to_bybit_symbol(stock_code)
            base_symbol = self._extract_base_symbol(stock_code)

            url = f"{self.BYBIT_BASE_URL}/market/tickers"
            params = {"category": "spot", "symbol": symbol}
            resp = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT)

            if resp.status_code != 200:
                return None

            data = resp.json()
            if data.get("retCode", -1) != 0:
                return None

            tickers = data.get("result", {}).get("list", [])
            if not tickers:
                return None

            ticker = tickers[0]

            return UnifiedRealtimeQuote(
                code=stock_code.upper(),
                name=CRYPTO_NAMES.get(base_symbol, base_symbol),
                source=RealtimeSource.CRYPTO,
                price=self._safe_float(ticker.get("lastPrice")),
                change_pct=self._safe_float(ticker.get("price24hPcnt")) * 100
                if ticker.get("price24hPcnt")
                else None,
                volume=self._safe_float(ticker.get("volume24h")),
                amount=self._safe_float(ticker.get("turnover24h")),
                high=self._safe_float(ticker.get("highPrice24h")),
                low=self._safe_float(ticker.get("lowPrice24h")),
            )

        except Exception as e:
            logger.debug(f"[Bybit] 实时行情失败: {e}")
            return None

    def _to_bybit_symbol(self, stock_code: str) -> str:
        """转换为 Bybit symbol 格式 (如 BTCUSDT)"""
        code = stock_code.strip().upper()
        for suffix in ["USDT", "USDC", "USD", "BUSD"]:
            if code.endswith(suffix):
                code = code[: -len(suffix)]
                break
        code = code.replace("-", "")
        return f"{code}USDT"

    # ==================== Hyperliquid API (备选，无区域限制，免费) ====================

    def _fetch_via_hyperliquid(
        self, stock_code: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        通过 Hyperliquid API 获取数据（免费，无区域限制）

        Hyperliquid API 特点：
        - 无区域限制，可从中国访问
        - 免费，无需 API Key 获取公开数据
        - 支持最多 5000 条历史蜡烛
        - 支持多种时间间隔: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 12h, 1d, 3d, 1w, 1M

        Args:
            stock_code: 加密货币代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame 或 None
        """
        try:
            # Hyperliquid 使用简单的符号名 (BTC, ETH 等)
            symbol = self._extract_base_symbol(stock_code)
            logger.debug(f"[Hyperliquid] 映射 {stock_code} -> {symbol}")

            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
            logger.debug(f"[Hyperliquid] 时间范围: {start_date} ~ {end_date}")

            url = f"{self.HYPERLIQUID_BASE_URL}/info"
            payload = {
                "type": "candleSnapshot",
                "req": {
                    "coin": symbol,
                    "interval": "1d",
                    "startTime": start_ts,
                    "endTime": end_ts,
                },
            }
            headers = {"Content-Type": "application/json"}

            logger.debug(f"[Hyperliquid] 请求: symbol={symbol}")
            resp = requests.post(
                url, json=payload, headers=headers, timeout=self.REQUEST_TIMEOUT
            )

            if resp.status_code != 200:
                logger.warning(
                    f"[Hyperliquid] HTTP {resp.status_code}: {resp.text[:200]}"
                )
                return None

            candles = resp.json()
            if not candles:
                logger.warning(f"[Hyperliquid] 无数据返回: symbol={symbol}")
                return None

            logger.debug(f"[Hyperliquid] 返回 {len(candles)} 条记录")

            # Hyperliquid candle 格式:
            # t: open time, T: close time, s: symbol, i: interval
            # o: open, h: high, l: low, c: close, v: volume, n: trades
            df = pd.DataFrame(candles)

            # 重命名列
            df = df.rename(
                columns={
                    "t": "timestamp",
                    "o": "open",
                    "h": "high",
                    "l": "low",
                    "c": "close",
                    "v": "volume",
                }
            )

            df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df[["date", "open", "high", "low", "close", "volume"]]
            df[["open", "high", "low", "close", "volume"]] = df[
                ["open", "high", "low", "close", "volume"]
            ].astype(float)

            # 过滤日期范围
            original_count = len(df)
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
            logger.debug(f"[Hyperliquid] 日期过滤: {original_count} -> {len(df)} 条")

            if df.empty:
                logger.warning(
                    f"[Hyperliquid] 过滤后无数据，日期范围: {start_date} ~ {end_date}"
                )
                return None

            logger.info(f"[Hyperliquid] 获取成功: {stock_code} {len(df)} 条记录")
            return df

        except Exception as e:
            logger.warning(f"[Hyperliquid] 获取失败: {type(e).__name__}: {e}")
            import traceback

            logger.debug(f"[Hyperliquid] 堆栈: {traceback.format_exc()}")
            return None

    def _get_realtime_quote_via_hyperliquid(
        self, stock_code: str
    ) -> Optional[UnifiedRealtimeQuote]:
        """通过 Hyperliquid 获取实时行情"""
        try:
            symbol = self._extract_base_symbol(stock_code)
            base_symbol = self._extract_base_symbol(stock_code)

            url = f"{self.HYPERLIQUID_BASE_URL}/info"
            payload = {"type": "allMids"}
            headers = {"Content-Type": "application/json"}

            resp = requests.post(
                url, json=payload, headers=headers, timeout=self.REQUEST_TIMEOUT
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            price = self._safe_float(data.get(symbol))

            if not price:
                return None

            return UnifiedRealtimeQuote(
                code=stock_code.upper(),
                name=CRYPTO_NAMES.get(base_symbol, base_symbol),
                source=RealtimeSource.CRYPTO,
                price=price,
            )

        except Exception as e:
            logger.debug(f"[Hyperliquid] 实时行情失败: {e}")
            return None

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
            logger.debug("[QVeris] API Key 未配置，跳过")
            return None

        try:
            logger.debug(
                f"[QVeris] 开始搜索工具: {stock_code}, 日期范围: {start_date} ~ {end_date}"
            )

            search_result = self._search_qveris_tool(
                "cryptocurrency historical price OHLC candlestick bitcoin ethereum",
                limit=5,
            )

            results = search_result.get("results", [])
            if not results:
                logger.warning("[QVeris] 未找到合适的加密货币历史数据工具")
                return None

            search_id = search_result.get("search_id", "")
            logger.debug(
                f"[QVeris] 找到 {len(results)} 个工具，search_id={search_id[:20]}..."
            )

            for idx, tool in enumerate(results):
                tool_id = tool.get("tool_id")
                tool_name = tool.get("name", "unknown")
                logger.debug(
                    f"[QVeris] 尝试工具 {idx + 1}/{len(results)}: {tool_name} (id={tool_id[:20]}...)"
                )

                params = {
                    "symbol": stock_code.upper(),
                    "start_date": start_date,
                    "end_date": end_date,
                    "interval": "daily",
                }

                result = self._execute_qveris_tool(tool_id, search_id, params)

                if result.get("success"):
                    data = result.get("result", {}).get("data", {})
                    logger.debug(
                        f"[QVeris] 工具返回成功，数据类型: {type(data).__name__}"
                    )

                    if isinstance(data, list) and len(data) > 0:
                        df = pd.DataFrame(data)
                        logger.info(f"[QVeris] 获取成功: {stock_code} {len(df)} 条记录")
                        return df
                    elif isinstance(data, dict):
                        for key in ["data", "items", "bars", "candles"]:
                            if key in data and isinstance(data[key], list):
                                df = pd.DataFrame(data[key])
                                logger.info(
                                    f"[QVeris] 获取成功: {stock_code} {len(df)} 条记录 (key={key})"
                                )
                                return df
                        logger.warning(
                            f"[QVeris] 数据结构不支持，keys: {list(data.keys())}"
                        )
                else:
                    error_msg = result.get("error_message", "unknown error")
                    logger.debug(f"[QVeris] 工具执行失败: {error_msg}")

            logger.warning(f"[QVeris] 所有工具都无法获取 {stock_code} 的历史数据")
            return None

        except Exception as e:
            logger.warning(f"[QVeris] 获取失败: {type(e).__name__}: {e}")
            import traceback

            logger.debug(f"[QVeris] 堆栈: {traceback.format_exc()}")
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
        try:
            exchange = self._get_exchange()
            symbol = self._to_ccxt_symbol(stock_code)
            logger.debug(
                f"[CCXT] 映射 {stock_code} -> {symbol}, 交易所: {self.exchange_name}"
            )

            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
            logger.debug(f"[CCXT] 时间范围: {start_date} ~ {end_date}")

            all_ohlcv = []
            current_ts = start_ts
            request_count = 0

            while current_ts < end_ts:
                request_count += 1
                logger.debug(f"[CCXT] 请求 #{request_count}: symbol={symbol}")

                try:
                    ohlcv = exchange.fetch_ohlcv(
                        symbol, timeframe="1d", since=current_ts, limit=1000
                    )
                except Exception as fetch_err:
                    logger.warning(f"[CCXT] fetch_ohlcv 失败: {fetch_err}")
                    raise

                if not ohlcv:
                    logger.debug(f"[CCXT] 返回空数据，停止分页")
                    break

                all_ohlcv.extend(ohlcv)
                logger.debug(
                    f"[CCXT] 本次返回 {len(ohlcv)} 条，累计 {len(all_ohlcv)} 条"
                )

                last_ts = ohlcv[-1][0]
                if last_ts <= current_ts:
                    break
                current_ts = last_ts + 86400000
                time.sleep(0.1)

            if not all_ohlcv:
                logger.warning(f"[CCXT] 未获取到 {symbol} 的数据")
                raise DataFetchError(f"未获取到 {symbol} 的数据")

            df = pd.DataFrame(
                all_ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )

            df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
            original_count = len(df)
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
            logger.debug(f"[CCXT] 日期过滤: {original_count} -> {len(df)} 条")

            logger.info(f"[CCXT] 获取成功: {stock_code} {len(df)} 条记录")
            return df

        except Exception as e:
            logger.warning(f"[CCXT] 获取失败: {type(e).__name__}: {e}")
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

        优先级: Hyperliquid -> Bybit -> CCXT -> QVeris

        注意：
        - Hyperliquid 无区域限制，免费，提供最多5000条历史数据（首选）
        - Bybit 可能在某些云环境被 Cloudflare 屏蔽 (HTTP 403)
        """
        errors = []
        error_details = []  # 存储详细错误信息

        # 1. Hyperliquid (首选，无区域限制，免费)
        logger.info(f"[CryptoFetcher] 尝试数据源 1/4: Hyperliquid (无区域限制，免费)")
        try:
            df = self._fetch_via_hyperliquid(stock_code, start_date, end_date)
            if df is not None and not df.empty:
                logger.info(f"[CryptoFetcher] Hyperliquid 成功: {len(df)} 条记录")
                return df
            errors.append("Hyperliquid")
            error_details.append("Hyperliquid: 返回空数据")
        except Exception as e:
            errors.append("Hyperliquid")
            error_details.append(f"Hyperliquid: {type(e).__name__}: {e}")
            logger.warning(f"[CryptoFetcher] Hyperliquid 失败: {e}")

        # 2. Bybit (第二选择，可能在云环境被屏蔽)
        logger.info(f"[CryptoFetcher] 尝试数据源 2/4: Bybit (无区域限制，完整日线)")
        try:
            df = self._fetch_via_bybit(stock_code, start_date, end_date)
            if df is not None and not df.empty:
                logger.info(f"[CryptoFetcher] Bybit 成功: {len(df)} 条记录")
                return df
            errors.append("Bybit")
            error_details.append("Bybit: 返回空数据")
        except Exception as e:
            errors.append("Bybit")
            error_details.append(f"Bybit: {type(e).__name__}: {e}")
            logger.warning(f"[CryptoFetcher] Bybit 失败: {e}")

        # 3. CCXT (第三选择)
        logger.info(f"[CryptoFetcher] 尝试数据源 3/4: CCXT")
        try:
            df = self._fetch_via_ccxt(stock_code, start_date, end_date)
            if df is not None and not df.empty:
                logger.info(f"[CryptoFetcher] CCXT 成功: {len(df)} 条记录")
                return df
        except Exception as e:
            errors.append("CCXT")
            error_details.append(f"CCXT: {type(e).__name__}: {e}")
            logger.warning(f"[CryptoFetcher] CCXT 失败: {e}")

        # 4. QVeris (最后备选)
        if self._qveris_available:
            logger.info(f"[CryptoFetcher] 尝试数据源 4/4: QVeris")
            try:
                df = self._fetch_via_qveris(stock_code, start_date, end_date)
                if df is not None and not df.empty:
                    logger.info(f"[CryptoFetcher] QVeris 成功: {len(df)} 条记录")
                    return df
                errors.append("QVeris")
                error_details.append("QVeris: 返回空数据")
            except Exception as e:
                errors.append("QVeris")
                error_details.append(f"QVeris: {type(e).__name__}: {e}")
                logger.warning(f"[CryptoFetcher] QVeris 失败: {e}")
        else:
            errors.append("QVeris")
            error_details.append("QVeris: API Key 未配置")

        # 打印详细错误摘要
        logger.error(f"[CryptoFetcher] 所有数据源均失败:")
        for detail in error_details:
            logger.error(f"  - {detail}")
        raise DataFetchError(f"所有数据源均失败 ({', '.join(errors)}): {stock_code}")

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取实时行情

        优先级: Hyperliquid -> Bybit -> CCXT -> QVeris
        """
        if not _is_crypto_code(stock_code):
            return None

        # 1. Hyperliquid (首选，无区域限制)
        quote = self._get_realtime_quote_via_hyperliquid(stock_code)
        if quote:
            return quote

        # 2. Bybit (可能在云环境被屏蔽)
        quote = self._get_realtime_quote_via_bybit(stock_code)
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
