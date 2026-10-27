# Fair robot engine contract

## Runtime integration

The authoritative game runtime owns turns, legality, hand mutation, completed
tricks and scoring. The synchronous selectors do not mutate a room:

* `core.robot.robot_utils.execute_robot_bid(room, physical_seat) -> str`
* `core.robot.robot_utils.execute_robot_card_play(room, physical_seat) -> str | None`

Imports use the `lambdas.` prefix in the source checkout. The returned card uses
the same spelling as the stored hand. Canonical engine cards are rank-suit
(`AS`, `TH`); legacy `SA`, `H10` are accepted. An empty hand returns `None`;
malformed public histories raise `ValueError` to the runtime rather than inventing
a state. The runtime must validate a selection before applying it.

The game schema is `gameData.hands`, `declarer`, `contract` (e.g. `3NT`),
`currentTrick: [{seat, card}]`, and
`tricks: [{leader, plays: [{seat, card}], winner}]`. Legacy completed-trick `cards`
is accepted as an alias for `plays`. Full seat names are required.

Pass the **dummy's physical seat**, not declarer's seat, when playing dummy.
The selector derives declarer as its controller and knows declarer's remaining
hand plus dummy's exposed hand. The runtime determines whether that controller is
a robot. `get_robot_turns_sequence` is a compatibility shim returning at most the
current actionable robot; never precompute subsequent actions. Recompute the
actual turn after every bid/card, trick completion and phase transition.

Live bidding is rule-based SAYC with a basic rule fallback. Every final proposal
is normalized and checked against `core.game.rules.legal_calls(gameData, seat)`.
An illegal proposal becomes pass and emits `robot_bid_degraded`. No live auction
uses DDS par or accesses another player's hand. SAYC conventions are incomplete;
legality is not a promise of bidding quality.

### Supported opening and natural notrump response agreements

