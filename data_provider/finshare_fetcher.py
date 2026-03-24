# -*- coding: utf-8 -*-
"""
===================================
FinshareFetcher - 多源聚合数据源 (Priority 1)
===================================

数据来源：
Finshare 是一个开源的 Python 库，聚合了多个数据源：
1. 东方财富 - 主数据源
2. 腾讯财经 - 备选
3. 新浪财经 - 备选
4. 通达信 - 备选
5. Baostock - 备选

特点：
- 完全免费，MIT 开源
- 无需 API Key
- 支持 A 股、港股、美股、期货、基金
- 多数据源自动切换

安装：pip install finshare
GitHub: https://github.com/finvfamily/finshare
"""

import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

import pandas as pd

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS, _is_crypto_code
from .realtime_types import UnifiedRealtimeQuote, ChipDistribution, safe_float

logger = logging.getLogger(__name__)


class FinshareFetcher(BaseFetcher):
    """
    Finshare 数据源获取器

    特点：
    1. 多数据源自动切换（东财、腾讯、新浪、通达信、Baostock）
    2. 完全免费，无需认证
    3. 支持 A 股、港股、美股
    """

    name: str = "FinshareFetcher"
    priority: int = 1  # 与 AkshareFetcher 同级

    def __init__(self):
        """初始化 Finshare 数据源"""
        self._fs = None
        self._initialized = False
        self._init_finshare()

    def _init_finshare(self) -> None:
        """初始化 Finshare 库"""
        try:
            import finshare as fs

            self._fs = fs
            self._initialized = True
            logger.info("[FinshareFetcher] Finshare 初始化成功")
        except ImportError:
            logger.warning(
                "[FinshareFetcher] finshare 库未安装，请运行: pip install finshare"
            )
            self._initialized = False
        except Exception as e:
            logger.error(f"[FinshareFetcher] 初始化失败: {e}")
            self._initialized = False

    def _fetch_raw_data(
        self, stock_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        从 Finshare 获取原始 K 线数据

        Args:
            stock_code: 股票代码（如 '600519'）
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'

        Returns:
            原始数据 DataFrame
        """
        if not self._initialized:
            raise DataFetchError("Finshare 未初始化")

        # 转换代码格式（Finshare 使用带后缀的格式）
        fs_code = self._convert_code_format(stock_code)

        try:
            # 使用 Finshare 获取历史数据
            df = self._fs.get_historical_data(
                symbol=fs_code, start=start_date, end=end_date
            )

            if df is None or df.empty:
                raise DataFetchError(f"Finshare 返回空数据: {stock_code}")

            return df

        except Exception as e:
            raise DataFetchError(f"Finshare 获取数据失败: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化数据列名

        将 Finshare 返回的数据标准化为统一格式：
        ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        """
        df = df.copy()

        # Finshare 返回的列名映射
        column_mapping = {
            "date": "date",
            "time": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "vol": "volume",
            "amount": "amount",
            "turnover": "amount",
            "change": "pct_chg",
            "pct_change": "pct_chg",
            "pctChg": "pct_chg",
        }

        # 重命名列
        df.columns = [
            column_mapping.get(col.lower(), col.lower()) for col in df.columns
        ]

        # 确保日期列存在
        if "date" not in df.columns:
            if df.index.name == "date" or "date" in str(df.index.name or ""):
                df = df.reset_index()

        # 确保必要列存在
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise DataFetchError(f"数据缺少必要列: {missing_cols}")

        # 计算涨跌幅（如果没有）
        if "pct_chg" not in df.columns:
            df["pct_chg"] = df["close"].pct_change() * 100

        # 确保金额列存在
        if "amount" not in df.columns:
            df["amount"] = df["close"] * df["volume"]

        # 选择标准列
        standard_cols = [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "pct_chg",
        ]
        df = df[[col for col in standard_cols if col in df.columns]]

        return df

    def _convert_code_format(self, stock_code: str) -> str:
        code = stock_code.strip().upper()

        # 加密货币代码不应该通过 Finshare 处理，抛出异常让调用方使用正确的数据源
        if _is_crypto_code(code):
            raise DataFetchError(
                f"[FinshareFetcher] 加密货币代码 {code} 不支持通过股票数据源获取，"
                f"请使用 CryptoFetcher"
            )

        # 已经是 Finshare 格式
        if "." in code:
            return code

        # 判断市场
        if code.startswith("HK"):
            # 港股: HK00700 -> 00700.HK
            numeric = code[2:].zfill(5)
            return f"{numeric}.HK"
        elif code.endswith(".HK"):
            # 已经是港股格式
            return code
        elif code.isdigit() and len(code) == 5:
            # 5 位数字，视为港股
            return f"{code}.HK"
        elif code.isdigit() and len(code) == 6:
            # A 股 6 位代码
            if code.startswith(("60", "68")):
                return f"{code}.SH"  # 上交所
            else:
                return f"{code}.SZ"  # 深交所
        elif code.isalpha() and 1 <= len(code) <= 5:
            # 美股代码
            return f"{code}.US"
        else:
            # 默认视为 A 股
            return f"{code}.SZ"

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取实时行情数据

        Args:
            stock_code: 股票代码

        Returns:
            UnifiedRealtimeQuote 对象，失败返回 None
        """
        if not self._initialized:
            return None

        try:
            fs_code = self._convert_code_format(stock_code)

            # 使用 Finshare 获取快照数据
            snapshot = self._fs.get_snapshot_data(fs_code)

            if snapshot is None:
                return None

            # 解析快照数据
            return self._parse_snapshot(snapshot, stock_code)

        except Exception as e:
            logger.warning(f"[FinshareFetcher] 获取实时行情失败 {stock_code}: {e}")
            return None

    def _parse_snapshot(
        self, snapshot: Any, stock_code: str
    ) -> Optional[UnifiedRealtimeQuote]:
        """
        解析快照数据

        Args:
            snapshot: Finshare 返回的快照对象
            stock_code: 股票代码

        Returns:
            UnifiedRealtimeQuote 对象
        """
        try:
            # Finshare 的 SnapshotData 对象属性
            if hasattr(snapshot, "price"):
                # 对象格式
                price = safe_float(getattr(snapshot, "price", 0))
                open_price = safe_float(getattr(snapshot, "open", 0))
                high = safe_float(getattr(snapshot, "high", 0))
                low = safe_float(getattr(snapshot, "low", 0))
                volume = safe_float(getattr(snapshot, "volume", 0))
                amount = safe_float(getattr(snapshot, "amount", 0))
                prev_close = safe_float(getattr(snapshot, "prev_close", 0))
                name = getattr(snapshot, "name", f"股票{stock_code}")
            elif isinstance(snapshot, dict):
                # 字典格式
                price = safe_float(snapshot.get("price", 0))
                open_price = safe_float(snapshot.get("open", 0))
                high = safe_float(snapshot.get("high", 0))
                low = safe_float(snapshot.get("low", 0))
                volume = safe_float(snapshot.get("volume", 0))
                amount = safe_float(snapshot.get("amount", 0))
                prev_close = safe_float(snapshot.get("prev_close", 0))
                name = snapshot.get("name", f"股票{stock_code}")
            else:
                return None

            # 计算涨跌
            change = price - prev_close if prev_close > 0 else 0
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0

            return UnifiedRealtimeQuote(
                code=stock_code,
                name=name,
                price=price,
                open_price=open_price,
                high=high,
                low=low,
                prev_close=prev_close,
                change=change,
                change_pct=change_pct,
                volume=volume,
                amount=amount,
                timestamp=datetime.now(),
                source="finshare",
            )

        except Exception as e:
            logger.warning(f"[FinshareFetcher] 解析快照失败: {e}")
            return None

    def get_chip_distribution(self, stock_code: str) -> Optional[ChipDistribution]:
        """
        获取筹码分布数据

        注意：Finshare 可能不支持筹码分布，返回 None

        Args:
            stock_code: 股票代码

        Returns:
            ChipDistribution 对象，不支持时返回 None
        """
        # Finshare 目前不支持筹码分布数据
        return None

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        return self._initialized

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        获取股票名称

        利用实时行情接口获取股票名称

        Args:
            stock_code: 股票代码

        Returns:
            股票名称，失败返回 None
        """
        # 检查缓存
        if not hasattr(self, "_stock_name_cache"):
            self._stock_name_cache = {}

        if stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]

        try:
            # 通过实时行情获取名称
            quote = self.get_realtime_quote(stock_code)
            if quote and quote.name:
                self._stock_name_cache[stock_code] = quote.name
                return quote.name

            return None

        except Exception as e:
            logger.debug(f"[FinshareFetcher] 获取股票名称失败 {stock_code}: {e}")
            return None

    def get_supported_markets(self) -> List[str]:
        """获取支持的市场列表"""
        return ["cn", "hk", "us"]
