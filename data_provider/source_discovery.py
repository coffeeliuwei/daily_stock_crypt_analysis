# -*- coding: utf-8 -*-
"""
===================================
动态数据源发现模块
===================================

功能：
1. 启动时搜索网络中的免费数据源
2. 自动检测新发现的数据源是否可用
3. 可用的数据源自动加入数据源池

使用方式：
    from data_provider.source_discovery import SourceDiscovery

    discovery = SourceDiscovery()
    new_sources = discovery.discover_and_test()
    for source in new_sources:
        print(f"发现新数据源: {source.name}")
"""

import importlib
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

from .source_health_checker import (
    SourceHealthChecker,
    HealthCheckResult,
    HealthCheckConfig,
    SourceStatus,
)
from .base import BaseFetcher

logger = logging.getLogger(__name__)


class DiscoveryStatus(Enum):
    """发现状态"""

    DISCOVERED = "discovered"  # 已发现
    INSTALLED = "installed"  # 已安装
    AVAILABLE = "available"  # 可用
    UNAVAILABLE = "unavailable"  # 不可用
    ERROR = "error"  # 错误


@dataclass
class DiscoveredSource:
    """发现的数据源"""

    name: str  # 数据源名称
    package_name: str  # pip 包名
    description: str  # 描述
    status: DiscoveryStatus  # 状态
    is_free: bool = True  # 是否免费
    requires_api_key: bool = False  # 是否需要 API Key
    supports_a_share: bool = True  # 是否支持 A 股
    supports_hk: bool = False  # 是否支持港股
    supports_us: bool = False  # 是否支持美股
    install_command: str = ""  # 安装命令
    import_path: str = ""  # 导入路径
    fetcher_class: str = ""  # Fetcher 类名
    priority: int = 99  # 优先级
    latency_ms: float = 0.0  # 响应时间
    error_message: Optional[str] = None  # 错误信息
    timestamp: str = ""  # 发现时间

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.install_command:
            self.install_command = f"pip install {self.package_name}"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "package_name": self.package_name,
            "description": self.description,
            "status": self.status.value,
            "is_free": self.is_free,
            "requires_api_key": self.requires_api_key,
            "supports_a_share": self.supports_a_share,
            "supports_hk": self.supports_hk,
            "supports_us": self.supports_us,
            "install_command": self.install_command,
            "priority": self.priority,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
        }


@dataclass
class DiscoveryConfig:
    """发现配置"""

    auto_install: bool = False  # 是否自动安装新数据源
    test_on_discover: bool = True  # 发现后是否测试
    timeout_seconds: float = 10.0  # 测试超时时间
    max_sources: int = 20  # 最大发现数量
    include_paid: bool = False  # 是否包含付费数据源


# 已知的开源数据源列表（注册表）
KNOWN_SOURCES: List[Dict[str, Any]] = [
    # 免费数据源
    {
        "name": "FinshareFetcher",
        "package_name": "finshare",
        "description": "多源聚合数据源（东财/腾讯/新浪/通达信/Baostock）",
        "is_free": True,
        "requires_api_key": False,
        "supports_a_share": True,
        "supports_hk": True,
        "supports_us": True,
        "import_path": "data_provider.finshare_fetcher",
        "fetcher_class": "FinshareFetcher",
        "priority": 1,
    },
    {
        "name": "AkshareFetcher",
        "package_name": "akshare",
        "description": "AkShare 开源财经数据接口",
        "is_free": True,
        "requires_api_key": False,
        "supports_a_share": True,
        "supports_hk": True,
        "supports_us": False,
        "import_path": "data_provider.akshare_fetcher",
        "fetcher_class": "AkshareFetcher",
        "priority": 1,
    },
    {
        "name": "EfinanceFetcher",
        "package_name": "efinance",
        "description": "东方财富数据源",
        "is_free": True,
        "requires_api_key": False,
        "supports_a_share": True,
        "supports_hk": True,
        "supports_us": False,
        "import_path": "data_provider.efinance_fetcher",
        "fetcher_class": "EfinanceFetcher",
        "priority": 0,
    },
    {
        "name": "PytdxFetcher",
        "package_name": "pytdx",
        "description": "通达信数据源",
        "is_free": True,
        "requires_api_key": False,
        "supports_a_share": True,
        "supports_hk": False,
        "supports_us": False,
        "import_path": "data_provider.pytdx_fetcher",
        "fetcher_class": "PytdxFetcher",
        "priority": 2,
    },
    {
        "name": "BaostockFetcher",
        "package_name": "baostock",
        "description": "Baostock 证券宝数据源",
        "is_free": True,
        "requires_api_key": False,
        "supports_a_share": True,
        "supports_hk": False,
        "supports_us": False,
        "import_path": "data_provider.baostock_fetcher",
        "fetcher_class": "BaostockFetcher",
        "priority": 3,
    },
    {
        "name": "YfinanceFetcher",
        "package_name": "yfinance",
        "description": "Yahoo Finance 数据源（美股优先）",
        "is_free": True,
        "requires_api_key": False,
        "supports_a_share": False,
        "supports_hk": True,
        "supports_us": True,
        "import_path": "data_provider.yfinance_fetcher",
        "fetcher_class": "YfinanceFetcher",
        "priority": 4,
    },
    # 需要 API Key 的数据源
    {
        "name": "TushareFetcher",
        "package_name": "tushare",
        "description": "Tushare Pro 数据源（需 Token）",
        "is_free": False,
        "requires_api_key": True,
        "supports_a_share": True,
        "supports_hk": False,
        "supports_us": False,
        "import_path": "data_provider.tushare_fetcher",
        "fetcher_class": "TushareFetcher",
        "priority": 2,
    },
    {
        "name": "QVerisFetcher",
        "package_name": "qveris",
        "description": "QVeris 统一 API 网关",
        "is_free": True,
        "requires_api_key": True,
        "supports_a_share": True,
        "supports_hk": True,
        "supports_us": True,
        "import_path": "data_provider.qveris_fetcher",
        "fetcher_class": "QVerisFetcher",
        "priority": 2,
    },
    # 新增外部数据源（待集成）
    {
        "name": "FinnhubFetcher",
        "package_name": "finnhub-python",
        "description": "Finnhub 美股数据源（60次/分钟免费）",
        "is_free": True,
        "requires_api_key": True,
        "supports_a_share": False,
        "supports_hk": False,
        "supports_us": True,
        "import_path": "",  # 待实现
        "fetcher_class": "FinnhubFetcher",
        "priority": 5,
    },
    {
        "name": "AllTickFetcher",
        "package_name": "alltick",
        "description": "AllTick 全球市场数据（10次/分钟免费）",
        "is_free": True,
        "requires_api_key": True,
        "supports_a_share": True,
        "supports_hk": True,
        "supports_us": True,
        "import_path": "",  # 待实现
        "fetcher_class": "AllTickFetcher",
        "priority": 6,
    },
]


