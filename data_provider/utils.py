# -*- coding: utf-8 -*-
"""
===================================
数据源工具函数
===================================

包含股票代码标准化、市场判断、异常处理等工具函数。
"""

import functools
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# === 标准化列名定义 ===
STANDARD_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pct_chg",
]

# ETF 代码前缀
ETF_PREFIXES = ("51", "52", "56", "58", "15", "16", "18")

# 支持的加密货币符号（不含报价货币的基础符号）
# 这是白名单用于快速匹配，不是完整列表
CRYPTO_SYMBOLS = {
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "ADA",
    "DOGE",
    "DOT",
    "MATIC",
    "LTC",
    "SHIB",
    "AVAX",
    "LINK",
    "ATOM",
    "UNI",
    "XMR",
    "ETC",
    "BCH",
    "NEAR",
    "APT",
    "ARB",
    "OP",
    "INJ",
    "FIL",
    "HBAR",
    "ICP",
    "SUI",
    "SEI",
    "TIA",
    "IMX",
    "RNDR",
    "FET",
    "GRT",
    "ALGO",
    "MANA",
    "SAND",
    "AAVE",
    "MKR",
    "SNX",
    "CRV",
    "LDO",
    "BLUR",
    "APE",
    "AXS",
    "GALA",
    "ENJ",
    "COMP",
    "YFI",
    "SUSHI",
    "1INCH",
    "CAKE",
    "VET",
    "TON",
    "WLD",
    "PEPE",
    "BONK",
    "WIF",
    "JUP",
    "PYTH",
    "ONDO",
}

# 加密货币交易对后缀
CRYPTO_QUOTE_SUFFIXES = ("USDT", "USDC", "USD", "BUSD", "EUR", "BTC", "ETH", "BNB")


def unwrap_exception(exc: Exception) -> Exception:
    """
    Follow chained exceptions and return the deepest non-cyclic cause.

    Args:
        exc: 原始异常

    Returns:
        最深层的异常原因
    """
    current = exc
    visited = set()

    while current is not None and id(current) not in visited:
        visited.add(id(current))
        next_exc = current.__cause__ or current.__context__
        if next_exc is None:
            break
        current = next_exc

    return current


def summarize_exception(exc: Exception) -> Tuple[str, str]:
    """
    Build a stable summary for logs while preserving the application-layer message.

    Args:
        exc: 原始异常

    Returns:
        (错误类型, 错误消息) 元组
    """
    root = unwrap_exception(exc)
    error_type = type(root).__name__
    message = str(exc).strip() or str(root).strip() or error_type
    return error_type, " ".join(message.split())


def normalize_stock_code(stock_code: str) -> str:
    """
    Normalize stock code by stripping exchange prefixes/suffixes.

    Accepted formats and their normalized results:
    - '600519'      -> '600519'   (already clean)
    - 'SH600519'    -> '600519'   (strip SH prefix)
    - 'SZ000001'    -> '000001'   (strip SZ prefix)
    - 'BJ920748'    -> '920748'   (strip BJ prefix, BSE)
    - 'sh600519'    -> '600519'   (case-insensitive)
    - '600519.SH'   -> '600519'   (strip .SH suffix)
    - '000001.SZ'   -> '000001'   (strip .SZ suffix)
    - '920748.BJ'   -> '920748'   (strip .BJ suffix, BSE)
    - 'HK00700'     -> 'HK00700'  (keep HK prefix for HK stocks)
    - '1810.HK'     -> 'HK01810'  (normalize HK suffix to canonical prefix form)
    - 'AAPL'        -> 'AAPL'     (keep US stock ticker as-is)

    This function is applied at the DataProviderManager layer so that
    all individual fetchers receive a clean 6-digit code (for A-shares/ETFs).

    Args:
        stock_code: 原始股票代码

    Returns:
        标准化后的股票代码
    """
    code = stock_code.strip()
    upper = code.upper()

    # Normalize HK prefix to a canonical 5-digit form (e.g. hk1810 -> HK01810)
    if upper.startswith("HK") and not upper.startswith("HK."):
        candidate = upper[2:]
        if candidate.isdigit() and 1 <= len(candidate) <= 5:
            return f"HK{candidate.zfill(5)}"

    # Strip SH/SZ prefix (e.g. SH600519 -> 600519)
    if (
        upper.startswith(("SH", "SZ"))
        and not upper.startswith("SH.")
        and not upper.startswith("SZ.")
    ):
        candidate = code[2:]
        # Only strip if the remainder looks like a valid numeric code
        if candidate.isdigit() and len(candidate) in (5, 6):
            return candidate

    # Strip BJ prefix (e.g. BJ920748 -> 920748)
    if upper.startswith("BJ") and not upper.startswith("BJ."):
        candidate = code[2:]
        if candidate.isdigit() and len(candidate) == 6:
            return candidate

    # Strip .SH/.SZ/.BJ suffix (e.g. 600519.SH -> 600519, 920748.BJ -> 920748)
    if "." in code:
        base, suffix = code.rsplit(".", 1)
        if suffix.upper() == "HK" and base.isdigit() and 1 <= len(base) <= 5:
            return f"HK{base.zfill(5)}"
        if suffix.upper() in ("SH", "SZ", "SS", "BJ") and base.isdigit():
            return base

    return code


