"""
Comprehensive tests for the web crawler functionality
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from urllib.parse import urlparse
from datetime import datetime

# Import the modules we're testing
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lambdas'))

from web_crawler import WebCrawler, CrawlResult, lambda_handler
from utils.crawler_utils import (
    is_kwbridge_url, normalize_url, calculate_url_depth, 
    is_valid_crawl_url, extract_links_from_html, clean_html_content,
    get_page_title, generate_s3_key
)
from models.crawler_models import CrawlMetadata, CrawlStatus, CrawlQueueMessage


class TestCrawlerUtils:
    """Test utility functions for the web crawler"""
    
    def test_is_kwbridge_url(self):
        """Test URL domain validation"""
        assert is_kwbridge_url("https://kwbridge.com/") == True
        assert is_kwbridge_url("http://kwbridge.com/page") == True
        assert is_kwbridge_url("https://www.kwbridge.com/") == False
        assert is_kwbridge_url("https://example.com/") == False
        assert is_kwbridge_url("not-a-url") == False
    
    def test_normalize_url(self):
        """Test URL normalization"""
        assert normalize_url("https://kwbridge.com/page?param=value#section") == "https://kwbridge.com/page"
        assert normalize_url("https://kwbridge.com/") == "https://kwbridge.com/"
        assert normalize_url("https://kwbridge.com/path/") == "https://kwbridge.com/path/"
    
    def test_calculate_url_depth(self):
        """Test URL depth calculation"""
        assert calculate_url_depth("https://kwbridge.com/") == 0
        assert calculate_url_depth("https://kwbridge.com/page") == 1
        assert calculate_url_depth("https://kwbridge.com/page/subpage") == 2
        assert calculate_url_depth("https://kwbridge.com/page/subpage/more") == 3
    
    def test_is_valid_crawl_url(self):
        """Test URL validation for crawling"""
        # Valid URLs
        assert is_valid_crawl_url("https://kwbridge.com/", max_depth=2) == True
        assert is_valid_crawl_url("https://kwbridge.com/page", max_depth=2) == True
        assert is_valid_crawl_url("https://kwbridge.com/page/sub", max_depth=2) == True
        
        # Invalid URLs
        assert is_valid_crawl_url("https://example.com/", max_depth=2) == False
        assert is_valid_crawl_url("https://kwbridge.com/page/sub/deep", max_depth=2) == False
        assert is_valid_crawl_url("https://kwbridge.com/file.pdf", max_depth=2) == False
        assert is_valid_crawl_url("mailto:test@example.com", max_depth=2) == False
    
    def test_extract_links_from_html(self):
        """Test link extraction from HTML"""
        html = '''
        <html>
            <body>
                <a href="/page1">Page 1</a>
                <a href="https://kwbridge.com/page2">Page 2</a>
                <a href="https://example.com/external">External</a>
                <a href="mailto:test@example.com">Email</a>
                <a href="javascript:void(0)">JS Link</a>
            </body>
        </html>
        '''
        
        links = extract_links_from_html(html, "https://kwbridge.com/")
        
        assert "https://kwbridge.com/page1" in links
        assert "https://kwbridge.com/page2" in links
        assert "https://example.com/external" not in links
        assert "mailto:test@example.com" not in links
        assert "javascript:void(0)" not in links
    
    def test_clean_html_content(self):
        """Test HTML cleaning"""
        html = '''
        <html>
            <head>
                <title>Test Page</title>
                <script>alert('test');</script>
                <style>body { color: red; }</style>
            </head>
            <body>
                <h1>Hello World</h1>
                <!-- This is a comment -->
                <p>Content here</p>
            </body>
        </html>
        '''
        
        cleaned = clean_html_content(html)
        
        # Should remove scripts and styles
        assert "alert('test')" not in cleaned
        assert "body { color: red; }" not in cleaned
        # Should keep content
        assert "Hello World" in cleaned
        assert "Content here" in cleaned
    
    def test_get_page_title(self):
        """Test page title extraction"""
        html_with_title = '<html><head><title>Test Title</title></head><body></body></html>'
        html_without_title = '<html><head></head><body></body></html>'
        
        assert get_page_title(html_with_title) == "Test Title"
        assert get_page_title(html_without_title) is None
    
    def test_generate_s3_key(self):
        """Test S3 key generation"""
        assert generate_s3_key("https://kwbridge.com/") == "index.html"
        assert generate_s3_key("https://kwbridge.com/page") == "page.html"
        assert generate_s3_key("https://kwbridge.com/page/") == "page/index.html"
        assert generate_s3_key("https://kwbridge.com/page/sub") == "page/sub.html"


class TestCrawlerModels:
    """Test Pydantic models"""
    
    def test_crawl_metadata(self):
        """Test CrawlMetadata model"""
        metadata = CrawlMetadata(
            url="https://kwbridge.com/test",
            title="Test Page",
            content_length=1000,
            status=CrawlStatus.SUCCESS
        )
        
        assert metadata.url == "https://kwbridge.com/test"
        assert metadata.title == "Test Page"
        assert metadata.content_length == 1000
        assert metadata.status == CrawlStatus.SUCCESS
    
    def test_crawl_queue_message(self):
        """Test CrawlQueueMessage model"""
        message = CrawlQueueMessage(
            url="https://kwbridge.com/test",
            parent_url="https://kwbridge.com/",
            depth=1,
            retry_count=0
        )
        
        assert message.url == "https://kwbridge.com/test"
        assert message.parent_url == "https://kwbridge.com/"
        assert message.depth == 1
        assert message.retry_count == 0


class TestWebCrawler:
    """Test the main WebCrawler class"""
    
    @pytest.fixture
    def mock_crawler(self):
        """Create a mock crawler for testing"""
        with patch('web_crawler.boto3.resource'), \
             patch('web_crawler.boto3.client'), \
             patch('web_crawler.s3_client'), \
             patch('web_crawler.sqs_client'):
            crawler = WebCrawler()
            return crawler
    
    def test_crawler_initialization(self, mock_crawler):
        """Test crawler initialization"""
        assert isinstance(mock_crawler.visited_urls, set)
        assert mock_crawler.table is not None
    
    @patch('web_crawler.requests.get')
    def test_successful_crawl(self, mock_get, mock_crawler):
        """Test successful URL crawling"""
        # Mock HTTP response
        mock_response = Mock()
        mock_response.text = '<html><head><title>Test</title></head><body><a href="/page1">Link</a></body></html>'
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Mock AWS services
        mock_crawler._store_html_in_s3 = Mock(return_value=True)
        mock_crawler._store_metadata_in_dynamodb = Mock(return_value=True)
        mock_crawler._add_urls_to_queue = Mock(return_value=1)
        
        result = mock_crawler.crawl_url("https://kwbridge.com/test")
        
        assert result.status == 'success'
        assert result.title == 'Test'
        assert len(result.new_urls) > 0
        assert "https://kwbridge.com/page1" in result.new_urls
    
    @patch('web_crawler.requests.get')
    def test_request_error(self, mock_get, mock_crawler):
        """Test handling of request errors"""
        # Mock HTTP error
        mock_get.side_effect = Exception("Connection error")
        
        result = mock_crawler.crawl_url("https://kwbridge.com/test")
        
        assert result.status == 'error'
        assert result.error_message == "Connection error"
    
    def test_already_visited_url(self, mock_crawler):
        """Test handling of already visited URLs"""
        mock_crawler.visited_urls.add("https://kwbridge.com/test")
        
        result = mock_crawler.crawl_url("https://kwbridge.com/test")
        
        assert result.status == 'already_visited'


class TestLambdaHandler:
    """Test the Lambda handler function"""
    
    @patch('web_crawler.WebCrawler')
    def test_lambda_handler_success(self, mock_crawler_class):
        """Test successful Lambda execution"""
        # Mock crawler instance
        mock_crawler = Mock()
        mock_crawler.crawl_url.return_value = CrawlResult(
            url="https://kwbridge.com/test",
            status='success'
        )
        mock_crawler_class.return_value = mock_crawler
        
        # Test event
        event = {
            'Records': [
                {
                    'body': json.dumps({'url': 'https://kwbridge.com/test'})
                }
            ]
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        assert json.loads(result['body'])['processed_count'] == 1
        mock_crawler.crawl_url.assert_called_once_with('https://kwbridge.com/test', None)
    
    @patch('web_crawler.WebCrawler')
    def test_lambda_handler_error(self, mock_crawler_class):
        """Test Lambda execution with errors"""
        # Mock crawler that raises exception
        mock_crawler = Mock()
        mock_crawler.crawl_url.side_effect = Exception("Test error")
        mock_crawler_class.return_value = mock_crawler
        
        # Test event
        event = {
            'Records': [
                {
                    'body': json.dumps({'url': 'https://kwbridge.com/test'})
                }
            ]
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200  # Lambda should still return 200
        assert json.loads(result['body'])['processed_count'] == 1


class TestIntegration:
    """Integration tests"""
    
    def test_full_crawl_workflow(self):
        """Test the complete crawl workflow"""
        # This would be an integration test that tests the full flow
        # In a real scenario, you might use moto to mock AWS services
        pass
    
    def test_url_discovery_chain(self):
        """Test that URLs are discovered and added to queue correctly"""
        html_content = '''
        <html>
            <body>
                <a href="/page1">Page 1</a>
                <a href="/page2">Page 2</a>
                <a href="/page1/sub">Page 1 Sub</a>
            </body>
        </html>
        '''
        
        links = extract_links_from_html(html_content, "https://kwbridge.com/")
        
        expected_links = [
            "https://kwbridge.com/page1",
            "https://kwbridge.com/page2",
            "https://kwbridge.com/page1/sub"
        ]
        
        for expected_link in expected_links:
            assert expected_link in links
    
    def test_depth_limiting(self):
        """Test that depth limiting works correctly"""
        # URLs at different depths
        root_url = "https://kwbridge.com/"
        level1_url = "https://kwbridge.com/page"
        level2_url = "https://kwbridge.com/page/sub"
        level3_url = "https://kwbridge.com/page/sub/deep"
        
        max_depth = 2
        
        assert is_valid_crawl_url(root_url, max_depth) == True
        assert is_valid_crawl_url(level1_url, max_depth) == True
        assert is_valid_crawl_url(level2_url, max_depth) == True
        assert is_valid_crawl_url(level3_url, max_depth) == False


if __name__ == "__main__":
    pytest.main([__file__])
