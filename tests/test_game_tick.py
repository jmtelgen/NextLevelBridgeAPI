"""Durable scheduling adapter tests; real AWS calls and wall-clock sleeps forbidden."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

from boto3.dynamodb.types import TypeSerializer

from lambdas.api.game import game_tick
from lambdas.core.game import runtime
from test_bridge_lifecycle import server  # noqa: F401
from test_game_pacing import opening


def stream_record(room, sequence="1"):
    serializer = TypeSerializer()
    return {"eventSource": "aws:dynamodb", "eventName": "MODIFY",
            "dynamodb": {"SequenceNumber": sequence, "NewImage": {
                key: serializer.serialize(value) for key, value in room.items()}}}


def sqs_record(tick, message_id="message"):
    return {"eventSource": "aws:sqs", "messageId": message_id, "body": json.dumps(tick)}


def test_stream_schedules_durable_deadline_with_second_rounding(server, monkeypatch):
    db, _ = opening(server)
    monkeypatch.setenv("GAME_TICK_QUEUE_URL", "local-test-queue")
    sqs = Mock()
    monkeypatch.setattr(game_tick.boto3, "client", lambda service: sqs)
    event = {"Records": [stream_record(db.room)]}
    assert game_tick.lambda_handler(event, None) == {"batchItemFailures": []}
    kwargs = sqs.send_message.call_args.kwargs
    assert kwargs["DelaySeconds"] == 1
    assert json.loads(kwargs["MessageBody"]) == game_tick.tick_for_room(db.room)
    assert kwargs["QueueUrl"] == "local-test-queue"


def test_early_queue_delivery_requeues_without_mutating(server, monkeypatch):
    db, _ = opening(server)
    monkeypatch.setenv("GAME_TICK_QUEUE_URL", "local-test-queue")
    monkeypatch.setattr(game_tick, "db_utils", db)
    monkeypatch.setattr(game_tick, "broadcast_to_connection", db.send)
    sqs = Mock()
    monkeypatch.setattr(game_tick.boto3, "client", lambda service: sqs)
    tick = game_tick.tick_for_room(db.room)
    before = copy.deepcopy(db.room)
    event = {"Records": [sqs_record(tick)]}
    assert game_tick.lambda_handler(event, None) == {"batchItemFailures": []}
    assert db.room == before
    assert sqs.send_message.call_args.kwargs["DelaySeconds"] == 1
    db.now = tick["dueAt"]
    sqs.reset_mock()
    assert game_tick.lambda_handler(event, None) == {"batchItemFailures": []}
    assert len(db.room["gameData"]["currentTrick"]) == 1
    sqs.send_message.assert_not_called()
    after = copy.deepcopy(db.room)
    assert game_tick.lambda_handler(event, None) == {"batchItemFailures": []}
    assert db.room == after


def test_missing_queue_or_enqueue_failure_returns_stream_partial_failure(server, monkeypatch):
    db, _ = opening(server)
    monkeypatch.delenv("GAME_TICK_QUEUE_URL", raising=False)
    event = {"Records": [stream_record(db.room, "sequence-42")]}
    assert game_tick.lambda_handler(event, None) == {
        "batchItemFailures": [{"itemIdentifier": "sequence-42"}]}
    monkeypatch.setenv("GAME_TICK_QUEUE_URL", "local-test-queue")
    sqs = Mock()
    sqs.send_message.side_effect = RuntimeError("queue unavailable")
    monkeypatch.setattr(game_tick.boto3, "client", lambda service: sqs)
    assert game_tick.lambda_handler(event, None) == {
        "batchItemFailures": [{"itemIdentifier": "sequence-42"}]}


def test_per_record_failure_does_not_retry_successful_messages(server, monkeypatch):
    db, _ = opening(server)
    db.now = db.room["gameData"]["pendingAction"]["dueAt"]
    tick = game_tick.tick_for_room(db.room)
    monkeypatch.setattr(game_tick, "db_utils", db)
    monkeypatch.setattr(game_tick, "broadcast_to_connection", db.send)
    event = {"Records": [{"eventSource": "aws:sqs", "messageId": "bad", "body": "not-json"},
                         sqs_record(tick, "good")]}
    assert game_tick.lambda_handler(event, None) == {
        "batchItemFailures": [{"itemIdentifier": "bad"}]}
    assert len(db.room["gameData"]["currentTrick"]) == 1


def test_stream_ignores_human_turn_deletions_and_completed_rooms(server, monkeypatch):
    db, _ = opening(server)
    enqueue = Mock()
    monkeypatch.setattr(game_tick, "enqueue_tick", enqueue)
    room = copy.deepcopy(db.room)
    room["gameData"]["pendingAction"] = None
    event = {"Records": [stream_record(room), {
        "eventSource": "aws:dynamodb", "eventName": "REMOVE",
        "dynamodb": {"SequenceNumber": "2"}}]}
    assert game_tick.lambda_handler(event, None) == {"batchItemFailures": []}
    enqueue.assert_not_called()


def test_autonomous_chain_needs_no_snapshot_requests(server, monkeypatch):
    db, _ = opening(server, humans=("West",))
    monkeypatch.setenv("GAME_TICK_QUEUE_URL", "local-test-queue")
    monkeypatch.setattr(game_tick, "db_utils", db)
    monkeypatch.setattr(game_tick, "broadcast_to_connection", db.send)
    sqs = Mock()
    monkeypatch.setattr(game_tick.boto3, "client", lambda service: sqs)
    for count in (1, 2):
        event = {"Records": [stream_record(db.room)]}
        assert game_tick.lambda_handler(event, None) == {"batchItemFailures": []}
        tick = json.loads(sqs.send_message.call_args.kwargs["MessageBody"])
        db.now = tick["dueAt"]
        assert game_tick.lambda_handler({"Records": [sqs_record(tick)]}, None) == {
            "batchItemFailures": []}
        assert len(db.room["gameData"]["currentTrick"]) == count
    assert db.room["gameData"]["turn"] == "West"
    assert db.room["gameData"]["pendingAction"] is None


def test_budget_limited_worker_requeues_with_backoff(server, monkeypatch):
    db, _ = opening(server)
    monkeypatch.setenv("GAME_TICK_QUEUE_URL", "local-test-queue")
    monkeypatch.setattr(game_tick, "db_utils", db)
    monkeypatch.setattr(game_tick, "broadcast_to_connection", db.send)
    sqs = Mock()
    monkeypatch.setattr(game_tick.boto3, "client", lambda service: sqs)
    db.now = db.room["gameData"]["pendingAction"]["dueAt"]
    tick = game_tick.tick_for_room(db.room)
    context = SimpleNamespace(get_remaining_time_in_millis=lambda: 1000)
    assert game_tick.lambda_handler({"Records": [sqs_record(tick)]}, context) == {
        "batchItemFailures": []}
    assert sqs.send_message.call_args.kwargs["DelaySeconds"] == 1
    assert db.room["gameData"]["currentTrick"] == []


def test_worker_round_trips_decimal_deadlines_and_composite_room_key(server, monkeypatch):
    import boto3
    from moto import mock_aws
    from lambdas.shared.database.db_utils import DatabaseUtils

    db, _ = opening(server)
    with mock_aws():
        table = boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName="paced-rooms", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "roomId", "KeyType": "HASH"},
                       {"AttributeName": "ownerId", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "roomId", "AttributeType": "S"},
                                  {"AttributeName": "ownerId", "AttributeType": "S"}])
        table.put_item(Item=db.room)
        database = DatabaseUtils.__new__(DatabaseUtils)
        monkeypatch.setattr(database, "get_table", lambda name: table)
        monkeypatch.setattr(database, "get_user_connections", lambda user: [])
        monkeypatch.setattr(game_tick, "db_utils", database)
        monkeypatch.setattr(game_tick, "broadcast_to_connection", db.send)
        tick = game_tick.tick_for_room(db.room)
        db.now = tick["dueAt"]
        assert game_tick.lambda_handler({"Records": [sqs_record(tick)]}, None) == {
            "batchItemFailures": []}
        persisted = table.get_item(
            Key={"roomId": "room", "ownerId": "user-North"}, ConsistentRead=True)["Item"]
        assert persisted["revision"] == tick["revision"] + 1
        assert len(persisted["gameData"]["currentTrick"]) == 1
        assert persisted["gameData"]["pendingAction"] is None


def test_corrupt_hand_is_not_silently_acknowledged_as_a_race(server, monkeypatch):
    db, _ = opening(server)
    monkeypatch.setattr(game_tick, "db_utils", db)
    monkeypatch.setattr(game_tick, "broadcast_to_connection", db.send)
    db.room["gameData"]["hands"]["East"] = []
    db.now = db.room["gameData"]["pendingAction"]["dueAt"]
    tick = game_tick.tick_for_room(db.room)
    before = copy.deepcopy(db.room)
    assert game_tick.lambda_handler({"Records": [sqs_record(tick)]}, None) == {
        "batchItemFailures": [{"itemIdentifier": "message"}]}
    assert db.room == before
