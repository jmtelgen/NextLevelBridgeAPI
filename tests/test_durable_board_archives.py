"""Offline crash-boundary, cross-process and immutable archive coverage."""
import copy

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from lambdas.core.game import archives, duplicate, rules, runtime
from test_bridge_lifecycle import call, fixed_deal, room_fixture
from test_duplicate_events import event_server, enroll, pass_board


@pytest.fixture
def durable(monkeypatch):
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.delenv("BOARD_ARCHIVES_TABLE", raising=False)
    with mock_aws():
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")

        def table(name, keys):
            return dynamo.create_table(
                TableName=name, BillingMode="PAY_PER_REQUEST",
                KeySchema=[{"AttributeName": key, "KeyType": kind}
                           for key, _, kind in keys],
                AttributeDefinitions=[{"AttributeName": key, "AttributeType": kind}
                                      for key, kind, _ in keys])

        rooms = table("durable-rooms", [("roomId", "S", "HASH"), ("ownerId", "S", "RANGE")])
        boards = table("durable-boards", [("roomId", "S", "HASH"), ("boardNumber", "N", "RANGE")])
        events = table("durable-events", [("eventId", "S", "HASH")])
        repository = archives.DynamoArchiveStore(boards)
        monkeypatch.setattr(archives, "store", repository)
        monkeypatch.setattr(duplicate, "store", duplicate.DynamoEventStore(events))
        room = room_fixture()
        rules.new_board(room, fixed_deal())
        rooms.put_item(Item=room)
        yield rooms, boards, events, room, repository


def finish(room):
    for _ in range(4):
        call(room, "pass")
    return room


def persisted(rooms, room):
    return rooms.get_item(Key={"roomId": room["roomId"], "ownerId": room["ownerId"]},
                          ConsistentRead=True)["Item"]


def event_room(rooms, events, room):
    room["eventId"] = "event"
    room["gameData"]["eventId"] = "event"
    rooms.put_item(Item=room)
    events.put_item(Item={
        "eventId": "event", "revision": 1, "status": "started", "tableCount": 2,
        "tables": [{"roomId": room["roomId"]}, {"roomId": "other"}],
        "boards": [{"boardId": room["gameData"]["boardId"], "boardNumber": 1, "results": {}}],
    })


def test_completion_is_durable_across_instances_and_next_board(durable):
    rooms, boards, _, room, repository = durable
    finish(room)
    runtime.save_room(rooms, room)
    expected = archives.record(room)
    reopened = archives.DynamoArchiveStore(boards)
    assert reopened.get(room["roomId"], expected["boardId"]) == expected
    assert persisted(rooms, room)["gameData"]["scoreboard"]["completedBoards"] == 1
    runtime.save_room(rooms, room)
    assert reopened.list(room["roomId"]) == [expected]
    rules.new_board(room, fixed_deal())
    runtime.save_room(rooms, room)
    assert repository.get(room["roomId"], expected["boardId"]) == expected
    assert persisted(rooms, room)["gameData"]["boardNumber"] == 2
    assert reopened.get("another-room", expected["boardId"]) is None


def test_failed_room_cas_rolls_back_archive_and_event(durable):
    rooms, boards, events, room, repository = durable
    event_room(rooms, events, room)
    stale = copy.deepcopy(room)
    runtime.save_room(rooms, room)
    finish(stale)
    with pytest.raises(runtime.RoomConflictError):
        runtime.save_room(rooms, stale)
    assert repository.list(room["roomId"]) == []
    assert events.get_item(Key={"eventId": "event"})["Item"]["boards"][0]["results"] == {}
    assert persisted(rooms, room)["state"] == "bidding"


def test_immutable_conflict_rolls_back_room_and_duplicate_score(durable):
    rooms, _, events, room, repository = durable
    event_room(rooms, events, room)
    finish(room)
    other = copy.deepcopy(room)
    other["gameData"]["initialHands"]["North"].reverse()
    repository.put_completed(other)
    with pytest.raises(archives.ArchiveConflict):
        runtime.save_room(rooms, room)
    assert persisted(rooms, room)["state"] == "bidding"
    assert duplicate.store.get("event")["boards"][0]["results"] == {}
    with pytest.raises(archives.ArchiveConflict):
        repository.put_completed(room)


