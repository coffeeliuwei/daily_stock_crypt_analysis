# -*- coding: utf-8 -*-
"""
===================================
加密货币 API 接口
===================================

职责：
1. GET /api/v1/crypto/quote/{symbol} - 获取实时行情
2. GET /api/v1/crypto/history/{symbol} - 获取历史数据
3. GET /api/v1/crypto/trending - 获取热门加密货币
4. GET /api/v1/crypto/list - 获取支持的符号列表
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.schemas.crypto import (
    CryptoQuote,
    CryptoHistoryResponse,
    CryptoListResponse,
    CryptoTrendingResponse,
    KLineData,
)
from api.v1.schemas.common import ErrorResponse
from src.services.crypto_service import CryptoService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/quote/{symbol}",
    response_model=CryptoQuote,
    responses={
        200: {"description": "实时行情"},
        404: {"description": "加密货币不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取加密货币实时行情",
    description="获取指定加密货币的实时行情数据（价格、涨跌幅、成交量等）"
)
def get_crypto_quote(symbol: str) -> CryptoQuote:
    """
    获取加密货币实时行情
    
    Args:
        symbol: 加密货币符号（如 BTC, ETH, SOL）
        
    Returns:
        CryptoQuote: 实时行情数据
    """
    try:
        service = CryptoService()
        result = service.get_realtime_quote(symbol.upper())
        
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到加密货币 {symbol} 的行情数据"
                }
            )
        
        return CryptoQuote(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取加密货币行情失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取加密货币行情失败: {str(e)}"
            }
        )


@router.get(
    "/history/{symbol}",
    response_model=CryptoHistoryResponse,
    responses={
        200: {"description": "历史数据"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取加密货币历史数据",
    description="获取指定加密货币的历史K线数据"
)
def get_crypto_history(
    symbol: str,
    days: int = Query(30, ge=1, le=365, description="获取天数"),
    period: str = Query("daily", description="K线周期", pattern="^(daily|weekly|monthly)$")
) -> CryptoHistoryResponse:
    """
    获取加密货币历史数据
    
    Args:
        symbol: 加密货币符号
        days: 获取天数
        period: K线周期
        
    Returns:
        CryptoHistoryResponse: 历史数据
    """
    try:
        service = CryptoService()
        result = service.get_history_data(symbol.upper(), days=days, period=period)
        
        data = [
            KLineData(**item) for item in result.get("data", [])
        ]
        
        return CryptoHistoryResponse(
            symbol=result.get("symbol", symbol.upper()),
            name=result.get("name", ""),
            data=data,
            source=result.get("source"),
        )
        
    except Exception as e:
        logger.error(f"获取加密货币历史数据失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取历史数据失败: {str(e)}"
            }
        )


@router.get(
    "/trending",
    response_model=CryptoTrendingResponse,
    responses={
        200: {"description": "热门加密货币"},
    },
    summary="获取热门加密货币",
    description="获取市值最高的热门加密货币列表"
)
def get_trending_cryptos(
    limit: int = Query(10, ge=1, le=50, description="返回数量")
) -> CryptoTrendingResponse:
    """
    获取热门加密货币
    
    Args:
        limit: 返回数量
        
    Returns:
        CryptoTrendingResponse: 热门加密货币列表
    """
    try:
        service = CryptoService()
        result = service.get_trending_cryptos(limit=limit)
        
        data = [CryptoQuote(**item) for item in result]
        
        return CryptoTrendingResponse(data=data, count=len(data))
        
    except Exception as e:
        logger.error(f"获取热门加密货币失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取热门加密货币失败: {str(e)}"
            }
        )


@router.get(
    "/list",
    response_model=CryptoListResponse,
    responses={
        200: {"description": "支持的加密货币列表"},
    },
    summary="获取支持的加密货币列表",
    description="返回系统支持的加密货币符号列表"
)
def list_supported_cryptos() -> CryptoListResponse:
    """
    获取支持的加密货币列表
    
    Returns:
        CryptoListResponse: 符号列表
    """
    try:
        service = CryptoService()
        symbols = service.get_supported_symbols()
        
        return CryptoListResponse(symbols=symbols, count=len(symbols))
        
    except Exception as e:
        logger.error(f"获取加密货币列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取加密货币列表失败: {str(e)}"
            }
        )