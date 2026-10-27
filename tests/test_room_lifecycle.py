"""Offline fake-clock reservations, revision races and private-room capability tests."""
import copy
import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from lambdas.core.game import runtime
from lambdas.core.rooms import lifecycle


class RoomDB:
    def __init__(self):
        self.room = {
            "roomId": "room", "ownerId": "owner", "state": "waiting",
            "roomName": "Bridge", "isPrivate": False, "revision": 0,
            "seats": {"North": "owner", "East": "guest", "South": "", "West": ""},
            "gameData": {"currentPhase": "waiting", "hands": {
                "North": ["AS"], "East": ["KS"], "South": ["QS"], "West": ["JS"]}},
        }
        self.connections = {
            "owner": [self.connection("owner", "owner-tab")],
            "guest": [self.connection("guest", "guest-tab")],
        }
        self.saved = []
        self.before_put = None

    @staticmethod
    def connection(user, identifier, expiry=1000):
        return {"userId": user, "connectionId": identifier, "authExpiresAt": expiry,
                "authType": "guest", "status": "connected"}

    def get_table(self, name):
        return self

    def find_room_by_id(self, identifier, table=None):
        return copy.deepcopy(self.room) if identifier == "room" else None

    def get_rooms_for_user(self, user, table=None):
        return [copy.deepcopy(self.room)] if user in self.room["seats"].values() else []

    def get_user_connection_records(self, user):
        return copy.deepcopy(self.connections.get(user, []))

    def get_user_connections(self, user):
        return [record["connectionId"] for record in self.connections.get(user, [])]

    def put_item(self, **kwargs):
        if self.before_put:
            callback, self.before_put = self.before_put, None
            callback()
        if kwargs["ExpressionAttributeValues"][":expected"] != self.room["revision"]:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.room = copy.deepcopy(kwargs["Item"])
        self.saved.append(copy.deepcopy(self.room))

    def refresh(self, now):
        return lifecycle.refresh_presence(self, self.find_room_by_id("room"), self, now)

    def control(self, action, data, now):
        return lifecycle.control_room(self, copy.deepcopy(self.room), "owner", action, data, now)


def test_duplicate_tabs_expiry_and_disconnect_preserve_reservation():
    db = RoomDB()
    db.connections["guest"].append(db.connection("guest", "renewed", expiry=2000))
    db.refresh(100)
    assert lifecycle.public_presence(db.room, 100)["East"] == {
        "status": "online", "connectionCount": 2, "userId": "guest"}
    db.connections["guest"].pop(0)
    db.refresh(200)
    assert lifecycle.public_presence(db.room, 200)["East"]["status"] == "online"
    db.connections["guest"] = []
    db.refresh(300)
    assert lifecycle.public_presence(db.room, 419)["East"]["status"] == "reconnecting"
    assert lifecycle.public_presence(db.room, 420)["East"]["status"] == "offline"
    db.refresh(500)
    assert db.room["presence"]["East"]["reservedUntil"] == 420
    with pytest.raises(runtime.GameRequestError, match="Transfer ownership"):
        lifecycle.replace_player(db, db, copy.deepcopy(db.room), "owner", "North", 500)


def test_unclosed_expired_tokens_reserve_from_expiry_not_snapshot_time():
    db = RoomDB()
    db.connections["guest"][0]["authExpiresAt"] = 200
    db.refresh(100)
    assert lifecycle.public_presence(db.room, 200)["East"]["reservedUntil"] == 320
    db.refresh(500)
    assert db.room["presence"]["East"]["disconnectedAt"] == 200
    assert lifecycle.public_presence(db.room, 500)["East"]["status"] == "offline"


def test_guest_renewed_same_id_rejoins_existing_active_seat_and_locked_room():
    db = RoomDB()
    db.refresh(100)
    db.connections["guest"] = []
    db.refresh(200)
    db.room.update(state="playing", locked=True, isPrivate=True)
    before = copy.deepcopy(db.room["gameData"])
    db.connections["guest"] = [db.connection("guest", "renewed", 5000)]
    room, seat, reconnected = lifecycle.join_room(db, db, copy.deepcopy(db.room), "guest", now=250)
    assert (seat, reconnected) == ("East", True)
    assert room["seats"]["East"] == "guest"
    assert lifecycle.public_presence(room, 250)["East"]["connectionCount"] == 1
    assert {key: value for key, value in room["gameData"].items() if key != "revision"} == {
        key: value for key, value in before.items() if key != "revision"}


