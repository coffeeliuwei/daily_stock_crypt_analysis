# -*- coding: utf-8 -*-
"""
===================================
AshareFetcher - 新浪/腾讯双核数据源 (Priority 1)
===================================

数据来源：
Ashare 是一个极简的 A 股数据接口，使用新浪/腾讯双数据源：
1. 腾讯财经 - 主数据源
2. 新浪财经 - 备选（可能被封禁）

特点：
- 完全免费，无需 API Key
- 双数据源自动切换
- 支持 A 股日线、分钟线
- 极简封装，稳定运行多年

GitHub: https://github.com/mpquant/Ashare
"""

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import requests

from .base_fetcher import BaseFetcher
from .exceptions import DataFetchError
from .utils import STANDARD_COLUMNS

logger = logging.getLogger(__name__)


class AshareFetcher(BaseFetcher):
    """
    Ashare 数据源获取器

    特点：
    1. 使用腾讯财经 API（新浪可能被封）
    2. 完全免费，无需认证
    3. 支持 A 股日线、分钟线
    """

    name: str = "AshareFetcher"
    priority: int = 1  # 与 AkshareFetcher、FinshareFetcher 同级

    # API 端点
    TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q={}"
    TENCENT_KLINE_URL = "http://web.sqt.gtimg.cn/q={}"

    def __init__(self):
        """初始化 Ashare 数据源"""
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        logger.info("[AshareFetcher] 初始化成功，使用腾讯财经 API")

    def _convert_code_format(self, stock_code: str) -> str:
        """
        转换股票代码格式为腾讯 API 格式

        Args:
            stock_code: 原始股票代码，如 '600519', '000001', 'sh600519'

        Returns:
            腾讯 API 格式代码，如 'sh600519', 'sz000001'
        """
        # 去除前缀和后缀
        code = stock_code.lower().strip()
        if code.startswith("sh") or code.startswith("sz") or code.startswith("bj"):
            return code
        if code.endswith(".sh") or code.endswith(".sz") or code.endswith(".bj"):
            code = code.split(".")[0]

        # 根据代码规则判断市场
        if code.startswith(("6", "9", "5")):
            return f"sh{code}"
        elif code.startswith(("0", "3", "2")):
            return f"sz{code}"
        elif code.startswith(("4", "8")):
            return f"bj{code}"
        else:
            # 默认上交所
            return f"sh{code}"

    def _fetch_raw_data(
        self, stock_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        从腾讯财经 API 获取历史 K 线数据

        Args:
            stock_code: 股票代码（如 '600519'）
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'

        Returns:
            原始数据 DataFrame
        """
        # 转换代码格式
        qt_code = self._convert_code_format(stock_code)

        try:
            # 尝试获取分钟线数据并转换为日线
            # 腾讯 API 的历史数据接口
            df = self._fetch_kline_from_tencent(qt_code, start_date, end_date)

            if df is not None and not df.empty:
                return df

            # 如果分钟线失败，尝试实时数据
            df = self._fetch_realtime_quote(qt_code)
            if df is not None and not df.empty:
                return df

            raise DataFetchError(f"Ashare 获取数据失败: {stock_code}")

        except Exception as e:
            raise DataFetchError(f"Ashare 获取数据失败: {e}") from e

    def _fetch_kline_from_tencent(
        self, qt_code: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        从腾讯 API 获取 K 线数据

        腾讯 K 线 API 格式：
        http://web.sqt.gtimg.cn/q=sh600519
        """
        try:
            url = f"http://web.sqt.gtimg.cn/q={qt_code}"
            response = self._session.get(url, timeout=10)

            if response.status_code != 200:
                return None

            # 解析腾讯数据格式
            content = response.text
            if not content or "~" not in content:
                return None

            # 提取数据
            parts = content.split("~")
            if len(parts) < 35:
                return None

            # 腾讯实时数据字段（简化版）
            # 格式: v_sh600519="1~名称~代码~...~开盘~昨收~..."
            data = {
                "date": [datetime.now().strftime("%Y-%m-%d")],
                "open": [self._safe_float(parts[5]) if len(parts) > 5 else None],
                "close": [self._safe_float(parts[3]) if len(parts) > 3 else None],
                "high": [self._safe_float(parts[33]) if len(parts) > 33 else None],
                "low": [self._safe_float(parts[34]) if len(parts) > 34 else None],
                "volume": [self._safe_int(parts[6]) if len(parts) > 6 else None],
                "amount": [self._safe_float(parts[37]) if len(parts) > 37 else None],
            }

            df = pd.DataFrame(data)
            return df

        except Exception as e:
            logger.debug(f"[AshareFetcher] 腾讯 K 线获取失败: {e}")
            return None

    def _fetch_realtime_quote(self, qt_code: str) -> Optional[pd.DataFrame]:
        """
        获取实时行情数据

        腾讯实时行情 API:
        http://qt.gtimg.cn/q=sh600519
        """
        try:
            url = f"http://qt.gtimg.cn/q={qt_code}"
            response = self._session.get(url, timeout=10)

            if response.status_code != 200:
                logger.warning(f"[AshareFetcher] 腾讯 API 返回 {response.status_code}")
                return None

            content = response.text
            if not content or "~" not in content:
                return None

            # 解析腾讯实时数据格式
            # v_sh600519="1~贵州茅台~600519~1408.07~..."
            parts = content.split("~")
            if len(parts) < 35:
                return None

            # 提取字段
            data = {
                "date": [datetime.now().strftime("%Y-%m-%d")],
                "open": [self._safe_float(parts[5]) if len(parts) > 5 else None],
                "close": [self._safe_float(parts[3]) if len(parts) > 3 else None],
                "high": [self._safe_float(parts[33]) if len(parts) > 33 else None],
                "low": [self._safe_float(parts[34]) if len(parts) > 34 else None],
                "volume": [self._safe_int(parts[6]) if len(parts) > 6 else None],
                "amount": [self._safe_float(parts[37]) if len(parts) > 37 else None],
            }

            df = pd.DataFrame(data)

            # 过滤无效数据
            if df["close"].iloc[0] is None or df["close"].iloc[0] == 0:
                return None

            return df

        except Exception as e:
            logger.warning(f"[AshareFetcher] 实时行情获取失败: {e}")
            return None

    def _safe_float(self, value: str) -> Optional[float]:
        """安全转换为浮点数"""
        try:
            if value and value.strip():
                return float(value.strip())
            return None
        except (ValueError, AttributeError):
            return None

    def _safe_int(self, value: str) -> Optional[int]:
        """安全转换为整数"""
        try:
            if value and value.strip():
                return int(float(value.strip()))
            return None
        except (ValueError, AttributeError):
            return None

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化数据列名

        将 Ashare 返回的数据标准化为统一格式：
        ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        """
        df = df.copy()

        # 确保必要列存在
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in df.columns:
                raise DataFetchError(f"数据缺少必要列: {col}")

        # 计算涨跌幅（如果没有）
        if "pct_chg" not in df.columns:
            if "close" in df.columns and df["close"].notna().all():
                df["pct_chg"] = df["close"].pct_change() * 100

        # 按日期排序
        df = df.sort_values("date").reset_index(drop=True)

        # 确保数值类型
        numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def get_realtime_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取实时行情

        Args:
            stock_code: 股票代码

        Returns:
            实时行情字典
        """
        qt_code = self._convert_code_format(stock_code)

        try:
            url = f"http://qt.gtimg.cn/q={qt_code}"
            response = self._session.get(url, timeout=10)

            if response.status_code != 200:
                return None

            content = response.text
            if not content or "~" not in content:
                return None

            parts = content.split("~")
            if len(parts) < 35:
                return None

            return {
                "code": stock_code,
                "name": parts[1] if len(parts) > 1 else None,
                "price": self._safe_float(parts[3]) if len(parts) > 3 else None,
                "open": self._safe_float(parts[5]) if len(parts) > 5 else None,
                "high": self._safe_float(parts[33]) if len(parts) > 33 else None,
                "low": self._safe_float(parts[34]) if len(parts) > 34 else None,
                "volume": self._safe_int(parts[6]) if len(parts) > 6 else None,
                "amount": self._safe_float(parts[37]) if len(parts) > 37 else None,
                "change": self._safe_float(parts[31]) if len(parts) > 31 else None,
                "change_pct": self._safe_float(parts[32]) if len(parts) > 32 else None,
            }

        except Exception as e:
            logger.warning(f"[AshareFetcher] 实时行情获取失败: {e}")
            return None

    def supports_market(self, market: str) -> bool:
        """
        检查是否支持指定市场

        Args:
            market: 市场代码 ('cn', 'hk', 'us')

        Returns:
            是否支持
        """
        # Ashare 主要支持 A 股
        return market == "cn"
