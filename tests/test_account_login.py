import pytest
from lambdas import account_login
import json
import os
from unittest.mock import patch, MagicMock
from passlib.hash import bcrypt

@patch('lambdas.account_login.boto3')
def test_account_login_success(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    password = 'testpass'
    password_hash = bcrypt.hash(password)
    user_item = {
        'userId': '123',
        'username': 'jacob',
        'passwordHash': password_hash,
        'createdAt': '2024-01-01T00:00:00Z'
    }
    mock_table = MagicMock()
    mock_boto3.resource.return_value.Table.return_value = mock_table
    mock_table.scan.return_value = {'Count': 1, 'Items': [user_item]}
    event = {'body': json.dumps({'username': 'jacob', 'password': password})}
    response = account_login.handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'user' in body
    user = body['user']
    assert user['username'] == 'jacob'
    assert 'userId' in user
    assert 'createdAt' in user
    assert 'passwordHash' not in user

@patch('lambdas.account_login.boto3')
def test_account_login_wrong_password(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    password_hash = bcrypt.hash('correctpass')
    user_item = {
        'userId': '123',
        'username': 'jacob',
        'passwordHash': password_hash,
        'createdAt': '2024-01-01T00:00:00Z'
    }
    mock_table = MagicMock()
    mock_boto3.resource.return_value.Table.return_value = mock_table
    mock_table.scan.return_value = {'Count': 1, 'Items': [user_item]}
    event = {'body': json.dumps({'username': 'jacob', 'password': 'wrongpass'})}
    response = account_login.handler(event, None)
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Invalid' in body['error']

@patch('lambdas.account_login.boto3')
def test_account_login_user_not_found(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    mock_table = MagicMock()
    mock_boto3.resource.return_value.Table.return_value = mock_table
    mock_table.scan.return_value = {'Count': 0, 'Items': []}
    event = {'body': json.dumps({'username': 'notfound', 'password': 'testpass'})}
    response = account_login.handler(event, None)
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Invalid' in body['error']

def test_account_login_missing_fields():
    os.environ['USER_TABLE'] = 'users-table'
    event = {'body': json.dumps({'username': 'jacob'})}
    response = account_login.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body

    event = {'body': json.dumps({'password': 'testpass'})}
    response = account_login.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body

    event = {'body': None}
    response = account_login.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body 