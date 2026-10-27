"""SOLO-only guided practice, projected before any optional policy computation."""
from functools import lru_cache
import threading

from lambdas.core.game import rules
from . import fair_play
from .level_policy import choose, room_level

_HINT_LOCK = threading.Lock()


class PracticeDenied(PermissionError):
    pass


def require_solo(room, user_id):
    seats = room.get("seats", {})
    if set(seats) != set(rules.SEATS):
        raise PracticeDenied("Practice requires one human and three robots")
    humans = [occupant for occupant in seats.values()
              if isinstance(occupant, str) and occupant and not occupant.startswith("ROBOT_")]
    robots = [occupant for occupant in seats.values()
              if isinstance(occupant, str) and occupant.startswith("ROBOT_")]
    if humans != [user_id] or len(robots) != 3:
        raise PracticeDenied("Practice requires one human and three robots")
    game = room.get("gameData", {})
    for source in (room, game):
        if any(source.get(key) for key in (
                "eventId", "tournamentId", "competitionId", "matchId",
                "competitive", "isCompetitive", "ranked", "isRanked")):
            raise PracticeDenied("Live practice is unavailable in competitive rooms")
        if source.get("mode", "solo") not in ("solo", "SOLO", "practice"):
            raise PracticeDenied("Live practice is available only in SOLO rooms")
    return next(seat for seat, occupant in seats.items() if occupant == user_id)


@lru_cache(maxsize=128)
def _cached_decision(state, level):
    # The bounded cache key contains only lawful information, never hidden deals.
    return choose(state, level)


def practice_hint(room, user_id, *, suggest=True):
    if type(suggest) is not bool:
        raise ValueError("suggest must be a boolean")
    seat = require_solo(room, user_id)
    policy = room_level(room)
    game = room.get("gameData", {})
    if game.get("completedTrick"):
        raise PracticeDenied("Wait until the completed trick is collected")
    phase = game.get("currentPhase")
    if phase not in ("bidding", "playing") or rules.controller(game) != seat:
        raise PracticeDenied("Only the current actor or declarer controlling dummy may request a hint")
    actor = game["turn"]
    if phase == "playing":
        declarer = game.get("declarer")
        if declarer not in rules.SEATS or game.get("dummy") != rules.partner(declarer):
            raise PracticeDenied("Invalid declarer/dummy control metadata")
    result = {"phase": phase, "actor": actor, "controller": seat,
              "computerLevel": policy.public(), "suggestion": None,
              "information": "Your hand, exposed dummy and public history only; no hidden allocation or par."}
    if phase == "bidding":
        # Read only the requesting actor's hand. No whole-room bidder is invoked.
        hand = tuple(fair_play.card(value) for value in game.get("hands", {}).get(seat, []))
        if len(hand) != 13 or len(set(hand)) != 13:
            raise ValueError("Bidding hint requires a complete thirteen-card visible hand")
        hcp = sum({"A": 4, "K": 3, "Q": 2, "J": 1}.get(value[0], 0) for value in hand)
        shape = {suit: sum(value[1] == suit for value in hand) for suit in fair_play.SUITS}
        result.update(legalActions=rules.legal_calls(game, seat), handHcp=hcp, shape=shape,
                      explanation="Pass is legal. A new contract must outrank the last contract; "
                                  "double/redouble depend on the last contract side and multiplier. "
                                  "HCP counts A=4, K=3, Q=2, J=1. No convention or hidden fit is inferred.")
        return result
    state = fair_play.observe(room, actor)
    legal = fair_play.legal_cards(state.hand, state.trick)
    led = fair_play.card(state.current[0][1])[1] if state.current else None
    must_follow = bool(led and any(value[1] == led for value in state.hand))
    result.update(legalActions=legal,
                  explanation=(f"You must follow {led} because this hand contains that suit."
                               if must_follow else
                               "You are leading; any card is legal." if not led else
                               f"This hand is void in {led}; any card is legal."))
    if suggest:
        with _HINT_LOCK:
            decision = _cached_decision(state, policy.name)
        # Do not expose solver exception text or imply evidence that was not obtained.
        degraded = decision.reason is not None
        result["suggestion"] = {
            "card": decision.card, "mode": decision.mode, "completedSamples": decision.samples,
            "degraded": degraded,
            "caution": ("Sampled analysis unavailable or budget exhausted; legal heuristic only."
                        if degraded else
                        "Legal heuristic, not an optimal-play guarantee." if decision.mode == "heuristic" else
                        "Only one legal card." if decision.mode == "forced" else
                        "Limited public-information samples, not certainty or a double-dummy answer to the actual deal."),
        }
    return result
