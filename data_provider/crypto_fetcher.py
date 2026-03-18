# -*- coding: utf-8 -*-
"""
===================================
CryptoFetcher - 加密货币数据源 (Priority 1)
===================================

数据来源：CCXT 库（默认使用 Binance 公开 API）
特点：免费、无需 API Key、支持主流加密货币
定位：为系统添加 BTC、ETH 等加密货币的数据支持

关键策略：
1. 自动将 BTC、ETH 等符号转换为 CCXT 格式（BTC/USDT）
2. 支持 K 线数据和实时行情
3. 支持多个交易所切换
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
    'BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'DOT', 'MATIC',
    'LTC', 'SHIB', 'AVAX', 'LINK', 'ATOM', 'UNI', 'XMR', 'ETC', 'BCH',
    'NEAR', 'APT', 'ARB', 'OP', 'INJ', 'FIL', 'VET', 'HBAR', 'ICP',
]

# 加密货币名称映射
CRYPTO_NAMES = {
    'BTC': 'Bitcoin',
    'ETH': 'Ethereum',
    'BNB': 'BNB',
    'SOL': 'Solana',
    'XRP': 'XRP',
    'ADA': 'Cardano',
    'DOGE': 'Dogecoin',
    'DOT': 'Polkadot',
    'MATIC': 'Polygon',
    'LTC': 'Litecoin',
    'SHIB': 'Shiba Inu',
    'AVAX': 'Avalanche',
    'LINK': 'Chainlink',
    'ATOM': 'Cosmos',
    'UNI': 'Uniswap',
}


class CryptoFetcher(BaseFetcher):
    """
    加密货币数据源实现
    
    优先级：1（高优先级）
    数据来源：CCXT（默认 Binance）
    
    关键策略：
    - 自动转换加密货币代码格式（BTC -> BTC/USDT）
    - 支持历史 K 线数据获取
    - 支持实时行情
    
    注意事项：
    - 需要安装 ccxt 库：pip install ccxt
    - 默认使用 Binance 公开 API，无需 API Key
    """

    name = "CryptoFetcher"
    priority = int(os.getenv("CRYPTO_PRIORITY", "1"))

    def __init__(self, exchange: str = "binance"):
        """
        初始化 CryptoFetcher
        
        Args:
            exchange: 交易所名称，默认 binance
                      支持：binance, coinbase, kraken, okx 等
        """
        self.exchange_name = exchange
        self._exchange = None
        self._ccxt = None
        
    def _get_ccxt(self):
        """延迟加载 CCXT 库"""
        if self._ccxt is None:
            try:
                import ccxt
                self._ccxt = ccxt
            except ImportError:
                raise DataFetchError(
                    "CCXT 库未安装，请运行: pip install ccxt"
                )
        return self._ccxt
    
    def _get_exchange(self):
        """获取交易所实例"""
        if self._exchange is None:
            ccxt = self._get_ccxt()
            exchange_class = getattr(ccxt, self.exchange_name, None)
            if exchange_class is None:
                raise DataFetchError(
                    f"不支持的交易所: {self.exchange_name}"
                )
            self._exchange = exchange_class({
                'enableRateLimit': True,
                'timeout': 30000,
            })
        return self._exchange
    
    def _to_ccxt_symbol(self, stock_code: str) -> str:
        """
        转换加密货币代码为 CCXT 格式
        
        BTC -> BTC/USDT
        BTC-USD -> BTC/USDT
        BTCUSDT -> BTC/USDT
        """
        code = stock_code.strip().upper()
        
        # 已经是 CCXT 格式
        if '/' in code:
            return code
        
        # 移除常见后缀
        for suffix in ['USDT', 'USDC', 'USD', 'BUSD']:
            if code.endswith(suffix):
                code = code[:-len(suffix)]
                break
        
        # 移除连字符
        code = code.replace('-', '')
        
        return f"{code}/USDT"
    
    def _extract_base_symbol(self, stock_code: str) -> str:
        """提取基础符号（如 BTC/USDT -> BTC）"""
        ccxt_symbol = self._to_ccxt_symbol(stock_code)
        return ccxt_symbol.split('/')[0]

    def _fetch_raw_data(
        self,
        stock_code: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        从 CCXT 获取原始 K 线数据
        
        Args:
            stock_code: 加密货币代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            DataFrame: 原始 K 线数据
        """
        exchange = self._get_exchange()
        symbol = self._to_ccxt_symbol(stock_code)
        
        logger.debug(f"[CryptoFetcher] 获取 {symbol} K线数据: {start_date} ~ {end_date}")
        
        try:
            # 转换日期为时间戳
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
            
            all_ohlcv = []
            current_ts = start_ts
            
            # CCXT 每次最多返回 1000 条，需要分批获取
            while current_ts < end_ts:
                ohlcv = exchange.fetch_ohlcv(
                    symbol,
                    timeframe='1d',
                    since=current_ts,
                    limit=1000
                )
                
                if not ohlcv:
                    break
                    
                all_ohlcv.extend(ohlcv)
                
                # 更新时间戳到最后一条数据的时间
                last_ts = ohlcv[-1][0]
                if last_ts <= current_ts:
                    break
                current_ts = last_ts + 86400000  # 加一天
                
                # 避免请求过快
                time.sleep(0.1)
            
            if not all_ohlcv:
                raise DataFetchError(f"未获取到 {symbol} 的数据")
            
            # 转换为 DataFrame
            df = pd.DataFrame(
                all_ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # 过滤日期范围
            df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
            
            return df
            
        except Exception as e:
            if isinstance(e, DataFetchError):
                raise
            raise DataFetchError(f"获取加密货币数据失败: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化加密货币数据
        
        CCXT 返回格式：timestamp, open, high, low, close, volume
        
        标准格式：date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 转换日期格式
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        
        # 计算涨跌幅
        df['pct_chg'] = df['close'].pct_change() * 100
        df['pct_chg'] = df['pct_chg'].fillna(0).round(2)
        
        # 计算成交额（CCXT 只有成交量，用 close * volume 估算）
        df['amount'] = df['close'] * df['volume']
        
        # 添加代码列
        df['code'] = stock_code
        
        # 只保留标准列
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取加密货币实时行情
        
        Args:
            stock_code: 加密货币代码（如 BTC, ETH）
            
        Returns:
            UnifiedRealtimeQuote: 统一格式的实时行情
        """
        if not _is_crypto_code(stock_code):
            return None
            
        try:
            exchange = self._get_exchange()
            symbol = self._to_ccxt_symbol(stock_code)
            base_symbol = self._extract_base_symbol(stock_code)
            
            logger.debug(f"[CryptoFetcher] 获取 {symbol} 实时行情")
            
            # 获取 ticker 数据
            ticker = exchange.fetch_ticker(symbol)
            
            # 获取最近两天的 K 线计算涨跌幅
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=2)
            
            prev_close = None
            if len(ohlcv) >= 2:
                prev_close = ohlcv[-2][4]  # 前一天的收盘价
            
            current_price = ticker.get('last', ticker.get('close', 0))
            
            # 计算涨跌幅
            change_pct = None
            change_amount = None
            if prev_close and prev_close > 0:
                change_amount = current_price - prev_close
                change_pct = (change_amount / prev_close) * 100
            
            # 获取名称
            name = CRYPTO_NAMES.get(base_symbol, base_symbol)
            
            return UnifiedRealtimeQuote(
                code=stock_code.upper(),
                name=name,
                source=RealtimeSource.CRYPTO,
                price=current_price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=int(ticker.get('baseVolume', 0) or 0),
                amount=ticker.get('quoteVolume'),  # USDT 计价的成交额
                volume_ratio=None,
                turnover_rate=None,
                amplitude=None,
                open_price=ticker.get('open'),
                high=ticker.get('high'),
                low=ticker.get('low'),
                pre_close=prev_close,
                pe_ratio=None,
                pb_ratio=None,
                total_mv=ticker.get('marketCap'),
                circ_mv=None,
            )
            
        except Exception as e:
            logger.warning(f"[CryptoFetcher] 获取 {stock_code} 实时行情失败: {e}")
            return None

    def get_supported_cryptos(self) -> List[str]:
        """获取支持的加密货币列表"""
        return DEFAULT_CRYPTO_SYMBOLS.copy()

    def get_crypto_trending(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取热门加密货币行情
        
        Args:
            limit: 返回数量
            
        Returns:
            List[Dict]: 加密货币行情列表
        """
        results = []
        for symbol in DEFAULT_CRYPTO_SYMBOLS[:limit]:
            quote = self.get_realtime_quote(symbol)
            if quote:
                results.append(quote.to_dict())
        return results


# 用于测试
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = CryptoFetcher()
    
    # 测试实时行情
    print("\n=== BTC 实时行情 ===")
    quote = fetcher.get_realtime_quote('BTC')
    if quote:
        print(f"价格: ${quote.price:,.2f}")
        print(f"涨跌: {quote.change_pct}%")
    
    # 测试 K 线数据
    print("\n=== BTC K线数据 ===")
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    df = fetcher.get_daily_data('BTC', start_date=start_date, end_date=end_date)
    if not df.empty:
        print(df.tail())