import json
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime

def lambda_handler(event, context):
    """
    WebSocket $connect handler
    Stores connection information in DynamoDB table
    
    Expected event structure:
    {
        "requestContext": {
            "connectionId": "connection-uuid",
            "routeKey": "$connect",
            "requestTimeEpoch": 1234567890,
            "identity": {
                "sourceIp": "192.168.1.1",
                "userAgent": "Mozilla/5.0..."
            }
        },
        "queryStringParameters": {
            "userId": "user-id",
            "userName": "User Name"
        }
    }
    """
    try:
        # Extract connection information
        connection_id = event.get('requestContext', {}).get('connectionId')
        request_time = event.get('requestContext', {}).get('requestTimeEpoch')
        source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp')
        user_agent = event.get('requestContext', {}).get('identity', {}).get('userAgent')
        
        # Extract user information from query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        user_id = query_params.get('userId')
        user_name = query_params.get('userName')
        
        print(f"Connection {connection_id} received for user {user_id}")
        
        if not connection_id:
            return {
                'statusCode': 400
            }
        
        # Get DynamoDB table name from environment
        connections_table_name = os.environ.get('WEBSOCKET_CONNECTIONS_TABLE')
        if not connections_table_name:
            return {
                'statusCode': 500
            }
        
        # Create DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        connections_table = dynamodb.Table(connections_table_name)
        
        # Prepare connection record
        connection_record = {
            'connectionId': connection_id,
            'connectedAt': request_time or int(datetime.now().timestamp() * 1000),
            'sourceIp': source_ip or 'unknown',
            'userAgent': user_agent or 'unknown',
            'status': 'connected',
            'lastActivity': request_time or int(datetime.now().timestamp() * 1000),
            'userId': user_id,
            'userName': user_name,
            'currentRoomId': None  # Will be set when user joins a room
        }
        
        # Store connection in DynamoDB
        connections_table.put_item(Item=connection_record)
        
        print(f"Connection {connection_id} stored successfully")
        
        # For $connect, we don't need to return a response to the client
        # The connection is established automatically by API Gateway
        print(f"Connection {connection_id} stored successfully")
        
        # Return success without body (API Gateway will handle the connection)
        return {
            'statusCode': 200
        }
        
    except ClientError as e:
        print(f"DynamoDB error: {e.response['Error']['Message']}")
        return {
            'statusCode': 500
        }
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500
        } 