"""Signed upgrade/guest-session regressions with an injected test-only JWT key."""
import copy
import json
import time
from unittest.mock import MagicMock

import jwt
import pytest

from lambdas.api.auth import guest_session
from lambdas.api.websocket import websocket_connect
from lambdas.core.game.runtime import connection_user, GameRequestError
from lambdas.shared.security.jwt_utils import JWTUtils
from lambdas.shared.security import socket_auth

KEY = "offline-test-only-signing-key-not-a-production-secret"
ORIGIN = "https://bridge.example.test"


def token(**claims):
    now = int(time.time())
    return jwt.encode({
        "userId": "user-account", "username": "Signed Name",
        "iat": now, "exp": now + 900, "type": "access", **claims,
    }, KEY, algorithm="HS256")


def connect_event(signed_token=None, **query):
    headers = {"Origin": ORIGIN}
    if signed_token is not None:
        headers["Sec-WebSocket-Protocol"] = f"bridge.v1, bridge.auth.{signed_token}"
    return {
        "requestContext": {"routeKey": "$connect", "connectionId": "connection", "requestTimeEpoch": 1234},
        "headers": headers, "queryStringParameters": query,
    }


def guest_event(body=None, bearer=None, method="POST"):
    headers = {"Origin": ORIGIN}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    return {"httpMethod": method, "headers": headers, "body": json.dumps(body or {})}


@pytest.fixture(autouse=True)
def configured_session(monkeypatch):
    monkeypatch.setenv("WS_ALLOWED_ORIGINS", ORIGIN)
    monkeypatch.setattr(JWTUtils, "secret_key", property(lambda self: KEY))
    db = MagicMock()
    db.create_connection_record.return_value = True
    monkeypatch.setattr(websocket_connect, "db_utils", db)
    return db


@pytest.mark.parametrize("kind", ["access", "guest"])
def test_signed_connection_derives_identity_and_echoes_only_public_protocol(configured_session, kind, capsys):
    signed = token(type=kind)
    event = connect_event(signed, userId="user-account", userName="Untrusted name")
    response = websocket_connect.lambda_handler(event, None)
    assert response == {"statusCode": 200, "headers": {"Sec-WebSocket-Protocol": "bridge.v1"}}
    saved = configured_session.create_connection_record.call_args.kwargs
    assert saved["user_id"] == "user-account"
    assert saved["user_name"] == "Signed Name"
    assert saved["auth_type"] == kind
    assert saved["auth_expires_at"] > time.time()
    assert signed not in capsys.readouterr().out
    assert signed not in json.dumps(response)


def test_native_client_bearer_transport(configured_session):
    event = connect_event()
    event["headers"]["Authorization"] = f"Bearer {token()}"
    response = websocket_connect.lambda_handler(event, None)
    assert response == {"statusCode": 200}
    configured_session.create_connection_record.assert_called_once()


@pytest.mark.parametrize("case", [
    "missing", "expired", "tampered", "refresh", "no-exp", "no-iat",
    "future-iat", "robot", "numeric-id", "unsigned", "wrong-key", "duplicate",
])
def test_invalid_or_unsigned_connection_never_creates_record(configured_session, case):
    now = int(time.time())
    signed = token()
    if case == "expired":
        signed = token(iat=now - 100, exp=now - 1)
    elif case == "tampered":
        parts = signed.split(".")
        parts[1] = jwt.utils.base64url_encode(b'{"userId":"victim","type":"access"}').decode()
        signed = ".".join(parts)
    elif case == "refresh":
        signed = token(type="refresh")
    elif case in ("no-exp", "no-iat"):
        claims = jwt.decode(signed, KEY, algorithms=["HS256"])
        del claims["exp" if case == "no-exp" else "iat"]
        signed = jwt.encode(claims, KEY, algorithm="HS256")
    elif case == "future-iat":
        signed = token(iat=now + 60, exp=now + 100)
    elif case == "robot":
        signed = token(userId="ROBOT_North")
    elif case == "numeric-id":
        signed = token(userId=42)
    elif case == "unsigned":
        signed = jwt.encode({"userId": "victim", "exp": now + 100}, "", algorithm="none")
    elif case == "wrong-key":
        signed = jwt.encode({"userId": "victim", "exp": now + 100}, KEY + "wrong", algorithm="HS256")
    event = connect_event(None if case == "missing" else signed, userId="user-account")
    if case == "duplicate":
        event["headers"]["Authorization"] = f"Bearer {signed}"
    response = websocket_connect.lambda_handler(event, None)
    assert response["statusCode"] == 401
    configured_session.create_connection_record.assert_not_called()


