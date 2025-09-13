"""
Pydantic models for web crawler data structures
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class CrawlStatus(str, Enum):
    """Enumeration of possible crawl statuses"""
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    REQUEST_ERROR = "request_error"
    S3_ERROR = "s3_error"
    METADATA_ERROR = "metadata_error"
    ALREADY_VISITED = "already_visited"
    INVALID_URL = "invalid_url"
    DEPTH_LIMIT_EXCEEDED = "depth_limit_exceeded"


class CrawlMetadata(BaseModel):
    """Metadata for a crawled URL"""
    url: str = Field(..., description="The crawled URL")
    title: Optional[str] = Field(None, description="Page title extracted from HTML")
    content_length: int = Field(0, description="Length of HTML content in bytes")
    crawl_timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the page was crawled")
    parent_url: Optional[str] = Field(None, description="URL that led to this page")
    status: CrawlStatus = Field(CrawlStatus.PENDING, description="Status of the crawl operation")
    error_message: Optional[str] = Field(None, description="Error message if crawl failed")
    s3_key: Optional[str] = Field(None, description="S3 key where HTML content is stored")
    depth: int = Field(0, description="Depth level from root domain")
    new_urls_found: int = Field(0, description="Number of new URLs discovered from this page")
    
    @validator('url')
    def validate_url(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("URL must be a non-empty string")
        return v
    
    @validator('content_length')
    def validate_content_length(cls, v):
        if v < 0:
            raise ValueError("Content length cannot be negative")
        return v
    
    @validator('depth')
    def validate_depth(cls, v):
        if v < 0:
            raise ValueError("Depth cannot be negative")
        return v


class CrawlResult(BaseModel):
    """Result of crawling a single URL"""
    url: str = Field(..., description="The crawled URL")
    status: CrawlStatus = Field(..., description="Status of the crawl operation")
    title: Optional[str] = Field(None, description="Page title")
    content_length: int = Field(0, description="Length of HTML content")
    new_urls: List[str] = Field(default_factory=list, description="New URLs discovered")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    s3_key: Optional[str] = Field(None, description="S3 key where content is stored")
    depth: int = Field(0, description="Depth level from root")
    
    class Config:
        use_enum_values = True


class CrawlQueueMessage(BaseModel):
    """Message structure for SQS queue"""
    url: str = Field(..., description="URL to crawl")
    parent_url: Optional[str] = Field(None, description="URL that led to this one")
    depth: int = Field(0, description="Current depth level")
    retry_count: int = Field(0, description="Number of retry attempts")
    
    @validator('url')
    def validate_url(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("URL must be a non-empty string")
        return v
    
    @validator('retry_count')
    def validate_retry_count(cls, v):
        if v < 0:
            raise ValueError("Retry count cannot be negative")
        return v


class CrawlStatistics(BaseModel):
    """Statistics about the crawling process"""
    total_urls_discovered: int = Field(0, description="Total URLs found during crawling")
    total_urls_processed: int = Field(0, description="Total URLs successfully processed")
    total_urls_failed: int = Field(0, description="Total URLs that failed to process")
    total_content_stored: int = Field(0, description="Total bytes of content stored")
    queue_depth: int = Field(0, description="Current number of URLs in queue")
    start_time: Optional[datetime] = Field(None, description="When crawling started")
    end_time: Optional[datetime] = Field(None, description="When crawling completed")
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.total_urls_processed + self.total_urls_failed == 0:
            return 0.0
        return (self.total_urls_processed / (self.total_urls_processed + self.total_urls_failed)) * 100
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate duration in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


class CrawlConfiguration(BaseModel):
    """Configuration settings for the crawler"""
    target_domain: str = Field("kwbridge.com", description="Domain to crawl")
    max_depth: int = Field(2, description="Maximum crawl depth")
    max_retries: int = Field(1, description="Maximum retry attempts per URL")
    request_timeout: int = Field(30, description="Request timeout in seconds")
    user_agent: str = Field("BridgeLambdas-WebCrawler/1.0", description="User agent string")
    bucket_name: str = Field("bridge-lambdas-crawler-html-2024", description="S3 bucket name")
    table_name: str = Field("crawler-metadata", description="DynamoDB table name")
    queue_url: Optional[str] = Field(None, description="SQS queue URL")
    
    @validator('max_depth')
    def validate_max_depth(cls, v):
        if v < 0:
            raise ValueError("Max depth cannot be negative")
        return v
    
    @validator('max_retries')
    def validate_max_retries(cls, v):
        if v < 0:
            raise ValueError("Max retries cannot be negative")
        return v


class CrawlRequest(BaseModel):
    """Request to start a crawl operation"""
    start_url: str = Field(..., description="URL to start crawling from")
    max_depth: Optional[int] = Field(None, description="Override max depth")
    force_recrawl: bool = Field(False, description="Force recrawl of already visited URLs")
    
    @validator('start_url')
    def validate_start_url(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("Start URL must be a non-empty string")
        return v


class CrawlResponse(BaseModel):
    """Response from crawl operation"""
    message: str = Field(..., description="Response message")
    processed_count: int = Field(0, description="Number of URLs processed")
    statistics: Optional[CrawlStatistics] = Field(None, description="Crawl statistics")
    errors: List[str] = Field(default_factory=list, description="List of errors encountered")
