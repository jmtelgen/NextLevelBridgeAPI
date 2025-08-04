import json
import uuid
import os
import random
from models.room import Room
from models.game_state import GameState
import boto3
from botocore.exceptions import ClientError

def handler(event, context):
    try:
        body = event.get('body')
        if body is None:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Missing request body'})}
        if isinstance(body, str):
            body = json.loads(body)
        
        # Validate required fields
        owner_id = body.get('ownerId')
        player_name = body.get('playerName')
        room_name = body.get('roomName')
        is_private = body.get('isPrivate', False)  # Default to public if not specified
        
        if not owner_id:
            return {'statusCode': 400, 'body': json.dumps({'error': 'ownerId required'})}
        if not player_name:
            return {'statusCode': 400, 'body': json.dumps({'error': 'playerName required'})}
        if not room_name:
            return {'statusCode': 400, 'body': json.dumps({'error': 'roomName required'})}
        room_id = str(uuid.uuid4())
        seats = {seat: '' for seat in ['N', 'E', 'S', 'W']}
        owner_seat = random.choice(['N', 'E', 'S', 'W'])
        seats[owner_seat] = owner_id
        state = 'waiting'
        game_data = GameState(
            currentPhase='bidding',
            turn=owner_seat,
            bids=[],
            hands={seat: [] for seat in ['N', 'E', 'S', 'W']},
            tricks=[]
        )
        room = Room(
            roomId=room_id,
            ownerId=owner_id,
            playerName=player_name,
            roomName=room_name,
            isPrivate=is_private,
            seats=seats,
            state=state,
            gameData=game_data.dict()
        )
        room_table_name = os.environ.get('ROOM_TABLE')
        if not room_table_name:
            return {'statusCode': 500, 'body': json.dumps({'error': 'ROOM_TABLE environment variable not set'})}
        dynamodb = boto3.resource('dynamodb')
        room_table = dynamodb.Table(room_table_name)
        room_table.put_item(Item=room.dict())
        return {'statusCode': 201, 'body': json.dumps({'room': room.dict()})}
    except ClientError as e:
        return {'statusCode': 500, 'body': json.dumps({'error': e.response['Error']['Message']})}
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})} 