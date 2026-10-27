"""Durable DynamoDB-stream -> delayed-SQS game clock, without Lambda sleeps.

Both event sources target this handler. Persisted deadlines are the authority;
queue delivery can be late/duplicated, but can never make a card play early.
"""
import json
import logging
import os

import boto3
from boto3.dynamodb.types import TypeDeserializer

from lambdas.core.game import runtime
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection

logger = logging.getLogger(__name__)


def tick_for_room(room):
    pending = room.get("gameData", {}).get("pendingAction")
    if not pending:
        return None
    return {"roomId": room["roomId"], "revision": int(room["revision"]),
            "kind": pending["kind"], "dueAt": int(pending["dueAt"])}


def enqueue_tick(tick, sqs=None, *, minimum_delay=0):
    queue_url = os.environ.get("GAME_TICK_QUEUE_URL")
    if not queue_url:
        raise RuntimeError("GAME_TICK_QUEUE_URL is required for autonomous game pacing")
    remaining = max(0, tick["dueAt"] - runtime.now_ms())
    delay = min(900, max(minimum_delay, (remaining + 999) // 1000))
    (sqs or boto3.client("sqs")).send_message(
        QueueUrl=queue_url, MessageBody=json.dumps(tick), DelaySeconds=delay)


def lambda_handler(event, context):
    failures = []
    deserializer = TypeDeserializer()
    for record in event["Records"]:
        source = record.get("eventSource")
        identifier = (record.get("dynamodb", {}).get("SequenceNumber")
                      if source == "aws:dynamodb" else record.get("messageId"))
        try:
            if source == "aws:dynamodb":
                if record.get("eventName") not in ("INSERT", "MODIFY"):
                    continue
                image = record["dynamodb"]["NewImage"]
                room = {key: deserializer.deserialize(value) for key, value in image.items()}
                tick = tick_for_room(room)
                if tick:
                    enqueue_tick(tick)
            elif source == "aws:sqs":
                tick = json.loads(record["body"])
                retry = runtime.process_due_tick(
                    db_utils, broadcast_to_connection, tick, context)
                if retry:
                    enqueue_tick(retry, minimum_delay=1)
            else:
                raise ValueError(f"Unsupported game tick event source: {source}")
        except Exception:
            logger.exception("Game tick failed; event source must retry")
            if not identifier:
                raise
            failures.append({"itemIdentifier": identifier})
    return {"batchItemFailures": failures}
