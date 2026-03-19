# -*- coding: utf-8 -*-
"""
Tests for notification.py to boost coverage from 29% to 60%+.

Covers:
- Channel detection methods
- Report generation methods
- Signal level calculations
- Context channel extraction
- Utility functions
"""

import os
import sys
import unittest
from unittest import mock
from typing import Optional
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock optional dependencies
for optional_module in ("litellm", "json_repair"):
    try:
        __import__(optional_module)
    except ModuleNotFoundError:
        sys.modules[optional_module] = mock.MagicMock()

from src.config import Config
from src.notification import (
    NotificationService,
    NotificationChannel,
    ChannelDetector,
)
from src.analyzer import AnalysisResult
from src.enums import ReportType
from bot.models import BotMessage


def _make_config(**overrides) -> Config:
    """Create a Config instance overriding only notification-related fields."""
    return Config(stock_list=[], **overrides)


def _make_result(**kwargs) -> AnalysisResult:
    """Create a minimal AnalysisResult for testing."""
    defaults = {
        "code": "600519",
        "name": "贵州茅台",
        "sentiment_score": 72,
        "trend_prediction": "看多",
        "operation_advice": "持有",
        "analysis_summary": "稳健",
    }
    defaults.update(kwargs)
    return AnalysisResult(**defaults)


class TestChannelDetector(unittest.TestCase):
    """Tests for ChannelDetector class."""

    def test_get_channel_name_wechat(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.WECHAT), "企业微信"
        )

    def test_get_channel_name_feishu(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.FEISHU), "飞书"
        )

    def test_get_channel_name_telegram(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.TELEGRAM), "Telegram"
        )

    def test_get_channel_name_email(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.EMAIL), "邮件"
        )

    def test_get_channel_name_pushover(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.PUSHOVER), "Pushover"
        )

    def test_get_channel_name_pushplus(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.PUSHPLUS), "PushPlus"
        )

    def test_get_channel_name_serverchan3(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.SERVERCHAN3),
            "Server酱3",
        )

    def test_get_channel_name_custom(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.CUSTOM),
            "自定义Webhook",
        )

    def test_get_channel_name_discord(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.DISCORD),
            "Discord机器人",
        )

    def test_get_channel_name_astrbot(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.ASTRBOT),
            "ASTRBOT机器人",
        )

    def test_get_channel_name_unknown(self):
        self.assertEqual(
            ChannelDetector.get_channel_name(NotificationChannel.UNKNOWN), "未知渠道"
        )


