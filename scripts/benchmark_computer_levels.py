#!/usr/bin/env python3
"""Paired fixed-contract comparisons of named server play-budget tiers."""
import argparse
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lambdas.core.game import rules
from lambdas.core.robot import fair_play as ai
from lambdas.core.robot import level_policy as levels
from scripts import benchmark_robots as baseline

MATCHUPS = (("standard", "heuristic"), ("thoughtful", "heuristic"), ("thoughtful", "standard"))


def _leg(template, north_south, east_west, seed, metrics, solver_factory):
    room = deepcopy(template)
    trace = []
    while room["gameData"]["currentPhase"] == "playing":
        game = room["gameData"]
        actor = game["turn"]
        policy = north_south if rules.side(actor) == "NS" else east_west
        started = time.perf_counter()
        state = ai.observe(room, actor)
        decision = levels.choose(state, policy, seed=seed, solver_factory=solver_factory)
        elapsed = (time.perf_counter() - started) * 1000
        record = metrics[policy]
        record["actions"] += 1
        record["latencies"].append(elapsed)
        record["modes"][decision.mode] += 1
        record["complete_sample_batches"] += decision.samples
        if decision.reason:
            record["fallback_reasons"][decision.reason] += 1
        if decision.card not in rules.legal_cards(game, actor):
            raise RuntimeError("Illegal named-policy decision")
        record["legal_actions"] += 1
        trace.append((actor, decision.card, policy))
        rules.apply_card(room, actor, decision.card)
    if len(trace) != 52 or len(room["gameData"]["tricks"]) != 13:
        raise RuntimeError("Benchmark card/trick conservation failed")
    return {"scoreNS": room["gameData"]["result"]["scoreNS"],
            "actionDigest": hashlib.sha256(json.dumps(trace).encode()).hexdigest(),
            "actions": len(trace)}


def run_benchmark(pairs=32, seed=20261026, solver_factory=ai.default_solver):
    if type(pairs) is not int or not 1 <= pairs <= 64:
        raise ValueError("pairs must be an integer in 1..64")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 65:
        raise ValueError("seed must be an integer in 0..4294967231")
    solver = solver_factory()  # Explicit failure, never a pretend successful DDS run.
    metrics = {name: baseline._new_metrics() for name in levels.LEVELS}
    records = []
    for index, matchup in zip(range(pairs), itertools.cycle(MATCHUPS)):
        first, second = matchup
        template = baseline.board_room(seed, index)
        game = template["gameData"]
        # Rotate each strain across all declarers, rather than coupling 3NT to North.
        declarer = ai.SEATS[(index + index // 4) % 4]
        game.update(boardId=f"level-benchmark-{seed}-{index}",
                    declarer=declarer, dummy=ai.partner(declarer), turn=ai.next_seat(declarer))
        legs = [_leg(template, first, second, seed + index, metrics, lambda: solver),
                _leg(template, second, first, seed + index, metrics, lambda: solver)]
        delta = legs[0]["scoreNS"] - legs[1]["scoreNS"]
        records.append({"board": index + 1, "dealSeed": seed + index,
                        "contract": game["contract"], "declarer": declarer,
                        "first": first, "second": second, "legs": legs,
                        "scoreDelta": delta, "impDelta": baseline.score_to_imps(delta)})
    comparisons = []
    for first, second in MATCHUPS:
        subset = [row for row in records if (row["first"], row["second"]) == (first, second)]
        if subset:
            imps = [row["impDelta"] for row in subset]
            comparisons.append({"first": first, "second": second, "positiveFavors": first,
                                "meanImpsPerPair": statistics.mean(imps),
                                "totalImps": sum(imps), **baseline.uncertainty(imps, seed)})
    return {
        "benchmarkVersion": 1, "seed": seed, "pairedBoards": pairs,
        "levels": [policy.public() for policy in levels.LEVELS.values()],
        "method": "Same seeded deal/contract twice with tiers swapped NS/EW; no bidding or par.",
        "information": "Every policy receives only fair_play.Observation, never actual hidden hands.",
        "reproducibility": "Deal seeds reproducible; soft wall-clock deadlines make action traces machine/load dependent.",
        "latencyScope": "Projection plus policy; initialization, networking and persistence excluded.",
        "biddingStrengthChanged": False, "expertStrengthProven": False,
        "policies": {name: baseline._summarize_metrics(record) for name, record in metrics.items()},
        "comparisons": comparisons, "pairs": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20261026)
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(**vars(args))
    except (ValueError, RuntimeError) as exc:
        parser.exit(2, f"benchmark failed: {exc}\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if any(policy["solver_error_actions"] for policy in report["policies"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
