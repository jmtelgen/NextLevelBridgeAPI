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
        
        # First, find all connection records for this connection ID
        # Since currentRoomId is the sort key, we need to find all items with this connectionId
        response = connections_table.query(
            KeyConditionExpression='connectionId = :connectionId',
            ExpressionAttributeValues={
                ':connectionId': connection_id
            }
        )
        
        deleted_count = 0
        for item in response.get('Items', []):
            current_room_id = item.get('currentRoomId', 'not-joined')
            
            try:
                # Delete each connection record with its specific sort key
                connections_table.delete_item(
                    Key={
                        'connectionId': connection_id,
                        'currentRoomId': current_room_id
                    }
                )
                deleted_count += 1
                print(f"Deleted connection record: {connection_id} with room: {current_room_id}")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    # Item was already deleted
                    print(f"Connection record {connection_id} with room {current_room_id} was already deleted")
                else:
                    print(f"Error deleting connection record {connection_id} with room {current_room_id}: {e.response['Error']['Message']}")
        
        print(f"Connection {connection_id} cleanup completed. Deleted {deleted_count} records.")
        
        # For $disconnect, we don't need to return a response to the client
        # The connection is already closed by API Gateway
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