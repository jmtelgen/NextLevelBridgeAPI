import pytest
from lambdas import room_start
import json
import os
from unittest.mock import patch, MagicMock

@patch('lambdas.room_start.boto3')
def test_room_start_success(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    os.environ['ROOM_TABLE'] = 'rooms-table'
    # Mock user exists
    mock_user_table = MagicMock()
    mock_user_table.scan.return_value = {'Count': 1, 'Items': [{'userId': 'owner-1'}]}
    # Mock room exists with some empty seats
    room_item = {
        'roomId': 'room-abc',
        'ownerId': 'owner-1',
        'seats': {'N': 'owner-1', 'E': '', 'S': '', 'W': 'user-2'},
        'state': 'waiting',
        'gameData': {}
    }
    expected_seats = room_item['seats'].copy()
    for seat in ['E', 'S']:
        expected_seats[seat] = f'robot-{seat}'
    expected_seats['N'] = 'owner-1'
    expected_seats['W'] = 'user-2'
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 1, 'Items': [room_item.copy()]}
    mock_room_table.put_item.return_value = {}
    mock_boto3.resource.return_value.Table.side_effect = [mock_user_table, mock_room_table]
    event = {'body': json.dumps({'userId': 'owner-1', 'roomId': 'room-abc'})}
    response = room_start.handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    room = body['room']
    assert room['state'] == 'bidding'
    assert room['seats'] == expected_seats

@patch('lambdas.room_start.boto3')
def test_room_start_not_owner(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    os.environ['ROOM_TABLE'] = 'rooms-table'
    mock_user_table = MagicMock()
    mock_user_table.scan.return_value = {'Count': 1, 'Items': [{'userId': 'user-2'}]}
    room_item = {
        'roomId': 'room-abc',
        'ownerId': 'owner-1',
        'seats': {'N': 'owner-1', 'E': '', 'S': '', 'W': 'user-2'},
        'state': 'waiting',
        'gameData': {}
    }
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 1, 'Items': [room_item.copy()]}
    mock_boto3.resource.return_value.Table.side_effect = [mock_user_table, mock_room_table]
    event = {'body': json.dumps({'userId': 'user-2', 'roomId': 'room-abc'})}
    response = room_start.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'owner' in body['error']

@patch('lambdas.room_start.boto3')
def test_room_start_not_waiting(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    os.environ['ROOM_TABLE'] = 'rooms-table'
    mock_user_table = MagicMock()
    mock_user_table.scan.return_value = {'Count': 1, 'Items': [{'userId': 'owner-1'}]}
    room_item = {
        'roomId': 'room-abc',
        'ownerId': 'owner-1',
        'seats': {'N': 'owner-1', 'E': '', 'S': '', 'W': 'user-2'},
        'state': 'bidding',
        'gameData': {}
    }
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 1, 'Items': [room_item.copy()]}
    mock_boto3.resource.return_value.Table.side_effect = [mock_user_table, mock_room_table]
    event = {'body': json.dumps({'userId': 'owner-1', 'roomId': 'room-abc'})}
    response = room_start.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'waiting' in body['error']

@patch('lambdas.room_start.boto3')
def test_room_start_user_not_logged_in(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    os.environ['ROOM_TABLE'] = 'rooms-table'
    mock_user_table = MagicMock()
    mock_user_table.scan.return_value = {'Count': 0, 'Items': []}
    mock_boto3.resource.return_value.Table.side_effect = [mock_user_table]
    event = {'body': json.dumps({'userId': 'owner-1', 'roomId': 'room-abc'})}
    response = room_start.handler(event, None)
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'not logged in' in body['error'] or 'does not exist' in body['error']

@patch('lambdas.room_start.boto3')
def test_room_start_room_not_found(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    os.environ['ROOM_TABLE'] = 'rooms-table'
    mock_user_table = MagicMock()
    mock_user_table.scan.return_value = {'Count': 1, 'Items': [{'userId': 'owner-1'}]}
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 0, 'Items': []}
    mock_boto3.resource.return_value.Table.side_effect = [mock_user_table, mock_room_table]
    event = {'body': json.dumps({'userId': 'owner-1', 'roomId': 'room-abc'})}
    response = room_start.handler(event, None)
    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'does not exist' in body['error']

def test_room_start_missing_fields():
    os.environ['USER_TABLE'] = 'users-table'
    os.environ['ROOM_TABLE'] = 'rooms-table'
    event = {'body': json.dumps({'userId': 'owner-1'})}
    response = room_start.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    event = {'body': json.dumps({'roomId': 'room-abc'})}
    response = room_start.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    event = {'body': None}
    response = room_start.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body 