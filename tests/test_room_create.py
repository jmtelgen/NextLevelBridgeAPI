import pytest
from lambdas import room_create
import json
import os
from unittest.mock import patch, MagicMock

@patch('lambdas.room_create.boto3')
def test_room_create_success(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    os.environ['USER_TABLE'] = 'users-table'
    # Mock user table returns user exists
    mock_user_table = MagicMock()
    mock_user_table.scan.return_value = {'Count': 1, 'Items': [{'userId': 'user-123'}]}
    # Mock room table
    mock_room_table = MagicMock()
    mock_room_table.put_item.return_value = {}
    # boto3.resource().Table() returns user table first, then room table
    mock_boto3.resource.return_value.Table.side_effect = [mock_user_table, mock_room_table]
    event = {'body': json.dumps({'ownerId': 'user-123'})}
    response = room_create.handler(event, None)
    assert response['statusCode'] == 201
    body = json.loads(response['body'])
    assert 'room' in body
    room = body['room']
    assert room['ownerId'] == 'user-123'
    assert room['state'] == 'waiting'
    assert set(room['seats'].keys()) == {'N', 'E', 'S', 'W'}
    assert 'gameData' in room
    assert 'user-123' in room['seats'].values()

@patch('lambdas.room_create.boto3')
def test_room_create_owner_not_logged_in(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    os.environ['USER_TABLE'] = 'users-table'
    # Mock user table returns no user
    mock_user_table = MagicMock()
    mock_user_table.scan.return_value = {'Count': 0, 'Items': []}
    mock_boto3.resource.return_value.Table.side_effect = [mock_user_table]
    event = {'body': json.dumps({'ownerId': 'user-123'})}
    response = room_create.handler(event, None)
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'not logged in' in body['error'] or 'does not exist' in body['error']

@patch('lambdas.room_create.boto3')
def test_room_create_missing_owner(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    os.environ['USER_TABLE'] = 'users-table'
    event = {'body': json.dumps({})}
    response = room_create.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'ownerId' in body['error']

@patch('lambdas.room_create.boto3')
def test_room_create_missing_room_table_env(mock_boto3):
    if 'ROOM_TABLE' in os.environ:
        del os.environ['ROOM_TABLE']
    os.environ['USER_TABLE'] = 'users-table'
    # Mock user table returns user exists
    mock_user_table = MagicMock()
    mock_user_table.scan.return_value = {'Count': 1, 'Items': [{'userId': 'user-123'}]}
    mock_boto3.resource.return_value.Table.side_effect = [mock_user_table]
    event = {'body': json.dumps({'ownerId': 'user-123'})}
    response = room_create.handler(event, None)
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'ROOM_TABLE' in body['error'] 