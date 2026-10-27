#!/usr/bin/env python3
"""Seeded, paired duplicate comparison of lawful sampled DDS and heuristic play."""

import argparse
from bisect import bisect_right
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lambdas.core.game import rules
from lambdas.core.robot import fair_play as ai

IMP_THRESHOLDS = (20, 50, 90, 130, 170, 220, 270, 320, 370, 430, 500, 600,
                  750, 900, 1100, 1300, 1500, 1750, 2000, 2250, 2500, 3000, 3500, 4000)
FIXED_CONTRACTS = ("3NT", "4S", "4H", "5D")
BOOTSTRAP_RESAMPLES = 2000


def score_to_imps(score_delta):
    magnitude = bisect_right(IMP_THRESHOLDS, abs(score_delta))
    return magnitude if score_delta >= 0 else -magnitude


def percentile(values, fraction):
    """Nearest-rank percentile; no dependency on NumPy or a statistics service."""
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def uncertainty(imps, seed):
    """Resample paired boards, never individual dependent card decisions."""
    if len(imps) < 2:
        interval = None
    else:
        rng = random.Random(seed ^ 0x425249444745)
        means = [statistics.mean(rng.choices(imps, k=len(imps)))
                 for _ in range(BOOTSTRAP_RESAMPLES)]
        interval = [percentile(means, .025), percentile(means, .975)]
    return {
        "paired_boards": len(imps),
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES if interval is not None else 0,
        "bootstrap_95_percentile_mean_imp_interval": interval,
        "sample_stddev_imps": statistics.stdev(imps) if len(imps) > 1 else None,
        "caution": "Exploratory paired-board bootstrap; a tiny fixed-contract corpus is not strength proof.",
    }


def board_room(seed, index):
    deck = list(ai.DECK)
    random.Random(seed + index).shuffle(deck)
    declarer = ai.SEATS[index % 4]
    return {"gameData": {
        "currentPhase": "playing", "turn": ai.next_seat(declarer),
        "boardNumber": index + 1, "declarer": declarer, "dummy": ai.partner(declarer),
        "contract": FIXED_CONTRACTS[index % len(FIXED_CONTRACTS)],
        "contractMultiplier": 1, "vulnerability": rules.VULNERABILITIES[index % 16],
        "hands": {seat: deck[offset * 13:(offset + 1) * 13]
                  for offset, seat in enumerate(ai.SEATS)},
        "tricks": [], "currentTrick": [], "dummyRevealed": False,
    }}


def _new_metrics():
    return {"actions": 0, "legal_actions": 0, "latencies": [], "modes": Counter(),
            "complete_sample_batches": 0, "fallback_reasons": Counter()}


def _play_leg(template, sampled_side, config, metrics, solver_factory, clock):
    room = deepcopy(template)
    trace = []
    started = clock()
    while room["gameData"]["currentPhase"] == "playing":
        game = room["gameData"]
        actor = game["turn"]
        policy = "sampled_dds" if rules.side(actor) == sampled_side else "heuristic"
        began = clock()
        # Neither policy receives a room, full deal, opponent hand lengths,
        # unrevealed dummy, or a reference to the mutable hands mapping.
        observation = ai.observe(room, actor)
        if policy == "sampled_dds":
            decision = ai.choose_card(observation, config, solver_factory=solver_factory)
        else:
            decision = ai.Decision(ai.heuristic(observation), "heuristic", 0)
        elapsed = (clock() - began) * 1000
        record = metrics[policy]
        record["actions"] += 1
        record["latencies"].append(elapsed)
        record["modes"][decision.mode] += 1
        record["complete_sample_batches"] += decision.samples
        if decision.reason:
            record["fallback_reasons"][decision.reason] += 1
        if decision.card not in rules.legal_cards(game, actor):
            raise RuntimeError(f"{policy} proposed an illegal action; benchmark aborted")
        record["legal_actions"] += 1
        trace.append((actor, decision.card, policy))
        rules.apply_card(room, actor, decision.card)
    game = room["gameData"]
    if len(trace) != 52 or len(game["tricks"]) != 13 or any(game["hands"].values()):
        raise RuntimeError("Benchmark board did not conserve 52 cards / 13 tricks")
    return {
        "sampled_side": sampled_side,
        "score_ns": game["result"]["scoreNS"],
        "declarer_tricks": game["result"]["declarerTricks"],
        "actions": len(trace),
        "elapsed_ms": (clock() - started) * 1000,
        "action_digest": hashlib.sha256(json.dumps(trace, separators=(",", ":")).encode()).hexdigest(),
    }


