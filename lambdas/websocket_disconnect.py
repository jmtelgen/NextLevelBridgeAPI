import json
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime

def lambda_handler(event, context):
    """
    WebSocket $disconnect handler
    Removes connection information from DynamoDB table
    
    Expected event structure:
    {
        "requestContext": {
            "connectionId": "connection-uuid",
            "routeKey": "$disconnect",
            "requestTimeEpoch": 1234567890
        }
    }
    """
    try:
        # Extract connection information
        connection_id = event.get('requestContext', {}).get('connectionId')
        request_time = event.get('requestContext', {}).get('requestTimeEpoch')
        
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
        
        # Remove connection from DynamoDB
        connections_table.delete_item(
            Key={
                'connectionId': connection_id
            }
        )
        
        print(f"Connection {connection_id} removed successfully")
        
        # For $disconnect, we don't need to return a response to the client
        # The connection is already closed by API Gateway
        print(f"Connection {connection_id} removed successfully")
        
        # Return success without body (API Gateway will handle the disconnection)
        return {
            'statusCode': 200
        }
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            # Connection was already removed or never existed
            print(f"Connection {connection_id} was already removed or never existed")
            return {
                'statusCode': 200
            }
        else:
            print(f"DynamoDB error: {e.response['Error']['Message']}")
            return {
                'statusCode': 500
            }
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500
        } 