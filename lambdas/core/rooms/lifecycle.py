"""Room-revision serialized membership; no automatic seat takeover."""
import copy
import hashlib
import secrets
import time
import uuid

from lambdas.core.game import runtime
from lambdas.core.game.runtime import GameRequestError
from lambdas.core.robot.robot_utils import is_robot_seat

SEATS = ("North", "East", "South", "West")
RECONNECT_SECONDS = 120
MAX_INVITATIONS = 32


def save_room(table, room):
    # Resolve the runtime hook dynamically so local revision-bound timers are rescheduled.
    return runtime.save_room(table, room)


def _timestamp(now=None):
    return int(time.time() if now is None else now)


def public_presence(room, now=None):
    """Only publish seat status, never connection identifiers or invitation hashes."""
    now = _timestamp(now)
    result = {}
    for seat, user in room.get("seats", {}).items():
        record = room.get("presence", {}).get(seat, {})
        connections = record.get("connections", {}) if record.get("userId") == user else {}
        count = sum(expiry > now for expiry in connections.values())
        deadline = record.get("reservedUntil")
        if not user:
            status = "empty"
        elif is_robot_seat(user):
            status = "robot"
        elif count:
            status = "online"
        else:
            # An expired token reserves from its expiry, not the next snapshot read.
            if connections and deadline is None:
                deadline = max(connections.values()) + RECONNECT_SECONDS
            status = "reconnecting" if deadline is None or deadline > now else "offline"
        item = {"status": status, "connectionCount": count}
        if user:
            item["userId"] = user
        if user and not count and not is_robot_seat(user) and deadline is not None:
            item["reservedUntil"] = deadline
        result[seat] = item
    return result


def refresh_presence(db, room, table=None, now=None):
    """Refresh every valid tab, committing on the same CAS as seat ownership.

    Callers must use the returned room/revision and fail/retry on conflict.
    Expired authentication is not presence, even before socket cleanup.
    """
    now = _timestamp(now)
    updated = copy.deepcopy(room)
    presence = {}
    for seat, user in room.get("seats", {}).items():
        if not user or is_robot_seat(user):
            continue
        old = room.get("presence", {}).get(seat, {})
        if old.get("userId") != user:
            old = {}
        records = db.get_user_connection_records(user)
        valid = {item["connectionId"]: int(item["authExpiresAt"])
                 for item in records if item["authExpiresAt"] > now}
        record = {"userId": user, "connections": valid}
        if not valid:
            if old.get("reservedUntil") is not None:
                disconnected = int(old["disconnectedAt"])
            else:
                previous = old.get("connections", {})
                # A disconnect before expiry starts grace now. Token expiry does not.
                expiries = [int(value) for value in previous.values()]
                expiries.extend(int(item["authExpiresAt"]) for item in records)
                disconnected = min(now, max(expiries)) if expiries else now
            record.update(disconnectedAt=disconnected,
                          reservedUntil=disconnected + RECONNECT_SECONDS)
        presence[seat] = record
    updated["presence"] = presence
    if updated.get("presence") != room.get("presence"):
        save_room(table if table is not None else db.get_table("ROOM_TABLE"), updated)
    return updated


def sync_user_presence(db, user_id, send=None, now=None):
    """Upgrade/disconnect hook; every occupied room, not just one tab's room."""
    from lambdas.core.game.runtime import publish, RoomConflictError
    table = db.get_table("ROOM_TABLE")
    for room in db.get_rooms_for_user(user_id, table):
        for _ in range(4):
            try:
                updated = refresh_presence(db, room, table, now)
                if updated.get("revision") != room.get("revision") and send:
                    publish(db, send, updated, "roomUpdated", "Player presence changed")
                break
            except RoomConflictError:
                room = db.find_room_by_id(room["roomId"], table)
                if not room or user_id not in room.get("seats", {}).values():
                    break
        else:
            raise GameRequestError(409, "Presence changed; reconnect or request a snapshot")


def require_owner(room, user_id):
    if room.get("ownerId") != user_id:
        raise GameRequestError(403, "Only the room owner may perform this action")


def require_waiting(room):
    if room.get("eventId"):
        raise GameRequestError(409, "Event table membership and ownership are frozen")
    if room.get("state") != "waiting":
        raise GameRequestError(409, "Seats cannot be released or moved during a board")


def _invitation_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_invitation(room, token, now=None):
    if not isinstance(token, str) or len(token) > 256 or "." not in token:
        raise GameRequestError(403, "A valid room invitation is required")
    identifier = token.split(".", 1)[0]
    invitation = room.get("invitations", {}).get(identifier)
    if (not invitation or invitation.get("revoked")
            or invitation.get("expiresAt", 0) <= _timestamp(now)
            or not secrets.compare_digest(invitation.get("digest", ""), _invitation_digest(token))):
        raise GameRequestError(403, "Invitation is expired, revoked, or invalid")