class SourceDiscovery:
    """
    动态数据源发现器

    功能：
    1. 扫描已注册的数据源
    2. 检测 pip 包是否安装
    3. 测试数据源可用性
    4. 返回可用的数据源列表
    """

    def __init__(self, config: Optional[DiscoveryConfig] = None):
        """
        初始化发现器

        Args:
            config: 发现配置
        """
        self.config = config or DiscoveryConfig()
        self._discovered: Dict[str, DiscoveredSource] = {}
        self._health_checker = SourceHealthChecker()

    def scan_registered_sources(self) -> List[DiscoveredSource]:
        """
        扫描已注册的数据源

        Returns:
            发现的数据源列表
        """
        results: List[DiscoveredSource] = []

        for source_info in KNOWN_SOURCES:
            # 跳过付费数据源（如果配置不允许）
            if not self.config.include_paid and not source_info.get("is_free", True):
                continue

            source = DiscoveredSource(
                name=source_info["name"],
                package_name=source_info["package_name"],
                description=source_info["description"],
                status=DiscoveryStatus.DISCOVERED,
                is_free=source_info.get("is_free", True),
                requires_api_key=source_info.get("requires_api_key", False),
                supports_a_share=source_info.get("supports_a_share", True),
                supports_hk=source_info.get("supports_hk", False),
                supports_us=source_info.get("supports_us", False),
                import_path=source_info.get("import_path", ""),
                fetcher_class=source_info.get("fetcher_class", ""),
                priority=source_info.get("priority", 99),
            )

            # 检查包是否已安装
            if self._check_package_installed(source.package_name):
                source.status = DiscoveryStatus.INSTALLED

            self._discovered[source.name] = source
            results.append(source)

        logger.info(f"[SourceDiscovery] 扫描完成，发现 {len(results)} 个数据源")
        return results

    def _check_package_installed(self, package_name: str) -> bool:
        """
        检查 pip 包是否已安装

        Args:
            package_name: 包名

        Returns:
            是否已安装
        """
        try:
            # 标准化包名（pip show 使用 - 而不是 _）
            normalized = package_name.replace("-", "_").replace(".", "_")
            importlib.import_module(normalized)
            return True
        except ImportError:
            # 尝试原始名称
            try:
                importlib.import_module(package_name)
                return True
            except ImportError:
                return False

    def test_discovered_sources(
        self, sources: Optional[List[DiscoveredSource]] = None
    ) -> List[DiscoveredSource]:
        """
        测试发现的数据源

        Args:
            sources: 要测试的数据源列表，None 表示测试所有

        Returns:
            测试结果列表
        """
        if sources is None:
            sources = list(self._discovered.values())

        results: List[DiscoveredSource] = []

        for source in sources:
            if source.status == DiscoveryStatus.INSTALLED:
                # 使用健康检测器测试
                health_result = self._health_checker.check_single(source.name)
                source.latency_ms = health_result.latency_ms
                source.error_message = health_result.error_message

                if health_result.available:
                    source.status = DiscoveryStatus.AVAILABLE
                else:
                    source.status = DiscoveryStatus.UNAVAILABLE

            results.append(source)
            self._discovered[source.name] = source

        available_count = sum(
            1 for s in results if s.status == DiscoveryStatus.AVAILABLE
        )
        logger.info(
            f"[SourceDiscovery] 测试完成: {available_count}/{len(results)} 个数据源可用"
        )

        return results

    def discover_and_test(self) -> List[DiscoveredSource]:
        """
        发现并测试数据源（主入口）

        Returns:
            可用的数据源列表
        """
        # Step 1: 扫描已注册的数据源
        sources = self.scan_registered_sources()

        # Step 2: 测试数据源
        if self.config.test_on_discover:
            sources = self.test_discovered_sources(sources)

        # Step 3: 返回可用的数据源
        available = [s for s in sources if s.status == DiscoveryStatus.AVAILABLE]

        return available

    def install_source(self, source: DiscoveredSource) -> bool:
        """
        安装数据源包

        Args:
            source: 数据源信息

        Returns:
            是否安装成功
        """
        if source.status == DiscoveryStatus.INSTALLED:
            return True

        try:
            logger.info(f"[SourceDiscovery] 正在安装 {source.package_name}...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", source.package_name, "-q"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                source.status = DiscoveryStatus.INSTALLED
                logger.info(f"[SourceDiscovery] {source.package_name} 安装成功")
                return True
            else:
                source.status = DiscoveryStatus.ERROR
                source.error_message = (
                    result.stderr[:200] if result.stderr else "安装失败"
                )
                logger.warning(
                    f"[SourceDiscovery] {source.package_name} 安装失败: {source.error_message}"
                )
                return False

        except Exception as e:
            source.status = DiscoveryStatus.ERROR
            source.error_message = str(e)[:200]
            logger.error(f"[SourceDiscovery] 安装异常: {e}")
            return False

    def get_available_sources(self) -> List[DiscoveredSource]:
        """获取可用的数据源列表"""
        return [
            s
            for s in self._discovered.values()
            if s.status == DiscoveryStatus.AVAILABLE
        ]

    def get_unavailable_sources(self) -> List[DiscoveredSource]:
        """获取不可用的数据源列表"""
        return [
            s
            for s in self._discovered.values()
            if s.status != DiscoveryStatus.AVAILABLE
        ]

    def get_discovery_report(self) -> Dict[str, Any]:
        """获取发现报告"""
        sources = list(self._discovered.values())

        return {
            "timestamp": datetime.now().isoformat(),
            "total_discovered": len(sources),
            "installed_count": sum(
                1 for s in sources if s.status == DiscoveryStatus.INSTALLED
            ),
            "available_count": sum(
                1 for s in sources if s.status == DiscoveryStatus.AVAILABLE
            ),
            "unavailable_count": sum(
                1 for s in sources if s.status == DiscoveryStatus.UNAVAILABLE
            ),
            "sources": [s.to_dict() for s in sources],
        }


def discover_data_sources(
    auto_install: bool = False,
    test_on_discover: bool = True,
) -> List[DiscoveredSource]:
    """
    发现数据源（便捷函数）

    Args:
        auto_install: 是否自动安装
        test_on_discover: 是否测试

    Returns:
        可用的数据源列表
    """
    config = DiscoveryConfig(
        auto_install=auto_install,
        test_on_discover=test_on_discover,
    )
    discovery = SourceDiscovery(config)
    return discovery.discover_and_test()


# ========================================
# 启动时数据源检测入口
# ========================================


def startup_source_check(
    verbose: bool = True,
    install_missing: bool = False,
) -> Dict[str, Any]:
    """
    启动时检测数据源（主入口）

    这个函数应该在项目启动时调用，用于：
    1. 检测所有已注册的数据源
    2. 测试数据源可用性
    3. 返回健康状态报告

    Args:
        verbose: 是否打印详细信息
        install_missing: 是否自动安装缺失的数据源

    Returns:
        检测报告
    """
    start_time = time.time()

    if verbose:
        logger.info("=" * 50)
        logger.info("开始检测数据源...")
        logger.info("=" * 50)

    # 创建发现器
    config = DiscoveryConfig(auto_install=install_missing)
    discovery = SourceDiscovery(config)

    # 发现并测试
    available = discovery.discover_and_test()

    # 获取报告
    report = discovery.get_discovery_report()
    report["elapsed_seconds"] = round(time.time() - start_time, 2)

    if verbose:
        logger.info("-" * 50)
        logger.info(f"数据源检测完成，耗时 {report['elapsed_seconds']} 秒")
        logger.info(f"  已发现: {report['total_discovered']} 个")
        logger.info(f"  已安装: {report['installed_count']} 个")
        logger.info(f"  可用: {report['available_count']} 个")
        logger.info(f"  不可用: {report['unavailable_count']} 个")

        if available:
            logger.info("可用数据源:")
            for source in available:
                logger.info(
                    f"  - {source.name} (P{source.priority}, {source.latency_ms:.0f}ms)"
                )

        unavailable = discovery.get_unavailable_sources()
        if unavailable:
            logger.info("不可用数据源:")
            for source in unavailable:
                reason = source.error_message or "未安装"
                logger.info(f"  - {source.name}: {reason}")

        logger.info("=" * 50)

    return report
