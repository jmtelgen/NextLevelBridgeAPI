"""Named, server-owned play budgets; bidding is identical across these tiers."""
from dataclasses import dataclass

from . import fair_play


@dataclass(frozen=True)
class Level:
    name: str
    samples: int
    budget_ms: int

    def public(self):
        return {"name": self.name, "samples": self.samples, "budgetMs": self.budget_ms,
                "scope": "card-play only; bidding is unchanged"}


LEVELS = {
    "heuristic": Level("heuristic", 0, 0),
    "standard": Level("standard", 4, 50),
    "thoughtful": Level("thoughtful", 8, 100),
}


def level_policy(name):
    if not isinstance(name, str) or name not in LEVELS:
        raise ValueError("computerLevel must be heuristic, standard or thoughtful")
    return LEVELS[name]


def room_level(room):
    return level_policy(room.get("computerLevel", "standard"))


def choose(state, level, *, solver_factory=None, seed=0):
    """Only a lawful Observation reaches either policy (never a room/full deal)."""
    policy = level_policy(level)
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an integer in 0..4294967295")
    if policy.samples == 0:
        return fair_play.Decision(fair_play.heuristic(state), "heuristic", 0)
    config = fair_play.PlayConfig(seed, policy.samples, policy.budget_ms)
    if solver_factory is None:
        return fair_play.choose_card(state, config)
    return fair_play.choose_card(state, config, solver_factory=solver_factory)


def choose_for_room(room, actor):
    policy = room_level(room)
    state = fair_play.observe(room, actor)
    if not state.hand:
        return None
    decision = choose(state, policy.name)
    return next(value for value in room["gameData"]["hands"][actor]
                if fair_play.card(value) == decision.card)
