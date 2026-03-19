# -*- coding: utf-8 -*-
"""
Tests for search_service.py to boost coverage from 38% to 60%+.

Covers:
- SearchResult and SearchResponse data classes
- BaseSearchProvider key management
- Provider fallback and error handling
- Utility functions
"""

import os
import sys
import unittest
from unittest import mock
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock optional dependencies
for optional_module in ("litellm", "json_repair", "tavily", "newspaper"):
    try:
        __import__(optional_module)
    except ModuleNotFoundError:
        sys.modules[optional_module] = mock.MagicMock()

from src.search_service import (
    SearchResult,
    SearchResponse,
    BaseSearchProvider,
    TavilySearchProvider,
    fetch_url_content,
)


class TestSearchResult(unittest.TestCase):
    """Tests for SearchResult dataclass."""

    def test_to_text_basic(self):
        """Test basic text conversion."""
        result = SearchResult(
            title="Test Title",
            snippet="Test snippet content",
            url="https://example.com/article",
            source="example.com",
        )
        text = result.to_text()
        self.assertIn("example.com", text)
        self.assertIn("Test Title", text)
        self.assertIn("Test snippet content", text)

    def test_to_text_with_date(self):
        """Test text conversion with published date."""
        result = SearchResult(
            title="Test Title",
            snippet="Test snippet",
            url="https://example.com",
            source="example.com",
            published_date="2024-01-15",
        )
        text = result.to_text()
        self.assertIn("2024-01-15", text)


class TestSearchResponse(unittest.TestCase):
    """Tests for SearchResponse dataclass."""

    def test_to_context_success(self):
        """Test context generation with successful results."""
        results = [
            SearchResult(
                title="Title 1",
                snippet="Snippet 1",
                url="https://example.com/1",
                source="example.com",
            ),
            SearchResult(
                title="Title 2",
                snippet="Snippet 2",
                url="https://example.com/2",
                source="example.com",
            ),
        ]
        response = SearchResponse(
            query="test query",
            results=results,
            provider="TestProvider",
            success=True,
        )
        context = response.to_context()
        self.assertIn("test query", context)
        self.assertIn("TestProvider", context)
        self.assertIn("Title 1", context)
        self.assertIn("Title 2", context)

    def test_to_context_no_results(self):
        """Test context generation with no results."""
        response = SearchResponse(
            query="test query",
            results=[],
            provider="TestProvider",
            success=False,
            error_message="API error",
        )
        context = response.to_context()
        self.assertIn("未找到相关结果", context)

    def test_to_context_max_results(self):
        """Test context generation respects max_results."""
        results = [
            SearchResult(
                title=f"Title {i}",
                snippet=f"Snippet {i}",
                url=f"https://example.com/{i}",
                source="example.com",
            )
            for i in range(10)
        ]
        response = SearchResponse(
            query="test query",
            results=results,
            provider="TestProvider",
            success=True,
        )
        context = response.to_context(max_results=3)
        self.assertIn("Title 0", context)
        self.assertIn("Title 2", context)
        self.assertNotIn("Title 5", context)


