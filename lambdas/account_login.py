import json
import os
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
        table_name = os.environ.get('USER_TABLE')
        if not table_name:
            return {'statusCode': 500, 'body': json.dumps({'error': 'USER_TABLE environment variable not set'})}
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        # Query for user by username
        result = table.scan(
            FilterExpression='username = :u',
            ExpressionAttributeValues={':u': username}
        )
        if result['Count'] == 0:
            return {'statusCode': 401, 'body': json.dumps({'error': 'Invalid username or password'})}
        user_item = result['Items'][0]
        if not bcrypt.verify(password, user_item['passwordHash']):
            return {'statusCode': 401, 'body': json.dumps({'error': 'Invalid username or password'})}
        user = User(**user_item)
        user_dict = user.dict()
        user_dict.pop('passwordHash')
        return {'statusCode': 200, 'body': json.dumps({'user': user_dict})}
    except ClientError as e:
        return {'statusCode': 500, 'body': json.dumps({'error': e.response['Error']['Message']})}
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})} 