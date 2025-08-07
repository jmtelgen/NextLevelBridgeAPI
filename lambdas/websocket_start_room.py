import json
import os
import boto3
from botocore.exceptions import ClientError

SEATS = ['N', 'E', 'S', 'W']

def lambda_handler(event, context):
    """
    WebSocket handler for starting a room/game
    Expected event structure:
    {
        "requestContext": {
            "connectionId": "connection-id",
            "routeKey": "$connect" | "$disconnect" | "startRoom"
        },
        "body": "{\"roomId\": \"room-id\", \"userId\": \"user-id\"}"
    }
    """
    try:
        # Extract connection ID for potential future use
        connection_id = event.get('requestContext', {}).get('connectionId')
        route_key = event.get('requestContext', {}).get('routeKey')
        
        # Handle different route keys
        if route_key == '$connect':
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Connected'})
            }
        elif route_key == '$disconnect':
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Disconnected'})
            }
        elif route_key != 'startRoom':
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid route key'})
            }
        
        # Parse the message body
        body = event.get('body')
        if not body:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing request body'})
            }
        
        if isinstance(body, str):
            body = json.loads(body)
        
        # Extract parameters
        user_id = body.get('userId')
        room_id = body.get('roomId')
        
        if not user_id or not room_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'userId and roomId required'})
            }
        
        # Check user existence
        user_table_name = os.environ.get('USER_TABLE')
        if not user_table_name:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'USER_TABLE environment variable not set'})
            }
        
        dynamodb = boto3.resource('dynamodb')
        user_table = dynamodb.Table(user_table_name)
        
        # Use get_item instead of scan for better performance
        user_result = user_table.get_item(Key={'username': user_id})
        
        if 'Item' not in user_result:
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'User is not logged in or does not exist'})
            }
        
        # Fetch room
        room_table_name = os.environ.get('ROOM_TABLE')
        if not room_table_name:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'ROOM_TABLE environment variable not set'})
            }
        
        room_table = dynamodb.Table(room_table_name)
        room_result = room_table.get_item(Key={'roomId': room_id})
        
        if 'Item' not in room_result:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Room does not exist'})
            }
        
        room_item = room_result['Item']
        
        # Check owner
        if room_item['ownerId'] != user_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Only the room owner can start the game'})
            }
        
        # Check state
        if room_item['state'] != 'waiting':
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Room is not in waiting state'})
            }
        
        # All seats should already be filled (either with humans or robots)
        # Update room state to bidding
        room_item['state'] = 'bidding'
        
        # Initialize game data if not present
        if 'gameData' not in room_item:
            room_item['gameData'] = {
                'currentPhase': 'bidding',
                'turn': room_item['ownerId'],
                'bids': [],
                'hands': {seat: [] for seat in SEATS},
                'tricks': []
            }
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'action': 'startRoom',
                'success': True,
                'room': room_item,
                'message': 'Game started successfully'
            })
        }
        
    except ClientError as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': e.response['Error']['Message']})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        } 