import pytest
from lambdas import room_create
import json
import os
from unittest.mock import patch, MagicMock

@patch('lambdas.room_create.boto3')
def test_room_create_success(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    mock_table = MagicMock()
    mock_boto3.resource.return_value.Table.return_value = mock_table
    mock_table.put_item.return_value = {}
    event = {'body': json.dumps({'ownerId': 'user-123', 'playerName': 'TestPlayer', 'roomName': 'TestRoom'})}
    response = room_create.handler(event, None)
    assert response['statusCode'] == 201
    body = json.loads(response['body'])
    assert 'room' in body
    room = body['room']
    assert room['ownerId'] == 'user-123'
    assert room['state'] == 'waiting'
    assert set(room['seats'].keys()) == {'N', 'E', 'S', 'W'}
    assert 'gameData' in room
    
    # Verify that all seats are filled (either with owner or robots)
    seats = room['seats']
    assert 'user-123' in seats.values()
    robot_count = sum(1 for occupant in seats.values() if occupant.startswith('robot-'))
    assert robot_count == 3  # Should have 3 robots

@patch('lambdas.room_create.boto3')
def test_room_create_robot_assignment(mock_boto3):
    os.environ['ROOM_TABLE'] = 'rooms-table'
    mock_table = MagicMock()
    mock_boto3.resource.return_value.Table.return_value = mock_table
    mock_table.put_item.return_value = {}
    event = {'body': json.dumps({'ownerId': 'user-123', 'playerName': 'TestPlayer', 'roomName': 'TestRoom'})}
    response = room_create.handler(event, None)
    assert response['statusCode'] == 201
    body = json.loads(response['body'])
    room = body['room']
    seats = room['seats']
    
    # Verify robot naming convention
    for seat, occupant in seats.items():
        if occupant.startswith('robot-'):
            assert occupant == f'robot-{seat}'

def test_room_create_missing_owner():
    os.environ['ROOM_TABLE'] = 'rooms-table'
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
    event = {'body': json.dumps({'ownerId': 'user-123', 'playerName': 'TestPlayer', 'roomName': 'TestRoom'})}
    response = room_create.handler(event, None)
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'ROOM_TABLE' in body['error'] 