"""Public-information, sampled double-dummy card selection.

This is a determinization baseline, not an expert imperfect-information solver.
Only ``observe`` touches a room; inference and evaluation receive its projection.
"""

from dataclasses import dataclass
from functools import lru_cache
import logging
import os
import random
import threading
import time
from typing import Callable, Optional

SEATS = ("North", "East", "South", "West")
SUITS = "SHDC"
RANKS = "23456789TJQKA"
DECK = tuple(rank + suit for suit in SUITS for rank in RANKS)
LOG = logging.getLogger(__name__)
_DDS_LOCK = threading.RLock()


def card(value: str) -> str:
    """Canonical rank-suit card; accept legacy suit-rank and 10 spellings."""
    value = value.strip().upper().replace("10", "T")
    if len(value) == 2:
        if value[0] in RANKS and value[1] in SUITS:
            return value
        if value[0] in SUITS and value[1] in RANKS:
            return value[::-1]
    raise ValueError(f"Invalid bridge card: {value!r}")


def rank(value: str) -> int:
    return RANKS.index(card(value)[0]) + 2


def partner(seat: str) -> str:
    return SEATS[(SEATS.index(seat) + 2) % 4]


def next_seat(seat: str) -> str:
    return SEATS[(SEATS.index(seat) + 1) % 4]


def legal_cards(hand, trick):
    normalized = [card(value) for value in hand]
    suit = card(trick[0]["card"])[1] if trick else None
    following = [value for value in normalized if value[1] == suit]
    return sorted(following or normalized, key=lambda value: (rank(value), SUITS.index(value[1])))


def trick_winner(plays, trump: str) -> str:
    led = card(plays[0]["card"])[1]

    def strength(play):
        value = card(play["card"])
        return (2 if value[1] == trump else 1 if value[1] == led else 0, rank(value))

    return max(plays, key=strength)["seat"]


@dataclass(frozen=True)
class Observation:
    actor: str
    controller: str
    known: tuple
    played: tuple
    current: tuple
    counts: tuple
    voids: tuple
    leader: str
    trump: str

    @property
    def hand(self):
        return dict(self.known)[self.actor]

    @property
    def trick(self):
        return [{"seat": seat, "card": value} for seat, value in self.current]


def observe(room: dict, actor: str) -> Observation:
    """Copy permitted information; never inspect concealed opponents' hands/counts."""
    if actor not in SEATS:
        raise ValueError("Unknown acting seat")
    game = room.get("gameData", {})
    declarer = game.get("declarer", "North")
    dummy = partner(declarer)
    completed = game.get("tricks", [])
    current = game.get("currentTrick", [])
    if len(current) > 3:
        raise ValueError("A completed trick must be resolved before selecting a card")
    history = [trick.get("plays", trick.get("cards", [])) for trick in completed]
    history.append(current)
    public_count = sum(len(trick) for trick in history)
    if actor == dummy and not public_count:
        raise ValueError("Dummy cannot play before the opening lead")
    controller = declarer if actor == dummy else actor
    hands = game.get("hands", {})
    known_seats = {controller}
    if public_count:
        known_seats.add(dummy)
    known = tuple((seat, tuple(sorted(card(value) for value in hands.get(seat, []))))
                  for seat in SEATS if seat in known_seats)
    counts = dict.fromkeys(SEATS, 13)
    voids = {seat: set() for seat in SEATS}
    played = []
    for index, trick in enumerate(history):
        if index < len(history) - 1 and len(trick) != 4:
            raise ValueError("Incomplete completed trick")
        if not trick:
            continue
        leader = trick[0]["seat"]
        led = card(trick[0]["card"])[1]
        for offset, play in enumerate(trick):
            seat, value = play["seat"], card(play["card"])
            if seat != SEATS[(SEATS.index(leader) + offset) % 4]:
                raise ValueError("Public trick seats are not clockwise")
            if value[1] in voids[seat]:
                raise ValueError("Public history contradicts an observed void")
            if value[1] != led:
                voids[seat].add(led)
            counts[seat] -= 1
            played.append(value)
    if len(set(played)) != len(played) or min(counts.values()) < 0:
        raise ValueError("Duplicate public cards or too many plays")
    if current:
        leader = current[0]["seat"]
        if actor != SEATS[(SEATS.index(leader) + len(current)) % 4]:
            raise ValueError("Actor is not next in the partial trick")
    elif completed:
        last = completed[-1]
        leader = last.get("winner") or trick_winner(history[-2], _trump(game))
        if actor != leader:
            raise ValueError("Actor is not the previous trick winner")
    else:
        leader = next_seat(declarer)
        if actor != leader:
            raise ValueError("Actor is not the opening leader")
    return Observation(actor, controller, known, tuple(played),
                       tuple((play["seat"], card(play["card"])) for play in current),
                       tuple(counts.items()),
                       tuple((seat, tuple(sorted(voids[seat]))) for seat in SEATS),
                       leader, _trump(game))