def test_transaction_failure_cannot_publish_partial_completion(durable, monkeypatch):
    rooms, _, _, room, repository = durable
    finish(room)

    def fail(**kwargs):
        raise ClientError({"Error": {"Code": "InternalServerError", "Message": "unavailable"}},
                          "TransactWriteItems")

    monkeypatch.setattr(repository.table.meta.client, "transact_write_items", fail)
    with pytest.raises(ClientError):
        runtime.save_room(rooms, room)
    assert persisted(rooms, room)["state"] == "bidding"
    assert repository.list(room["roomId"]) == []


def test_crash_after_commit_keeps_room_archive_and_event_together(durable, monkeypatch):
    rooms, boards, events, room, repository = durable
    event_room(rooms, events, room)
    finish(room)
    client = repository.table.meta.client
    transact = client.transact_write_items

    def commit_then_crash(**kwargs):
        transact(**kwargs)
        raise RuntimeError("process ended after durable commit")

    monkeypatch.setattr(client, "transact_write_items", commit_then_crash)
    with pytest.raises(RuntimeError, match="process ended"):
        runtime.save_room(rooms, room)
    stored = persisted(rooms, room)
    assert stored["state"] == "completed"
    reopened = archives.DynamoArchiveStore(boards)
    assert reopened.get(room["roomId"], room["gameData"]["boardId"]) == archives.record(stored)
    assert duplicate.DynamoEventStore(events).get("event")["boards"][0]["results"] == {
        room["roomId"]: {"scoreNS": 0, "scoreEW": 0}}
    monkeypatch.setattr(client, "transact_write_items", transact)
    runtime.save_room(rooms, stored)
    assert duplicate.store.get("event")["revision"] == 2
    assert stored["gameData"]["scoreboard"]["completedBoards"] == 1


