"""Consent-only claims. No solver, hidden-hand evaluation, or fabricated plays."""
import copy
import re

from lambdas.core.game import rules
from lambdas.core.robot.robot_utils import is_robot_seat

OPERATIONS = ("proposeClaim", "respondClaim", "cancelClaim")
TIMEOUT_MS = 60000
MAX_PROPOSALS = 16


def pending(game):
    return game.get("claim", {}).get("status") == "pending"


def close(room, status, timestamp):
    game = room["gameData"]
    claim = game["claim"]
    claim.update(status=status, resolvedAt=timestamp)
    suspended = game.pop("claimSuspendedAction", None)
    game["pendingAction"] = None
    if suspended:
        suspended["dueAt"] += timestamp - claim["createdAt"]
        game["pendingAction"] = suspended


def reconcile(room, timestamp):
    game = room["gameData"]
    if not pending(game):
        return False
    claim = game["claim"]
    if timestamp >= claim["expiresAt"]:
        close(room, "expired", timestamp)
        return True
    seats = [claim["proposer"], *claim["requiredSeats"]]
    from lambdas.core.rooms.lifecycle import public_presence
    presence = public_presence(room, now=timestamp / 1000) if room.get("presence") else {}
    if any(presence.get(seat, {}).get("status") in ("reconnecting", "offline") for seat in seats):
        close(room, "disconnected", timestamp)
        return True
    return False


def check_selectors(game, data):
    if data.get("boardId") != game.get("boardId"):
        raise ValueError("Claim requires the current boardId")
    proposal_id = data.get("proposalId")
    if not isinstance(proposal_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", proposal_id):
        raise ValueError("proposalId must contain 1..80 letters, digits, underscores or hyphens")


def duplicate(room, seat, operation, data):
    """Authenticate retries against the actual proposal before ignoring revision."""
    game = room["gameData"]
    check_selectors(game, data)
    claim = game.get("claim") or {}
    if claim.get("proposalId") != data["proposalId"]:
        return False
    if operation == "proposeClaim":
        if claim["proposer"] != seat or type(data.get("tricks")) is not int or data["tricks"] != claim["tricks"]:
            raise ValueError("proposalId already identifies a different proposal")
        return True
    if operation == "respondClaim":
        if seat not in claim["requiredSeats"] or type(data.get("accept")) is not bool:
            raise ValueError("Only a required human may submit a boolean vote")
        if seat in claim["votes"]:
            if claim["votes"][seat] != data["accept"]:
                raise ValueError("A claim vote cannot be changed")
            return True
    elif operation == "cancelClaim" and claim["proposer"] == seat and claim["status"] == "cancelled":
        return True
    return False


def apply(room, seat, operation, data, timestamp):
    game = room["gameData"]
    check_selectors(game, data)
    if operation == "proposeClaim":
        if pending(game):
            raise ValueError("A claim is already pending")
        if game.get("currentPhase") != "playing" or game.get("completedTrick") or rules.controller(game) != seat:
            raise ValueError("Only the current human controller may claim at a stable play position")
        count = game.get("claimCount", 0)
        if count >= MAX_PROPOSALS:
            raise ValueError("This board has reached its 16-proposal limit")
        used = game.setdefault("claimProposalIds", [])
        if data["proposalId"] in used:
            raise ValueError("proposalId has already been used on this board")
        remaining = 13 - len(game["tricks"])
        tricks = data.get("tricks")
        if type(tricks) is not int or not 0 <= tricks <= remaining:
            raise ValueError("tricks must be an integer from zero to remainingTricks")
        if tricks and any(is_robot_seat(user) for position, user in room["seats"].items()
                          if rules.side(position) != rules.side(seat)):
            raise ValueError("Computer opponents reject unproven positive claims")
        required = [position for position, user in room["seats"].items()
                    if position != seat and user and not is_robot_seat(user)]
        game["claim"] = {
            "proposalId": data["proposalId"], "boardId": game["boardId"],
            "proposer": seat, "side": rules.side(seat), "tricks": tricks,
            "remainingTricks": remaining, "requiredSeats": required, "votes": {},
            "status": "pending", "createdAt": timestamp,
            "expiresAt": timestamp + TIMEOUT_MS,
        }
        game["claimCount"] = count + 1
        used.append(data["proposalId"])
        game["claimSuspendedAction"] = copy.deepcopy(game.get("pendingAction"))
        game["pendingAction"] = {"kind": "claimExpiry", "dueAt": timestamp + TIMEOUT_MS}
        game["robotPending"] = False
    else:
        claim = game.get("claim") or {}
        if claim.get("proposalId") != data["proposalId"] or not pending(game):
            raise ValueError("No matching pending proposal")
        if operation == "cancelClaim":
            if seat != claim["proposer"]:
                raise ValueError("Only the proposer may cancel")
            close(room, "cancelled", timestamp)
            return
        if seat not in claim["requiredSeats"] or type(data.get("accept")) is not bool:
            raise ValueError("Only a required human may submit a boolean vote")
        claim["votes"][seat] = data["accept"]
        if not data["accept"]:
            close(room, "rejected", timestamp)
            return
    claim = game["claim"]
    if all(claim["votes"].get(position) is True for position in claim["requiredSeats"]):
        close(room, "accepted", timestamp)
        allocation = {claim["side"]: claim["tricks"],
                      "EW" if claim["side"] == "NS" else "NS":
                          claim["remainingTricks"] - claim["tricks"]}
        game["claimSettlement"] = {
            "proposalId": claim["proposalId"], "proposer": claim["proposer"],
            "allocation": allocation, "acceptedAt": timestamp,
            "unplayedTrick": copy.deepcopy(game.get("currentTrick", [])),
        }
        game["currentTrick"] = []
        game["pendingAction"] = None
        game["robotPending"] = False
        rules.finish_board(room)