class TestNotificationServiceChannelDetection(unittest.TestCase):
    """Tests for NotificationService channel detection."""

    @mock.patch("src.notification.get_config")
    def test_detect_all_channels_empty(self, mock_get_config):
        """No channels should be detected when no config is set."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        self.assertEqual(service.get_available_channels(), [])
        self.assertFalse(service.is_available())

    @mock.patch("src.notification.get_config")
    def test_detect_wechat_channel(self, mock_get_config):
        """WeChat channel should be detected when webhook URL is set."""
        cfg = _make_config(wechat_webhook_url="https://wechat.example")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.WECHAT, service.get_available_channels())
        self.assertTrue(service.is_available())

    @mock.patch("src.notification.get_config")
    def test_detect_feishu_channel(self, mock_get_config):
        """Feishu channel should be detected when webhook URL is set."""
        cfg = _make_config(feishu_webhook_url="https://feishu.example")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.FEISHU, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_telegram_channel(self, mock_get_config):
        """Telegram channel should be detected when bot token and chat ID are set."""
        cfg = _make_config(telegram_bot_token="TOKEN", telegram_chat_id="123")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.TELEGRAM, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_email_channel(self, mock_get_config):
        """Email channel should be detected when sender, password, and receivers are set."""
        cfg = _make_config(
            email_sender="user@qq.com",
            email_password="PASS",
            email_receivers=["to@example.com"],
        )
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.EMAIL, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_pushover_channel(self, mock_get_config):
        """Pushover channel should be detected when user key and token are set."""
        cfg = _make_config(pushover_user_key="USER", pushover_api_token="TOKEN")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.PUSHOVER, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_pushplus_channel(self, mock_get_config):
        """PushPlus channel should be detected when token is set."""
        cfg = _make_config(pushplus_token="TOKEN")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.PUSHPLUS, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_serverchan3_channel(self, mock_get_config):
        """ServerChan3 channel should be detected when sendkey is set."""
        cfg = _make_config(serverchan3_sendkey="SCTKEY")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.SERVERCHAN3, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_custom_webhook_channel(self, mock_get_config):
        """Custom webhook channel should be detected when URLs are set."""
        cfg = _make_config(custom_webhook_urls=["https://example.com/webhook"])
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.CUSTOM, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_discord_webhook_channel(self, mock_get_config):
        """Discord channel should be detected when webhook URL is set."""
        cfg = _make_config(discord_webhook_url="https://discord.example/webhook")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.DISCORD, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_discord_bot_channel(self, mock_get_config):
        """Discord channel should be detected when bot token and channel ID are set."""
        cfg = _make_config(discord_bot_token="TOKEN", discord_main_channel_id="123")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.DISCORD, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_astrbot_channel(self, mock_get_config):
        """AstrBot channel should be detected when URL is set."""
        cfg = _make_config(astrbot_url="https://astrbot.example")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertIn(NotificationChannel.ASTRBOT, service.get_available_channels())

    @mock.patch("src.notification.get_config")
    def test_detect_multiple_channels(self, mock_get_config):
        """Multiple channels should be detected when multiple configs are set."""
        cfg = _make_config(
            wechat_webhook_url="https://wechat.example",
            feishu_webhook_url="https://feishu.example",
            telegram_bot_token="TOKEN",
            telegram_chat_id="123",
        )
        mock_get_config.return_value = cfg
        service = NotificationService()
        channels = service.get_available_channels()
        self.assertIn(NotificationChannel.WECHAT, channels)
        self.assertIn(NotificationChannel.FEISHU, channels)
        self.assertIn(NotificationChannel.TELEGRAM, channels)
        self.assertEqual(len(channels), 3)


class TestNotificationServiceReportGeneration(unittest.TestCase):
    """Tests for report generation methods."""

    @mock.patch("src.notification.get_config")
    def test_generate_daily_report_basic(self, mock_get_config):
        """Generate basic daily report with minimal data."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result()
        report = service.generate_daily_report([result])

        self.assertIn("股票智能分析报告", report)
        self.assertIn("贵州茅台", report)
        self.assertIn("600519", report)
        self.assertIn("操作建议", report)

    @mock.patch("src.notification.get_config")
    def test_generate_daily_report_with_date(self, mock_get_config):
        """Generate daily report with custom date."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result()
        report = service.generate_daily_report([result], report_date="2024-01-15")

        self.assertIn("2024-01-15", report)

    @mock.patch("src.notification.get_config")
    def test_generate_daily_report_multiple_stocks(self, mock_get_config):
        """Generate daily report with multiple stocks sorted by score."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        results = [
            _make_result(code="000001", name="平安银行", sentiment_score=50),
            _make_result(code="600519", name="贵州茅台", sentiment_score=80),
            _make_result(code="300750", name="宁德时代", sentiment_score=65),
        ]
        report = service.generate_daily_report(results)

        # Higher score should appear first
        maotai_pos = report.find("贵州茅台")
        ningde_pos = report.find("宁德时代")
        pingan_pos = report.find("平安银行")
        self.assertLess(maotai_pos, ningde_pos)
        self.assertLess(ningde_pos, pingan_pos)

    @mock.patch("src.notification.get_config")
    def test_generate_daily_report_summary_only(self, mock_get_config):
        """Generate summary-only report when configured."""
        cfg = _make_config(report_summary_only=True)
        mock_get_config.return_value = cfg
        service = NotificationService()
        result = _make_result()
        report = service.generate_daily_report([result])

        self.assertIn("分析结果摘要", report)
        self.assertNotIn("个股详细分析", report)

    @mock.patch("src.notification.get_config")
    def test_generate_daily_report_with_buy_reason(self, mock_get_config):
        """Generate report with buy reason."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result(buy_reason="技术面支撑强劲")
        report = service.generate_daily_report([result])

        self.assertIn("操作理由", report)
        self.assertIn("技术面支撑强劲", report)

    @mock.patch("src.notification.get_config")
    def test_generate_daily_report_with_risk_warning(self, mock_get_config):
        """Generate report with risk warning."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result(risk_warning="注意回调风险")
        report = service.generate_daily_report([result])

        self.assertIn("风险提示", report)
        self.assertIn("注意回调风险", report)

    @mock.patch("src.notification.get_config")
    def test_generate_daily_report_with_error(self, mock_get_config):
        """Generate report with error message for failed analysis."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result(success=False, error_message="API timeout")
        report = service.generate_daily_report([result])

        self.assertIn("分析异常", report)
        self.assertIn("API timeout", report)

    @mock.patch("src.notification.get_config")
    def test_generate_aggregate_report_simple_type(self, mock_get_config):
        """Generate aggregate report with simple type routes to dashboard."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result()

        with mock.patch.object(
            service, "generate_dashboard_report", return_value="dashboard"
        ) as mock_dash:
            report = service.generate_aggregate_report([result], "simple")
            mock_dash.assert_called_once()

    @mock.patch("src.notification.get_config")
    def test_generate_aggregate_report_brief_type(self, mock_get_config):
        """Generate aggregate report with brief type routes to brief."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result()

        with mock.patch.object(
            service, "generate_brief_report", return_value="brief"
        ) as mock_brief:
            report = service.generate_aggregate_report([result], "brief")
            mock_brief.assert_called_once()


class TestNotificationServiceSignalLevel(unittest.TestCase):
    """Tests for _get_signal_level method."""

    @mock.patch("src.notification.get_config")
    def test_signal_level_buy_advice(self, mock_get_config):
        """Buy advice should return buy signal."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result(operation_advice="买入", sentiment_score=50)
        signal, emoji, tag = service._get_signal_level(result)
        self.assertEqual(signal, "买入")
        self.assertEqual(emoji, "🟢")

    @mock.patch("src.notification.get_config")
    def test_signal_level_sell_advice(self, mock_get_config):
        """Sell advice should return sell signal."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result(operation_advice="卖出", sentiment_score=80)
        signal, emoji, tag = service._get_signal_level(result)
        self.assertEqual(signal, "卖出")
        self.assertEqual(emoji, "🔴")

    @mock.patch("src.notification.get_config")
    def test_signal_level_hold_advice(self, mock_get_config):
        """Hold advice should return hold signal."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result(operation_advice="持有", sentiment_score=50)
        signal, emoji, tag = service._get_signal_level(result)
        self.assertEqual(signal, "持有")
        self.assertEqual(emoji, "🟡")

    @mock.patch("src.notification.get_config")
    def test_signal_level_score_fallback_high(self, mock_get_config):
        """High score should return strong buy when advice is unrecognized."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result(operation_advice="未知建议", sentiment_score=85)
        signal, emoji, tag = service._get_signal_level(result)
        self.assertEqual(signal, "强烈买入")
        self.assertEqual(emoji, "💚")

    @mock.patch("src.notification.get_config")
    def test_signal_level_score_fallback_low(self, mock_get_config):
        """Low score should return sell when advice is unrecognized."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = _make_result(operation_advice="未知建议", sentiment_score=30)
        signal, emoji, tag = service._get_signal_level(result)
        self.assertEqual(signal, "卖出")


