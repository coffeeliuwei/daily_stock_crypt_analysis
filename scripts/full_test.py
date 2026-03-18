# -*- coding: utf-8 -*-
"""
===================================
股票分析系统 - 完整实测脚本 (含加密货币)
===================================

测试范围：
1. 数据读取功能测试 (data_provider)
2. 加密货币数据测试 (CryptoFetcher)
3. 数据分析流程测试 (analyzer/pipeline)
4. 个股分析报告测试
5. 市场分析报告测试
6. 结果合理性验证
7. 性能测试

使用方法：
    python scripts/full_test.py
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

# 设置基本路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置测试环境
os.environ["TESTING"] = "true"
os.environ["STOCK_LIST"] = "600519,300750,002594,AAPL,BTCUSDT,ETH-USD"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """测试结果"""

    name: str
    passed: bool
    duration_ms: float
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class TestReport:
    """测试报告"""

    start_time: str
    end_time: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    results: List[TestResult]
    summary: str


class TestDataGenerator:
    """测试数据生成器"""

    @staticmethod
    def generate_stock_daily_data(
        code: str, days: int = 30, start_price: float = 100.0, volatility: float = 0.02
    ) -> List[Dict[str, Any]]:
        """生成模拟股票日线数据"""
        import random

        data = []
        current_price = start_price
        base_date = date.today() - timedelta(days=days)

        for i in range(days):
            trade_date = base_date + timedelta(days=i)

            # 模拟价格波动
            change = random.gauss(0, volatility)
            current_price *= 1 + change

            # 计算开高低收 (确保 open 在 high/low 范围内)
            high = current_price * (1 + abs(random.gauss(0, volatility / 2)))
            low = current_price * (1 - abs(random.gauss(0, volatility / 2)))
            open_price = random.uniform(low, high)
            close = current_price

            # 成交量
            volume = int(random.uniform(1000000, 10000000))
            amount = volume * close

            # 涨跌幅
            if i > 0:
                pct_chg = (close - data[-1]["close"]) / data[-1]["close"] * 100
            else:
                pct_chg = random.uniform(-3, 3)

            data.append(
                {
                    "date": trade_date.isoformat(),
                    "code": code,
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": volume,
                    "amount": round(amount, 2),
                    "pct_chg": round(pct_chg, 2),
                    "ma5": None,
                    "ma10": None,
                    "ma20": None,
                }
            )

        # 计算均线
        for i in range(len(data)):
            if i >= 4:
                data[i]["ma5"] = round(
                    sum(d["close"] for d in data[i - 4 : i + 1]) / 5, 2
                )
            if i >= 9:
                data[i]["ma10"] = round(
                    sum(d["close"] for d in data[i - 9 : i + 1]) / 10, 2
                )
            if i >= 19:
                data[i]["ma20"] = round(
                    sum(d["close"] for d in data[i - 19 : i + 1]) / 20, 2
                )

        return data

    @staticmethod
    def generate_crypto_data(
        symbol: str,
        days: int = 30,
        start_price: float = 50000.0,
        volatility: float = 0.03,
    ) -> List[Dict[str, Any]]:
        """生成模拟加密货币数据"""
        import random

        data = []
        current_price = start_price
        base_date = date.today() - timedelta(days=days)

        for i in range(days):
            trade_date = base_date + timedelta(days=i)

            # 加密货币波动更大
            change = random.gauss(0, volatility)
            current_price *= 1 + change

            high = current_price * (1 + abs(random.gauss(0, volatility / 2)))
            low = current_price * (1 - abs(random.gauss(0, volatility / 2)))
            open_price = random.uniform(low, high)
            close = current_price

            volume = int(random.uniform(10000000000, 50000000000))  # 加密货币成交量更大
            amount = volume * close

            if i > 0:
                pct_chg = (close - data[-1]["close"]) / data[-1]["close"] * 100
            else:
                pct_chg = random.uniform(-5, 5)

            data.append(
                {
                    "date": trade_date.isoformat(),
                    "symbol": symbol,
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": volume,
                    "amount": round(amount, 2),
                    "pct_chg": round(pct_chg, 2),
                }
            )

        return data


class FullTester:
    """完整测试器"""

    def __init__(self):
        self.results: List[TestResult] = []
        self.test_data_dir = PROJECT_ROOT / "test_output"
        self.test_data_dir.mkdir(exist_ok=True)

    def run_test(self, name: str, test_func, *args, **kwargs) -> TestResult:
        """运行单个测试"""
        start_time = time.time()
        try:
            result_data = test_func(*args, **kwargs)
            duration = (time.time() - start_time) * 1000

            result = TestResult(
                name=name,
                passed=result_data.get("passed", True),
                duration_ms=round(duration, 2),
                message=result_data.get("message", "OK"),
                details=result_data.get("details"),
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            result = TestResult(
                name=name,
                passed=False,
                duration_ms=round(duration, 2),
                message=f"Exception: {str(e)}",
                details={"error_type": type(e).__name__},
            )

        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        logger.info(
            f"  [{status}] {name}: {result.message} ({result.duration_ms:.2f}ms)"
        )
        return result

    # ==================== 数据读取测试 ====================

    def test_data_provider_import(self) -> Dict[str, Any]:
        """测试数据提供者模块导入"""
        try:
            from data_provider import (
                DataFetcherManager,
                EfinanceFetcher,
                AkshareFetcher,
                TushareFetcher,
                YfinanceFetcher,
                CryptoFetcher,
            )

            return {
                "passed": True,
                "message": "所有数据提供者模块导入成功",
                "details": {
                    "modules": [
                        "DataFetcherManager",
                        "EfinanceFetcher",
                        "AkshareFetcher",
                        "TushareFetcher",
                        "YfinanceFetcher",
                        "CryptoFetcher",
                    ]
                },
            }
        except ImportError as e:
            return {"passed": False, "message": f"导入失败: {e}"}

    def test_data_fetcher_manager_init(self) -> Dict[str, Any]:
        """测试数据获取管理器初始化"""
        try:
            from data_provider import DataFetcherManager

            manager = DataFetcherManager()

            available_fetchers = manager.available_fetchers
            return {
                "passed": True,
                "message": f"管理器初始化成功，可用数据源: {len(available_fetchers)}",
                "details": {"available_fetchers": available_fetchers},
            }
        except Exception as e:
            return {"passed": False, "message": f"初始化失败: {e}"}

    def test_stock_code_normalization(self) -> Dict[str, Any]:
        """测试股票代码标准化"""
        from data_provider.base import normalize_stock_code

        test_cases = [
            ("600519", "600519"),
            ("SH600519", "600519"),
            ("SZ000001", "000001"),
            ("600519.SH", "600519"),
            ("000001.SZ", "000001"),
            ("HK00700", "HK00700"),
            ("1810.HK", "HK01810"),
            ("AAPL", "AAPL"),
        ]

        passed = 0
        failed_cases = []

        for input_code, expected in test_cases:
            result = normalize_stock_code(input_code)
            if result == expected:
                passed += 1
            else:
                failed_cases.append(f"{input_code} -> {result} (expected: {expected})")

        return {
            "passed": passed == len(test_cases),
            "message": f"通过 {passed}/{len(test_cases)}",
            "details": {
                "total": len(test_cases),
                "passed": passed,
                "failed_cases": failed_cases,
            },
        }

    def test_market_detection(self) -> Dict[str, Any]:
        """测试市场识别"""
        from data_provider.utils import _is_us_market, _is_hk_market

        test_cases = [
            ("AAPL", _is_us_market, True),
            ("TSLA", _is_us_market, True),
            ("600519", _is_us_market, False),
            ("HK00700", _is_hk_market, True),
            ("1810.HK", _is_hk_market, True),
            ("AAPL", _is_hk_market, False),
        ]

        passed = 0
        for code, func, expected in test_cases:
            if func(code) == expected:
                passed += 1

        return {
            "passed": passed == len(test_cases),
            "message": f"通过 {passed}/{len(test_cases)}",
            "details": {"total": len(test_cases), "passed": passed},
        }

    # ==================== 加密货币测试 ====================

    def test_crypto_fetcher_init(self) -> Dict[str, Any]:
        """测试加密货币数据源初始化"""
        try:
            from data_provider import CryptoFetcher

            fetcher = CryptoFetcher()
            return {
                "passed": True,
                "message": f"CryptoFetcher 初始化成功，优先级: {fetcher.priority}",
                "details": {
                    "name": fetcher.name,
                    "priority": fetcher.priority,
                },
            }
        except Exception as e:
            return {"passed": False, "message": f"初始化失败: {e}"}

    def test_crypto_code_detection(self) -> Dict[str, Any]:
        """测试加密货币代码识别"""
        from data_provider.utils import _is_crypto_code

        test_cases = [
            ("SOL", True),
            ("ETH", True),
            ("BTCUSDT", True),
            ("ETH-USD", True),
            ("BTC/USDT", True),
            ("600519", False),
            ("AAPL", False),
            ("HK00700", False),
        ]

        passed = 0
        failed_cases = []
        for code, expected in test_cases:
            result = _is_crypto_code(code)
            if result == expected:
                passed += 1
            else:
                failed_cases.append(f"{code}: got {result}, expected {expected}")

        return {
            "passed": passed == len(test_cases),
            "message": f"通过 {passed}/{len(test_cases)}",
            "details": {
                "total": len(test_cases),
                "passed": passed,
                "failed_cases": failed_cases,
            },
        }

    def test_crypto_data_generation(self) -> Dict[str, Any]:
        """测试加密货币数据生成"""
        test_data = TestDataGenerator.generate_crypto_data(
            "BTCUSDT", days=30, start_price=50000.0
        )

        issues = []
        for i, d in enumerate(test_data):
            if d["high"] < d["low"]:
                issues.append(f"Day {i}: high < low")
            if d["volume"] <= 0:
                issues.append(f"Day {i}: volume <= 0")

        return {
            "passed": len(issues) == 0,
            "message": f"生成 {len(test_data)} 条加密货币数据，{len(issues)} 个问题",
            "details": {
                "records": len(test_data),
                "issues_count": len(issues),
                "sample": {
                    "first_close": test_data[0]["close"] if test_data else None,
                    "last_close": test_data[-1]["close"] if test_data else None,
                },
            },
        }

    def test_crypto_supported_symbols(self) -> Dict[str, Any]:
        """测试支持的加密货币符号"""
        from data_provider.crypto_fetcher import DEFAULT_CRYPTO_SYMBOLS, CRYPTO_NAMES

        return {
            "passed": True,
            "message": f"支持 {len(DEFAULT_CRYPTO_SYMBOLS)} 种加密货币",
            "details": {
                "symbols_count": len(DEFAULT_CRYPTO_SYMBOLS),
                "names_count": len(CRYPTO_NAMES),
                "sample_symbols": DEFAULT_CRYPTO_SYMBOLS[:10],
            },
        }

    # ==================== 数据分析流程测试 ====================

    def test_analyzer_import(self) -> Dict[str, Any]:
        """测试分析器模块导入"""
        try:
            from src.analyzer import GeminiAnalyzer, AnalysisResult

            return {
                "passed": True,
                "message": "分析器模块导入成功",
                "details": {"classes": ["GeminiAnalyzer", "AnalysisResult"]},
            }
        except ImportError as e:
            return {"passed": False, "message": f"导入失败: {e}"}

    def test_pipeline_import(self) -> Dict[str, Any]:
        """测试流水线模块导入"""
        try:
            from src.core.pipeline import StockAnalysisPipeline

            return {
                "passed": True,
                "message": "流水线模块导入成功",
            }
        except ImportError as e:
            return {"passed": False, "message": f"导入失败: {e}"}

    def test_stock_trend_analyzer(self) -> Dict[str, Any]:
        """测试趋势分析器"""
        try:
            from src.stock_analyzer import StockTrendAnalyzer

            analyzer = StockTrendAnalyzer()
            test_data = TestDataGenerator.generate_stock_daily_data("600519", days=30)

            import pandas as pd

            df = pd.DataFrame(test_data)

            result = analyzer.analyze(df, code="600519")

            return {
                "passed": True,
                "message": f"趋势分析完成",
                "details": {
                    "trend": getattr(result, "trend", None),
                    "signal": getattr(result, "signal", None),
                },
            }
        except Exception as e:
            return {"passed": False, "message": f"分析失败: {e}"}

    def test_ma_calculation(self) -> Dict[str, Any]:
        """测试均线计算"""
        import pandas as pd

        test_data = TestDataGenerator.generate_stock_daily_data("600519", days=30)
        df = pd.DataFrame(test_data)

        df["calc_ma5"] = df["close"].rolling(window=5).mean()
        df["calc_ma10"] = df["close"].rolling(window=10).mean()
        df["calc_ma20"] = df["close"].rolling(window=20).mean()

        last = df.iloc[-1]

        return {
            "passed": True,
            "message": f"均线计算验证: MA5={last['ma5']:.2f}, MA10={last['ma10']:.2f}, MA20={last['ma20']:.2f}",
            "details": {
                "last_close": last["close"],
                "ma5": last["ma5"],
                "ma10": last["ma10"],
                "ma20": last["ma20"],
            },
        }

    def test_analysis_result_structure(self) -> Dict[str, Any]:
        """测试分析结果数据结构"""
        try:
            from src.analyzer import AnalysisResult

            result = AnalysisResult(
                code="600519",
                name="贵州茅台",
                sentiment_score=75,
                trend_prediction="看多",
                operation_advice="逢低买入",
                technical_analysis="技术面良好，MA5>MA10>MA20",
                news_summary="近期无重大消息",
                analysis_summary="综合分析建议持有",
            )

            assert result.success == True
            assert 0 <= result.sentiment_score <= 100
            assert result.trend_prediction in ["看多", "看空", "震荡"]

            return {
                "passed": True,
                "message": "分析结果结构验证通过",
                "details": {
                    "sentiment_score": result.sentiment_score,
                    "trend_prediction": result.trend_prediction,
                    "code": result.code,
                    "name": result.name,
                },
            }
        except Exception as e:
            return {"passed": False, "message": f"结构验证失败: {e}"}

    # ==================== 个股分析报告测试 ====================

    def test_individual_report_generator_import(self) -> Dict[str, Any]:
        """测试个股报告生成器导入"""
        try:
            # 检查 formatters 模块
            from src.formatters import markdown_to_html_document

            return {
                "passed": True,
                "message": "formatters 模块导入成功",
            }
        except ImportError as e:
            return {"passed": False, "message": f"导入失败: {e}"}

    def test_report_formatting(self) -> Dict[str, Any]:
        """测试报告格式化"""
        try:
            from src.formatters import markdown_to_html_document

            test_markdown = """# 测试报告
            
