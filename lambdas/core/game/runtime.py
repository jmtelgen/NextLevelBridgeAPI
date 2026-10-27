"""Durable, connection-bound multiplayer transitions with optimistic concurrency."""
import copy
import json
import logging
import time
import uuid
from decimal import Decimal

from botocore.exceptions import ClientError

from lambdas.core.game import rules, archives, agreements, match, claims, duplicate
from lambdas.core.game.pacing import Pacing, now_ms
from lambdas.core.robot.robot_utils import (
    execute_robot_bid, execute_robot_card_play, is_robot_seat,
)
from lambdas.shared.utils.seat_filtering import create_seat_based_response, get_user_seat

logger = logging.getLogger(__name__)


class GameRequestError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class RoomConflictError(GameRequestError):
    pass


def connection_user(db, event, claimed_user=None):
    connection_id = event.get("requestContext", {}).get("connectionId")
    if not connection_id:
        raise GameRequestError(401, "Connection identity is required")
    response = db.websocket_connections_table.query(
        KeyConditionExpression="connectionId = :connectionId",
        ExpressionAttributeValues={":connectionId": connection_id},
        ConsistentRead=True,
    )
    users = {item.get("userId") for item in response.get("Items", [])
             if item.get("status") == "connected" and item.get("userId")
             and item.get("authType") in ("access", "guest")
             and isinstance(item.get("authExpiresAt"), (int, float, Decimal))
             and item["authExpiresAt"] > time.time()}
    if len(users) != 1:
        raise GameRequestError(401, "Unknown or expired connection; reconnect before playing")
    user_id = users.pop()
    if is_robot_seat(user_id) or (claimed_user is not None and claimed_user != user_id):
        raise GameRequestError(403, "Request identity does not match connection")
    return user_id


def normalize_room(room):
    """Accept pre-lifecycle completed-trick records without exposing legacy hands."""
    game = room.setdefault("gameData", {})
    game.setdefault("currentPhase", room.get("state", "waiting"))
    game.setdefault("bids", [])
    game.setdefault("hands", {})
    game.setdefault("currentTrick", [])
    game.setdefault("tricks", [])
    if game.get("boardNumber"):
        game.setdefault("boardId", str(uuid.uuid5(
            uuid.NAMESPACE_URL, f"bridge:{room['roomId']}:{game['boardNumber']}")))
        game.setdefault("agreements", agreements.board_agreements())
    for trick in game["tricks"]:
        if "plays" not in trick:
            trick["plays"] = trick.pop("cards", [])
        if trick["plays"]:
            trick.setdefault("leader", trick["plays"][0]["seat"])
    if game.get("previousTrick") and "plays" not in game["previousTrick"]:
        previous = game["previousTrick"]
        previous["plays"] = previous.pop("cards", [])
        if previous["plays"]:
            previous.setdefault("leader", previous["plays"][0]["seat"])
    if game["currentPhase"] in ("playing", "completed"):
        last, multiplier = rules.auction_contract(game["bids"])
        if last:
            declarer, leader = rules.declarer_and_leader(game["bids"])
            game["contract"] = last["bid"]
            game.setdefault("contractMultiplier", multiplier)
            game.setdefault("declarer", declarer)
            game.setdefault("dummy", rules.partner(declarer))
            game.setdefault("openingLeader", leader)
        game["dummyRevealed"] = bool(game["tricks"] or game["currentTrick"])
        if game["currentPhase"] == "completed":
            game["turn"] = None
            if len(game["tricks"]) == 13 and last:
                rules.finish_board(room)
            elif not last and len(game["bids"]) >= 4:
                rules.finish_board(room, passed_out=True)
    game["revision"] = int(room.get("revision", 0))
    game["practiceMode"] = bool(room.get("practiceSettings") and solo_room(room))
    return room