def _summarize_metrics(record):
    actions = record["actions"]
    reasons = record["fallback_reasons"]
    degraded = sum(reasons.values())
    solver_errors = sum(count for reason, count in reasons.items() if reason != "budget_exhausted")
    return {
        "actions": actions, "legal_actions": record["legal_actions"],
        "illegal_actions": actions - record["legal_actions"],
        "legal_action_rate": record["legal_actions"] / actions if actions else None,
        "degraded_actions": degraded,
        "degraded_solver_rate": degraded / actions if actions else None,
        "solver_error_actions": solver_errors,
        "solver_error_rate": solver_errors / actions if actions else None,
        "fallback_reasons": dict(reasons), "modes": dict(record["modes"]),
        "complete_sample_batches": record["complete_sample_batches"],
        "latency_ms": {
            "p50": percentile(record["latencies"], .5),
            "p95": percentile(record["latencies"], .95),
            "max": max(record["latencies"]) if actions else None,
            "mean": statistics.mean(record["latencies"]) if actions else None,
        },
    }


def run_benchmark(boards=4, seed=2026, samples=4, budget_ms=0, allow_degraded=False,
                  solver_factory=ai.default_solver, clock=time.perf_counter):
    if not 1 <= boards <= 64:
        raise ValueError("boards must be 1..64")
    config = ai.PlayConfig(seed=seed, samples=samples, budget_ms=budget_ms)
    initialized = clock()
    solver_available = True
    solver_error = None
    try:
        solver = solver_factory()
    except Exception as exc:
        if not allow_degraded:
            raise RuntimeError(f"DDS preflight failed (use --allow-degraded only deliberately): {exc}") from exc
        solver_available, solver_error = False, str(exc)

        def get_solver():
            raise RuntimeError(solver_error)
    else:
        def get_solver():
            return solver
    initialization_ms = (clock() - initialized) * 1000
    metrics = {policy: _new_metrics() for policy in ("sampled_dds", "heuristic")}
    pairs = []
    started = clock()
    for index in range(boards):
        template = board_room(seed, index)
        board_config = ai.PlayConfig(seed=seed + index, samples=samples, budget_ms=budget_ms)
        ns = _play_leg(template, "NS", board_config, metrics, get_solver, clock)
        ew = _play_leg(template, "EW", board_config, metrics, get_solver, clock)
        delta = ns["score_ns"] - ew["score_ns"]
        pairs.append({
            "board": index + 1, "deal_seed": seed + index,
            "contract": template["gameData"]["contract"],
            "declarer": template["gameData"]["declarer"],
            "vulnerability": template["gameData"]["vulnerability"],
            "legs": [ns, ew], "sampled_score_delta": delta,
            "sampled_imp_delta": score_to_imps(delta),
        })
    imps = [pair["sampled_imp_delta"] for pair in pairs]
    summarized = {policy: _summarize_metrics(record) for policy, record in metrics.items()}
    return {
        "benchmark_version": 1, "python_version": platform.python_version(),
        "method": "Identical seeded deals, fixed contracts, sampled NS then sampled EW; no bidding or par.",
        "information": "Both policies receive only fair_play.Observation; dummy visible after the opening lead.",
        "config": {"boards": boards, "seed": seed, "samples": config.samples,
                   "budget_ms": config.budget_ms, "allow_degraded": allow_degraded},
        "reproducibility": "Scores/action digests reproducible with budget_ms=0; latencies are observational.",
        "solver_available": solver_available, "solver_preflight_error": solver_error,
        "solver_initialization_ms": initialization_ms,
        "elapsed_play_ms": (clock() - started) * 1000,
        "latency_scope": "Policy projection+decision, excludes initialization, persistence, AWS and broadcasting.",
        "policies": summarized, "pairs": pairs,
        "comparison": {
            "positive_favors": "sampled_dds",
            "total_score_delta": sum(pair["sampled_score_delta"] for pair in pairs),
            "mean_score_delta_per_board": statistics.mean(pair["sampled_score_delta"] for pair in pairs),
            "total_imps": sum(imps), "mean_imps_per_board": statistics.mean(imps),
            "wins": sum(value > 0 for value in imps), "ties": imps.count(0),
            "losses": sum(value < 0 for value in imps),
            **uncertainty(imps, seed),
        },
        "expert_strength_proven": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boards", type=int, default=4, help="Paired boards, 1..64 (two legs each)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--samples", type=int, default=4, help="Samples per decision, 1..32")
    parser.add_argument("--budget-ms", type=int, default=0, help="Soft move deadline; default 0 gives fixed-sample replay")
    parser.add_argument("--allow-degraded", action="store_true",
                        help="Explicitly permit unavailable/failed DDS, reported as degraded")
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(**vars(args))
    except (ValueError, RuntimeError) as exc:
        parser.exit(2, f"benchmark failed: {exc}\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["policies"]["sampled_dds"]["solver_error_actions"] and not args.allow_degraded else 0


if __name__ == "__main__":
    raise SystemExit(main())
