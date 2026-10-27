# Local board records, agreements and cumulative scores

These features run through the local development server. No AWS deployment or
cloud storage configuration is included. Archives are in a **separate
process-memory repository**, not an ever-growing list inside the room item.
They survive disconnect/reconnect, new boards and ownership/seat changes for the
server lifetime, but **not server restart**. The local server has its own
repository instance. Retention has no automatic expiry or board-count cap during
that lifetime; memory grows with completed boards. This is intentional local
retention, not a production durability guarantee.

## Authorization and state boundaries

All routes below are authenticated WebSocket actions. Use the same `bridge.v1`
and `bridge.auth.<access-or-guest-token>` subprotocols as game actions. The
connection's unexpired signed identity is authoritative; supplying a different
`userId` is forbidden. The identity must currently occupy a human seat in the
requested room. A guessed board ID never grants access to another room.
There is no unauthenticated archive HTTP endpoint.

Archives become available only after a successful conditional room write has
committed completion, scoring and final-trick clearance. During the final
visible trick, the board is still playing and archive access returns 409.
Passed-out boards complete after the fourth pass, without a trick delay.
Normal live snapshots still contain only the requester's remaining hand and
lawfully exposed dummy; neither original hands nor archive contents are added.
Agreement cards contain static system descriptions, never hand-derived advice.

`archives.embargo_allows(room, board, user_id)` checks the authoritative local
duplicate event: records stay embargoed until every assigned table completes
that same board, including after advancing. Missing events fail closed.
Release still requires original own-table membership; organizers cannot bypass
it. See [claims and duplicate events](claims-duplicate.md) for enrollment,
comparison scoring, release policy and claim-settled archive additions.

## Request and response contract

Send `{"action": "<action>", "data": {...}}`; flat data is also accepted by the
shared handler. Optional `userId` must match the authenticated connection.
All timestamps are integer Unix epoch **milliseconds**. Card strings use
rank-suit notation (`AS`, `TH`). Seat order is North, East, South, West.

| Action | Data | Response action and fields |
| --- | --- | --- |
| `getBoardArchive` | `roomId`, `boardId` | `boardArchive`, `roomId`, `board` |
| `listBoardArchives` | `roomId`, optional `limit` (1–100; default 50), optional positive integer `beforeBoardNumber` | `boardArchives`, `roomId`, `boards`, `nextBeforeBoardNumber` |
| `getAgreementCard` | `roomId`, optional `version` | `agreementCard`, `roomId`, `card`, `agreements` |
| `getMatchScoreboard` | `roomId` | `matchScoreboard`, `roomId`, `scoreboard` |
| `setPracticePace` | `roomId`, `practiceMode: true`, integer `robotCardDelayMs` (100–10000), integer `trickHoldMs` (1000–10000), optional `revision` | personalized snapshot with action `practicePaceChanged` |

An archive `board` has these stable fields:

```text
schemaVersion: 1
roomId, boardId, boardNumber, dealer, vulnerability
initialHands: {North: [card...], East: [...], South: [...], West: [...]}
auction: [{seat, bid, timestamp}...]
tricks: [{leader, plays: [{seat, card, timestamp}...], winner}...]
contract: string | null
contractMultiplier: 1 | 2 | 4
declarer: seat | null
openingLeader: seat | null
result: {passedOut, scoreNS, scoreEW, ...normal duplicate result fields}
agreements: {NS: {system, version}, EW: {system, version}}
completedAt
eventId: string | null
```

Auction order, trick order and play order are authoritative. Replaying starts
from `initialHands`, sets the recorded dealer/vulnerability, applies `auction`,
then applies all `tricks[].plays`. No robot or random deal is needed. A
passed-out archive has four passes, an empty trick list, null contract/declarer/
opening leader and zero scores. Completed contract boards have 13 tricks and
52 plays unless explicitly claim-settled. Claim archives contain only genuinely
played tricks plus `claimSettlement` (including any partial plays and remaining
allocation); they never invent 52 plays. Records are deep-copy isolated. Rewriting an identical record is a
no-op; a different record under the same `(roomId, boardId)` is rejected.
Failed room CAS writes never archive their uncommitted candidate.

List entries are summaries only: `boardId`, `boardNumber`, `dealer`,
`vulnerability`, `contract`, `result`, `completedAt`. Newest boards come first.
For the next page pass `nextBeforeBoardNumber` as `beforeBoardNumber`; null
means no next page. An exactly full last page may yield an empty final page.
No original hands are sent in summaries.

The scoreboard is
`{completedBoards, scoreNS, scoreEW, lastBoardId}`. These are signed cumulative
**duplicate points**, not IMPs, matchpoints or rubber scores; `scoreEW` is the
negative of `scoreNS`. Existing `publicState.scores.{NS,EW}` is preserved.
Score, completed-board count and last board ID commit in the same CAS as the
result, exactly once. Snapshots/reconnects do not add scores again.

