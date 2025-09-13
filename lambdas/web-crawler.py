"""
Web Crawler Lambda Function

Crawls kwbridge.com domain and stores HTML content in S3 with metadata in DynamoDB.
Processes URLs from SQS queue sequentially.
"""

import json
import boto3
import requests
from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup
import re
from datetime import datetime
import logging
from typing import List, Dict, Optional, Set
from dataclasses import dataclass

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sqs_client = boto3.client('sqs')

# Configuration - using environment variables
import os

BUCKET_NAME = os.environ.get('BUCKET_NAME', 'bridge-lambdas-crawler-text-2024')
TABLE_NAME = os.environ.get('TABLE_NAME', 'crawler-metadata')
QUEUE_URL = os.environ.get('QUEUE_URL')
TARGET_DOMAIN = os.environ.get('TARGET_DOMAIN', 'kwbridge.com')
MAX_DEPTH = int(os.environ.get('MAX_DEPTH', '2'))

# Validate required environment variables
if not QUEUE_URL:
    raise ValueError("QUEUE_URL environment variable is required")


@dataclass
class CrawlResult:
    """Result of crawling a single URL"""
    url: str
    status: str
    title: Optional[str] = None
    content_length: int = 0
    new_urls: List[str] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.new_urls is None:
            self.new_urls = []