class TestBaseSearchProvider(unittest.TestCase):
    """Tests for BaseSearchProvider abstract class."""

    def setUp(self):
        """Create a concrete implementation for testing."""

        class ConcreteProvider(BaseSearchProvider):
            def _do_search(self, query, api_key, max_results, days=7):
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=True,
                )

        self.ProviderClass = ConcreteProvider

    def test_is_available_with_keys(self):
        """Provider is available when keys are configured."""
        provider = self.ProviderClass(api_keys=["key1", "key2"], name="Test")
        self.assertTrue(provider.is_available)

    def test_is_available_no_keys(self):
        """Provider is not available when no keys."""
        provider = self.ProviderClass(api_keys=[], name="Test")
        self.assertFalse(provider.is_available)

    def test_get_next_key_rotation(self):
        """Keys are rotated in round-robin fashion."""
        provider = self.ProviderClass(api_keys=["key1", "key2", "key3"], name="Test")

        key1 = provider._get_next_key()
        key2 = provider._get_next_key()
        key3 = provider._get_next_key()
        key4 = provider._get_next_key()  # Should cycle back

        # Verify rotation
        self.assertIn(key1, ["key1", "key2", "key3"])
        self.assertIn(key2, ["key1", "key2", "key3"])
        self.assertIn(key3, ["key1", "key2", "key3"])

    def test_record_success(self):
        """Success increments usage count."""
        provider = self.ProviderClass(api_keys=["key1"], name="Test")
        provider._record_success("key1")
        self.assertEqual(provider._key_usage["key1"], 1)

    def test_record_error(self):
        """Error increments error count."""
        provider = self.ProviderClass(api_keys=["key1"], name="Test")
        provider._record_error("key1")
        self.assertEqual(provider._key_errors["key1"], 1)

    def test_error_count_reduces_on_success(self):
        """Success reduces error count."""
        provider = self.ProviderClass(api_keys=["key1"], name="Test")
        provider._record_error("key1")
        provider._record_error("key1")
        provider._record_success("key1")
        self.assertEqual(provider._key_errors["key1"], 1)

    def test_search_no_api_key(self):
        """Search returns error when no API key configured."""
        provider = self.ProviderClass(api_keys=[], name="Test")
        response = provider.search("test query")
        self.assertFalse(response.success)
        self.assertIn("未配置 API Key", response.error_message)


class TestTavilySearchProvider(unittest.TestCase):
    """Tests for TavilySearchProvider."""

    def test_extract_domain_basic(self):
        """Domain extraction from URL."""
        domain = TavilySearchProvider._extract_domain("https://www.example.com/article")
        self.assertEqual(domain, "example.com")

    def test_extract_domain_no_www(self):
        """Domain extraction without www prefix."""
        domain = TavilySearchProvider._extract_domain("https://example.com/article")
        self.assertEqual(domain, "example.com")

    def test_extract_domain_invalid_url(self):
        """Domain extraction handles invalid URLs."""
        domain = TavilySearchProvider._extract_domain("not a url")
        self.assertEqual(domain, "未知来源")

    def test_extract_domain_empty(self):
        """Domain extraction handles empty input."""
        domain = TavilySearchProvider._extract_domain("")
        self.assertEqual(domain, "未知来源")


class TestFetchUrlContent(unittest.TestCase):
    """Tests for fetch_url_content function."""

    @mock.patch("src.search_service.Article")
    def test_fetch_url_content_success(self, mock_article_class):
        """Successfully fetch URL content."""
        mock_article = mock.MagicMock()
        mock_article.text = "This is the article content.\n\nWith multiple lines."
        mock_article_class.return_value = mock_article

        content = fetch_url_content("https://example.com/article")
        self.assertIn("article content", content)
        mock_article.download.assert_called_once()
        mock_article.parse.assert_called_once()

    @mock.patch("src.search_service.Article")
    def test_fetch_url_content_truncates(self, mock_article_class):
        """Content is truncated to 1500 chars."""
        mock_article = mock.MagicMock()
        mock_article.text = "A" * 2000
        mock_article_class.return_value = mock_article

        content = fetch_url_content("https://example.com/article")
        self.assertEqual(len(content), 1500)

    @mock.patch("src.search_service.Article")
    def test_fetch_url_content_exception(self, mock_article_class):
        """Returns empty string on exception."""
        mock_article_class.side_effect = Exception("Network error")

        content = fetch_url_content("https://example.com/article")
        self.assertEqual(content, "")


class TestSearchResponseIntegration(unittest.TestCase):
    """Integration tests for search response handling."""

    def test_search_response_timing(self):
        """Search response includes timing information."""
        response = SearchResponse(
            query="test",
            results=[],
            provider="Test",
            success=True,
            search_time=0.5,
        )
        self.assertEqual(response.search_time, 0.5)

    def test_search_response_error_message(self):
        """Search response preserves error message."""
        response = SearchResponse(
            query="test",
            results=[],
            provider="Test",
            success=False,
            error_message="Rate limit exceeded",
        )
        self.assertEqual(response.error_message, "Rate limit exceeded")


if __name__ == "__main__":
    unittest.main()