def test_cross_process_duplicate_cas_rereads_and_preserves_other_table(durable, monkeypatch):
    rooms, _, events, room, repository = durable
    event_room(rooms, events, room)
    finish(room)
    client = repository.table.meta.client
    transact = client.transact_write_items
    calls = []

    def race(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            event = duplicate.store.get("event")
            event["boards"][0]["results"]["other"] = {"scoreNS": 50, "scoreEW": -50}
            event["revision"] += 1
            events.put_item(Item=event)
        return transact(**kwargs)

    monkeypatch.setattr(client, "transact_write_items", race)
    runtime.save_room(rooms, room)
    assert len(calls) == 2
    event = duplicate.store.get("event")
    assert event["status"] == "completed"
    assert event["revision"] == 3
    assert event["boards"][0]["results"] == {
        "other": {"scoreNS": 50, "scoreEW": -50},
        room["roomId"]: {"scoreNS": 0, "scoreEW": 0}}
    assert len(repository.list(room["roomId"])) == 1


def test_event_contention_is_bounded_and_leaves_no_partial_completion(durable, monkeypatch):
    rooms, _, events, room, repository = durable
    event_room(rooms, events, room)
    finish(room)
    client = repository.table.meta.client
    transact = client.transact_write_items
    attempts = []

    def race(**kwargs):
        attempts.append(kwargs)
        event = duplicate.store.get("event")
        event["revision"] += 1
        events.put_item(Item=event)
        return transact(**kwargs)

    monkeypatch.setattr(client, "transact_write_items", race)
    with pytest.raises(runtime.GameRequestError) as error:
        runtime.save_room(rooms, room)
    assert error.value.status == 409
    assert len(attempts) == 5
    assert persisted(rooms, room)["state"] == "bidding"
    assert repository.list(room["roomId"]) == []
    assert duplicate.store.get("event")["boards"][0]["results"] == {}


def test_durable_routes_preserve_event_embargo_and_authorization(durable, event_server, monkeypatch):
    _, boards, _, _, repository = durable
    db, _, request = event_server
    monkeypatch.setattr(archives, "store", repository)
    rooms, event_id, _ = enroll(event_server, boards=1)
    owner = rooms[0]["ownerId"]
    assert request("startDuplicateEvent", owner, eventId=event_id)[0] == 200
    first = pass_board(db, request, rooms[0]["roomId"])
    board_id = first["gameData"]["boardId"]
    monkeypatch.setattr(archives, "store", archives.DynamoArchiveStore(boards))
    assert request("getBoardArchive", owner, roomId=first["roomId"], boardId=board_id)[0] == 403
    assert request("listBoardArchives", owner, roomId=first["roomId"])[1]["boards"] == []
    assert request("getBoardArchive", "outsider", roomId=first["roomId"], boardId=board_id)[0] == 403
    assert request("getBoardArchive", owner, roomId=rooms[1]["roomId"], boardId=board_id)[0] == 403
    pass_board(db, request, rooms[1]["roomId"])
    assert request("getBoardArchive", owner, roomId=first["roomId"], boardId=board_id)[0] == 200
    listed = request("listBoardArchives", owner, roomId=first["roomId"], limit=1)[1]
    assert listed["boards"][0]["boardId"] == board_id
    assert "initialHands" not in listed["boards"][0]


def test_numeric_pagination_and_board_lookup_follow_dynamodb_pages(durable, monkeypatch):
    _, boards, _, room, repository = durable
    expected = []
    for _ in range(4):
        finish(room)
        expected.append(repository.put_completed(room))
        rules.new_board(room, fixed_deal())
    query = boards.query

    def one_per_page(**kwargs):
        kwargs["Limit"] = 1
        return query(**kwargs)

    monkeypatch.setattr(boards, "query", one_per_page)
    assert [board["boardNumber"] for board in repository.list("room", limit=3)] == [4, 3, 2]
    assert [board["boardNumber"] for board in repository.list("room", before=3)] == [2, 1]
    assert repository.get("room", expected[-1]["boardId"]) == expected[-1]
    assert repository.get("room", "missing") is None
    assert repository.put_completed(room) is None


@pytest.mark.parametrize("event_problem", ["missing-store", "missing-event", "wrong-board"])
def test_durable_duplicate_completion_fails_closed(durable, monkeypatch, event_problem):
    rooms, _, events, room, repository = durable
    event_room(rooms, events, room)
    finish(room)
    if event_problem == "missing-store":
        monkeypatch.setattr(duplicate, "store", None)
    elif event_problem == "missing-event":
        events.delete_item(Key={"eventId": "event"})
    else:
        room["gameData"]["boardId"] = "unassigned"
    with pytest.raises((RuntimeError, ValueError)):
        runtime.save_room(rooms, room)
    assert persisted(rooms, room)["state"] == "bidding"
    assert repository.list("room") == []


def test_factory_requires_explicit_lambda_storage_and_reuses_table(durable, monkeypatch):
    _, boards, events, _, repository = durable
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "staging-game")
    with pytest.raises(RuntimeError, match="BOARD_ARCHIVES_TABLE"):
        archives.get_store()
    monkeypatch.setenv("BOARD_ARCHIVES_TABLE", boards.name)
    monkeypatch.delenv("DUPLICATE_EVENTS_TABLE", raising=False)
    with pytest.raises(RuntimeError, match="DUPLICATE_EVENTS_TABLE"):
        archives.get_store()
    monkeypatch.setenv("DUPLICATE_EVENTS_TABLE", "wrong-event-table")
    with pytest.raises(RuntimeError, match="must be initialized"):
        archives.get_store()
    monkeypatch.setenv("DUPLICATE_EVENTS_TABLE", events.name)
    assert archives.configure_from_environment() is repository
    monkeypatch.setattr(archives, "store", archives.MemoryArchiveStore())

    class DB:
        def get_table(self, variable):
            assert variable == "BOARD_ARCHIVES_TABLE"
            return boards

    assert archives.configure_from_environment(DB()).table is boards


def test_lambda_factory_rejects_missing_event_adapter_even_with_env(durable, monkeypatch):
    _, boards, events, _, _ = durable
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "staging-game")
    monkeypatch.setenv("BOARD_ARCHIVES_TABLE", boards.name)
    monkeypatch.setenv("DUPLICATE_EVENTS_TABLE", events.name)
    monkeypatch.setattr(duplicate, "store", None)
    with pytest.raises(RuntimeError, match="must be initialized"):
        archives.configure_from_environment()
