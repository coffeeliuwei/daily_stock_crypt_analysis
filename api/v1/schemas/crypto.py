# -*- coding: utf-8 -*-
"""
===================================
加密货币 API Schema
===================================

定义加密货币相关的请求和响应模型
"""

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class CryptoQuote(BaseModel):
    """加密货币实时行情"""
    symbol: str = Field(..., description="加密货币符号")
    name: str = Field(default="", description="加密货币名称")
    current_price: Optional[float] = Field(None, description="当前价格（USDT）")
    change_percent: Optional[float] = Field(None, description="24h涨跌幅(%)")
    change: Optional[float] = Field(None, description="24h涨跌额")
    volume: Optional[float] = Field(None, description="24h成交量")
    amount: Optional[float] = Field(None, description="24h成交额（USDT）")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="24h最高价")
    low: Optional[float] = Field(None, description="24h最低价")
    prev_close: Optional[float] = Field(None, description="昨收价")
    market_cap: Optional[float] = Field(None, description="市值（USDT）")
    source: Optional[str] = Field(None, description="数据来源")
    update_time: Optional[datetime] = Field(None, description="更新时间")


class KLineData(BaseModel):
    """K线数据"""
    date: str = Field(..., description="日期")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    close: Optional[float] = Field(None, description="收盘价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    change_percent: Optional[float] = Field(None, description="涨跌幅(%)")


class CryptoHistoryResponse(BaseModel):
    """加密货币历史数据响应"""
    symbol: str = Field(..., description="加密货币符号")
    name: str = Field(default="", description="加密货币名称")
    data: List[KLineData] = Field(default=[], description="K线数据列表")
    source: Optional[str] = Field(None, description="数据来源")


class CryptoListResponse(BaseModel):
    """支持的加密货币列表响应"""
    symbols: List[str] = Field(..., description="支持的加密货币符号列表")
    count: int = Field(..., description="数量")


class CryptoTrendingResponse(BaseModel):
    """热门加密货币响应"""
    data: List[CryptoQuote] = Field(..., description="热门加密货币列表")
    count: int = Field(..., description="数量")