def _trump(game):
    contract = str(game.get("contract", "1NT")).upper()
    return "N" if "N" in contract else next((suit for suit in SUITS if suit in contract), "N")


def sample_deal(state: Observation, rng: random.Random) -> dict:
    """Randomized capacity-constrained matching; finite, not rejection sampling.

    Slot matching satisfies every public void and remaining count. The resulting
    distribution is deliberately not claimed to be uniform over feasible deals.
    """
    known = {seat: list(values) for seat, values in state.known}
    counts, voids = dict(state.counts), dict(state.voids)
    used = list(state.played) + [value for values in known.values() for value in values]
    if len(set(used)) != len(used):
        raise ValueError("Known/public cards overlap")
    for seat, values in known.items():
        if len(values) != counts[seat] or any(value[1] in voids[seat] for value in values):
            raise ValueError("Known hand contradicts public remaining counts/voids")
    unseen = [value for value in DECK if value not in set(used)]
    slots = [seat for seat in SEATS if seat not in known for _ in range(counts[seat])]
    if len(unseen) != len(slots):
        raise ValueError("Cards do not conserve a 52-card deal")
    rng.shuffle(unseen)
    options = {}
    for value in unseen:
        options[value] = [index for index, seat in enumerate(slots) if value[1] not in voids[seat]]
        rng.shuffle(options[value])
    assigned = {}

    def augment(value, visited):
        for index in options[value]:
            if index in visited:
                continue
            visited.add(index)
            if index not in assigned or augment(assigned[index], visited):
                assigned[index] = value
                return True
        return False

    for value in sorted(unseen, key=lambda item: len(options[item])):
        if not augment(value, set()):
            raise ValueError("No hidden allocation satisfies public constraints")
    result = {seat: known.get(seat, [])[:] for seat in SEATS}
    for index, value in assigned.items():
        result[slots[index]].append(value)
    return {seat: sorted(values) for seat, values in result.items()}


def heuristic(state: Observation) -> str:
    """Legal deterministic baseline: sequence/low lead, cheap winner, low discard."""
    available = legal_cards(state.hand, state.trick)
    if not available:
        raise ValueError("No cards in acting hand")
    if not state.current:
        suits = {suit: [value for value in available if value[1] == suit] for suit in SUITS}
        suit = max(SUITS, key=lambda item: (len(suits[item]), -SUITS.index(item)))
        ordered = sorted(suits[suit], key=rank, reverse=True)
        if len(ordered) > 1 and rank(ordered[0]) >= 11 and rank(ordered[0]) - rank(ordered[1]) == 1:
            return ordered[0]
        return min(ordered, key=rank)
    winner = trick_winner(state.trick, state.trump)
    if winner == partner(state.actor):
        return available[0]
    winning = [value for value in available
               if trick_winner(state.trick + [{"seat": state.actor, "card": value}], state.trump) == state.actor]
    if winning:
        return min(winning, key=lambda value: (value[1] == state.trump, rank(value), SUITS.index(value[1])))
    return available[0]


@dataclass(frozen=True)
class PlayConfig:
    seed: int = 0
    samples: int = 4
    budget_ms: int = 50

    def __post_init__(self):
        if not 1 <= self.samples <= 32 or not 0 <= self.budget_ms <= 5000:
            raise ValueError("samples must be 1..32; budget_ms must be 0..5000")

    @classmethod
    def from_env(cls):
        return cls(int(os.environ.get("ROBOT_PLAY_SEED", "0")),
                   int(os.environ.get("ROBOT_PLAY_SAMPLES", "4")),
                   int(os.environ.get("ROBOT_PLAY_BUDGET_MS", "50")))


