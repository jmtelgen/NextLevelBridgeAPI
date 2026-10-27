"""Credential-safe auth handlers, using only in-memory collaborators."""
import json
import logging
import sys
from unittest.mock import MagicMock, patch

import pytest
import tests as project_tests

# Account creation's legacy path append must not expose lambdas/tests as tests.
with patch.object(sys, 'path', sys.path.copy()):
    from lambdas.api.auth import account_create, account_login, account_logout, account_refresh_token
    from lambdas.shared.security import auth_middleware
    from lambdas.shared.security.password_utils import PasswordUtils


@pytest.fixture
def account(monkeypatch):
    table = MagicMock()
    table.scan.return_value = {'Count': 0, 'Items': []}
    resource = MagicMock()
    resource.Table.return_value = table
    monkeypatch.setattr(account_create.boto3, 'resource', lambda *a, **kw: resource)
    monkeypatch.setenv('USER_TABLE', 'in-memory-users')
    return table


def invoke(handler, data):
    return handler({'body': json.dumps(data), 'headers': {
        'Authorization': 'Bearer header-secret', 'Cookie': 'refresh_token=cookie-secret',
    }}, None)


@pytest.mark.parametrize('password', [
    '', 'Ab1!abc', 'ABCDEFG1!', 'abcdefg1!', 'Abcdefgh!', 'Abcdefg1/',
    'a' * 125 + 'A1!x',
])
def test_signup_rejects_weak_passwords_without_logging(account, password, capsys, caplog):
    result = invoke(account_create.lambda_handler, {
        'username': 'private-user', 'email': 'private@example.test', 'password': password,
    })
    assert result['statusCode'] == 400
    account.put_item.assert_not_called()
    logs = capsys.readouterr().out + caplog.text
    for secret in ['private-user', 'private@example.test', 'header-secret', 'cookie-secret', password]:
        if secret:
            assert secret not in logs


@pytest.mark.parametrize('password', ['Abcdef1!', 'a' * 125 + 'A1!', 'Abcdef1?'])
def test_valid_password_boundaries_signup_login_and_safe_logs(account, password, monkeypatch, capsys, caplog):
    caplog.set_level(logging.INFO)
    payload = {'username': 'private-user', 'email': 'private@example.test', 'password': password}
    created = invoke(account_create.lambda_handler, payload)
    assert created['statusCode'] == 201
    stored = account.put_item.call_args.kwargs['Item']
    assert PasswordUtils.verify_password(password, stored['passwordHash'], stored['salt'])
    assert 'passwordHash' not in json.loads(created['body'])['user']
    account.scan.return_value = {'Count': 1, 'Items': [stored]}
    duplicate = invoke(account_create.lambda_handler, payload)
    assert duplicate['statusCode'] == 409
    assert 'already exists' in json.loads(duplicate['body'])['message']
    jwt = MagicMock()
    jwt.generate_access_token.return_value = 'access-secret'
    jwt.generate_refresh_token.return_value = 'refresh-secret'
    monkeypatch.setattr(account_login, 'JWTUtils', lambda: jwt)
    logged_in = invoke(account_login.lambda_handler, payload)
    assert logged_in['statusCode'] == 200
    assert 'HttpOnly' in logged_in['multiValueHeaders']['Set-Cookie'][0]
    bad_login = invoke(account_login.lambda_handler, {**payload, 'password': 'Wrong123!'})
    assert bad_login['statusCode'] == 401
    logs = capsys.readouterr().out + caplog.text
    for secret in [*payload.values(), stored['passwordHash'], stored['salt'],
                   'access-secret', 'refresh-secret', 'cookie-secret', 'header-secret']:
        assert secret not in logs


@pytest.mark.parametrize('data', [
    [], None, 'invalid', {'username': [], 'email': 'a@b.test', 'password': 'Strong123!'},
    {'username': 'valid', 'email': 12, 'password': 'Strong123!'},
    {'username': 'valid', 'email': 'a@b.test', 'password': 42},
    {'username': 'ab', 'email': 'a@b.test', 'password': 'Strong123!'},
    {'username': 'valid', 'email': 'invalid', 'password': 'Strong123!'},
])
def test_signup_invalid_payload_is_client_error(account, data):
    result = invoke(account_create.lambda_handler, data)
    assert result['statusCode'] == 400
    assert json.loads(result['body'])['message']
    account.put_item.assert_not_called()


@pytest.mark.parametrize('production', [True, False])
def test_logout_expires_matching_cookie_without_revocation_claim(monkeypatch, production):
    monkeypatch.setenv('ENVIRONMENT', 'production' if production else 'development')
    monkeypatch.setenv('FRONTEND_URL', 'https://bridge.example.test')
    result = account_logout.lambda_handler({'headers': {'Cookie': 'refresh_token=secret'}}, None)
    cookie = result['multiValueHeaders']['Set-Cookie'][0]
    assert result['statusCode'] == 200
    assert all(value in cookie for value in ['refresh_token=;', 'Path=/', 'HttpOnly', 'Max-Age=0', 'SameSite=Strict', 'Expires='])
    assert ('Secure' in cookie) == production
    assert 'secret' not in json.dumps(result)
    assert result['headers']['Access-Control-Allow-Credentials'] == 'true'


@pytest.mark.parametrize('success', [True, False])
def test_refresh_never_logs_credentials_or_reissues_cookie(monkeypatch, success, capsys, caplog):
    caplog.set_level(logging.INFO)
    jwt = MagicMock()
    if success:
        jwt.refresh_access_token.return_value = 'new-access-secret'
    else:
        jwt.refresh_access_token.side_effect = ValueError('private-cookie-secret')
    monkeypatch.setattr(account_refresh_token, 'JWTUtils', lambda: jwt)
    result = account_refresh_token.lambda_handler({
        'headers': {'Cookie': 'refresh_token=private-cookie-secret', 'Authorization': 'Bearer header-secret'},
        'body': '{}',
    }, None)
    assert result['statusCode'] == (200 if success else 401)
    assert 'Set-Cookie' not in result['headers']
    logs = capsys.readouterr().out + caplog.text
    assert 'private-cookie-secret' not in logs
    assert 'new-access-secret' not in logs
    assert 'header-secret' not in logs


def test_shared_auth_logging_drops_raw_request_and_auth_headers(caplog):
    caplog.set_level(logging.INFO)
    with pytest.raises(Exception, match='Invalid Authorization header format'):
        auth_middleware.get_user_from_event({'headers': {'Authorization': 'private-header-secret'}})
    auth_middleware.log_auth_event('failure', {
        'request_id': 'test-id', 'error_type': 'invalid_token',
        'error_message': 'private-error-secret', 'body': 'private-password-secret',
        'headers': {'Cookie': 'private-cookie-secret'},
    })
    assert 'invalid_token' in caplog.text
    for secret in ['private-header-secret', 'private-error-secret', 'private-password-secret', 'private-cookie-secret']:
        assert secret not in caplog.text