## Board transitions and agreements

Snapshots expose `publicState.boardId`, `agreements`, `scoreboard` and
`practiceMode`. New board IDs are generated once at board creation and survive
reconnection. Board numbers increase by one; dealer rotates N/E/S/W and
vulnerability follows the normal 16-board duplicate cycle.

**`nextBoard` now requires `revision` or the completed `boardId`**, in addition
to `roomId`. Send both from the completed snapshot when possible. Missing both
is 400; stale revision/board ID is 409. The caller must be the owner and the
current board must be completed. This prevents a delayed duplicate next-board
request from skipping a quickly passed-out subsequent board. Conditional room
writes also resolve concurrent requests. No next-board request auto-completes
an auction, collects an unfinished trick or scores a board.

The immutable agreement catalog currently contains only
`sayc-supported-1`, system `SAYC`. It is deliberately a **supported SAYC-style
subset**, based on `docs/robot-engine-contract.md`, not an invented full
convention card. A card contains `system`, `version`, `title`, `source`,
`supported: [{topic, description}]`, `unsupported: [string]` and
`deviations: [string]`. It documents the implemented NT ranges and natural NT
response bands, house five-card-major deviations, and explicitly incomplete
conventions/later rounds. There is no agreement-edit route.

Each partnership's version reference is copied into the board at creation and
frozen through auction, play and archive. Later catalog additions apply only
to newly started boards; old versions must remain retrievable. With no version,
`getAgreementCard` returns the current catalog card; use the snapshot's explicit
version to inspect a historical board. It also returns the current board's
partnership references. Unknown versions are 400.

## Practice pace

Only the owner of an exactly-one-human, three-robot SOLO, non-event,
noncompetitive room may opt in with `setPracticePace`. Multiplayer rooms and
event/tournament/ranked/competitive flags reject the change with 403. There is
no automatic application of a browser's saved preference. Both bounded integer
values are required; booleans, fractions and numeric strings are invalid.
The settings persist on the room across boards and reconnects. Snapshots show
the effective `publicState.pacing` and `practiceMode`.

Changing pace never edits an already persisted `pendingAction.dueAt`. Future
robot-card and trick-collection deadlines use the new pace; robot auctions
remain immediate. If a room ceases to qualify as solo practice, environment
defaults apply to future scheduling and `practiceMode` is false. Browsers must
not run authoritative game timers. Hint and computer-level APIs are described
in their own practice documentation.

## Error contract

Errors return the normal handler status code and, over WebSocket, an
`{"action":"error","statusCode":N,"message":"...","error":"..."}` envelope.
Clients should use numeric status and refresh state after conflicts rather than
matching text.

* **400**: malformed request, missing fields, unsupported version/operation,
  invalid page/pace values, `nextBoard` without a concurrency selector,
  or action in the wrong game phase.
* **401**: missing/unknown/expired authenticated connection.
* **403**: identity mismatch, nonmember, owner-only action, forbidden practice,
  or embargoed archive.
* **404**: room or board archive not found, including cross-room board IDs.
* **409**: board not completed/cleared, stale board/revision, failed room CAS.
* **503**: invalid environment pacing configuration.

## Verification and follow-on work

Offline tests contain no game sleeps. Clocks advance directly to persisted
deadlines. The real-client test starts its own loopback-only local server on
ephemeral ports and does not touch a running 3001/3002 server.

```sh
PYTHONDONTWRITEBYTECODE=1 AWS_EC2_METADATA_DISABLED=true \
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
AWS_DEFAULT_REGION=us-east-1 venv/bin/python -m pytest -q \
tests/test_board_records.py tests/test_bridge_lifecycle.py \
tests/test_game_pacing.py tests/test_game_tick.py tests/test_local_server.py
```

Coverage includes passed-out and full replay, original deal, final-clearance
gating, membership/cross-room boundaries, embargo, immutable/idempotent writes,
failed CAS, pagination limits, catalog-version freezing, multi-board totals,
stale/repeated nextBoard commands, solo pace bounds and preservation of pending
deadlines. The real two-client full-board regression checks live privacy,
agreement responses, multiplayer pace rejection, 52-play archives visible
equally to both members, cumulative scores and replay retention after nextBoard.

Before production: implement a durable conditional archive repository and
transactional completion/outbox recovery, set explicit retention/capacity
policies, add deployment/IAM configuration, and define event-release/participant
policies. Current request-time archive recovery is sufficient for the local
server lifetime, not a cross-process crash guarantee. Local IMP/matchpoint
comparisons use actual fixed multi-table event semantics. Claims/concessions use explicit settlement metadata and deliberate completion
eligibility; see [claims and duplicate events](claims-duplicate.md).