def test_mismatched_query_identity_is_rejected(configured_session):
    response = websocket_connect.lambda_handler(connect_event(token(), userId="victim"), None)
    assert response["statusCode"] == 403
    configured_session.create_connection_record.assert_not_called()


@pytest.mark.parametrize("origin", [None, "https://evil.test", "null", ORIGIN + ".evil.test"])
def test_upgrade_origin_is_exact_and_required(configured_session, origin):
    event = connect_event(token())
    if origin is None:
        event["headers"].pop("Origin")
    else:
        event["headers"]["Origin"] = origin
    assert websocket_connect.lambda_handler(event, None)["statusCode"] == 403
    configured_session.create_connection_record.assert_not_called()


def test_missing_or_wildcard_configuration_fails_closed(configured_session, monkeypatch):
    for value in ("", "*", "https://*.example.test", "https://example.test/path",
                  "https://[broken", "https://example.test:bad"):
        monkeypatch.setenv("WS_ALLOWED_ORIGINS", value)
        monkeypatch.delenv("FRONTEND_URL", raising=False)
        assert websocket_connect.lambda_handler(connect_event(token()), None)["statusCode"] == 503
    configured_session.create_connection_record.assert_not_called()


def test_missing_signing_service_fails_closed(configured_session, monkeypatch):
    def unavailable(self):
        raise RuntimeError("Do not expose configuration details")
    monkeypatch.setattr(JWTUtils, "secret_key", property(unavailable))
    response = websocket_connect.lambda_handler(connect_event(token()), None)
    assert response["statusCode"] == 503
    assert "configuration details" not in response["body"]
    configured_session.create_connection_record.assert_not_called()


def test_guest_server_chooses_identity_and_can_authenticate_upgrade(configured_session):
    result = guest_session.lambda_handler(guest_event({"userId": "victim", "username": "Alice"}), None)
    assert result["statusCode"] == 200
    assert result["headers"]["Access-Control-Allow-Origin"] == ORIGIN
    assert result["headers"]["Cache-Control"] == "no-store"
    body = json.loads(result["body"])
    assert body["userId"].startswith("guest_")
    assert body["userId"] != "victim"
    assert body["username"] == "Alice"
    assert body["expiresIn"] == 86400
    assert body["isGuest"] is True
    claims = socket_auth.verify_identity(body["accessToken"])
    assert claims["userId"] == body["userId"]
    assert claims["type"] == "guest"
    assert websocket_connect.lambda_handler(connect_event(body["accessToken"]), None)["statusCode"] == 200
    with pytest.raises(jwt.InvalidTokenError):
        socket_auth.verify_identity(body["accessToken"], allowed_types=("access",))


def test_guest_valid_renewal_preserves_subject_invalid_does_not_downgrade():
    first = json.loads(guest_session.lambda_handler(guest_event(), None)["body"])
    second = guest_session.lambda_handler(
        guest_event({"username": "Updated"}, bearer=first["accessToken"]), None)
    assert second["statusCode"] == 200
    assert json.loads(second["body"])["userId"] == first["userId"]
    assert json.loads(second["body"])["username"] == "Updated"
    now = int(time.time())
    for bad in ("tampered", token(type="access"),
                token(type="guest", iat=now - 100, exp=now - 1)):
        result = guest_session.lambda_handler(guest_event(bearer=bad), None)
        assert result["statusCode"] == 401
        assert "accessToken" not in json.loads(result["body"])


def test_guest_preflight_and_origin_rejection():
    result = guest_session.lambda_handler(guest_event(method="OPTIONS"), None)
    assert result["statusCode"] == 204
    assert result["headers"]["Access-Control-Allow-Credentials"] == "true"
    event = guest_event()
    event["headers"]["Origin"] = "https://evil.test"
    result = guest_session.lambda_handler(event, None)
    assert result["statusCode"] == 403
    assert "Access-Control-Allow-Origin" not in result["headers"]