The opening HCP ranges agree with the [ACBL Standard Yellow Card booklet
(September 1988 text mirror)](https://www.andrew.cmu.edu/user/gc00/bidding/yellow.html):
**1NT 15–17, 2NT 20–21, 3NT 25–27**, all balanced. Balanced shapes are 4333,
4432 and 5332. Selection considers these NT ranges before the strong 2C
fallback, so balanced 25–27 opens 3NT rather than being captured by 22+ HCP.
Balanced 18–19 still opens a suit; balanced 22–24 and 28+ opens 2C.
HCP, not distribution-adjusted total points, determines these ranges.

Existing house agreements are preserved, **not silently replaced by full SAYC**:
the 1NT and 2NT openings deny a five-card major, although the booklet permits
one; 3NT currently permits a balanced five-card major. Five-card minors are
permitted in all three NT ranges. The simplified 2C fallback also treats
unbalanced 20–21 HCP as strong without estimating playing tricks. These are
explicit limitations/deviations, not claims of strict complete SAYC compliance.

For balanced responders with **no four-card major and no five-card minor**,
the supported natural decisions are:

| Partner opened | Responder HCP | Natural response |
| --- | --- | --- |
| 1NT | 0–7 | pass |
| 1NT | 8–9 | 2NT, invitation to game |
| 1NT | 10–15 | 3NT, to play |
| 1NT | 16–17 | 4NT, quantitative invitation |
| 2NT | 0–3 | pass |
| 2NT | 4–10 | 3NT, to play |
| 2NT | 11–12 | 4NT, quantitative invitation |

These natural game/invitation cases are checked before generic shortness-based
Stayman or automatic Gerber. Previously a balanced 10–14 HCP responder could pass
1NT, while a balanced 15 HCP responder could be sent to ace asking instead of
placing 3NT. The 2NT responder likewise lacked natural game placement.
Existing routing for major-suit Stayman/transfers and long-minor conventions is
unchanged. Their strength requirements, later rounds and higher-strength slam
decisions remain incomplete: in particular, natural responses beyond these
documented bands are not newly implemented or certified by this change.
Quantitative invitation continuations by opener also remain incomplete.

The three historical 20/21/25-HCP opening failures were **fixture errors**, not
wrong NT thresholds or priority: their 14 malformed entries (e.g. `KQ`, `J9`,
single ranks) produced an unbalanced analysis, then only `hcp` was overwritten.
Those three tests now use 13 distinct valid cards with independently verified
HCP and balance. Production opening thresholds/order were not loosened to make
invalid fixtures pass.

`tests/test_robot_sayc_boundaries.py` adds table-driven shape/HCP opening edges,
HCP-versus-total-point boundaries, natural response edges, convention-priority
preservation, real 13-card hand evaluation and legal live response tests with
protected concealed hands and a forbidden advanced/DDS bidding oracle.
Run the directly related suites:

```sh
PYTHONDONTWRITEBYTECODE=1 AWS_EC2_METADATA_DISABLED=true \
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
AWS_DEFAULT_REGION=us-east-1 venv/bin/python -m pytest -q \
lambdas/tests/unit/test_sayc_opening_bids.py \
lambdas/tests/unit/test_sayc_simple.py \
lambdas/tests/unit/test_sayc_1nt_responses.py \
tests/test_robot_sayc_boundaries.py
```

## Information boundary and sampling

`core.robot.fair_play.observe` is the sole room-to-engine projection. It reads:

* The acting controller's hand.
* Dummy's hand only **after at least one actual public card**, regardless of a
  prematurely set `dummyRevealed` flag.
* Public completed/current plays, contract and declarer.

It does not read concealed hand contents **or their lengths**. Remaining counts
are `13 - public plays by seat`. Off-suit public plays establish void suits.
Public history must be complete; do not supply a truncated history with a
mid-board position. Counts, uniqueness and known-hand/void contradictions are
validated before sampling. A projection is immutable and is independent of
concealed allocation.

A local seeded PRNG randomizes a bounded bipartite matching of unseen cards to
remaining seat slots. An augmenting-path matcher either fills all slots or
reports infeasibility, without an unbounded rejection loop. Every resulting deal
has all 52 distinct cards across public plays and remaining hands, exact seat
capacities, preserved known cards and no cards in observed void suits.
The distribution is **not uniform** over feasible deals and has no auction,
signal, lead-style, HCP or shape likelihood model.

## Sampled double-dummy evaluation

Every legal candidate is evaluated on the **same sampled deals**. For each
candidate, remove its card, add it to the current trick, and ask the existing
`dds.working_dds_wrapper.DDS` adapter for the optimal continuation
(`target=-1`, `solutions=1`, `mode=1`):

* A partial trick keeps its real leader, not the acting player.
* A completed trick is resolved using led suit/trump, contributes its immediate
  partnership trick, and its winner leads the next trick.
* Native DDS scores refer to the next player's partnership; scores are
  complemented when that is the acting side's opponents.
* The final completed trick is scored without a zero-card DDS call.

The one-solution continuation approach does not depend on the wrapper expanding
DDS equivalent-card masks. Native calls use one configured thread, 32 MB requested
DDS memory and a process-local lock around native access. This is a resource
request, not a measured memory ceiling. Production must package the existing
native library in a location the adapter searches (for example `./libdds.so.2` or
`/usr/local/lib/libdds.so.2`). No model downloads, network or AWS calls are used.

The selected card maximizes mean future **partnership tricks**, not duplicate
score, contract success probability or matchpoints. Ties prefer the deterministic
heuristic and then stable rank/suit ordering.

## Configuration, budgets and reproducibility

Environment defaults (or explicit `PlayConfig` for internal calls/tests):

| Variable | Default | Limits |
| --- | --- | --- |
| `ROBOT_PLAY_SEED` | `0` | Integer |
| `ROBOT_PLAY_SAMPLES` | `4` | 1–32 complete candidate batches |
| `ROBOT_PLAY_BUDGET_MS` | `50` | 0–5000; zero disables the deadline |

Sampling and tie-breaking do not use global randomness, timestamps, room IDs or
concealed information. With identical public observation, seed and completed
sample count, actions are identical. Use budget zero and a fixed sample count
for strictly reproducible experiments. A wall-clock deadline can produce a
different number of completed batches across machines/runs; do not claim strict
wall-clock-mode replay determinism.

The deadline is **soft**: checked before sampling and before each native call.
A single in-process DDS call cannot be interrupted and may exceed the entire
budget. Partial candidate batches are discarded, never averaged against more
complete candidates. Completed batches may still be used after time expires.
Four samples/50 ms keeps ordinary full robot chains practical without letting
each move consume 250 ms by default. It is not a calibrated strength or latency
guarantee; native overruns and persistence/broadcast time remain outside this
bound. The runtime also checks its remaining invocation time between actions.
No claim of expert strength is made.

## Explicit degraded behavior

Unavailable DDS, invalid continuation results or infeasible samples emit a
warning `robot_play_degraded` with the reason and completed sample count, then
use a deterministic legal heuristic. Deadline exhaustion before one complete
batch also warns and uses that fallback. Unexpected solver exceptions are logged,
not silently swallowed. `Decision` exposes card, mode, sample count and reason;
the public selector logs mode/sample count without logging private cards.

The fallback follows suit whenever possible, leads the top of an honor sequence
or low from the longest suit, avoids overtaking a currently winning partner,
otherwise uses its cheapest currently winning card, then its lowest legal
discard. These are transparent heuristics, not a complete bridge carding system.
A forced legal card skips DDS entirely.

## Validation and follow-on acceptance criteria

`tests/test_robot_fair_play.py` and `tests/test_robot_bidder_fair.py` cover canonical
parsing, legal follow suit/opening leads, protected concealed-hand reads,
allocation-invariant actions, dummy controller knowledge, seeded feasible
sampling, all-card conservation/voids, impossible constraints, equal-world
candidate comparisons, partial-trick leaders/side conversion, native DDS
known-answer endgames, bounded-batch fallback, auction legality and complete
52-card legal fallback play. Native checks skip explicitly when the native
library is absent; they must run in a deployment-qualified environment.

An illustrative local native run completed three seeded shuffled deals (156 legal
actions, 39 tricks, all hands empty) with two samples and a 50 ms soft budget:

| Deal seed / contract | Sampled / forced / fallback actions | Mean / p95 / max move ms |
| --- | --- | --- |
| 0 / 3NT | 40 / 10 / 2 | 7.57 / 61.31 / 95.46 |
| 1 / 4S | 41 / 11 / 0 | 3.73 / 13.63 / 53.05 |
| 2 / 5D | 40 / 12 / 0 | 3.91 / 17.90 / 55.41 |

These are single-machine smoke measurements, not a strength benchmark or service
SLA. In particular, measured deadline overruns demonstrate the native-call soft
budget limitation. The persisted native full-deal test uses fixed samples with
the time budget disabled rather than asserting machine-dependent timing.

Run from the project root with the existing venv and no external AWS:

```sh
PYTHONDONTWRITEBYTECODE=1 AWS_EC2_METADATA_DISABLED=true \
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
AWS_DEFAULT_REGION=us-east-1 venv/bin/python -m pytest -q \
tests/test_robot_fair_play.py tests/test_robot_bidder_fair.py
```

## Reproducible paired strength/latency pilot

`scripts/benchmark_robots.py` compares the sampled player against the exact
documented legal heuristic. For every seeded deal it plays two duplicate legs:
sampled NS versus heuristic EW, then heuristic NS versus sampled EW. Both legs
use identical hands, declarer, vulnerability and contract; neither policy receives
the full deal. Both are called with only an immutable lawful observation, and
dummy is exposed only after the lead. No par bidding or unequal auction agreements
are involved: **there is no bidding**, and the explicitly fixed contracts cycle
`3NT`, `4S`, `4H`, `5D`, with declarer cycling North/East/South/West. These contracts
are not selected for fit or game quality.

The pair's sampled-team score delta is `NS(first leg) - NS(second leg)`, converted
to standard duplicate IMPs. Positive favors sampled DDS. Bootstrap uncertainty
resamples whole paired boards, not the dependent card decisions. The JSON output
includes per-leg results/action digests, paired score/IMP deltas, 2,000-resample
percentile intervals, legal/degraded/solver-error rates, completed sample batches,
and nearest-rank p50/p95 move latency. Intentional heuristic use is not classified
as degraded DDS. Budget fallback is distinguished from actual solver errors.

Run the bounded four-pair native pilot (fixed sample count for replay):

```sh
PYTHONDONTWRITEBYTECODE=1 AWS_EC2_METADATA_DISABLED=true \
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
AWS_DEFAULT_REGION=us-east-1 venv/bin/python scripts/benchmark_robots.py \
  --boards 4 --seed 2026 --samples 4 --budget-ms 0
```

CLI defaults are four paired boards, seed 2026, four samples and no time deadline;
the production selector defaults to the 50 ms soft deadline instead. Board count
is limited to 1–64, samples to 1–32. A native call is still not interruptible.
Native DDS preflight failure exits nonzero unless `--allow-degraded` is explicitly
given; later solver errors are logged, counted and cause a nonzero CLI status
unless that flag was supplied. This prevents an accidental heuristic-only run
from masquerading as a successful DDS comparison.

### Recorded local pilot, 2026-10-25

Native DDS was active; four pairs produced eight complete games, **416/416 legal
actions**, and **zero solver errors or degraded moves**. Sampled DDS used 664
complete sample batches over 166 sampled decisions plus 42 forced decisions.

| Board | Fixed contract / declarer / vulnerability | Sampled score delta | IMP delta |
| --- | --- | --- | --- |
| 1 | 3NT / North / None | +100 | +3 |
| 2 | 4S / East / NS | +500 | +11 |
| 3 | 4H / South / EW | +150 | +4 |
| 4 | 5D / West / Both | 0 | 0 |

Total: **+750 points / +18 IMPs**, mean +4.5 IMPs per paired board; three wins,
one tie. The exploratory 95% paired-board bootstrap interval for the mean was
**[+1, +9] IMPs** (only four paired observations; sample SD 4.65 IMPs).

| Policy | Actions | Legal rate | Degraded rate | p50 / p95 / max move ms |
| --- | --- | --- | --- | --- |
| Sampled DDS | 208 | 100% | 0% | 3.05 / 55.43 / 299.41 |
| Legal heuristic | 208 | 100% | 0% | 0.057 / 0.084 / 0.164 |

Native initialization took 83.99 ms; eight-game play took 2,582.34 ms. Move timing
includes observation construction and decision, including forced moves, but
excludes native preflight, persistence, AWS and broadcasting. These are
single-machine measurements, not Lambda service-level latency claims.

A separate practical-default run of the same four pairs with `--budget-ms 50`
took 1,819.79 ms for eight games: sampled p50/p95/max 3.07/50.08/62.10 ms, zero
illegal actions or solver errors, two logged budget fallbacks out of 208 sampled
policy moves (0.96%). This supports lowering runtime defaults to four samples and
50 ms, but not a hard deadline guarantee. Time-limited sample counts and results
vary with execution timing; the fixed-sample pilot above is the replay target.

**This is initial sanity evidence, not expert-strength proof.** Four random deals,
fixed potentially unsuitable contracts, a weak local comparator, no auction and
no independent held-out corpus cannot establish tournament strength. The small
bootstrap interval is exploratory, not a claim of general statistical superiority.
Do not tune on these four deals and then reuse them as independent validation.

Benchmark tests (`tests/test_robot_benchmark.py`) cover standard IMP boundaries,
duplicate score arithmetic, paired replay/action digests, seeded uncertainty,
protected concealed-hand reads for **both policies on all 104 moves of a pair**,
explicit degraded-mode opt-in, CLI bounds, native CLI smoke/replay and production
defaults. The original no-peeking tests additionally replace concealed actual
allocations/lengths while asserting identical observations, samples and actions.

```sh
PYTHONDONTWRITEBYTECODE=1 AWS_EC2_METADATA_DISABLED=true \
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
AWS_DEFAULT_REGION=us-east-1 venv/bin/python -m pytest -q \
tests/test_robot_fair_play.py tests/test_robot_bidder_fair.py \
tests/test_robot_benchmark.py
```

Remaining work, with explicit acceptance gates:

1. **Held-out strength benchmark:** extend the pilot to a versioned held-out
   duplicate-board corpus, seeds,
   comparator engines and scoring method; report confidence intervals for
   duplicate IMPs, contract success and per-move latency before strength claims.
2. **Better inference:** model auction/lead/shape likelihoods without reading
   concealed data; retain protected-hand/no-peeking tests and measure calibrated
   inference and held-out playing strength against this baseline.
3. **Hard deadlines:** isolate native evaluation in a killable worker, preserving
   complete candidate batches; demonstrate a measured p99 deadline/memory ceiling
   and deterministic legal timeout fallback under stalled-native tests.
4. **Imperfect-information search:** quantify and reduce determinization's
   strategy fusion and nonlocality; compare against this equal-world baseline
   under identical resource limits. More samples alone do not remove those flaws.
5. **SAYC completion:** add convention/rebid/competitive auction fixtures with
   reference agreements and legality checks; do not substitute perfect-information
   par bids or label the current bidder tournament-strength.