def save_room(table, room):
    claims.reconcile(room, now_ms())
    expected = int(room.get("revision", 0))
    room["revision"] = expected + 1
    room.setdefault("gameData", {})["revision"] = expected + 1
    names = {"#revision": "revision", "#room": "roomId"}
    if expected == 0:
        condition = "attribute_exists(#room) AND (attribute_not_exists(#revision) OR #revision = :expected)"
    else:
        condition = "attribute_exists(#room) AND #revision = :expected"
    try:
        table.put_item(
            Item=room, ConditionExpression=condition,
            ExpressionAttributeNames=names, ExpressionAttributeValues={":expected": expected})
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise RoomConflictError(409, "Room changed; request getGameState before retrying") from exc
        raise
    archives.store.put_completed(room)
    duplicate.record_completion(room)


def room_metadata(room):
    from lambdas.core.rooms.lifecycle import public_presence

    metadata = {key: room.get(key) for key in (
        "roomId", "ownerId", "roomName", "isPrivate", "seats", "state", "locked")}
    metadata["presence"] = public_presence(room)
    metadata["computerLevel"] = room.get("computerLevel", "standard")
    metadata["eventId"] = room.get("eventId")
    return metadata


def personalized(room, user_id, action, message):
    response = create_seat_based_response(
        game_data=room["gameData"], room_seats=room["seats"],
        user_id=user_id, action=action, message=message)
    response.room = room_metadata(room)
    # DynamoDB numbers inside result/metadata are Decimal, including nested Any fields.
    payload = json.loads(response.json())
    payload["publicState"]["serverTimeMs"] = int(now_ms())
    payload["publicState"]["computerLevel"] = room.get("computerLevel", "standard")
    return payload


def publish(db, send, room, action, message):
    for user_id in set(room["seats"].values()):
        if not user_id or is_robot_seat(user_id):
            continue
        payload = personalized(room, user_id, action, message)
        try:
            connections = db.get_user_connections(user_id)
        except Exception:
            logger.warning("Connection lookup failed; snapshot is available", exc_info=True)
            continue
        for connection in connections:
            try:
                send(connection, payload)
            except Exception:
                logger.warning("Socket delivery failed; snapshot is available", exc_info=True)


def robot_pending(room):
    game = room["gameData"]
    if claims.pending(game):
        return False
    return bool(game.get("completedTrick") or (
        game.get("currentPhase") in ("bidding", "playing")
        and is_robot_seat(room["seats"].get(rules.controller(game)))))


def plan_next_action(room, pacing, timestamp):
    """Create deadlines only on transitions, never extend them on snapshot reads."""
    game = room["gameData"]
    game["pacing"] = pacing.public()
    game["robotPending"] = robot_pending(room)
    if claims.pending(game):
        game["pendingAction"] = {"kind": "claimExpiry", "dueAt": game["claim"]["expiresAt"]}
        return
    if game.get("completedTrick"):
        kind, delay = "clearTrick", pacing.trick_hold_ms
    elif game["robotPending"]:
        kind = "robotBid" if game["currentPhase"] == "bidding" else "robotCard"
        delay = 0 if kind == "robotBid" else pacing.robot_card_delay_ms
    else:
        game["pendingAction"] = None
        return
    game["pendingAction"] = {"kind": kind, "dueAt": timestamp + delay}