def _is_crypto_code(code: str) -> bool:
    """
    Detect cryptocurrency symbols with flexible matching.

    Detection strategy (in order):
    1. Direct match in known crypto whitelist (fast path)
    2. Has crypto trading pair suffix (e.g., BTCUSDT, ETH-USD)
    3. Unknown symbol with crypto suffix pattern

    This approach is inclusive - it's better to route a stock to crypto handler
    (which will fail gracefully) than to route a crypto to stock handler
    (which might return wrong data like ETF).

    Args:
        code: Stock/asset code to check

    Returns:
        True if the code appears to be a cryptocurrency symbol
    """
    if not code:
        return False

    normalized = code.strip().upper()

    # Remove common separators first
    base = normalized.replace("-", "").replace("/", "").replace("_", "")

    # Fast path 1: Direct match in known crypto whitelist
    if base in CRYPTO_SYMBOLS:
        return True

    # Fast path 2: Has crypto trading pair suffix (e.g., BTCUSDT -> BTC)
    for suffix in CRYPTO_QUOTE_SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix):
            potential_base = base[: -len(suffix)]
            if potential_base in CRYPTO_SYMBOLS:
                return True
            # Unknown base with crypto suffix - likely a new crypto
            if len(potential_base) >= 2 and potential_base.isalpha():
                return True

    # Fast path 3: Original code had crypto suffix pattern
    # e.g., BTC-USD, ETH/USDT
    original_upper = code.strip().upper()
    for suffix in ["-USDT", "-USDC", "-USD", "-BUSD", "/USDT", "/USDC", "/USD"]:
        if suffix in original_upper:
            return True

    return False


def _is_us_market(code: str) -> bool:
    """
    判断是否为美股/美股指数代码（不含中文前后缀）。

    Args:
        code: 股票代码

    Returns:
        True 如果是美股代码
    """
    from .us_index_mapping import is_us_stock_code, is_us_index_code

    normalized = (code or "").strip().upper()
    return is_us_index_code(normalized) or is_us_stock_code(normalized)


def _is_hk_market(code: str) -> bool:
    """
    判定是否为港股代码。

    支持 `HK00700` 及纯 5 位数字形式（A 股 ETF/股票常见为 6 位）。

    Args:
        code: 股票代码

    Returns:
        True 如果是港股代码
    """
    normalized = (code or "").strip().upper()
    if normalized.endswith(".HK"):
        base = normalized[:-3]
        return base.isdigit() and 1 <= len(base) <= 5
    if normalized.startswith("HK"):
        digits = normalized[2:]
        return digits.isdigit() and 1 <= len(digits) <= 5
    if normalized.isdigit() and len(normalized) == 5:
        return True
    return False


def _is_etf_code(code: str) -> bool:
    """
    判定 A 股 ETF 基金代码（保守规则）。

    Args:
        code: 股票代码

    Returns:
        True 如果是 ETF 代码
    """
    normalized = normalize_stock_code(code)
    return (
        normalized.isdigit()
        and len(normalized) == 6
        and normalized.startswith(ETF_PREFIXES)
    )


def _market_tag(code: str) -> str:
    """
    返回市场标签。

    Args:
        code: 股票代码

    Returns:
        市场标签: cn/us/hk/crypto
    """
    if _is_crypto_code(code):
        return "crypto"
    if _is_us_market(code):
        return "us"
    if _is_hk_market(code):
        return "hk"
    return "cn"


