# -*- coding: utf-8 -*-
"""
===================================
加密货币服务层
===================================

职责：
1. 获取加密货币实时行情
2. 获取历史 K 线数据
3. 获取热门加密货币列表
4. 支持多种交易所
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from data_provider import CryptoFetcher
from data_provider.realtime_types import RealtimeSource

logger = logging.getLogger(__name__)


class CryptoService:
    """
    加密货币业务服务
    
    提供加密货币相关的业务逻辑：
    - 实时行情
    - 历史数据
    - 热门币种
    """
    
    def __init__(self, exchange: str = "binance"):
        """
        初始化加密货币服务
        
        Args:
            exchange: 交易所名称，默认 binance
        """
        self._fetcher = CryptoFetcher(exchange=exchange)
    
    def get_realtime_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取实时行情
        
        Args:
            symbol: 加密货币符号（如 BTC, ETH）
            
        Returns:
            行情数据字典，失败返回 None
        """
        try:
            quote = self._fetcher.get_realtime_quote(symbol)
            if quote:
                return {
                    "symbol": quote.code,
                    "name": quote.name,
                    "current_price": quote.price,
                    "change_percent": quote.change_pct,
                    "change": quote.change_amount,
                    "volume": quote.volume,
                    "amount": quote.amount,
                    "open": quote.open_price,
                    "high": quote.high,
                    "low": quote.low,
                    "prev_close": quote.pre_close,
                    "market_cap": quote.total_mv,
                    "source": quote.source.value,
                    "update_time": datetime.now().isoformat(),
                }
            return None
        except Exception as e:
            logger.error(f"获取 {symbol} 实时行情失败: {e}")
            return None
    
    def get_history_data(
        self,
        symbol: str,
        days: int = 30,
        period: str = "daily"
    ) -> Dict[str, Any]:
        """
        获取历史 K 线数据
        
        Args:
            symbol: 加密货币符号
            days: 获取天数
            period: K 线周期（daily/weekly/monthly）
            
        Returns:
            历史数据字典
        """
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            df, source = self._fetcher.get_daily_data(
                stock_code=symbol,
                start_date=start_date,
                end_date=end_date,
                days=days
            )
            
            if df.empty:
                return {"symbol": symbol, "data": [], "error": "无数据"}
            
            data = []
            for _, row in df.iterrows():
                data.append({
                    "date": row.get("date"),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                    "change_percent": row.get("pct_chg"),
                })
            
            return {
                "symbol": symbol,
                "name": self._get_crypto_name(symbol),
                "data": data,
                "source": source,
            }
            
        except Exception as e:
            logger.error(f"获取 {symbol} 历史数据失败: {e}")
            return {"symbol": symbol, "data": [], "error": str(e)}
    
    def get_trending_cryptos(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取热门加密货币
        
        Args:
            limit: 返回数量
            
        Returns:
            热门加密货币列表
        """
        try:
            return self._fetcher.get_crypto_trending(limit=limit)
        except Exception as e:
            logger.error(f"获取热门加密货币失败: {e}")
            return []
    
    def get_supported_symbols(self) -> List[str]:
        """
        获取支持的加密货币符号列表
        
        Returns:
            符号列表
        """
        return self._fetcher.get_supported_cryptos()
    
    def _get_crypto_name(self, symbol: str) -> str:
        """获取加密货币名称"""
        from data_provider.crypto_fetcher import CRYPTO_NAMES
        return CRYPTO_NAMES.get(symbol.upper(), symbol.upper())