def advance_robots(db, table, send, room, context=None, pacing=None):
    """Drain bounded auction work, but commit at most one due timed transition."""
    from lambdas.core.robot.level_policy import room_level
    room_level(room)
    pacing = pacing or Pacing.for_room(room)
    if claims.reconcile(room, now_ms()):
        if not room["gameData"].get("pendingAction"):
            plan_next_action(room, pacing, now_ms())
        save_room(table, room)
        publish(db, send, room, action="claimUpdated", message="Claim closed; play resumes")
    if robot_pending(room) and not room["gameData"].get("pendingAction"):
        # Old rooms acquire a real deadline once. Concurrent recoveries use CAS.
        plan_next_action(room, pacing, now_ms())
        save_room(table, room)
        publish(db, send, room, action="gameState", message="Pending action scheduled")
    for _ in range(128):
        if not robot_pending(room):
            break
        pending = room["gameData"].get("pendingAction")
        if not pending or now_ms() < pending["dueAt"]:
            break
        remaining = getattr(context, "get_remaining_time_in_millis", lambda: None)()
        if isinstance(remaining, (int, float)) and remaining < 2000:
            break
        game = room["gameData"]
        seat = game["turn"]
        if pending["kind"] == "clearTrick":
            rules.clear_completed_trick(room)
            action, message = "trickCleared", "Completed trick collected"
        elif game["currentPhase"] == "bidding":
            try:
                call = execute_robot_bid(copy.deepcopy(room), seat)
            except Exception:
                logger.warning("Robot bidding fallback", exc_info=True)
                call = "pass"
            if call not in rules.legal_calls(game, seat):
                call = "pass"
            rules.apply_call(room, seat, call)
            action, message = "bidMade", f"{seat} bid {call}"
        else:
            legal = rules.legal_cards(game, seat)
            if not legal:
                raise GameRequestError(409, "Invalid persisted hand; board recovery required")
            try:
                card = execute_robot_card_play(copy.deepcopy(room), seat)
            except Exception:
                logger.warning("Robot play fallback", exc_info=True)
                card = None
            if card not in legal:
                card = legal[0]
            rules.apply_card(room, seat, card, timestamp=now_ms(), hold_trick=True)
            action, message = "cardPlayed", f"{seat} played {card}"
        plan_next_action(room, pacing, now_ms())
        save_room(table, room)
        publish(db, send, room, action=action, message=message)
        if pending["kind"] != "robotBid":
            break
    return room


def process_due_tick(db, send, tick, context=None):
    """Authenticated worker entry, not a client route. Stale deliveries are no-ops."""
    table = db.get_table("ROOM_TABLE")
    found = db.find_room_by_id(tick["roomId"], table)
    if not found:
        return None
    room = normalize_room(copy.deepcopy(found))
    pending = room["gameData"].get("pendingAction")
    if (int(room.get("revision", 0)) != tick["revision"]
            or pending != {"kind": tick["kind"], "dueAt": tick["dueAt"]}):
        return None
    if now_ms() < pending["dueAt"]:
        return tick
    try:
        advance_robots(db, table, send, room, context)
    except RoomConflictError:
        # Another worker or a snapshot won; its stream event owns continuation.
        return None
    if room["revision"] == tick["revision"]:
        return tick
    return None


def solo_room(room):
    from lambdas.core.robot.practice import require_solo, PracticeDenied
    humans = [user for user in room.get("seats", {}).values()
              if user and not is_robot_seat(user)]
    if len(humans) != 1:
        return False
    try:
        require_solo(room, humans[0])
    except PracticeDenied:
        return False
    return True


def read_feature(room, user_id, operation, data):
    """Read-only records use the same connection and room membership gate as play."""
    game = room["gameData"]
    archives.store.put_completed(room)
    duplicate.record_completion(room)
    payload = {"roomId": room["roomId"]}
    if operation == "getAgreementCard":
        payload.update(action="agreementCard", card=agreements.card(data.get("version")),
                       agreements=game.get("agreements") or agreements.board_agreements())
    elif operation == "getMatchScoreboard":
        payload.update(action="matchScoreboard",
                       scoreboard=copy.deepcopy(game.get("scoreboard") or match.empty()))
    elif operation == "getBoardArchive":
        board_id = data.get("boardId")
        if not isinstance(board_id, str) or not board_id:
            raise GameRequestError(400, "boardId is required")
        if board_id == game.get("boardId") and not archives.eligible(room):
            raise GameRequestError(409, "Board is not completed and cleared")
        board = archives.store.get(room["roomId"], board_id)
        if not board:
            raise GameRequestError(404, "Board archive does not exist")
        if not archives.embargo_allows(room, board, user_id):
            raise GameRequestError(403, "Board archive is embargoed")
        payload.update(action="boardArchive", board=board)
    else:
        limit, before = data.get("limit", 50), data.get("beforeBoardNumber")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise GameRequestError(400, "limit must be an integer from 1 to 100")
        if before is not None and (type(before) is not int or before < 1):
            raise GameRequestError(400, "beforeBoardNumber must be a positive integer")
        boards = archives.store.list(room["roomId"], limit=limit, before=before)
        visible = [board for board in boards
                   if archives.embargo_allows(room, board, user_id)]
        summaries = [{key: board[key] for key in (
            "boardId", "boardNumber", "dealer", "vulnerability", "contract",
            "result", "completedAt")} for board in visible]
        payload.update(action="boardArchives", boards=summaries,
                       nextBeforeBoardNumber=boards[-1]["boardNumber"]
                       if len(boards) == limit else None)
    return payload