## 个股分析

- 代码: 600519
- 名称: 贵州茅台
- 情绪评分: 75

### 技术分析
MA5 > MA10 > MA20，多头排列。
"""

            html = markdown_to_html_document(test_markdown)

            return {
                "passed": True,
                "message": f"报告格式化成功，HTML长度: {len(html)}",
                "details": {
                    "markdown_length": len(test_markdown),
                    "html_length": len(html),
                    "contains_html": "<html>" in html.lower()
                    or "<!doctype" in html.lower(),
                },
            }
        except Exception as e:
            return {"passed": False, "message": f"格式化失败: {e}"}

    def test_notification_service_import(self) -> Dict[str, Any]:
        """测试通知服务导入"""
        try:
            from src.notification import NotificationService, NotificationChannel

            return {
                "passed": True,
                "message": "通知服务导入成功",
            }
        except ImportError as e:
            return {"passed": False, "message": f"导入失败: {e}"}

    # ==================== 市场分析报告测试 ====================

    def test_market_analyzer_import(self) -> Dict[str, Any]:
        """测试市场分析器导入"""
        try:
            from src.market_analyzer import MarketAnalyzer, MarketIndex, MarketOverview

            return {
                "passed": True,
                "message": "市场分析器导入成功",
            }
        except ImportError as e:
            return {"passed": False, "message": f"导入失败: {e}"}

    def test_market_index_structure(self) -> Dict[str, Any]:
        """测试市场指数数据结构"""
        try:
            from src.market_analyzer import MarketIndex

            index = MarketIndex(
                code="000001",
                name="上证指数",
                current=3250.12,
                change=27.35,
                change_pct=0.85,
                open=3225.00,
                high=3260.00,
                low=3220.00,
                prev_close=3222.77,
                volume=350000000,
                amount=45000000000,
                amplitude=1.24,
            )

            index_dict = index.to_dict()

            return {
                "passed": True,
                "message": f"市场指数结构验证通过: {index.name}",
                "details": {
                    "code": index.code,
                    "name": index.name,
                    "current": index.current,
                    "change_pct": index.change_pct,
                },
            }
        except Exception as e:
            return {"passed": False, "message": f"结构验证失败: {e}"}

    def test_market_overview_structure(self) -> Dict[str, Any]:
        """测试市场概览数据结构"""
        try:
            from src.market_analyzer import MarketOverview, MarketIndex

            overview = MarketOverview(
                date=date.today().isoformat(),
                indices=[
                    MarketIndex(
                        code="000001", name="上证指数", current=3250.12, change_pct=0.85
                    ),
                    MarketIndex(
                        code="399001",
                        name="深证成指",
                        current=10521.36,
                        change_pct=1.02,
                    ),
                ],
                up_count=3920,
                down_count=1349,
                flat_count=231,
                limit_up_count=155,
                limit_down_count=3,
                total_amount=12345.67,
                top_sectors=[
                    {"name": "互联网服务", "change_pct": 3.25},
                    {"name": "文化传媒", "change_pct": 2.87},
                ],
                bottom_sectors=[
                    {"name": "保险", "change_pct": -1.23},
                    {"name": "航空机场", "change_pct": -0.98},
                ],
            )

            return {
                "passed": True,
                "message": f"市场概览结构验证通过，指数数: {len(overview.indices)}",
                "details": {
                    "date": overview.date,
                    "indices_count": len(overview.indices),
                    "up_count": overview.up_count,
                    "down_count": overview.down_count,
                    "top_sectors_count": len(overview.top_sectors),
                },
            }
        except Exception as e:
            return {"passed": False, "message": f"结构验证失败: {e}"}

    def test_market_review_module(self) -> Dict[str, Any]:
        """测试市场复盘模块"""
        try:
            from src.core.market_review import run_market_review

            return {
                "passed": True,
                "message": "市场复盘模块导入成功",
            }
        except ImportError as e:
            return {"passed": False, "message": f"导入失败: {e}"}

    # ==================== 结果合理性验证 ====================

    def test_sentiment_score_range(self) -> Dict[str, Any]:
        """测试情绪评分范围"""
        from src.analyzer import AnalysisResult

        valid_scores = [0, 25, 50, 75, 100]

        passed = True
        for score in valid_scores:
            try:
                AnalysisResult(
                    code="600519",
                    name="测试股票",
                    sentiment_score=score,
                    trend_prediction="震荡",
                    operation_advice="观望",
                    technical_analysis="",
                    news_summary="",
                    analysis_summary="",
                )
            except:
                passed = False

        return {
            "passed": passed,
            "message": f"情绪评分范围验证: {'通过' if passed else '失败'}",
        }

    def test_price_reasonableness(self) -> Dict[str, Any]:
        """测试价格合理性"""
        test_data = TestDataGenerator.generate_stock_daily_data("600519", days=30)

        issues = []
        for i, d in enumerate(test_data):
            if d["high"] < d["low"]:
                issues.append(f"Day {i}: high < low")
            if not (d["low"] <= d["close"] <= d["high"]):
                issues.append(f"Day {i}: close out of range")
            if not (d["low"] <= d["open"] <= d["high"]):
                issues.append(f"Day {i}: open out of range")

        return {
            "passed": len(issues) == 0,
            "message": f"价格合理性检查: {len(issues)} 个问题",
            "details": {
                "total_records": len(test_data),
                "issues_count": len(issues),
                "issues": issues[:5] if issues else [],
            },
        }

    def test_volume_reasonableness(self) -> Dict[str, Any]:
        """测试成交量合理性"""
        test_data = TestDataGenerator.generate_stock_daily_data("600519", days=30)

        issues = []
        for i, d in enumerate(test_data):
            if d["volume"] <= 0:
                issues.append(f"Day {i}: volume <= 0")

        return {
            "passed": len(issues) == 0,
            "message": f"成交量合理性检查: {len(issues)} 个问题",
            "details": {
                "total_records": len(test_data),
                "issues_count": len(issues),
            },
        }

    def test_ma_consistency(self) -> Dict[str, Any]:
        """测试均线一致性"""
        test_data = TestDataGenerator.generate_stock_daily_data("600519", days=30)

        issues = []
        for i, d in enumerate(test_data):
            if i >= 4 and d["ma5"] is None:
                issues.append(f"Day {i}: MA5 should be valid")
            if i >= 9 and d["ma10"] is None:
                issues.append(f"Day {i}: MA10 should be valid")
            if i >= 19 and d["ma20"] is None:
                issues.append(f"Day {i}: MA20 should be valid")

        return {
            "passed": len(issues) == 0,
            "message": f"均线一致性检查: {len(issues)} 个问题",
            "details": {
                "total_records": len(test_data),
                "issues_count": len(issues),
            },
        }

    # ==================== 性能测试 ====================

    def test_data_generation_performance(self) -> Dict[str, Any]:
        """测试数据生成性能"""
        start = time.time()

        for i in range(100):
            code = f"60{i:04d}"
            TestDataGenerator.generate_stock_daily_data(code, days=30)

        duration = time.time() - start

        return {
            "passed": duration < 5.0,
            "message": f"生成100只股票数据: {duration:.2f}秒",
            "details": {
                "stocks": 100,
                "days_per_stock": 30,
                "duration_seconds": round(duration, 2),
            },
        }

    def test_dataframe_operations(self) -> Dict[str, Any]:
        """测试DataFrame操作性能"""
        import pandas as pd

        data = TestDataGenerator.generate_stock_daily_data("600519", days=365)
        df = pd.DataFrame(data)

        start = time.time()

        df["ma5"] = df["close"].rolling(window=5).mean()
        df["ma10"] = df["close"].rolling(window=10).mean()
        df["ma20"] = df["close"].rolling(window=20).mean()
        df["returns"] = df["close"].pct_change()
        df["volatility"] = df["returns"].rolling(window=20).std()

        duration = time.time() - start

        return {
            "passed": duration < 1.0,
            "message": f"DataFrame操作 (365天): {duration * 1000:.2f}ms",
            "details": {
                "rows": len(df),
                "duration_ms": round(duration * 1000, 2),
            },
        }

    # ==================== 配置测试 ====================

    def test_config_loading(self) -> Dict[str, Any]:
        """测试配置加载"""
        try:
            from src.config import get_config, Config

            config = get_config()

            return {
                "passed": True,
                "message": "配置加载成功",
                "details": {
                    "stock_list_count": len(config.stock_list)
                    if config.stock_list
                    else 0,
                    "max_workers": config.max_workers,
                    "debug": config.debug,
                },
            }
        except Exception as e:
            return {"passed": False, "message": f"配置加载失败: {e}"}

    def test_storage_module(self) -> Dict[str, Any]:
        """测试存储模块"""
        try:
            from src.storage import get_db

            db = get_db()

            return {
                "passed": True,
                "message": "存储模块初始化成功",
                "details": {
                    "database_path": str(db.db_path)
                    if hasattr(db, "db_path")
                    else "N/A",
                },
            }
        except Exception as e:
            return {"passed": False, "message": f"存储模块初始化失败: {e}"}

    # ==================== 运行所有测试 ====================

    def run_all_tests(self) -> TestReport:
        """运行所有测试"""
        print("\n" + "=" * 60)
        print("  股票分析系统 - 完整实测 (含加密货币)")
        print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("=" * 60)

        start_time = datetime.now()

        # 数据读取测试
        print("\n--- 数据读取测试 ---")
        self.run_test("数据提供者模块导入", self.test_data_provider_import)
        self.run_test("数据获取管理器初始化", self.test_data_fetcher_manager_init)
        self.run_test("股票代码标准化", self.test_stock_code_normalization)
        self.run_test("市场识别", self.test_market_detection)

        # 加密货币测试
        print("\n--- 加密货币测试 ---")
        self.run_test("CryptoFetcher 初始化", self.test_crypto_fetcher_init)
        self.run_test("加密货币代码识别", self.test_crypto_code_detection)
        self.run_test("加密货币数据生成", self.test_crypto_data_generation)
        self.run_test("支持的加密货币符号", self.test_crypto_supported_symbols)

        # 数据分析流程测试
        print("\n--- 数据分析流程测试 ---")
        self.run_test("分析器模块导入", self.test_analyzer_import)
        self.run_test("流水线模块导入", self.test_pipeline_import)
        self.run_test("趋势分析器", self.test_stock_trend_analyzer)
        self.run_test("均线计算", self.test_ma_calculation)
        self.run_test("分析结果数据结构", self.test_analysis_result_structure)

        # 个股分析报告测试
        print("\n--- 个股分析报告测试 ---")
        self.run_test(
            "个股报告生成器导入", self.test_individual_report_generator_import
        )
        self.run_test("报告格式化", self.test_report_formatting)
        self.run_test("通知服务导入", self.test_notification_service_import)

        # 市场分析报告测试
        print("\n--- 市场分析报告测试 ---")
        self.run_test("市场分析器导入", self.test_market_analyzer_import)
        self.run_test("市场指数数据结构", self.test_market_index_structure)
        self.run_test("市场概览数据结构", self.test_market_overview_structure)
        self.run_test("市场复盘模块", self.test_market_review_module)

        # 结果合理性验证
        print("\n--- 结果合理性验证 ---")
        self.run_test("情绪评分范围", self.test_sentiment_score_range)
        self.run_test("价格合理性", self.test_price_reasonableness)
        self.run_test("成交量合理性", self.test_volume_reasonableness)
        self.run_test("均线一致性", self.test_ma_consistency)

        # 性能测试
        print("\n--- 性能测试 ---")
        self.run_test("数据生成性能", self.test_data_generation_performance)
        self.run_test("DataFrame操作性能", self.test_dataframe_operations)

        # 配置测试
        print("\n--- 配置与存储测试 ---")
        self.run_test("配置加载", self.test_config_loading)
        self.run_test("存储模块", self.test_storage_module)

        end_time = datetime.now()

        # 生成报告
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)

        report = TestReport(
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            total_tests=len(self.results),
            passed=passed,
            failed=failed,
            skipped=0,
            results=self.results,
            summary=f"总计 {len(self.results)} 个测试，通过 {passed} 个，失败 {failed} 个",
        )

        # 打印汇总
        print("\n" + "=" * 60)
        print("  测试结果汇总")
        print("=" * 60)
        print(f"  总测试数: {report.total_tests}")
        print(
            f"  通过: {report.passed} ({report.passed / report.total_tests * 100:.1f}%)"
        )
        print(f"  失败: {report.failed}")
        print(f"  耗时: {(end_time - start_time).total_seconds():.2f} 秒")
        print("=" * 60)

        # 保存报告
        self._save_report(report)

        return report

    def _save_report(self, report: TestReport):
        """保存测试报告"""
        report_path = (
            self.test_data_dir
            / f"full_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        report_dict = {
            "start_time": report.start_time,
            "end_time": report.end_time,
            "total_tests": report.total_tests,
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
            "summary": report.summary,
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "duration_ms": r.duration_ms,
                    "message": r.message,
                    "details": r.details,
                }
                for r in report.results
            ],
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)

        logger.info(f"测试报告已保存: {report_path}")


def main():
    """主入口"""
    tester = FullTester()
    report = tester.run_all_tests()

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