def is_bse_code(code: str) -> bool:
    """
    Check if the code is a Beijing Stock Exchange (BSE) A-share code.

    BSE rules:
    - Old format (pre-2024): 8xxxxx (e.g. 838163), 4xxxxx (e.g. 430047)
    - New format (2024+, post full migration Oct 2025): 920xxx+
    Note: 900xxx are Shanghai B-shares, NOT BSE — must return False.

    Args:
        code: 股票代码

    Returns:
        True 如果是北交所股票
    """
    c = (code or "").strip().split(".")[0]
    if len(c) != 6 or not c.isdigit():
        return False
    return c.startswith(("8", "4")) or c.startswith("92")


def is_st_stock(name: str) -> bool:
    """
    Check if the stock is an ST or *ST stock based on its name.

    ST stocks have special trading rules and typically a ±5% limit.

    Args:
        name: 股票名称

    Returns:
        True 如果是 ST 股票
    """
    n = (name or "").upper()
    return "ST" in n


def is_kc_cy_stock(code: str) -> bool:
    """
    Check if the stock is a STAR Market (科创板) or ChiNext (创业板) stock based on its code.

    - STAR Market: Codes starting with 688
    - ChiNext: Codes starting with 300
    Both have a ±20% limit.

    Args:
        code: 股票代码

    Returns:
        True 如果是科创板或创业板股票
    """
    c = (code or "").strip().split(".")[0]
    return c.startswith("688") or c.startswith("30")


def canonical_stock_code(code: str) -> str:
    """
    Return the canonical (uppercase) form of a stock code.

    This is a display/storage layer concern, distinct from normalize_stock_code
    which strips exchange prefixes. Apply at system input boundaries to ensure
    consistent case across BOT, WEB UI, API, and CLI paths (Issue #355).

    Examples:
        'aapl'    -> 'AAPL'
        'AAPL'    -> 'AAPL'
        '600519'  -> '600519'  (digits are unchanged)
        'hk00700' -> 'HK00700'

    Args:
        code: 股票代码

    Returns:
        规范化的大写股票代码
    """
    return (code or "").strip().upper()


# === TTL 缓存工具 ===


class TTLCache:
    """
    线程安全的 TTL (Time-To-Live) 缓存实现。

    用于缓存函数调用结果，减少重复网络请求和数据库查询。

    使用示例:
        cache = TTLCache(default_ttl=300)  # 5分钟缓存

        @cache.cached(key_func=lambda x: f"stock:{x}")
        def get_stock_data(code: str):
            # 昂贵的网络请求
            return fetch_from_api(code)
    """

    def __init__(self, default_ttl: int = 300):
        """
        初始化 TTL 缓存。

        Args:
            default_ttl: 默认缓存时间（秒），默认 5 分钟
        """
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值，如果过期或不存在返回 None。"""
        with self._lock:
            if key not in self._cache:
                return None
            expire_time, value = self._cache[key]
            if time.time() > expire_time:
                del self._cache[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值。"""
        with self._lock:
            expire_time = time.time() + (ttl if ttl is not None else self._default_ttl)
            self._cache[key] = (expire_time, value)

    def delete(self, key: str) -> None:
        """删除缓存值。"""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """清空所有缓存。"""
        with self._lock:
            self._cache.clear()

    def cached(
        self,
        key_func: Optional[Callable[..., str]] = None,
        ttl: Optional[int] = None,
    ) -> Callable:
        """
        装饰器：缓存函数调用结果。

        Args:
            key_func: 生成缓存键的函数，接收与被装饰函数相同的参数
            ttl: 缓存时间（秒），None 使用默认值

        Returns:
            装饰器函数
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # 生成缓存键
                if key_func:
                    cache_key = key_func(*args, **kwargs)
                else:
                    cache_key = f"{func.__name__}:{args}:{kwargs}"

                # 尝试从缓存获取
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"[TTLCache] Cache hit: {cache_key}")
                    return cached_value

                # 执行函数并缓存结果
                result = func(*args, **kwargs)
                if result is not None:
                    self.set(cache_key, result, ttl)
                    logger.debug(f"[TTLCache] Cache set: {cache_key}")
                return result

            return wrapper

        return decorator


# 全局缓存实例
# - 历史数据缓存: 1 小时
# - 筹码分布缓存: 30 分钟
# - 新闻搜索缓存: 15 分钟
GLOBAL_CACHE = TTLCache(default_ttl=300)
HISTORICAL_DATA_CACHE = TTLCache(default_ttl=3600)  # 1 小时
CHIP_DISTRIBUTION_CACHE = TTLCache(default_ttl=1800)  # 30 分钟
NEWS_CACHE = TTLCache(default_ttl=900)  # 15 分钟
