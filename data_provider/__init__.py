# -*- coding: utf-8 -*-
"""
===================================
数据源策略层 - 包初始化
===================================

本包实现策略模式管理多个数据源，实现：
1. 统一的数据获取接口
2. 自动故障切换
3. 防封禁流控策略

数据源优先级（三层架构）：
【第一层：主数据源 - Priority 0】
- QVerisFetcher (Priority 0) - 🔥 主数据源，统一 API 网关
  - 支持股票、加密货币、外汇等多种资产
  - 需要配置 QVERIS_API_KEY

【第二层：免费数据源 - Priority 1】
- EfinanceFetcher (Priority 1) - 东方财富（免费）
- AkshareFetcher (Priority 1) - Akshare（免费）
- CryptoFetcher (Priority 1) - 加密货币（首选 QVeris，备用 CCXT）
- PytdxFetcher (Priority 2) - 通达信（免费）

【第三层：收费/兜底数据源 - Priority 3-4】
- TushareFetcher (Priority 3) - Tushare Pro（需 Token）
- BaostockFetcher (Priority 3) - Baostock（需注册）
- YfinanceFetcher (Priority 4) - Yahoo Finance（国际兜底）

提示：
- 优先级数字越小越优先
- QVerisFetcher 需配置 QVERIS_API_KEY
- CryptoFetcher 首选 QVeris API，回退到 CCXT
- 未配置 API Key 的数据源会自动降级优先级
"""

from .base import BaseFetcher, DataFetcherManager
from .qveris_fetcher import QVerisFetcher
from .efinance_fetcher import EfinanceFetcher
from .akshare_fetcher import AkshareFetcher, is_hk_stock_code
from .tushare_fetcher import TushareFetcher
from .pytdx_fetcher import PytdxFetcher
from .baostock_fetcher import BaostockFetcher
from .yfinance_fetcher import YfinanceFetcher
from .crypto_fetcher import CryptoFetcher
from .us_index_mapping import (
    is_us_index_code,
    is_us_stock_code,
    get_us_index_yf_symbol,
    US_INDEX_MAPPING,
)

__all__ = [
    "BaseFetcher",
    "DataFetcherManager",
    "QVerisFetcher",
    "EfinanceFetcher",
    "AkshareFetcher",
    "TushareFetcher",
    "PytdxFetcher",
    "BaostockFetcher",
    "YfinanceFetcher",
    "CryptoFetcher",
    "is_us_index_code",
    "is_us_stock_code",
    "is_hk_stock_code",
    "get_us_index_yf_symbol",
    "US_INDEX_MAPPING",
]
