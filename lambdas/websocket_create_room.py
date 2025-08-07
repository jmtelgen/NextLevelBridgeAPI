import json
import uuid
import os
import random
import boto3
from botocore.exceptions import ClientError

def update_user_room(user_id, room_id):
    """
    Update the user's current room in the connections table
    """
    try:
        connections_table_name = os.environ.get('WEBSOCKET_CONNECTIONS_TABLE')
        if not connections_table_name:
            return
        
        dynamodb = boto3.resource('dynamodb')
        connections_table = dynamodb.Table(connections_table_name)
        
        # Find the user's connection and update their current room
        print(f"Attempting to scan connections table for user {user_id}")
        try:
            response = connections_table.scan(
                FilterExpression='#userId = :userId AND #status = :status',
                ExpressionAttributeNames={
                    '#userId': 'userId',
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':userId': user_id,
                    ':status': 'connected'
                }
            )
            print(f"Scan completed successfully")
        except ClientError as e:
            print(f"Scan failed with ClientError: {e.response['Error']['Message']}")
            return
        except Exception as e:
            print(f"Scan failed with unexpected error: {str(e)}")
            return
        
        print(f"Found {response.get('Count', 0)} connections for user {user_id}")
        if response.get('Items'):
            print(f"Connection items: {response.get('Items')}")
        
        for item in response.get('Items', []):
            connection_id = item.get('connectionId')
            if not connection_id:
                print(f"Warning: connectionId is missing or empty for user {user_id}")
                continue
            
            # Ensure connectionId is a string and not empty
            if not isinstance(connection_id, str) or not connection_id.strip():
                print(f"Warning: connectionId is not a valid string for user {user_id}: {connection_id}")
                continue
                
            try:
                # Since currentRoomId is the sort key, we need to delete the old item and create a new one
                old_key = {'connectionId': connection_id, 'currentRoomId': item.get('currentRoomId', 'not-joined')}
                print(f"Attempting to delete old connection with key: {old_key}")
                
                # Delete the old item
                connections_table.delete_item(Key=old_key)
                
                # Create new item with updated currentRoomId
                new_item = item.copy()
                new_item['currentRoomId'] = room_id
                print(f"Creating new connection item with currentRoomId: {room_id}")
                
                connections_table.put_item(Item=new_item)
                print(f"Updated user {user_id} current room to {room_id}")
            except ClientError as e:
                print(f"Error updating connection {connection_id}: {e.response['Error']['Message']}")
                # Continue with other connections even if one fails
                continue
            
    except Exception as e:
        print(f"Error updating user room: {str(e)}")

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
        
        # Update the user's connection record to reflect they're now in the room
        update_user_room(owner_id, room_id)
        
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