"""
Demo script to test web crawler functionality locally
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'lambdas'))

from utils.crawler_utils import (
    is_kwbridge_url, normalize_url, calculate_url_depth,
    extract_links_from_html, clean_html_content, get_page_title
)

def test_crawler_utils():
    """Test the crawler utility functions"""
    print("🧪 Testing Web Crawler Utility Functions")
    print("=" * 50)
    
    # Test URL validation
    print("\n1. Testing URL validation:")
    test_urls = [
        "https://kwbridge.com/",
        "https://kwbridge.com/page",
        "https://example.com/",
        "mailto:test@example.com"
    ]
    
    for url in test_urls:
        is_valid = is_kwbridge_url(url)
        print(f"  {url} -> {is_valid}")
    
    # Test URL normalization
    print("\n2. Testing URL normalization:")
    test_urls = [
        "https://kwbridge.com/page?param=value#section",
        "https://kwbridge.com/path/",
        "https://kwbridge.com/"
    ]
    
    for url in test_urls:
        normalized = normalize_url(url)
        print(f"  {url} -> {normalized}")
    
    # Test depth calculation
    print("\n3. Testing depth calculation:")
    test_urls = [
        "https://kwbridge.com/",
        "https://kwbridge.com/page",
        "https://kwbridge.com/page/sub",
        "https://kwbridge.com/page/sub/deep"
    ]
    
    for url in test_urls:
        depth = calculate_url_depth(url)
        print(f"  {url} -> depth: {depth}")
    
    # Test HTML processing
    print("\n4. Testing HTML processing:")
    sample_html = '''
    <html>
        <head>
            <title>Test Page - Bridge Learning</title>
            <script>alert('test');</script>
            <style>body { color: red; }</style>
        </head>
        <body>
            <h1>Welcome to Bridge Learning</h1>
            <p>This is a test page with some content.</p>
            <a href="/page1">Go to Page 1</a>
            <a href="/page2">Go to Page 2</a>
            <a href="https://example.com/external">External Link</a>
            <!-- This is a comment -->
        </body>
    </html>
    '''
    
    # Extract title
    title = get_page_title(sample_html)
    print(f"  Extracted title: {title}")
    
    # Clean HTML
    cleaned = clean_html_content(sample_html)
    print(f"  HTML cleaned: {'script' not in cleaned.lower()}")
    
    # Extract links
    links = extract_links_from_html(sample_html, "https://kwbridge.com/")
    print(f"  Extracted links: {len(links)}")
    for link in links:
        print(f"    - {link}")
    
    print("\n✅ All utility function tests completed!")


def test_crawler_models():
    """Test the Pydantic models"""
    print("\n🧪 Testing Web Crawler Models")
    print("=" * 50)
    
    try:
        from models.crawler_models import CrawlMetadata, CrawlStatus, CrawlQueueMessage
        
        # Test CrawlMetadata
        metadata = CrawlMetadata(
            url="https://kwbridge.com/test",
            title="Test Page",
            content_length=1000,
            status=CrawlStatus.SUCCESS
        )
        print(f"✅ CrawlMetadata created: {metadata.url}")
        
        # Test CrawlQueueMessage
        message = CrawlQueueMessage(
            url="https://kwbridge.com/test",
            parent_url="https://kwbridge.com/",
            depth=1
        )
        print(f"✅ CrawlQueueMessage created: {message.url}")
        
    except ImportError as e:
        print(f"❌ Error importing models: {e}")
    except Exception as e:
        print(f"❌ Error testing models: {e}")


if __name__ == "__main__":
    print("🚀 Web Crawler Demo Test")
    print("=" * 50)
    
    try:
        test_crawler_utils()
        test_crawler_models()
        
        print("\n🎉 All tests completed successfully!")
        print("\n📋 Next steps:")
        print("1. Run: ./deploy.sh web-crawler")
        print("2. Set up AWS resources (SQS, DynamoDB, S3)")
        print("3. Configure environment variables")
        print("4. Start crawling with: aws lambda invoke --function-name web-crawler-trigger")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