def join_room(db, table, room, user_id, token=None, now=None):
    room = refresh_presence(db, room, table, now)
    if user_id in room["seats"].values():
        # An existing seat is a reconnect, including during the active board.
        return room, next(seat for seat, occupant in room["seats"].items() if occupant == user_id), True
    require_waiting(room)
    if room.get("locked", False):
        raise GameRequestError(403, "Room is locked")
    if room.get("isPrivate", False):
        require_invitation(room, token, now)
    available = next((seat for seat in SEATS if not room["seats"].get(seat)), None)
    if not available:
        raise GameRequestError(409, "No seats available")
    room["seats"][available] = user_id
    records = db.get_user_connection_records(user_id)
    now = _timestamp(now)
    room.setdefault("presence", {})[available] = {
        "userId": user_id,
        "connections": {item["connectionId"]: int(item["authExpiresAt"])
                        for item in records if item["authExpiresAt"] > now},
    }
    save_room(table, room)
    return room, available, False


def change_seat(table, room, user_id, new_seat):
    require_waiting(room)
    if new_seat not in SEATS:
        raise GameRequestError(400, "Invalid seat")
    old = next((seat for seat, user in room["seats"].items() if user == user_id), None)
    if not old:
        raise GameRequestError(403, "User is not seated in this room")
    if room["seats"].get(new_seat):
        raise GameRequestError(409, "Seat is occupied")
    room["seats"][old], room["seats"][new_seat] = "", user_id
    record = room.setdefault("presence", {}).pop(old, None)
    if record:
        room["presence"][new_seat] = record
    save_room(table, room)
    return old


def leave_room(table, room, user_id):
    require_waiting(room)
    seat = next((seat for seat, user in room["seats"].items() if user == user_id), None)
    if not seat:
        raise GameRequestError(403, "User is not seated in this room")
    if room.get("ownerId") == user_id:
        raise GameRequestError(409, "Transfer ownership to another seated human before leaving")
    room["seats"][seat] = ""
    room.setdefault("presence", {}).pop(seat, None)
    save_room(table, room)
    return seat


def replace_player(db, table, room, user_id, seat, now=None):
    require_owner(room, user_id)
    if room.get("eventId"):
        raise GameRequestError(409, "Event table membership is frozen")
    if seat not in SEATS:
        raise GameRequestError(400, "Invalid seat")
    occupant = room["seats"].get(seat)
    if not occupant or is_robot_seat(occupant):
        raise GameRequestError(409, "Seat is not occupied by a human")
    if occupant == room.get("ownerId"):
        raise GameRequestError(409, "Transfer ownership before replacing the owner")
    room = refresh_presence(db, room, table, now)
    if public_presence(room, now)[seat]["status"] != "offline":
        raise GameRequestError(409, "Player is online or the reconnect reservation has not expired")
    # This CAS competes with reconnect on the same revision. Hands/turn/scores stay intact.
    room["seats"][seat] = f"ROBOT_{seat}"
    room.setdefault("presence", {}).pop(seat, None)
    room.setdefault("roomEvents", []).append({
        "type": "playerReplaced", "seat": seat, "previousUserId": occupant,
        "by": user_id, "at": _timestamp(now)})
    room["roomEvents"] = room["roomEvents"][-32:]
    save_room(table, room)
    return room


def control_room(table, room, user_id, action, data, now=None, db=None):
    require_owner(room, user_id)
    now = _timestamp(now)
    if action == "transferOwnership":
        require_waiting(room)
        target = data.get("newOwnerId")
        if not target or target not in room["seats"].values() or is_robot_seat(target):
            raise GameRequestError(400, "New owner must be a seated human")
        if target == user_id:
            raise GameRequestError(400, "New owner must differ from the current owner")
        if db is None:
            raise GameRequestError(503, "Atomic ownership transfer is unavailable")
        transferred = db.transfer_room_ownership(table, room, target)
        room.clear()
        room.update(transferred)
        return None
    elif action == "setRoomLock":
        if not isinstance(data.get("locked"), bool):
            raise GameRequestError(400, "locked must be a boolean")
        room["locked"] = data["locked"]
    elif action == "createInvitation":
        lifetime = data.get("expiresInSeconds", 3600)
        if isinstance(lifetime, bool) or not isinstance(lifetime, int) or not 1 <= lifetime <= 86400:
            raise GameRequestError(400, "expiresInSeconds must be between 1 and 86400")
        invitations = {key: value for key, value in room.get("invitations", {}).items()
                       if value["expiresAt"] > now and not value.get("revoked")}
        if len(invitations) >= MAX_INVITATIONS:
            raise GameRequestError(409, "Revoke an invitation before creating another")
        identifier = uuid.uuid4().hex
        token = identifier + "." + secrets.token_urlsafe(32)
        invitations[identifier] = {
            "digest": _invitation_digest(token), "expiresAt": now + lifetime}
        room["invitations"] = invitations
        save_room(table, room)
        return {"action": "roomInvitation", "success": True, "roomId": room["roomId"],
                "invitationId": identifier, "invitationToken": token, "expiresAt": now + lifetime}
    elif action == "revokeInvitation":
        identifier = data.get("invitationId")
        if not isinstance(identifier, str) or identifier not in room.get("invitations", {}):
            raise GameRequestError(404, "Invitation does not exist")
        room["invitations"][identifier]["revoked"] = True
    else:
        raise GameRequestError(400, "Unknown room control")
    save_room(table, room)
    return None