@pytest.mark.parametrize("username", ["", "x" * 51, "\nGuest", 3])
def test_guest_rejects_invalid_display_names(username):
    assert guest_session.lambda_handler(guest_event({"username": username}), None)["statusCode"] == 400


def test_expired_and_legacy_connection_records_cannot_mutate_game():
    db = MagicMock()
    event = {"requestContext": {"connectionId": "connection"}}
    valid = {"userId": "guest_signed", "status": "connected", "authType": "guest",
             "authExpiresAt": int(time.time()) + 60}
    db.websocket_connections_table.query.return_value = {"Items": [valid]}
    assert connection_user(db, event) == "guest_signed"
    for record in (
        {**valid, "authExpiresAt": int(time.time()) - 1},
        {"userId": "victim", "status": "connected"},
    ):
        db.websocket_connections_table.query.return_value = {"Items": [copy.deepcopy(record)]}
        with pytest.raises(GameRequestError) as error:
            connection_user(db, event)
        assert error.value.status == 401


def test_expired_and_unsigned_sessions_are_excluded_from_private_delivery(monkeypatch):
    import boto3
    try:
        from moto import mock_aws
    except ImportError:
        from moto import mock_dynamodb as mock_aws
    from lambdas.shared.database.db_utils import DatabaseUtils

    monkeypatch.setenv("WEBSOCKET_CONNECTIONS_TABLE", "sessions")
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="sessions", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "connectionId", "KeyType": "HASH"},
                       {"AttributeName": "currentRoomId", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "connectionId", "AttributeType": "S"},
                                  {"AttributeName": "currentRoomId", "AttributeType": "S"}])
        now = int(time.time())
        db = DatabaseUtils()
        assert db.create_connection_record(
            "valid", "guest_signed", "Guest", auth_expires_at=now + 60, auth_type="guest")
        for connection, attributes in (
            ("expired", {"authExpiresAt": now - 1, "authType": "guest"}),
            ("unsigned", {}),
            ("refresh", {"authExpiresAt": now + 60, "authType": "refresh"}),
        ):
            table.put_item(Item={
                "connectionId": connection, "currentRoomId": "not-joined",
                "userId": "guest_signed", "status": "connected", **attributes})
        assert db.get_user_connections("guest_signed") == ["valid"]
        assert db.get_room_connection("guest_signed") == "valid"
        assert db.update_user_room("guest_signed", "room")
        item = table.get_item(Key={"connectionId": "valid", "currentRoomId": "room"})["Item"]
        assert item["authExpiresAt"] == now + 60
        assert item["authType"] == "guest"


def test_account_login_scans_past_unrelated_first_page():
    from lambdas.api.auth.account_login import find_login_user
    table = MagicMock()
    table.scan.side_effect = [
        {"Count": 0, "Items": [], "LastEvaluatedKey": {"userId": "unrelated"}},
        {"Count": 1, "Items": [{"userId": "wanted", "username": "second"}]},
    ]
    result = find_login_user(table, "second")
    assert result["Items"][0]["userId"] == "wanted"
    assert table.scan.call_count == 2
    assert table.scan.call_args_list[1].kwargs["ExclusiveStartKey"] == {"userId": "unrelated"}
    assert all("Limit" not in entry.kwargs for entry in table.scan.call_args_list)


def test_account_login_missing_gsi_falls_back_and_paginates():
    from botocore.exceptions import ClientError
    from lambdas.api.auth.account_login import find_login_user
    table = MagicMock()
    table.scan.side_effect = [
        ClientError({"Error": {"Code": "ValidationException", "Message": "missing index"}}, "Scan"),
        {"Count": 0, "Items": [], "LastEvaluatedKey": {"userId": "first"}},
        {"Count": 1, "Items": [{"userId": "wanted"}]},
    ]
    assert find_login_user(table, "second")["Items"][0]["userId"] == "wanted"
    assert "IndexName" in table.scan.call_args_list[0].kwargs
    assert "IndexName" not in table.scan.call_args_list[1].kwargs
    assert table.scan.call_args_list[2].kwargs["ExclusiveStartKey"] == {"userId": "first"}
