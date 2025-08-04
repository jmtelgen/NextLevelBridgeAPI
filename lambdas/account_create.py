import json
import uuid
import os
from datetime import datetime, timezone
from passlib.hash import bcrypt
from models.user import User
import boto3
from botocore.exceptions import ClientError

def handler(event, context):
    try:
        body = event.get('body')
        if body is None:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Missing request body'})}
        if isinstance(body, str):
            body = json.loads(body)
        username = body.get('username')
        password = body.get('password')
        if not username or not password:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Username and password required'})}
        user_id = str(uuid.uuid4())
        password_hash = bcrypt.hash(password)
        created_at = datetime.now(timezone.utc).isoformat()
        user = User(userId=user_id, username=username, passwordHash=password_hash, createdAt=created_at)
        # DynamoDB storage
        table_name = os.environ.get('USER_TABLE')
        if not table_name:
            return {'statusCode': 500, 'body': json.dumps({'error': 'USER_TABLE environment variable not set'})}
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        # Check if username already exists
        existing = table.scan(
            FilterExpression='username = :u',
            ExpressionAttributeValues={':u': username}
        )
        if existing['Count'] > 0:
            return {'statusCode': 409, 'body': json.dumps({'error': 'Username already exists'})}
        table.put_item(Item=user.dict())
        user_dict = user.dict()
        user_dict.pop('passwordHash')
        return {'statusCode': 201, 'body': json.dumps({'user': user_dict})}
    except ClientError as e:
        return {'statusCode': 500, 'body': json.dumps({'error': e.response['Error']['Message']})}
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})} 