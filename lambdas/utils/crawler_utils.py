"""
Utility functions for the web crawler
"""

import re
from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup
from typing import List, Set, Optional


def is_kwbridge_url(url: str) -> bool:
    """
    Check if URL belongs to kwbridge.com domain
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is from kwbridge.com domain
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc == 'kwbridge.com'
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """
    Normalize URL by removing fragments and query parameters
    
    Args:
        url: URL to normalize
        
    Returns:
        Normalized URL
    """
    try:
        parsed = urlparse(url)
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            '',  # Remove query
            ''   # Remove fragment
        ))
    except Exception:
        return url


def calculate_url_depth(url: str) -> int:
    """
    Calculate the depth of a URL from the root domain
    
    Args:
        url: URL to analyze
        
    Returns:
        Depth level (0 for root, 1 for first level, etc.)
    """
    try:
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split('/') if part]
        return len(path_parts)
    except Exception:
        return 0


def is_valid_crawl_url(url: str, max_depth: int = 2) -> bool:
    """
    Check if URL is valid for crawling
    
    Args:
        url: URL to check
        max_depth: Maximum allowed depth
        
    Returns:
        True if URL should be crawled
    """
    try:
        parsed = urlparse(url)
        
        # Must be from kwbridge.com
        if not is_kwbridge_url(url):
            return False
        
        # Must be HTTP/HTTPS
        if parsed.scheme not in ['http', 'https']:
            return False
        
        # Check depth
        if calculate_url_depth(url) > max_depth:
            return False
        
        # Skip file extensions that shouldn't be crawled
        skip_extensions = ['.pdf', '.doc', '.docx', '.zip', '.jpg', '.jpeg', '.png', '.gif', '.css', '.js']
        if any(url.lower().endswith(ext) for ext in skip_extensions):
            return False
        
        return True
    except Exception:
        return False


def extract_links_from_html(html_content: str, base_url: str) -> List[str]:
    """
    Extract valid links from HTML content
    
    Args:
        html_content: HTML content to parse
        base_url: Base URL for resolving relative links
        
    Returns:
        List of valid URLs found in the HTML
    """
    links = []
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Skip empty or javascript links
            if not href or href.startswith('javascript:') or href.startswith('mailto:'):
                continue
            
            # Convert relative URLs to absolute
            absolute_url = urljoin(base_url, href)
            
            # Normalize the URL
            normalized_url = normalize_url(absolute_url)
            
            if is_valid_crawl_url(normalized_url):
                links.append(normalized_url)
        
        # Remove duplicates and sort
        return sorted(list(set(links)))
    except Exception as e:
        print(f"Error extracting links: {e}")
        return []


def clean_html_content(html_content: str) -> str:
    """
    Clean HTML content by removing scripts and normalizing
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        Cleaned HTML content
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        
        # Remove comments
        from bs4 import Comment
        comments = soup.findAll(text=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()
        
        # Get the cleaned HTML
        return soup.prettify()
    except Exception as e:
        print(f"Error cleaning HTML: {e}")
        return html_content


def get_page_title(html_content: str) -> Optional[str]:
    """
    Extract page title from HTML content
    
    Args:
        html_content: HTML content to parse
        
    Returns:
        Page title or None if not found
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text().strip()
        return None
    except Exception:
        return None


def generate_s3_key(url: str) -> str:
    """
    Generate S3 key that mirrors URL structure
    
    Args:
        url: URL to convert to S3 key
        
    Returns:
        S3 key path
    """
    try:
        parsed = urlparse(url)
        path = parsed.path
        
        # Handle root path
        if path == '/' or path == '':
            return 'index.html'
        
        # Remove leading slash
        path = path.lstrip('/')
        
        # If path ends with slash, add index.html
        if path.endswith('/'):
            path += 'index.html'
        # If no extension, add .html
        elif not '.' in path.split('/')[-1]:
            path += '.html'
        
        return path
    except Exception:
        return 'index.html'


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe storage
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove multiple consecutive underscores
    filename = re.sub(r'_+', '_', filename)
    # Remove leading/trailing underscores
    filename = filename.strip('_')
    
    return filename or 'index'


def chunk_list(items: List, chunk_size: int) -> List[List]:
    """
    Split a list into chunks of specified size
    
    Args:
        items: List to chunk
        chunk_size: Size of each chunk
        
    Returns:
        List of chunks
    """
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
