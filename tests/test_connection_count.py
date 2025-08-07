import pytest
from lambdas import connection_count
import json
import os
from unittest.mock import patch, MagicMock

@patch('lambdas.connection_count.boto3')
def test_connection_count_success(mock_boto3):
    os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
    
    # Mock DynamoDB table with connections in different rooms and users
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        'Items': [
            {'currentRoomId': 'room-1', 'userId': 'user-1', 'status': 'connected'},
            {'currentRoomId': 'room-1', 'userId': 'user-2', 'status': 'connected'},
            {'currentRoomId': 'room-2', 'userId': 'user-3', 'status': 'connected'},
            {'currentRoomId': 'not-joined', 'userId': 'user-4', 'status': 'connected'},
            {'currentRoomId': 'room-3', 'userId': 'user-5', 'status': 'connected'}
        ]
    }
    mock_boto3.resource.return_value.Table.return_value = mock_table
    
    event = {'httpMethod': 'GET'}
    response = connection_count.handler(event, None)
    
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['activeUserCount'] == 5  # All 5 users are connected
    assert body['activeRoomCount'] == 3  # room-1, room-2, room-3 (excluding 'not-joined')

@patch('lambdas.connection_count.boto3')
def test_connection_count_with_pagination(mock_boto3):
    os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
    
    # Mock DynamoDB table with pagination
    mock_table = MagicMock()
    mock_table.scan.side_effect = [
        {
            'Items': [
                {'currentRoomId': 'room-1', 'userId': 'user-1', 'status': 'connected'},
                {'currentRoomId': 'room-2', 'userId': 'user-2', 'status': 'connected'}
            ],
            'LastEvaluatedKey': 'key1'
        },
        {
            'Items': [
                {'currentRoomId': 'room-2', 'userId': 'user-3', 'status': 'connected'},  # Duplicate room, new user
                {'currentRoomId': 'room-3', 'userId': 'user-4', 'status': 'connected'}
            ],
            'LastEvaluatedKey': 'key2'
        },
        {
            'Items': [
                {'currentRoomId': 'room-4', 'userId': 'user-5', 'status': 'connected'}
            ]
        }
    ]
    mock_boto3.resource.return_value.Table.return_value = mock_table
    
    event = {'httpMethod': 'GET'}
    response = connection_count.handler(event, None)
    
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['activeUserCount'] == 5  # user-1, user-2, user-3, user-4, user-5
    assert body['activeRoomCount'] == 4  # room-1, room-2, room-3, room-4 (unique rooms)

def test_connection_count_wrong_method():
    event = {'httpMethod': 'POST'}
    response = connection_count.handler(event, None)
    
    assert response['statusCode'] == 405
    body = json.loads(response['body'])
    assert 'Method not allowed' in body['error']

def test_connection_count_missing_env_var():
    # Clear the environment variable
    if 'WEBSOCKET_CONNECTIONS_TABLE' in os.environ:
        del os.environ['WEBSOCKET_CONNECTIONS_TABLE']
    
    event = {'httpMethod': 'GET'}
    response = connection_count.handler(event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'WEBSOCKET_CONNECTIONS_TABLE environment variable not set' in body['error']

@patch('lambdas.connection_count.boto3')
def test_connection_count_dynamodb_error(mock_boto3):
    os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
    
    # Mock DynamoDB error
    mock_table = MagicMock()
    mock_table.scan.side_effect = Exception('DynamoDB error')
    mock_boto3.resource.return_value.Table.return_value = mock_table
    
    event = {'httpMethod': 'GET'}
    response = connection_count.handler(event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'Unexpected error' in body['error'] 