class WebCrawler:
    """Main web crawler class"""
    
    def __init__(self):
        self.table = dynamodb.Table(TABLE_NAME)
        self.visited_urls: Set[str] = set()
        self._load_visited_urls()
    
    def _load_visited_urls(self):
        """Load already visited URLs from DynamoDB"""
        try:
            response = self.table.scan(
                ProjectionExpression='#url',
                ExpressionAttributeNames={'#url': 'url'}
            )
            self.visited_urls = {item['url'] for item in response.get('Items', [])}
            logger.info(f"Loaded {len(self.visited_urls)} previously visited URLs")
        except Exception as e:
            logger.warning(f"Could not load visited URLs: {e}")
            self.visited_urls = set()
    
    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid for crawling"""
        try:
            parsed = urlparse(url)
            return (
                parsed.netloc == TARGET_DOMAIN and
                parsed.scheme in ['http', 'https'] and
                not any(ext in url.lower() for ext in ['.pdf', '.doc', '.docx', '.zip', '.jpg', '.jpeg', '.png', '.gif'])
            )
        except Exception:
            return False
    
    def _calculate_url_depth(self, url: str) -> int:
        """Calculate the depth of a URL from the root domain"""
        try:
            parsed = urlparse(url)
            path_parts = [part for part in parsed.path.split('/') if part]
            return len(path_parts)
        except Exception:
            return 0
    
    def _extract_text_from_html(self, html_content: str) -> str:
        """Extract clean text content from HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script, style, and other non-content elements
            for element in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
                element.decompose()
            
            # Remove comments
            from bs4 import Comment
            comments = soup.findAll(text=lambda text: isinstance(text, Comment))
            for comment in comments:
                comment.extract()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text
        except Exception as e:
            logger.error(f"Error extracting text from HTML: {e}")
            # Fallback to simple text extraction
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                return soup.get_text()
            except:
                return html_content
    
    def _extract_links(self, html_content: str, base_url: str) -> List[str]:
        """Extract valid links from HTML content"""
        links = []
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                # Convert relative URLs to absolute
                absolute_url = urljoin(base_url, href)
                
                # Remove fragments and query parameters for consistency
                parsed = urlparse(absolute_url)
                clean_url = urlunparse((
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    '',  # Remove query
                    ''   # Remove fragment
                ))
                
                if self._is_valid_url(clean_url):
                    links.append(clean_url)
            
            print(f"Links: {links}")
            # Remove duplicates and sort
            return sorted(list(set(links)))
        except Exception as e:
            logger.error(f"Error extracting links: {e}")
            return []
    
    def _get_s3_key(self, url: str) -> str:
        """Generate S3 key that mirrors URL structure"""
        try:
            parsed = urlparse(url)
            path = parsed.path
            
            # Handle root path
            if path == '/' or path == '':
                return 'index.txt'
            
            # Remove leading slash and add .txt if no extension
            path = path.lstrip('/')
            if not path.endswith('.txt') and not '.' in path.split('/')[-1]:
                path += '/index.txt'
            else:
                # Replace existing extension with .txt
                path_parts = path.split('.')
                if len(path_parts) > 1:
                    path_parts[-1] = 'txt'
                    path = '.'.join(path_parts)
            
            return path
        except Exception:
            return 'index.txt'
    
    def _store_text_in_s3(self, url: str, text_content: str) -> bool:
        """Store text content in S3"""
        try:
            s3_key = self._get_s3_key(url)
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=s3_key,
                Body=text_content,
                ContentType='text/plain'
            )
            logger.info(f"Stored text for {url} at s3://{BUCKET_NAME}/{s3_key}")
            return True
        except Exception as e:
            logger.error(f"Error storing text in S3 for {url}: {e}")
            return False
    
    def _store_metadata_in_dynamodb(self, result: CrawlResult, parent_url: Optional[str] = None) -> bool:
        """Store crawl metadata in DynamoDB"""
        try:
            item = {
                'url': result.url,
                'title': result.title,
                'content_length': result.content_length,
                'crawl_timestamp': datetime.utcnow().isoformat(),
                'parent_url': parent_url,
                'status': result.status,
                'error_message': result.error_message
            }
            
            self.table.put_item(Item=item)
            logger.info(f"Stored metadata for {result.url}")
            return True
        except Exception as e:
            logger.error(f"Error storing metadata in DynamoDB for {result.url}: {e}")
            return False
    
    def _add_urls_to_queue(self, urls: List[str]) -> int:
        """Add new URLs to SQS queue"""
        added_count = 0
        try:
            for url in urls:
                if url not in self.visited_urls:
                    # Calculate depth to respect MAX_DEPTH
                    depth = self._calculate_url_depth(url)
                    if depth <= MAX_DEPTH:
                        sqs_client.send_message(
                            QueueUrl=QUEUE_URL,
                            MessageBody=json.dumps({'url': url})
                        )
                        added_count += 1
                        logger.info(f"Added URL to queue: {url} (depth: {depth})")
                    else:
                        logger.info(f"Skipped URL due to depth limit: {url} (depth: {depth})")
        except Exception as e:
            logger.error(f"Error adding URLs to queue: {e}")
        
        return added_count
    
    def crawl_url(self, url: str, parent_url: Optional[str] = None) -> CrawlResult:
        """Crawl a single URL and return results"""
        logger.info(f"Crawling URL: {url}")
        
        # Check if already visited
        if url in self.visited_urls:
            logger.info(f"URL already visited: {url}")
            return CrawlResult(url=url, status='already_visited')
        
        try:
            # Fetch HTML content
            headers = {
                'User-Agent': 'Bridge-WebCrawler/1.0 (Educational Purpose)'
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            html_content = response.text
            content_length = len(html_content)
            
            # Extract text from HTML
            text_content = self._extract_text_from_html(html_content)
            text_length = len(text_content)
            
            # Extract title
            soup = BeautifulSoup(html_content, 'html.parser')
            title = soup.title.string.strip() if soup.title else None
            
            # Store text in S3
            if not self._store_text_in_s3(url, text_content):
                return CrawlResult(url=url, status='s3_error', error_message='Failed to store text in S3')
            
            # Extract new URLs
            new_urls = self._extract_links(html_content, url)
            
            # Create result
            result = CrawlResult(
                url=url,
                status='success',
                title=title,
                content_length=text_length,
                new_urls=new_urls
            )
            
            # Store metadata
            if not self._store_metadata_in_dynamodb(result, parent_url):
                result.status = 'metadata_error'
                result.error_message = 'Failed to store metadata in DynamoDB'
            
            # Add to visited URLs
            self.visited_urls.add(url)
            
            # Add new URLs to queue
            added_count = self._add_urls_to_queue(new_urls)
            logger.info(f"Added {added_count} new URLs to queue from {url}")
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for {url}: {e}")
            return CrawlResult(url=url, status='request_error', error_message=str(e))
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e}")
            return CrawlResult(url=url, status='error', error_message=str(e))


def lambda_handler(event, context):
    """Lambda handler function"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Initialize crawler
    crawler = WebCrawler()
    
    # Process SQS messages
    for record in event.get('Records', []):
        try:
            # Parse SQS message
            message_body = json.loads(record['body'])
            url = message_body['url']
            parent_url = message_body.get('parent_url')
            
            # Crawl the URL
            result = crawler.crawl_url(url, parent_url)
            
            logger.info(f"Crawl result for {url}: {result.status}")
            if result.error_message:
                logger.error(f"Error message: {result.error_message}")
            
        except Exception as e:
            logger.error(f"Error processing SQS record: {e}")
            continue
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Crawler processing completed',
            'processed_count': len(event.get('Records', []))
        })
    }
