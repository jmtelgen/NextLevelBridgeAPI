# SOLO practice and computer play budgets

These are **card-play policy/budget tiers**, not calibrated skill ratings or
claims of expert strength. Bidding remains the same legal, rule-based SAYC
implementation for all three tiers.

| `computerLevel` | Policy | Samples | Soft move budget |
| --- | --- | ---: | ---: |
| `heuristic` | Deterministic legal sequence/low lead, cheap winner, low discard | 0 | No DDS |
| `standard` (default) | Public-information sampled DDS | 4 | 50 ms |
| `thoughtful` | Public-information sampled DDS | 8 | 100 ms |

The persisted room-level `computerLevel` is authoritative; clients cannot send
arbitrary samples, seeds, solver options, or budgets. Unknown names, nulls,
booleans, misspellings and extra policy parameters are rejected, never treated as
another level. Named tiers intentionally do not use `ROBOT_PLAY_*` environment
overrides. Those overrides still apply to direct legacy `fair_play` callers.
Each policy uses the same legality and observation boundary.

Budgets are soft: an in-progress native DDS solve cannot be interrupted. Only
complete candidate-comparison sample batches count as evidence. A timeout before
one complete batch or a solver failure produces a legal heuristic decision,
explicitly marked degraded in a hint. Increasing the budget is not guaranteed to
improve any individual decision. Samples respect public voids and remaining card
counts; they do not assume the actual hidden allocation or an optimal par score.

## WebSocket API

Routes use the same signed, unexpired, connection-bound identity as game actions.
`userId` is optional and, when provided, must match that identity. Payloads may
use the existing top-level or nested `data` convention.

### Read-only hint

```json
{"action":"getPracticeHint","roomId":"room-123","revision":7,"suggest":true}
```

Returns privately to the requesting connection, never a room-wide hint:

```json
{
  "action": "practiceHint",
  "roomId": "room-123",
  "revision": 7,
  "hint": {
    "phase": "playing",
    "actor": "South",
    "controller": "North",
    "legalActions": ["2H", "AH"],
    "explanation": "You must follow H because this hand contains that suit.",
    "suggestion": {
      "card": "2H",
      "mode": "heuristic",
      "completedSamples": 0,
      "degraded": false,
      "caution": "Legal heuristic, not an optimal-play guarantee."
    }
  }
}
```

The full hint also includes named tier parameters and an information-boundary
notice. `suggest:false` skips policy work and returns only the legal-action
explanation. In bidding, hints show legal calls, visible-hand HCP and S/H/D/C suit
lengths; they explain contract ordering and double/redouble legality, **not**
invented conventions or a fabricated recommendation. `suggestion` is null during
bidding. No opponent hand, actual allocation, par result, or internal solver
exception is returned.

Authorization is checked on every request:

* exactly one seated human (the authenticated requester) and three robot seats;
* no event/tournament/match/competitive/ranked indicators, and no non-SOLO mode;
* only the current acting human, or declarer when controlling exposed dummy;
* no hint during the completed-trick hold or outside active bidding/play.

Multihuman rooms, spectators, outsiders and human dummy when a robot declarer
controls it are denied. Archive analysis is separate; this is not an archive or
competitive-analysis endpoint. Hints neither mutate rooms nor advance clocks.
Responses include the evaluated revision so clients can discard a response after
the board changes. A supplied stale revision returns 409.

An in-process, serialized, 128-entry LRU caches decisions keyed only by lawful
`Observation` and tier, bounding repeat work without caching full hidden deals.
It is a warm-process optimization, not a cross-instance quota or persisted hint
history. All membership/actor checks precede lookup. Cached degraded results
retain their explicit warning.

### Change computer tier

```json
{"action":"setComputerLevel","roomId":"room-123","revision":7,"computerLevel":"thoughtful"}
```

Only the owner of a qualifying SOLO room may change this setting. It is saved
using the same optimistic revision CAS as game actions. The response action is
`computerLevelChanged`, with the new revision, tier parameters and available
tiers. Other game snapshots expose the persisted room `computerLevel`.
Existing pending-action deadlines are not shortened or recomputed; the next
robot selection uses the new tier. Play speed is a separate SOLO pacing setting,
not a substitute for a computer policy tier.

## Benchmark and validation

```sh
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B -m pytest -q \
  tests/test_practice_computer_levels.py tests/test_websocket_practice.py \
  tests/test_practice_local.py tests/test_robot_fair_play.py tests/test_robot_benchmark.py
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B scripts/benchmark_computer_levels.py \
  --pairs 32 --seed 20261026
```

The tier runner reuses the existing seeded benchmark's fixed contract corpus,
metrics, IMP conversion and paired-board bootstrap. It rotates all declarers
across 3NT/4S/4H/5D and swaps the two policies NS/EW on the identical deal and
contract. Matchups cycle standard–heuristic, thoughtful–heuristic and
thoughtful–standard. Every policy receives only `fair_play.Observation`.
The report includes legal-action rate, completed batches, fallback/solver-error
rates, p50/p95/maximum latency, paired scores, IMP differences and exploratory
95% bootstrap intervals. DDS preflight fails explicitly if unavailable.

Deal seeds and contracts are reproducible; action traces are load-dependent
because these are the real wall-clock-budget tiers, not an unbounded fixed-sample
substitute. Native initialization is excluded from decision latency. These are
small, arbitrary fixed-contract comparisons with no auction. They do not establish
a strength ranking, bidding strength or competitive match performance.

The bounded native 32-pair report is stored at
[`benchmarks/computer-levels-20261026.json`](benchmarks/computer-levels-20261026.json).

### Recorded exploratory result

Local native DDS run, seed `20261026`, 32 pairs / 64 complete boards:

| Comparison (positive favors first) | Pairs | Mean IMP/pair | Exploratory 95% paired bootstrap interval |
| --- | ---: | ---: | --- |
| standard − heuristic | 11 | +3.55 | [+1.18, +5.91] |
| thoughtful − heuristic | 11 | +7.36 | [+4.73, +10.09] |
| thoughtful − standard | 10 | +0.70 | [−0.40, +1.90] |

These matchups use different small subsets, so the two heuristic comparisons
cannot be subtracted to estimate thoughtful versus standard. The direct interval
includes zero; this run does **not** establish that thoughtful is stronger.

| Tier | Decisions | Legal | p50 / p95 / max policy latency (ms) | Zero-batch budget fallbacks |
| --- | ---: | ---: | --- | ---: |
| heuristic | 1,144 | 100% | 0.06 / 0.09 / 0.40 | 0 |
| standard | 1,092 | 100% | 3.32 / 51.21 / 200.05 | 13 |
| thoughtful | 1,092 | 100% | 7.12 / 100.11 / 134.72 | 3 |

There were no solver errors or illegal actions. All sixteen combinations of
the four fixed strains/contracts and four declarers appeared. The maximum
standard latency exceeding 50 ms demonstrates the soft-budget caveat rather
than a hard latency guarantee. These numbers describe this machine/run only.
