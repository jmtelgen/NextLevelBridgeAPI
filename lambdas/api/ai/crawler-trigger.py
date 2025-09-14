"""
Manual trigger mechanism for starting web crawler
This Lambda function can be invoked manually to start crawling by adding URLs to the SQS queue
"""

import json
import boto3
import logging
from typing import List, Dict, Any
from lambdas.models.crawler_models import CrawlRequest, CrawlResponse, CrawlStatistics

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
sqs_client = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')

# Configuration - using environment variables
import os

QUEUE_URL = os.environ.get('QUEUE_URL')
TABLE_NAME = os.environ.get('TABLE_NAME', 'crawler-metadata')

# Validate required environment variables
if not QUEUE_URL:
    raise ValueError("QUEUE_URL environment variable is required")


def start_crawl(start_url: str, force_recrawl: bool = False) -> Dict[str, Any]:
    """
    Start a crawl by adding the starting URL to the SQS queue
    
    Args:
        start_url: URL to start crawling from
        force_recrawl: Whether to recrawl already visited URLs
        
    Returns:
        Response dictionary with status and details
    """
    try:
        # Validate URL
        if not start_url.startswith('http'):
            return {
                'status': 'error',
                'message': 'URL must start with http:// or https://'
            }
        
        # Check if already crawled (unless force_recrawl)
        if not force_recrawl:
            table = dynamodb.Table(TABLE_NAME)
            response = table.get_item(Key={'url': start_url})
            if 'Item' in response:
                return {
                    'status': 'already_crawled',
                    'message': f'URL {start_url} has already been crawled. Use force_recrawl=true to recrawl.',
                    'crawl_info': response['Item']
                }
        
        # Add URL to SQS queue
        message_body = {
            'url': start_url,
            'parent_url': None,
            'depth': 0,
            'retry_count': 0
        }
        
        sqs_client.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message_body)
        )
        
        logger.info(f"Added starting URL to queue: {start_url}")
        
        return {
            'status': 'success',
            'message': f'Crawl started for {start_url}',
            'queue_url': QUEUE_URL
        }
        
    except Exception as e:
        logger.error(f"Error starting crawl: {e}")
        return {
            'status': 'error',
            'message': f'Failed to start crawl: {str(e)}'
        }


def get_crawl_status() -> Dict[str, Any]:
    """
    Get current status of the crawl operation
    
    Returns:
        Dictionary with crawl statistics and status
    """
    try:
        # Get queue attributes
        queue_attrs = sqs_client.get_queue_attributes(
            QueueUrl=QUEUE_URL,
            AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
        )
        
        queue_depth = int(queue_attrs['Attributes']['ApproximateNumberOfMessages'])
        processing_count = int(queue_attrs['Attributes']['ApproximateNumberOfMessagesNotVisible'])
        
        # Get DynamoDB statistics
        table = dynamodb.Table(TABLE_NAME)
        scan_response = table.scan(Select='COUNT')
        total_crawled = scan_response['Count']
        
        # Get detailed statistics
        response = table.scan()
        items = response.get('Items', [])
        
        success_count = len([item for item in items if item.get('status') == 'success'])
        error_count = len([item for item in items if item.get('status') == 'error'])
        total_content = sum(item.get('content_length', 0) for item in items)
        
        return {
            'status': 'success',
            'statistics': {
                'queue_depth': queue_depth,
                'processing_count': processing_count,
                'total_crawled': total_crawled,
                'success_count': success_count,
                'error_count': error_count,
                'total_content_bytes': total_content,
                'is_complete': queue_depth == 0 and processing_count == 0
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting crawl status: {e}")
        return {
            'status': 'error',
            'message': f'Failed to get crawl status: {str(e)}'
        }


def clear_crawl_data() -> Dict[str, Any]:
    """
    Clear all crawl data from DynamoDB and S3
    WARNING: This will delete all crawled data!
    
    Returns:
        Response dictionary with status
    """
    try:
        # Clear DynamoDB table
        table = dynamodb.Table(TABLE_NAME)
        
        # Get all items
        scan_response = table.scan()
        items = scan_response.get('Items', [])
        
        # Delete all items
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={'url': item['url']})
        
        return {
            'status': 'success',
            'message': f'Cleared {len(items)} records from DynamoDB',
            'note': 'S3 files were not deleted - delete manually if needed'
        }
        
    except Exception as e:
        logger.error(f"Error clearing crawl data: {e}")
        return {
            'status': 'error',
            'message': f'Failed to clear crawl data: {str(e)}'
        }


def lambda_handler(event, context):
    """
    Lambda handler for manual crawler trigger
    
    Expected event format:
    {
        "action": "start_crawl" | "get_status" | "clear_data",
        "start_url": "https://kwbridge.com/",  // Required for start_crawl
        "force_recrawl": false                 // Optional for start_crawl
    }
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    action = event.get('action', '').lower()
    
    try:
        if action == 'start_crawl':
            start_url = event.get('start_url')
            force_recrawl = event.get('force_recrawl', False)
            
            if not start_url:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'status': 'error',
                        'message': 'start_url is required for start_crawl action'
                    })
                }
            
            result = start_crawl(start_url, force_recrawl)
            
        elif action == 'get_status':
            result = get_crawl_status()
            
        elif action == 'clear_data':
            result = clear_crawl_data()
            
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'status': 'error',
                    'message': f'Invalid action: {action}. Valid actions are: start_crawl, get_status, clear_data'
                })
            }
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'message': f'Unexpected error: {str(e)}'
            })
        }
