# -*- coding: utf-8 -*-
"""
===================================
数据源异常类
===================================

定义数据获取过程中可能出现的异常类型。
"""


class DataFetchError(Exception):
    """数据获取异常基类"""

    pass


class RateLimitError(DataFetchError):
    """API 速率限制异常"""

    pass


class DataSourceUnavailableError(DataFetchError):
    """数据源不可用异常"""

    pass
