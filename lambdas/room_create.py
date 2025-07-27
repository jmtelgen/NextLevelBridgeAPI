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
        owner_id = body.get('ownerId')
        if not owner_id:
            return {'statusCode': 400, 'body': json.dumps({'error': 'ownerId required'})}
        # Check if ownerId exists in users table
        user_table_name = os.environ.get('USER_TABLE')
        if not user_table_name:
            return {'statusCode': 500, 'body': json.dumps({'error': 'USER_TABLE environment variable not set'})}
        dynamodb = boto3.resource('dynamodb')
        user_table = dynamodb.Table(user_table_name)
        user_result = user_table.scan(
            FilterExpression='userId = :u',
            ExpressionAttributeValues={':u': owner_id}
        )
        if user_result['Count'] == 0:
            return {'statusCode': 401, 'body': json.dumps({'error': 'Owner is not logged in or does not exist'})}
        # Proceed with room creation
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
            seats=seats,
            state=state,
            gameData=game_data.model_dump()
        )
        room_table_name = os.environ.get('ROOM_TABLE')
        if not room_table_name:
            return {'statusCode': 500, 'body': json.dumps({'error': 'ROOM_TABLE environment variable not set'})}
        room_table = dynamodb.Table(room_table_name)
        room_table.put_item(Item=room.model_dump())
        return {'statusCode': 201, 'body': json.dumps({'room': room.model_dump()})}
    except ClientError as e:
        return {'statusCode': 500, 'body': json.dumps({'error': e.response['Error']['Message']})}
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})} 