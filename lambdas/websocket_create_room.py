import json
import uuid
import os
import random
import boto3
from botocore.exceptions import ClientError

def lambda_handler(event, context):
    """
    WebSocket handler for creating a room
    Expected event structure:
    {
        "requestContext": {
            "connectionId": "connection-id",
            "routeKey": "$connect" | "$disconnect" | "createRoom"
        },
        "body": "{\"ownerId\": \"user-id\", \"playerName\": \"Player Name\", \"roomName\": \"Room Name\", \"isPrivate\": false}"
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
        elif route_key != 'createRoom':
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
        
        # Extract data from the nested data object
        data = body.get('data', {})
        
        # Validate required fields
        owner_id = data.get('ownerId')
        player_name = data.get('playerName')
        room_name = data.get('roomName')
        is_private = data.get('isPrivate', False)  # Default to public if not specified
        
        if not owner_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'ownerId required'})
            }
        if not player_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'playerName required'})
            }
        if not room_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'roomName required'})
            }
        
        # Generate room ID
        room_id = str(uuid.uuid4())
        
        # Initialize seats
        seats = {seat: '' for seat in ['N', 'E', 'S', 'W']}
        owner_seat = random.choice(['N', 'E', 'S', 'W'])
        seats[owner_seat] = owner_id
        
        # Set initial state
        state = 'waiting'
        
        # Initialize game data
        game_data = {
            'currentPhase': 'waiting',
            'turn': owner_id,
            'bids': [],
            'hands': {seat: [] for seat in ['N', 'E', 'S', 'W']},
            'tricks': []
        }
        
        # Create room object
        room = {
            'roomId': room_id,
            'ownerId': owner_id,
            'playerName': player_name,
            'roomName': room_name,
            'isPrivate': is_private,
            'seats': seats,
            'state': state,
            'gameData': game_data
        }
        
        # Save to DynamoDB
        room_table_name = os.environ.get('ROOM_TABLE')
        if not room_table_name:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'ROOM_TABLE environment variable not set'})
            }
        
        dynamodb = boto3.resource('dynamodb')
        room_table = dynamodb.Table(room_table_name)
        room_table.put_item(Item=room)
        
        # Return success response with game state
        response_data = {
            'action': 'createRoom',
            'success': True,
            'room': room,
            'assignedSeat': owner_seat,
            'gameState': game_data,
            'message': 'Room created successfully'
        }
        
        return {
            'statusCode': 201,
            'body': json.dumps(response_data)
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