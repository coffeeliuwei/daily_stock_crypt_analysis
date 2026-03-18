# -*- coding: utf-8 -*-
"""
===================================
QVerisFetcher - 主数据源 (Priority 0)
===================================

数据来源：QVeris AI API (https://qveris.ai)
特点：统一的 API 网关，支持股票、加密货币、外汇等多种资产
定位：主数据源，优先级最高

关键策略：
1. 支持 A 股、港股、美股、加密货币
2. 统一的 API 接口
3. 高可用性和稳定性

配置：
- 需要配置 QVERIS_API_KEY 环境变量
- 获取 API Key: https://qveris.ai
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
import httpx

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .realtime_types import UnifiedRealtimeQuote, RealtimeSource

logger = logging.getLogger(__name__)

# QVeris API 配置
QVERIS_BASE_URL = "https://qveris.ai/api/v1"
QVERIS_TIMEOUT = 30  # 秒


class QVerisFetcher(BaseFetcher):
    """
    QVeris 数据源实现
    
    优先级：0（最高，主数据源）
    数据来源：QVeris AI API
    
    关键策略：
    - 统一的 API 网关
    - 支持多种资产类型
    - 高可用性
    
    注意事项：
    - 需要配置 QVERIS_API_KEY 环境变量
    - 支持 A 股、港股、美股、加密货币
    """

    name = "QVerisFetcher"
    priority = 0  # 最高优先级

    def __init__(self):
        """初始化 QVerisFetcher"""
        self.api_key = os.getenv("QVERIS_API_KEY")
        self._available = bool(self.api_key)
        
        if not self.api_key:
            logger.warning(
                "[QVerisFetcher] 未配置 QVERIS_API_KEY，该数据源将不可用。"
                "请在环境变量中设置 QVERIS_API_KEY，或访问 https://qveris.ai 获取 API Key。"
            )
            # 未配置时，设置最低优先级，避免影响其他数据源
            self.priority = 99
        else:
            logger.info("[QVerisFetcher] 已配置 API Key，作为主数据源启用")

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        return self._available

    def _get_headers(self) -> Dict[str, str]:
        """获取 API 请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _search_tool(self, query: str, limit: int = 5) -> Dict:
        """
        搜索可用的工具
        
        Args:
            query: 搜索查询（如 "stock price", "crypto price"）
            limit: 返回数量限制
            
        Returns:
            搜索结果
        """
        try:
            with httpx.Client(timeout=QVERIS_TIMEOUT) as client:
                response = client.post(
                    f"{QVERIS_BASE_URL}/search",
                    headers=self._get_headers(),
                    json={"query": query, "limit": limit}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.warning(f"[QVerisFetcher] 搜索工具失败: {e}")
            return {}

    def _execute_tool(
        self,
        tool_id: str,
        search_id: str,
        parameters: Dict[str, Any],
        max_response_size: int = 20480
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
                        "max_response_size": max_response_size
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.warning(f"[QVerisFetcher] 执行工具失败: {e}")
            return {"success": False, "error_message": str(e)}

    def _fetch_raw_data(
        self,
        stock_code: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        从 QVeris 获取原始 K 线数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            DataFrame: 原始数据
        """
        if not self._available:
            raise DataFetchError("QVeris API Key 未配置")

        # 搜索股票历史数据工具
        search_result = self._search_tool("stock historical data OHLC K-line candlestick", limit=5)
        
        if not search_result.get("results"):
            raise DataFetchError(f"未找到适合的工具获取 {stock_code} 的历史数据")
        
        search_id = search_result.get("search_id", "")
        tools = search_result.get("results", [])
        
        # 尝试每个工具
        for tool in tools:
            tool_id = tool.get("tool_id")
            tool_name = tool.get("name", "")
            
            logger.debug(f"[QVerisFetcher] 尝试工具: {tool_name} ({tool_id})")
            
            # 构建参数
            params = {
                "symbol": stock_code,
                "start_date": start_date,
                "end_date": end_date,
                "interval": "daily"
            }
            
            result = self._execute_tool(tool_id, search_id, params)
            
            if result.get("success"):
                data = result.get("result", {}).get("data", {})
                
                # 尝试解析数据
                if isinstance(data, list) and len(data) > 0:
                    df = pd.DataFrame(data)
                    return df
                elif isinstance(data, dict):
                    # 可能是嵌套结构
                    for key in ["data", "items", "bars", "candles"]:
                        if key in data and isinstance(data[key], list):
                            df = pd.DataFrame(data[key])
                            return df
        
        raise DataFetchError(f"所有工具都无法获取 {stock_code} 的历史数据")

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化数据格式
        
        Args:
            df: 原始数据
            stock_code: 股票代码
            
        Returns:
            标准化后的 DataFrame
        """
        df = df.copy()
        
        # 尝试映射列名
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
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        # 计算涨跌幅
        if "close" in df.columns:
            df["pct_chg"] = df["close"].pct_change() * 100
            df["pct_chg"] = df["pct_chg"].fillna(0).round(2)
        
        # 添加代码列
        df["code"] = stock_code
        
        # 只保留标准列
        keep_cols = ["code"] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取实时行情
        
        Args:
            stock_code: 股票代码
            
        Returns:
            统一格式的实时行情
        """
        if not self._available:
            return None
        
        try:
            # 搜索实时行情工具
            search_result = self._search_tool("real-time stock price quote current", limit=5)
            
            if not search_result.get("results"):
                return None
            
            search_id = search_result.get("search_id", "")
            tools = search_result.get("results", [])
            
            for tool in tools:
                tool_id = tool.get("tool_id")
                
                params = {"symbol": stock_code}
                result = self._execute_tool(tool_id, search_id, params)
                
                if result.get("success"):
                    data = result.get("result", {}).get("data", {})
                    
                    if isinstance(data, dict):
                        return UnifiedRealtimeQuote(
                            code=stock_code,
                            name=data.get("name", ""),
                            source=RealtimeSource.QVERIS,
                            price=safe_float(data.get("price") or data.get("last") or data.get("close")),
                            change_pct=safe_float(data.get("change_pct") or data.get("changePercent")),
                            change_amount=safe_float(data.get("change") or data.get("changeAmount")),
                            volume=safe_int(data.get("volume")),
                            amount=safe_float(data.get("amount") or data.get("turnover")),
                            open_price=safe_float(data.get("open")),
                            high=safe_float(data.get("high")),
                            low=safe_float(data.get("low")),
                            pre_close=safe_float(data.get("prev_close") or data.get("previousClose")),
                        )
            
            return None
            
        except Exception as e:
            logger.warning(f"[QVerisFetcher] 获取 {stock_code} 实时行情失败: {e}")
            return None


def safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """安全转换为浮点数"""
    try:
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """安全转换为整数"""
    try:
        if val is None:
            return default
        return int(float(val))
    except (ValueError, TypeError):
        return default


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = QVerisFetcher()
    
    if fetcher.is_available():
        print("[QVerisFetcher] 数据源可用")
        
        # 测试搜索
        result = fetcher._search_tool("stock price AAPL", limit=3)
        print(f"搜索结果: {result}")
    else:
        print("[QVerisFetcher] 数据源不可用，请配置 QVERIS_API_KEY")