def test_replacement_is_explicit_after_grace_preserves_board_and_blocks_reclaim():
    db = RoomDB()
    db.refresh(100)
    db.connections["guest"] = []
    db.refresh(200)
    db.room.update(state="playing")
    game = db.room["gameData"]
    game.update(currentPhase="playing", turn="East", scores={"NS": 30, "EW": -30})
    before = copy.deepcopy(game)
    for user, timestamp in (("guest", 400), ("owner", 319)):
        with pytest.raises(runtime.GameRequestError):
            lifecycle.replace_player(db, db, copy.deepcopy(db.room), user, "East", timestamp)
    assert db.room["seats"]["East"] == "guest"
    room = lifecycle.replace_player(db, db, copy.deepcopy(db.room), "owner", "East", 320)
    assert room["seats"]["East"] == "ROBOT_East"
    assert room["roomEvents"][-1]["type"] == "playerReplaced"
    assert {key: value for key, value in room["gameData"].items() if key != "revision"} == {
        key: value for key, value in before.items() if key != "revision"}
    db.connections["guest"] = [db.connection("guest", "late")]
    with pytest.raises(runtime.GameRequestError, match="during a board"):
        lifecycle.join_room(db, db, copy.deepcopy(db.room), "guest", now=321)
    assert lifecycle.public_presence(db.room, 321)["East"]["status"] == "robot"


def test_reconnect_wins_cas_against_stale_robot_replacement():
    db = RoomDB()
    db.refresh(100)
    db.connections["guest"] = []
    db.refresh(200)
    stale = copy.deepcopy(db.room)

    def reconnect():
        db.connections["guest"] = [db.connection("guest", "new-tab")]
        db.refresh(320)

    db.before_put = reconnect
    with pytest.raises(runtime.RoomConflictError):
        lifecycle.replace_player(db, db, stale, "owner", "East", 320)
    assert db.room["seats"]["East"] == "guest"
    assert lifecycle.public_presence(db.room, 320)["East"]["status"] == "online"


def test_replacement_wins_cas_and_reconnect_does_not_restore_old_membership():
    db = RoomDB()
    db.refresh(100)
    db.connections["guest"] = []
    db.refresh(200)
    stale = copy.deepcopy(db.room)
    lifecycle.replace_player(db, db, copy.deepcopy(db.room), "owner", "East", 320)
    db.connections["guest"] = [db.connection("guest", "late-tab")]
    with pytest.raises(runtime.RoomConflictError):
        lifecycle.refresh_presence(db, stale, db, 321)
    lifecycle.sync_user_presence(db, "guest", now=321)
    assert db.room["seats"]["East"] == "ROBOT_East"


def test_simultaneous_claimants_cannot_take_same_empty_seat():
    db = RoomDB()
    db.room["seats"]["West"] = "ROBOT_West"
    db.refresh(100)
    stale = copy.deepcopy(db.room)
    first, seat, _ = lifecycle.join_room(db, db, copy.deepcopy(stale), "first", now=100)
    assert seat == "South"
    with pytest.raises(runtime.RoomConflictError):
        lifecycle.join_room(db, db, stale, "second", now=100)
    assert db.room["seats"]["South"] == "first"


def test_private_expiring_revocable_invitation_and_lock_enforcement():
    db = RoomDB()
    db.room["isPrivate"] = True
    db.refresh(100)
    with pytest.raises(runtime.GameRequestError):
        lifecycle.join_room(db, db, copy.deepcopy(db.room), "new", now=100)
    created = db.control("createInvitation", {"expiresInSeconds": 60}, 100)
    token = created["invitationToken"]
    assert token not in json.dumps(db.room)
    assert token not in json.dumps(runtime.room_metadata(db.room))
    assert "invitations" not in runtime.room_metadata(db.room)
    lifecycle.require_invitation(db.room, token, 159)
    for bad_token, timestamp in ((token, 160), (token + "x", 101), ("signed.auth.token", 101)):
        with pytest.raises(runtime.GameRequestError):
            lifecycle.require_invitation(db.room, bad_token, timestamp)
    db.room["locked"] = True
    with pytest.raises(runtime.GameRequestError, match="locked"):
        lifecycle.join_room(db, db, copy.deepcopy(db.room), "new", token, 101)
    db.room["locked"] = False
    db.control("revokeInvitation", {"invitationId": created["invitationId"]}, 101)
    with pytest.raises(runtime.GameRequestError, match="revoked"):
        lifecycle.join_room(db, db, copy.deepcopy(db.room), "new", token, 102)
    invitation = db.control("createInvitation", {}, 102)
    room, _, _ = lifecycle.join_room(db, db, copy.deepcopy(db.room), "new",
                                    invitation["invitationToken"], 103)
    assert "new" in room["seats"].values()


