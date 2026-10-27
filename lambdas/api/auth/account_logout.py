"""Expire the browser refresh cookie; stateless JWTs remain valid until expiry."""
import json
import os


def lambda_handler(event, context):
    cookie = 'refresh_token=; HttpOnly; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Strict'
    if os.environ.get('ENVIRONMENT') == 'production':
        cookie += '; Secure'
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': os.environ.get('FRONTEND_URL', '*'),
            'Access-Control-Allow-Credentials': 'true',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,OPTIONS',
            'Cache-Control': 'no-store',
        },
        'multiValueHeaders': {'Set-Cookie': [cookie]},
        'body': json.dumps({'message': 'Refresh cookie cleared'}),
    }
