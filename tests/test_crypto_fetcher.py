# -*- coding: utf-8 -*-
"""
===================================
加密货币功能单元测试
===================================
"""

import pytest
from data_provider.base import _is_crypto_code, _market_tag, CRYPTO_SYMBOLS


class TestCryptoDetection:
    """加密货币符号检测测试"""
    
    def test_is_crypto_code_btc(self):
        """测试 BTC 符号"""
        assert _is_crypto_code('BTC') == True
        assert _is_crypto_code('btc') == True
        assert _is_crypto_code('Btc') == True
    
    def test_is_crypto_code_eth(self):
        """测试 ETH 符号"""
        assert _is_crypto_code('ETH') == True
        assert _is_crypto_code('eth') == True
    
    def test_is_crypto_code_with_suffix(self):
        """测试带后缀的符号"""
        assert _is_crypto_code('BTC-USD') == True
        assert _is_crypto_code('BTCUSDT') == True
        assert _is_crypto_code('BTC-USDT') == True
        assert _is_crypto_code('ETH-USD') == True
    
    def test_is_not_crypto_stock(self):
        """测试非加密货币符号"""
        assert _is_crypto_code('600519') == False  # A股
        assert _is_crypto_code('AAPL') == False    # 美股
        assert _is_crypto_code('hk00700') == False # 港股
    
    def test_market_tag_crypto(self):
        """测试加密货币市场标签"""
        assert _market_tag('BTC') == 'crypto'
        assert _market_tag('ETH') == 'crypto'
        assert _market_tag('BTCUSDT') == 'crypto'
    
    def test_market_tag_other(self):
        """测试其他市场标签"""
        assert _market_tag('600519') == 'cn'
        assert _market_tag('AAPL') == 'us'


class TestCryptoSymbols:
    """加密货币符号列表测试"""
    
    def test_common_symbols_exist(self):
        """测试常见符号存在"""
        assert 'BTC' in CRYPTO_SYMBOLS
        assert 'ETH' in CRYPTO_SYMBOLS
        assert 'BNB' in CRYPTO_SYMBOLS
        assert 'SOL' in CRYPTO_SYMBOLS
    
    def test_symbols_count(self):
        """测试符号数量"""
        assert len(CRYPTO_SYMBOLS) >= 20


class TestRealtimeSource:
    """实时行情数据源枚举测试"""
    
    def test_crypto_source_exists(self):
        """测试 CRYPTO 数据源存在"""
        from data_provider.realtime_types import RealtimeSource
        assert hasattr(RealtimeSource, 'CRYPTO')
        assert RealtimeSource.CRYPTO.value == 'crypto'
    
    def test_qveris_source_exists(self):
        """测试 QVERIS 数据源存在"""
        from data_provider.realtime_types import RealtimeSource
        assert hasattr(RealtimeSource, 'QVERIS')
        assert RealtimeSource.QVERIS.value == 'qveris'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])