@pytest.mark.parametrize("action,data", [
    ("setRoomLock", {"locked": True}), ("createInvitation", {}),
    ("revokeInvitation", {"invitationId": "unknown"}),
    ("transferOwnership", {"newOwnerId": "guest"}),
])
def test_private_controls_require_owner(action, data):
    db = RoomDB()
    with pytest.raises(runtime.GameRequestError) as error:
        lifecycle.control_room(db, db.room, "guest", action, data, now=100)
    assert error.value.status == 403


def test_owner_cannot_orphan_room_and_active_board_cannot_release_or_move():
    db = RoomDB()
    with pytest.raises(runtime.GameRequestError, match="differ"):
        lifecycle.control_room(db, copy.deepcopy(db.room), "owner", "transferOwnership",
                               {"newOwnerId": "owner"}, now=100, db=db)
    with pytest.raises(runtime.GameRequestError, match="Transfer ownership"):
        lifecycle.leave_room(db, copy.deepcopy(db.room), "owner")
    lifecycle.leave_room(db, copy.deepcopy(db.room), "guest")
    assert db.room["seats"]["East"] == ""
    db.room.update(state="playing")
    for operation in (
        lambda: lifecycle.leave_room(db, copy.deepcopy(db.room), "owner"),
        lambda: lifecycle.change_seat(db, copy.deepcopy(db.room), "owner", "South"),
    ):
        with pytest.raises(runtime.GameRequestError, match="during a board"):
            operation()


def test_control_response_and_replacement_use_filtered_snapshots_and_real_coordinator(monkeypatch):
    from lambdas.api.websocket import websocket_room_controls as controls
    db = RoomDB()
    db.connections["guest"] = []
    db.refresh(100)
    db.room.update(state="bidding")
    db.room["gameData"].update(currentPhase="bidding", turn="East", bids=[])
    monkeypatch.setattr(controls, "db_utils", db)
    monkeypatch.setattr(runtime, "connection_user", lambda *args: "owner")
    monkeypatch.setattr(lifecycle.time, "time", lambda: 220)
    monkeypatch.setattr(controls, "broadcast_to_connection", lambda *args: None)
    coordinator = MagicMock(side_effect=lambda db, table, send, room, context: room)
    monkeypatch.setattr(runtime, "advance_robots", coordinator)
    event = {"requestContext": {"routeKey": "replacePlayer", "connectionId": "owner-tab"},
             "body": json.dumps({"roomId": "room", "seat": "East"})}
    response = controls.handler.process_websocket_request(event, None)
    assert response["statusCode"] == 200, response
    payload = json.loads(response["body"])
    assert payload["updateType"] == "playerReplaced"
    assert "hands" not in payload["publicState"]
    assert payload["room"]["presence"]["East"]["status"] == "robot"
    coordinator.assert_called_once()


def test_atomic_owner_transfer_moves_composite_key_and_rejects_stale_revision(monkeypatch):
    """Moto owns all SDK calls; no network, account, or deployed table is touched."""
    from moto import mock_aws
    import boto3
    from lambdas.shared.database.db_utils import DatabaseUtils

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        db = DatabaseUtils()
        table = db.dynamodb.create_table(
            TableName="room-transfer-test", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "roomId", "KeyType": "HASH"},
                       {"AttributeName": "ownerId", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "roomId", "AttributeType": "S"},
                                  {"AttributeName": "ownerId", "AttributeType": "S"}])
        room = RoomDB().room
        table.put_item(Item=room)
        stale = copy.deepcopy(room)
        lifecycle.control_room(table, room, "owner", "transferOwnership",
                               {"newOwnerId": "guest"}, now=100, db=db)
        assert room["ownerId"] == "guest"
        items = table.scan(ConsistentRead=True)["Items"]
        assert len(items) == 1 and items[0]["ownerId"] == "guest"
        with pytest.raises(runtime.RoomConflictError):
            db.transfer_room_ownership(table, stale, "another")
        assert len(table.scan()["Items"]) == 1
        lifecycle.leave_room(table, room, "owner")
        assert table.scan()["Items"][0]["seats"]["North"] == ""


