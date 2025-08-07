import json
import boto3
import os
from botocore.exceptions import ClientError
from typing import Dict, Any, List, Optional

def send_websocket_message(connection_id: str, message: Dict[str, Any]) -> bool:
    """
    Send a message to a specific WebSocket connection using the Management API
    
    Args:
        connection_id: The WebSocket connection ID
        message: The message to send (will be JSON serialized)
    
    Returns:
        True if message sent successfully, False otherwise
    """
    try:
        # Get the WebSocket endpoint from environment
        endpoint_url = os.environ.get('WEBSOCKET_ENDPOINT')
        if not endpoint_url:
            print("WEBSOCKET_ENDPOINT environment variable not set")
            return False
        
        # Create API Gateway Management API client
        apigateway = boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)
        
        # Send the message
        response = apigateway.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message)
        )
        
        print(f"Message sent to connection {connection_id}: {message}")
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'GoneException':
            print(f"Connection {connection_id} is no longer available")
        else:
            print(f"Error sending message to {connection_id}: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        print(f"Unexpected error sending message: {str(e)}")
        return False

def broadcast_to_connections(connection_ids: List[str], message: Dict[str, Any]) -> Dict[str, bool]:
    """
    Send a message to multiple WebSocket connections
    
    Args:
        connection_ids: List of connection IDs
        message: The message to send
    
    Returns:
        Results for each connection (connection_id -> success)
    """
    results = {}
    print(f"Broadcasting to {connection_ids}")
    for connection_id in connection_ids:
        results[connection_id] = send_websocket_message(connection_id, message)
    return results

def get_active_connections() -> List[str]:
    """
    Get all active WebSocket connections from DynamoDB
    
    Returns:
        List of active connection IDs
    """
    try:
        connections_table_name = os.environ.get('WEBSOCKET_CONNECTIONS_TABLE')
        if not connections_table_name:
            print("WEBSOCKET_CONNECTIONS_TABLE environment variable not set")
            return []
        
        dynamodb = boto3.resource('dynamodb')
        connections_table = dynamodb.Table(connections_table_name)
        
        # Scan for active connections
        response = connections_table.scan(
            FilterExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': 'connected'}
        )
        
        return [item['connectionId'] for item in response.get('Items', [])]
        
    except Exception as e:
        print(f"Error getting active connections: {str(e)}")
        return [] 