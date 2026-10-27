"""Explicit socket replies: Lambda return values are not API Gateway deliveries."""
import json
import logging

logger = logging.getLogger(__name__)


def publish_update(db, send, room, message, **fields):
    """Deliver command metadata alongside a separately filtered snapshot per member."""
    from lambdas.core.game.runtime import personalized
    from lambdas.core.robot.robot_utils import is_robot_seat
    for user in set(room["seats"].values()):
        if not user or is_robot_seat(user):
            continue
        payload = personalized(room, user, "roomUpdated", message)
        payload.update(success=True, **fields)
        try:
            for connection in db.get_user_connections(user):
                send(connection, payload)
        except Exception:
            logger.warning("Room update delivery failed; snapshot remains available", exc_info=True)


def deliver_reply(event, result, send):
    connection = event.get("requestContext", {}).get("connectionId")
    if connection and result.get("body"):
        payload = json.loads(result["body"])
        if result["statusCode"] >= 400:
            payload.update(action="error", statusCode=result["statusCode"])
        try:
            send(connection, payload)
        except Exception:
            logger.warning("Room response delivery failed; request a snapshot", exc_info=True)
    return result
