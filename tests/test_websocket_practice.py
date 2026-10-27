from copy import deepcopy
import json
from unittest.mock import Mock

from botocore.exceptions import ClientError
import pytest

from lambdas.api.websocket import websocket_practice as api
from lambdas.core.game import runtime
from tests.test_practice_computer_levels import solo_room


@pytest.fixture
def route(monkeypatch):
    room = solo_room()
    db = Mock()
    db.find_room_by_id.return_value = room
    db.websocket_connections_table.query.return_value = {"Items": [{
        "userId": "human", "authType": "guest", "status": "connected", "authExpiresAt": 4102444800,
    }]}
    sent = Mock()
    monkeypatch.setattr(api, "db_utils", db)
    monkeypatch.setattr(api, "broadcast_to_connection", sent)
    monkeypatch.setattr(runtime, "publish", Mock())
    handler = object.__new__(api.WebSocketPracticeHandler)

    def call(action="getPracticeHint", **data):
        event = {"requestContext": {"routeKey": action, "connectionId": "connection"},
                 "body": json.dumps({"roomId": "room", **data})}
        return handler.process_websocket_request(event, None)

    return call, db, sent, room


def test_hint_is_connection_authenticated_private_and_read_only(route):
    call, db, sent, room = route
    before = deepcopy(room)
    response = call(suggest=False, revision=7)
    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["action"] == "practiceHint"
    assert payload["hint"]["actor"] == "East"
    assert room == before
    db.get_table.return_value.put_item.assert_not_called()
    runtime.publish.assert_not_called()
    assert sent.call_args.args[0] == "connection"


@pytest.mark.parametrize("identity", ["outsider", "ROBOT_East"])
def test_claimed_identity_never_authorizes_hint(route, identity):
    call, db, sent, room = route
    assert call(userId=identity)["statusCode"] == 403
    db.get_table.return_value.put_item.assert_not_called()


def test_expired_or_unauthenticated_connection_denied(route):
    call, db, sent, room = route
    db.websocket_connections_table.query.return_value = {"Items": []}
    assert call()["statusCode"] == 401


def test_room_member_must_be_sole_human_and_current_controller(route):
    call, db, sent, room = route
    room["seats"]["South"] = "other"
    assert call()["statusCode"] == 403
    room["seats"]["South"] = "ROBOT_South"
    room["gameData"]["turn"] = "West"
    assert call()["statusCode"] == 403


def test_level_setting_validated_persisted_and_cas_protected(route):
    call, db, sent, room = route
    response = call("setComputerLevel", computerLevel="thoughtful", revision=7)
    assert response["statusCode"] == 200
    stored = db.get_table.return_value.put_item.call_args.kwargs
    assert stored["Item"]["computerLevel"] == "thoughtful"
    assert stored["Item"]["revision"] == 8
    assert stored["ExpressionAttributeValues"][":expected"] == 7
    assert "ConditionExpression" in stored
    assert room["computerLevel"] == "heuristic"
    runtime.publish.assert_called_once()


@pytest.mark.parametrize("data", [
    {"computerLevel": "expert"}, {"computerLevel": None},
    {"computerLevel": "thoughtful", "samples": 1000},
    {"computerLevel": "standard", "budgetMs": 0},
])
def test_invalid_or_browser_supplied_policy_parameters_do_not_persist(route, data):
    call, db, sent, room = route
    assert call("setComputerLevel", **data)["statusCode"] == 400
    db.get_table.return_value.put_item.assert_not_called()


def test_setting_requires_owner_and_stale_revisions_rejected(route):
    call, db, sent, room = route
    assert call("setComputerLevel", computerLevel="standard", revision=6)["statusCode"] == 409
    room["ownerId"] = "other"
    assert call("setComputerLevel", computerLevel="standard")["statusCode"] == 403
    db.get_table.return_value.put_item.assert_not_called()


def test_setting_concurrent_change_returns_conflict(route):
    call, db, sent, room = route
    db.get_table.return_value.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "conflict"}}, "PutItem")
    assert call("setComputerLevel", computerLevel="standard")["statusCode"] == 409
    runtime.publish.assert_not_called()


def test_invalid_hint_parameters_and_actual_hidden_world_do_not_affect_response(route):
    call, db, sent, room = route
    assert call(suggest="yes")["statusCode"] == 400
    assert call(hiddenHands={})["statusCode"] == 400
    first = call(suggest=False)
    room["gameData"]["hands"]["North"] = ["SECRET"]
    room["gameData"]["hands"]["South"] = []
    assert call(suggest=False) == first