def test_actual_replacement_coordinator_legally_continues_same_auction(monkeypatch):
    from lambdas.api.websocket import websocket_room_controls as controls
    from lambdas.core.game import rules
    db = RoomDB()
    db.room["seats"].update(South="south-player", West="ROBOT_West")
    db.connections["south-player"] = [db.connection("south-player", "south-tab")]
    rules.new_board(db.room)
    rules.apply_call(db.room, "North", "1NT")
    db.connections["guest"] = []
    db.refresh(100)
    hands = copy.deepcopy(db.room["gameData"]["hands"])
    scores = copy.deepcopy(db.room["gameData"]["scores"])
    monkeypatch.setattr(controls, "db_utils", db)
    monkeypatch.setattr(runtime, "connection_user", lambda *args: "owner")
    monkeypatch.setattr(lifecycle.time, "time", lambda: 220)
    monkeypatch.setattr(runtime, "now_ms", lambda: 220000)
    monkeypatch.setattr(runtime, "execute_robot_bid", lambda *args: "pass")
    monkeypatch.setattr(controls, "broadcast_to_connection", lambda *args: None)
    event = {"requestContext": {"routeKey": "replacePlayer", "connectionId": "owner-tab"},
             "body": json.dumps({"roomId": "room", "seat": "East"})}
    result = controls.handler.process_websocket_request(event, None)
    assert result["statusCode"] == 200, result
    game = db.room["gameData"]
    assert [bid["bid"] for bid in game["bids"]] == ["1NT", "pass"]
    assert game["turn"] == "South"
    assert game["hands"] == hands and game["scores"] == scores
    assert game["pendingAction"] is None


def test_failed_upgrade_presence_sync_rolls_back_new_connection(monkeypatch):
    from lambdas.api.websocket import websocket_connect as connect
    db = MagicMock()
    db.create_connection_record.return_value = True
    monkeypatch.setattr(connect, "db_utils", db)
    monkeypatch.setattr(connect, "require_origin", lambda event: None)
    monkeypatch.setattr(connect, "socket_identity", lambda event: ({
        "userId": "guest", "username": "Guest", "exp": 1000, "type": "guest"}, False))
    monkeypatch.setattr(connect, "sync_user_presence", MagicMock(side_effect=RuntimeError("unavailable")))
    event = {"requestContext": {"routeKey": "$connect", "connectionId": "new"}}
    result = connect.handler.process_websocket_request(event, None)
    assert result["statusCode"] == 503
    db.delete_connection_record.assert_called_once_with("new")


def test_disconnect_deletes_all_pages_before_synchronizing_each_identity(monkeypatch):
    from lambdas.api.websocket import websocket_disconnect as disconnect
    table = MagicMock()
    table.query.side_effect = [
        {"Items": [{"connectionId": "socket", "currentRoomId": "one", "userId": "guest"}],
         "LastEvaluatedKey": {"connectionId": "socket", "currentRoomId": "one"}},
        {"Items": [{"connectionId": "socket", "currentRoomId": "two", "userId": "guest"}]},
    ]
    resource = MagicMock()
    resource.Table.return_value = table
    monkeypatch.setenv("WEBSOCKET_CONNECTIONS_TABLE", "offline")
    monkeypatch.setattr(disconnect.boto3, "resource", lambda *args: resource)
    sync = MagicMock()
    monkeypatch.setattr(disconnect, "sync_user_presence", sync)
    result = disconnect.lambda_handler({"requestContext": {"connectionId": "socket"}}, None)
    assert result["statusCode"] == 200
    assert table.delete_item.call_count == 2
    assert table.query.call_args.kwargs["ExclusiveStartKey"]["currentRoomId"] == "one"
    sync.assert_called_once_with(disconnect.db_utils, "guest", disconnect.broadcast_to_connection)


@pytest.mark.parametrize("body", ["[]", '{"data":[]}', '{"data":"not-an-object"}'])
def test_room_controls_reject_nonobject_data(body):
    from lambdas.api.websocket import websocket_room_controls as controls
    event = {"requestContext": {"routeKey": "setRoomLock"}, "body": body}
    assert controls.handler.process_websocket_request(event, None)["statusCode"] == 400
