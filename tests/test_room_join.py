import pytest
from lambdas import room_join
import json
import os
from unittest.mock import patch, MagicMock

@patch('lambdas.room_join.boto3')
def test_room_join_success_replace_robot(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    # Mock room exists with robots in seats
    room_item = {
        'roomId': 'room-abc',
        'ownerId': 'owner-1',
        'seats': {'N': 'owner-1', 'E': 'robot-E', 'S': 'robot-S', 'W': 'robot-W'},
        'state': 'waiting',
        'gameData': {}
    }
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 1, 'Items': [room_item.copy()]}
    mock_room_table.put_item.return_value = {}
    mock_boto3.resource.return_value.Table.return_value = mock_room_table
    event = {'body': json.dumps({'userId': 'user-123', 'roomId': 'room-abc'})}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'room' in body
    room = body['room']
    assert room['roomId'] == 'room-abc'
    assert 'user-123' in room['seats'].values()
    # Verify that a robot was replaced
    robot_count = sum(1 for occupant in room['seats'].values() if occupant.startswith('robot-'))
    assert robot_count == 2  # Should have 2 robots now

@patch('lambdas.room_join.boto3')
def test_room_join_success_specific_robot_seat(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    room_item = {
        'roomId': 'room-abc',
        'ownerId': 'owner-1',
        'seats': {'N': 'owner-1', 'E': 'robot-E', 'S': 'robot-S', 'W': 'robot-W'},
        'state': 'waiting',
        'gameData': {}
    }
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 1, 'Items': [room_item.copy()]}
    mock_room_table.put_item.return_value = {}
    mock_boto3.resource.return_value.Table.return_value = mock_room_table
    event = {'body': json.dumps({'userId': 'user-123', 'roomId': 'room-abc', 'seat': 'E'})}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    room = body['room']
    assert room['seats']['E'] == 'user-123'

@patch('lambdas.room_join.boto3')
def test_room_join_room_not_found(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 0, 'Items': []}
    mock_boto3.resource.return_value.Table.return_value = mock_room_table
    event = {'body': json.dumps({'userId': 'user-123', 'roomId': 'room-abc'})}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'does not exist' in body['error']

@patch('lambdas.room_join.boto3')
def test_room_join_seat_not_available_human_occupied(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    room_item = {
        'roomId': 'room-abc',
        'ownerId': 'owner-1',
        'seats': {'N': 'owner-1', 'E': 'user-999', 'S': 'robot-S', 'W': 'robot-W'},
        'state': 'waiting',
        'gameData': {}
    }
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 1, 'Items': [room_item.copy()]}
    mock_room_table.put_item.return_value = {}
    mock_boto3.resource.return_value.Table.return_value = mock_room_table
    event = {'body': json.dumps({'userId': 'user-123', 'roomId': 'room-abc', 'seat': 'E'})}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Seat not available' in body['error']

@patch('lambdas.room_join.boto3')
def test_room_join_user_already_in_room(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    room_item = {
        'roomId': 'room-abc',
        'ownerId': 'owner-1',
        'seats': {'N': 'owner-1', 'E': 'user-123', 'S': 'robot-S', 'W': 'robot-W'},
        'state': 'waiting',
        'gameData': {}
    }
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 1, 'Items': [room_item.copy()]}
    mock_boto3.resource.return_value.Table.return_value = mock_room_table
    event = {'body': json.dumps({'userId': 'user-123', 'roomId': 'room-abc'})}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'already in room' in body['error']

@patch('lambdas.room_join.boto3')
def test_room_join_no_seats_available_all_humans(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    room_item = {
        'roomId': 'room-abc',
        'ownerId': 'owner-1',
        'seats': {'N': 'owner-1', 'E': 'user-999', 'S': 'user-888', 'W': 'user-777'},
        'state': 'waiting',
        'gameData': {}
    }
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 1, 'Items': [room_item.copy()]}
    mock_boto3.resource.return_value.Table.return_value = mock_room_table
    event = {'body': json.dumps({'userId': 'user-123', 'roomId': 'room-abc'})}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'No seats available' in body['error']

@patch('lambdas.room_join.boto3')
def test_room_join_success_with_empty_seats(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    # Test backward compatibility with rooms that might have empty seats
    room_item = {
        'roomId': 'room-abc',
        'ownerId': 'owner-1',
        'seats': {'N': 'owner-1', 'E': '', 'S': 'robot-S', 'W': 'robot-W'},
        'state': 'waiting',
        'gameData': {}
    }
    mock_room_table = MagicMock()
    mock_room_table.scan.return_value = {'Count': 1, 'Items': [room_item.copy()]}
    mock_room_table.put_item.return_value = {}
    mock_boto3.resource.return_value.Table.return_value = mock_room_table
    event = {'body': json.dumps({'userId': 'user-123', 'roomId': 'room-abc', 'seat': 'E'})}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    room = body['room']
    assert room['seats']['E'] == 'user-123'

def test_room_join_missing_fields():
    os.environ['ROOM_TABLE'] = 'rooms-table'
    event = {'body': json.dumps({'userId': 'user-123'})}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    event = {'body': json.dumps({'roomId': 'room-abc'})}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    event = {'body': None}
    response = room_join.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body 