class TestNotificationServiceUtilityMethods(unittest.TestCase):
    """Tests for utility methods."""

    def test_escape_md_special_chars(self):
        """Escape markdown special characters."""
        self.assertEqual(NotificationService._escape_md("*ST"), r"\*ST")
        self.assertEqual(NotificationService._escape_md("正常名称"), "正常名称")
        self.assertEqual(NotificationService._escape_md(""), "")
        self.assertEqual(NotificationService._escape_md(None), None)

    def test_clean_sniper_value_none(self):
        """Clean sniper value when None."""
        self.assertEqual(NotificationService._clean_sniper_value(None), "N/A")

    def test_clean_sniper_value_number(self):
        """Clean sniper value when number."""
        self.assertEqual(NotificationService._clean_sniper_value(100), "100")
        self.assertEqual(NotificationService._clean_sniper_value(100.5), "100.5")

    def test_clean_sniper_value_string(self):
        """Clean sniper value when string with prefix."""
        self.assertEqual(
            NotificationService._clean_sniper_value("理想买入点：100"), "100"
        )
        self.assertEqual(NotificationService._clean_sniper_value("止损位：50"), "50")
        self.assertEqual(NotificationService._clean_sniper_value("普通值"), "普通值")

    def test_clean_sniper_value_empty(self):
        """Clean sniper value when empty or N/A."""
        self.assertEqual(NotificationService._clean_sniper_value(""), "")
        self.assertEqual(NotificationService._clean_sniper_value("N/A"), "N/A")