@dataclass(frozen=True)
class Decision:
    card: str
    mode: str
    samples: int
    reason: Optional[str] = None


@lru_cache(maxsize=1)
def default_solver():
    from lambdas.dds.working_dds_wrapper import DDS
    with _DDS_LOCK:
        return DDS(max_threads=1, max_memory=32)


def evaluate_candidate(solver, state: Observation, deal: dict, candidate: str) -> int:
    """Return future tricks for actor's partnership, including the current trick."""
    hands = {seat: list(values) for seat, values in deal.items()}
    hands[state.actor].remove(candidate)
    trick = state.trick + [{"seat": state.actor, "card": candidate}]
    immediate = 0
    if len(trick) == 4:
        leader = trick_winner(trick, state.trump)
        immediate = int(leader in (state.actor, partner(state.actor)))
        trick = []
        to_play = leader
    else:
        leader = state.leader
        to_play = next_seat(state.actor)
    remaining = (sum(len(values) for values in hands.values()) + len(trick)) // 4
    if not remaining:
        return immediate
    # The existing adapter expects suit-rank; native scores belong to the
    # partnership of the NEXT player, not necessarily the trick leader.
    with _DDS_LOCK:
        results = solver.solve_board(
            trump=state.trump, first=leader[0],
            current_trick=[play["card"][::-1] for play in trick],
            hands={seat[0]: [value[::-1] for value in values] for seat, values in hands.items()},
            target=-1, solutions=1, mode=1, thread_index=0,
        )
    if not results:
        raise RuntimeError("DDS returned no continuation score")
    score = max(value for _, value in results)
    if not 0 <= score <= remaining:
        raise RuntimeError("DDS returned an invalid continuation score")
    return immediate + (score if to_play in (state.actor, partner(state.actor)) else remaining - score)


def choose_card(state: Observation, config: Optional[PlayConfig] = None,
                solver_factory: Callable = default_solver,
                clock: Callable = time.monotonic) -> Decision:
    config = config or PlayConfig.from_env()
    fallback = heuristic(state)
    candidates = legal_cards(state.hand, state.trick)
    if len(candidates) == 1:
        return Decision(candidates[0], "forced", 0)
    started = clock()
    rng = random.Random(config.seed)
    totals = dict.fromkeys(candidates, 0)
    completed = 0
    try:
        solver = solver_factory()
        for _ in range(config.samples):
            if config.budget_ms and (clock() - started) * 1000 >= config.budget_ms:
                break
            deal = sample_deal(state, rng)
            scores = {}
            for candidate in candidates:
                if config.budget_ms and (clock() - started) * 1000 >= config.budget_ms:
                    break
                scores[candidate] = evaluate_candidate(solver, state, deal, candidate)
            if len(scores) != len(candidates):
                break
            for candidate, score in scores.items():
                totals[candidate] += score
            completed += 1
    except Exception as exc:
        # A failed batch must never leave some candidates with more evidence.
        LOG.warning("robot_play_degraded reason=%s samples=%s", type(exc).__name__ + ": " + str(exc), completed)
        return Decision(fallback, "heuristic", completed, str(exc))
    if not completed:
        LOG.warning("robot_play_degraded reason=budget_exhausted samples=0")
        return Decision(fallback, "heuristic", 0, "budget_exhausted")
    best = max(candidates, key=lambda candidate: (totals[candidate], candidate == fallback, -candidates.index(candidate)))
    return Decision(best, "sampled_dds", completed)


def select_card(room: dict, actor: str, config: Optional[PlayConfig] = None) -> Optional[str]:
    state = observe(room, actor)
    if not state.hand:
        return None
    decision = choose_card(state, config)
    LOG.info("robot_play mode=%s samples=%s seat=%s", decision.mode, decision.samples, actor)
    # Preserve the storage spelling while keeping the engine canonical.
    return next(value for value in room["gameData"]["hands"][actor] if card(value) == decision.card)