READ_FEATURES = ("getBoardArchive", "listBoardArchives",
                 "getAgreementCard", "getMatchScoreboard")


def process_game_request(handler, event, context, operation, db, send, hands_factory=None):
    """Common route transaction. Clients may send revision to reject stale commands."""
    try:
        body = handler.parse_body(event)
        if not isinstance(body, dict):
            raise GameRequestError(400, "Request must be an object")
        if "data" in body and body["data"] is not None and not isinstance(body["data"], dict):
            raise GameRequestError(400, "data must be an object")
        data = handler.extract_data_from_body(body)
        if not isinstance(data, dict):
            raise GameRequestError(400, "Request must be an object")
        try:
            pacing = Pacing.from_environment()
        except ValueError as exc:
            raise GameRequestError(503, f"Invalid game pacing configuration: {exc}") from exc
        room_id = data.get("roomId")
        if operation not in duplicate.OPERATIONS and (not isinstance(room_id, str) or not room_id):
            raise GameRequestError(400, "roomId is required")
        if operation == "makeBid":
            if not data.get("bid"):
                raise GameRequestError(400, "bid is required")
            if data["bid"] not in ["pass", "double", "redouble"] + rules.CONTRACTS:
                raise GameRequestError(400, "Invalid bid")
        user_id = connection_user(db, event, data.get("userId"))
        if operation in duplicate.OPERATIONS:
            payload = handler._convert_for_json(
                duplicate.request(db, user_id, operation, data, send, context))
            send(handler.get_connection_id(event), payload)
            return handler.success_response(payload)
        table = db.get_table("ROOM_TABLE")
        found = db.find_room_by_id(room_id, table)
        if not found:
            raise GameRequestError(404, "Room does not exist")
        from lambdas.core.rooms.lifecycle import refresh_presence
        room = normalize_room(copy.deepcopy(found))
        seat = get_user_seat(room["seats"], user_id)
        if not seat:
            raise GameRequestError(403, "User is not seated in this room")
        room = normalize_room(refresh_presence(db, room, table=table))
        pacing = Pacing.for_room(room)
        if claims.reconcile(room, now_ms()):
            if not room["gameData"].get("pendingAction"):
                plan_next_action(room, pacing, now_ms())
            save_room(table, room)
            publish(db, send, room, action="claimUpdated", message="Claim closed; play resumes")
        if operation in READ_FEATURES:
            payload = handler._convert_for_json(read_feature(room, user_id, operation, data))
            send(handler.get_connection_id(event), payload)
            return handler.success_response(payload)
        claim_retry = operation in claims.OPERATIONS and claims.duplicate(room, seat, operation, data)
        if operation in claims.OPERATIONS and not claim_retry and "revision" not in data:
            raise GameRequestError(400, "Claim operations require revision")
        if operation != "getGameState" and "revision" in data and not claim_retry:
            if type(data["revision"]) is not int:
                raise GameRequestError(400, "revision must be an integer")
            if data["revision"] != int(room.get("revision", 0)):
                raise GameRequestError(409, "Stale revision; request getGameState")
        action, message = "gameState", "Current game state"
        if operation in claims.OPERATIONS:
            if not claim_retry:
                claims.apply(room, seat, operation, data, now_ms())
            action, message = "claimUpdated", "Claim updated"
        elif claims.pending(room["gameData"]) and operation != "getGameState":
            raise GameRequestError(409, "Play is frozen while a claim awaits consent")
        elif operation in ("startRoom", "nextBoard"):
            if room["ownerId"] != user_id:
                raise GameRequestError(403, "Only the room owner can start a board")
            required = "waiting" if operation == "startRoom" else "completed"
            if room.get("state") != required:
                raise GameRequestError(400, f"Room must be {required}")
            if operation == "nextBoard":
                if "revision" not in data and "boardId" not in data:
                    raise GameRequestError(400, "nextBoard requires revision or completed boardId")
                if "boardId" in data and data["boardId"] != room["gameData"].get("boardId"):
                    raise GameRequestError(409, "Stale boardId; request getGameState")
                archives.store.put_completed(room)
            for position in rules.SEATS:
                if not room["seats"].get(position):
                    room["seats"][position] = f"ROBOT_{position}"
            if room.get("eventId"):
                if operation == "startRoom":
                    raise GameRequestError(409, "Start event tables with startDuplicateEvent")
                duplicate.record_completion(room)
                duplicate.deal_for_room(room)
            else:
                rules.new_board(room, hands_factory() if hands_factory else None)
            room["gameData"]["practiceMode"] = bool(room.get("practiceSettings") and solo_room(room))
            action = "roomStarted" if operation == "startRoom" else "boardStarted"
            message = "Board started"
        elif operation == "setPracticePace":
            if room["ownerId"] != user_id or not solo_room(room):
                raise GameRequestError(403, "Practice pace requires the solo non-event room owner")
            if data.get("practiceMode") is not True:
                raise GameRequestError(400, "practiceMode must be true")
            pacing = Pacing.validated(data)
            room["practiceSettings"] = {"practiceMode": True, **pacing.public()}
            room["gameData"]["practiceMode"] = True
            room["gameData"]["pacing"] = pacing.public()
            action, message = "practicePaceChanged", "Practice pace updated"
        elif operation == "makeBid":
            if room.get("state") != "bidding":
                raise GameRequestError(400, "Room is not in bidding phase")
            rules.apply_call(room, seat, data.get("bid"))
            action, message = "bidMade", f"{seat} bid {data.get('bid')}"
        elif operation == "playCard":
            game = room["gameData"]
            if game.get("completedTrick"):
                raise GameRequestError(400, "Wait for the completed trick to be collected")
            if game.get("currentPhase") != "playing" or rules.controller(game) != seat:
                raise GameRequestError(400, "Not your turn to play")
            play_seat = game["turn"]
            rules.apply_card(room, play_seat, data.get("card"),
                             timestamp=now_ms(), hold_trick=True)
            action, message = "cardPlayed", f"{play_seat} played {data.get('card')}"
        elif operation != "getGameState":
            raise GameRequestError(400, "Unknown game operation")
        if operation != "getGameState" and not claim_retry:
            if operation not in ("setPracticePace", *claims.OPERATIONS):
                plan_next_action(room, pacing, now_ms())
            save_room(table, room)
            publish(db, send, room, action=action, message=message)
        try:
            advance_robots(db, table, send, room, context, pacing)
        except GameRequestError as exc:
            if exc.status != 409:
                raise
            latest = db.find_room_by_id(room_id, table)
            if not latest:
                raise
            room = normalize_room(copy.deepcopy(latest))
        payload = handler._convert_for_json(personalized(room, user_id, action, message))
        # API Gateway does not deliver a Lambda return body without a route response.
        try:
            send(handler.get_connection_id(event), payload)
        except Exception:
            logger.warning("Response delivery failed; snapshot is available", exc_info=True)
        return handler.success_response(payload)
    except (ValueError, TypeError, KeyError) as exc:
        error = GameRequestError(400, str(exc))
    except GameRequestError as exc:
        error = exc
    payload = {"action": "error", "statusCode": error.status, "message": str(error),
               "error": str(error)}
    connection_id = handler.get_connection_id(event)
    if connection_id:
        try:
            send(connection_id, payload)
        except Exception:
            logger.warning("Error delivery failed", exc_info=True)
    return handler.error_response(error.status, str(error))