class TestNotificationServiceContextChannel(unittest.TestCase):
    """Tests for context channel extraction."""

    @mock.patch("src.notification.get_config")
    def test_extract_dingtalk_session_webhook_none(self, mock_get_config):
        """Return None when no source message."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        self.assertIsNone(service._extract_dingtalk_session_webhook())

    @mock.patch("src.notification.get_config")
    def test_extract_dingtalk_session_webhook_from_raw_data(self, mock_get_config):
        """Extract session webhook from raw_data."""
        mock_get_config.return_value = _make_config()

        # Create mock BotMessage with session webhook
        msg = mock.MagicMock(spec=BotMessage)
        msg.raw_data = {"session_webhook": "https://dingtalk.example/webhook"}

        service = NotificationService(source_message=msg)
        webhook = service._extract_dingtalk_session_webhook()
        self.assertEqual(webhook, "https://dingtalk.example/webhook")

    @mock.patch("src.notification.get_config")
    def test_extract_feishu_reply_info_none(self, mock_get_config):
        """Return None when no source message."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        self.assertIsNone(service._extract_feishu_reply_info())

    @mock.patch("src.notification.get_config")
    def test_extract_feishu_reply_info_wrong_platform(self, mock_get_config):
        """Return None when platform is not feishu."""
        mock_get_config.return_value = _make_config()

        msg = mock.MagicMock(spec=BotMessage)
        msg.platform = "wechat"
        msg.chat_id = "123"

        service = NotificationService(source_message=msg)
        self.assertIsNone(service._extract_feishu_reply_info())

    @mock.patch("src.notification.get_config")
    def test_extract_feishu_reply_info_success(self, mock_get_config):
        """Extract feishu reply info successfully."""
        mock_get_config.return_value = _make_config()

        msg = mock.MagicMock(spec=BotMessage)
        msg.platform = "feishu"
        msg.chat_id = "oc_123456"

        service = NotificationService(source_message=msg)
        info = service._extract_feishu_reply_info()
        self.assertEqual(info, {"chat_id": "oc_123456"})


class TestNotificationServiceHistoryCompare(unittest.TestCase):
    """Tests for history comparison context."""

    @mock.patch("src.notification.get_config")
    def test_history_compare_disabled(self, mock_get_config):
        """Return empty dict when history compare is disabled."""
        mock_get_config.return_value = _make_config(report_history_compare_n=0)
        service = NotificationService()
        result = _make_result()
        ctx = service._get_history_compare_context([result])
        self.assertEqual(ctx, {"history_by_code": {}})

    @mock.patch("src.notification.get_config")
    def test_history_compare_empty_results(self, mock_get_config):
        """Return empty dict when no results."""
        mock_get_config.return_value = _make_config(report_history_compare_n=3)
        service = NotificationService()
        ctx = service._get_history_compare_context([])
        self.assertEqual(ctx, {"history_by_code": {}})


class TestNotificationServiceNormalizeReportType(unittest.TestCase):
    """Tests for _normalize_report_type method."""

    @mock.patch("src.notification.get_config")
    def test_normalize_report_type_enum(self, mock_get_config):
        """Return enum as-is."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = service._normalize_report_type(ReportType.SIMPLE)
        self.assertEqual(result, ReportType.SIMPLE)

    @mock.patch("src.notification.get_config")
    def test_normalize_report_type_string(self, mock_get_config):
        """Convert string to enum."""
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = service._normalize_report_type("brief")
        self.assertEqual(result, ReportType.BRIEF)


class TestNotificationServiceGetChannelNames(unittest.TestCase):
    """Tests for get_channel_names method."""

    @mock.patch("src.notification.get_config")
    def test_get_channel_names_single(self, mock_get_config):
        """Get single channel name."""
        cfg = _make_config(wechat_webhook_url="https://wechat.example")
        mock_get_config.return_value = cfg
        service = NotificationService()
        self.assertEqual(service.get_channel_names(), "企业微信")

    @mock.patch("src.notification.get_config")
    def test_get_channel_names_multiple(self, mock_get_config):
        """Get multiple channel names."""
        cfg = _make_config(
            wechat_webhook_url="https://wechat.example",
            feishu_webhook_url="https://feishu.example",
        )
        mock_get_config.return_value = cfg
        service = NotificationService()
        names = service.get_channel_names()
        self.assertIn("企业微信", names)
        self.assertIn("飞书", names)


if __name__ == "__main__":
    unittest.main()
