# Local claims, concessions and small duplicate-club events

Implemented in the **local server only**; no AWS provisioning, deployment,
cloud table configuration or migration is included. The adapter creates
`local-duplicate-events` inside its isolated Moto context alongside its local
rooms/connections. Event documents use revision-conditional writes and atomic
event/room enrollment and start transactions. The separate archive repository
remains process memory. All local data is lost on server restart.

## Shared transport and identity

Use authenticated WebSocket actions with `bridge.v1` and the signed
`bridge.auth.<token>` protocol. Requests are
`{"action":"...", "data":{...}}` (existing flat requests also work).
An optional `userId` must match the unexpired connection identity. No action
accepts a client-supplied seat, actor, deal, score, seed, vote map or allocation
as authority. Card strings and full seat names follow the existing contract.
Times below are integer epoch **milliseconds**.

## Claims and full concessions

| Action | Required data | Reply |
| --- | --- | --- |
| `proposeClaim` | `roomId`, current `boardId`, `proposalId`, integer `tricks`, `revision` | personalized snapshot, `action: claimUpdated` |
| `respondClaim` | same selectors, boolean `accept`, `revision` | same |
| `cancelClaim` | same selectors, `revision` | same |

The current human **controller** may propose only during active play, never
auction, completion, or four-card trick collection. Declarer controls dummy;
human dummy cannot independently propose on declarer's turn. A partially played
trick is a stable position: it counts among the remaining tricks.

`tricks` allocates remaining tricks to the **proposer's partnership**, not
necessarily declarer, and must be from zero through `remainingTricks`.
Zero is a full concession of all remaining tricks. It works against robots.
Positive claims require **both opponents human**. Computer opponents reject
unproven positive claims, even if the actual hidden deal would make the claim
true. This feature never calls DDS or uses hidden-hand evaluation.

Every **other seated human**, including the proposer's partner and human dummy,
must explicitly accept. Robot participants automatically permit a full
concession; there are no implicit human accepts or partner overrides.
A single rejection resumes play. An unrelated authenticated room member cannot
vote as a different seat by sending `userId`, `seat` or a fabricated vote map.

`publicState.claim` is null/absent before the first proposal, otherwise:

```text
proposalId, boardId
proposer: full seat name
side: NS | EW
tricks, remainingTricks: integer
requiredSeats: [human seat...]
votes: {seat: boolean}
status: pending | accepted | rejected | cancelled | expired | disconnected
createdAt, expiresAt
resolvedAt: present after resolution
```

While pending, ordinary game mutations return 409, legal cards are empty,
`isMyTurn` is false and robots do not act. `pendingAction` becomes
`{kind:"claimExpiry",dueAt:expiresAt}`. The previous pending deadline, if any,
is saved privately and shifted by the actual pause duration on resumption,
never shortened or replaced with an already-expired robot deadline.
The ordinary 700 ms card delay, 1200 ms collection, and explicit trick-clear
transition remain unchanged outside the pause.

The proposer may cancel. A proposal expires **60 seconds** after creation.
Any participating human's final valid connection disconnect/token expiration
closes it as `disconnected`; a still-valid second tab preserves presence.
Presence synchronization and snapshots reconcile disconnects; persisted expiry
ticks provide the bounded fallback. No Lambda sleeps or client-authoritative
timers are involved. Rejection/cancellation/expiration/disconnection leaves
hands, current trick, completed tricks, auction and actor unchanged, without
revealing any new hand.

`proposalId` must match `[A-Za-z0-9_-]{1,80}`; UUIDs are suitable. There are at
most **16 proposals per board**. IDs cannot be reused for another proposal.
Identical retries of the current proposal or an already-recorded same vote are
idempotent even with an old revision; changed payloads/votes are rejected.
Other claim changes require the latest integer revision and current board ID.
After another proposal has replaced the visible claim, old IDs cannot mutate
the new proposal.

### Accepted settlement and replay

Final unanimous acceptance atomically closes the room board using normal
duplicate scoring and cumulative-score machinery, exactly once.
`result.settledByClaim` is true. Public snapshots and the archive contain:

```text
claimSettlement: {
  proposalId, proposer,
  allocation: {NS: remainingTricksForNS, EW: remainingTricksForEW},
  acceptedAt,
  unplayedTrick: [{seat,card,timestamp}...]
}
```

`tricks` includes only **fully played** tricks. Any partial trick's actual
played cards are moved to `claimSettlement.unplayedTrick`; it is not assigned a
fake winner. The remaining allocation includes that unfinished trick.
`result.declarerTricks` adds genuinely won completed tricks to declarer's
settled remaining allocation. Remaining hands are not fabricated as empty and
there are **no invented 52 plays**. Replay should apply original hands/auction,
recorded full tricks, then the partial plays, and explicitly display the claim
settlement rather than continuing fake card play.

The existing schema-version-1 archive adds optional `claimSettlement` (null for
ordinary boards). Accepted completion is cleared immediately because there is
no new completed four-card trick to hold. Normal live privacy remains in place;
full original deals require an authorized archive request, additionally subject
to the event embargo below. Rejected/pending claims never grant archive access.

## Duplicate event enrollment and start

| Action | Required data | Reply action |
| --- | --- | --- |
| `createDuplicateEvent` | `roomId`, integer `tableCount` 2–4, integer `boardCount` 1–8 | `duplicateEventCreated` |
| `joinDuplicateEvent` | `eventId`, own `roomId`, `invitationToken` | `duplicateEventJoined` |
| `startDuplicateEvent` | `eventId` | `duplicateEventStarted` |
| `getDuplicateEvent` | `eventId` | `duplicateEvent` |

All replies contain `{action,eventId,event}`. Only create additionally returns
`invitationToken`, a random event-enrollment capability. Store/share it
separately from signed login credentials. Only its SHA-256 hash is persisted;
neither token nor hash is broadcast. Lost capabilities cannot currently be
retrieved or rotated.

Create/join enroll a **fresh waiting room**, never a room with prior boards.
The authenticated caller must already be its seated owner. Participants first
join their ordinary room, respecting its private invitation and lock policy,
then the owner enrolls that room. Tables are numbered in enrollment order;
joining does not let an organizer choose a different room's seat.
Overlapping human identities across an event's tables are forbidden, including
non-owner partners and the organizer. An invitation enrolls an already-owned
room; it does not authorize entering any other event room.

For safety, membership/ownership freeze **immediately on enrollment**, not just
start. New joins, seat moves, leaves, replacement and ownership transfers are
blocked, even for organizers/room owners/invitees. Original occupants may
reconnect with their same signed identity at any phase. Existing 120-second
reservations and duplicate-tab semantics remain; no automatic event takeover.
This local version has no event unenroll, cancellation, movement or replacement
API. Assemble the desired tables first.

Only the organizer may start, after exactly the requested tables enroll.
One transaction freezes the complete assignments and starts board one at all
tables. Vacant seats are filled with robots. Deals use cryptographic
`SystemRandom`, with the **same authoritative deal, board ID, dealer and
vulnerability** at every table. Raw event documents/deals/random state are
never returned. Start retries after start/completion return current status and
do not redeal.

`room.eventId` and `publicState.eventId` identify the event.
`publicState.computerLevel` and `room.computerLevel` retain the named robot tier.
Hints, computer-level settings and SOLO pace APIs are backend-denied for event
rooms, **even with only one human**; hiding a UI button is not authorization.

Use normal bidding/play/claims. Use owner-only `nextBoard` with the just-finished
`boardId` and/or revision, as before. Tables advance independently by exactly
one predealt event board. No action skips or exceeds `boardCount`. A stale
selector cannot skip a quickly completed board. `startRoom` cannot bypass the
event organizer/start transaction.

## Public event status and scoring

Enrolled participants can call `getDuplicateEvent` while waiting, playing or
completed. Outsiders cannot, even with a guessed event ID. Its `event` is:

```text
eventId, organizerId
status: waiting | started | completed
tableCount, boardCount
scoring: IMPs | matchpoints
tables: [{tableNumber,roomId}]
boards: [{
  boardNumber,boardId,completedTables,released,
  results: [{tableNumber,scoreNS,scoreEW,pointsNS,pointsEW}]
}]
totals: [{tableNumber,pointsNS,pointsEW}]
```

Before start, `boards` is empty. **Until every table finishes that board**,
`released` is false and `results` is empty. Totals include only released boards.
Completed-table counts reveal progress, not results/deals from unfinished
comparisons. Event status becomes completed only when every board has results
from every table. Results are immutable and completion/recovery is idempotent.

Two tables compare signed **NS duplicate scores** with the standard 0–24 IMP
thresholds:
`20,50,90,130,170,220,270,320,370,430,500,600,750,900,1100,1300,1500,1750,2000,2250,2500,3000,3500,4000`.
For difference `scoreNS(table1)-scoreNS(table2)`, table one's NS gets those
signed IMPs; its EW gets the negative. Table two's NS gets the opposite and EW
the complement. This is a fixed-table comparison, not an invented team movement
or an average against robots.

Three/four tables use matchpoints: each NS score earns **2** for each lower
other NS score, **1** per tie, **0** per higher score. EW receives
`2*(tableCount-1)-pointsNS`. Thus three tied tables each receive 2/2, four tied
tables 3/3. Totals are sums of released board points; no unimplemented ranking,
percentage, adjustment, missing-board estimate or tie-break is implied.

Create/join/start broadcast normal seat-filtered `gameState` snapshots to the
affected room(s), not raw event documents. `claimUpdated` broadcasts claim
transitions; disconnect updates also carry resolved claim state in their
normal room/presence snapshots. **Other-table completion does not push an
event broadcast**. Clients should refresh/poll `getDuplicateEvent` and retry
their own archive list once the board is released.

### Replay embargo across every route

`getBoardArchive` returns 403 and `listBoardArchives` omits a completed event
board until **all tables finish that same board**. This applies after advancing
to later boards as well as on the current board, including passed-out and
claim-settled boards. An organizer has no exception. Release does not grant
cross-table archive membership: only the requesting player's original event
table is accessible through existing room-authenticated archive APIs.

The centralized `archives.embargo_allows` hook checks authoritative event
results and frozen table membership. Unknown/missing event repositories or
records fail closed. Normal snapshots never add original hands. Agreement and
cumulative table-score routes do not include other tables' hidden deals.

## Errors, persistence limits and handoff

Errors use the standard numeric status and socket `action:error` envelope:

* **400**: malformed data/limits, wrong claim actor/phase, unsupported positive
  robot claim, invalid selectors/proposal IDs, unauthorized vote shape or
  cancellation, reused/changed proposal/vote, missing claim revision.
* **401**: missing, expired or unknown connection identity.
* **403**: identity mismatch, nonmember/outsider, wrong room owner/organizer,
  overlapping table membership, invalid event capability, SOLO policy violation,
  embargoed or cross-table archive access.
* **404**: missing room/event/archive.
* **409**: stale revision/board or failed transaction/CAS, frozen membership,
  pending-claim ordinary mutation, premature event start, enrollment closed,
  event direct start or board limit exceeded.
* **503**: events outside the explicitly configured local adapter, or invalid
  pacing configuration.

Room scoring commits before separate archive/event-result publication; snapshot,
archive and event reads recover committed completion idempotently. Local
single-process serialization plus transaction/CAS protects concurrent requests.
An interrupted cross-process publication is not a production outbox guarantee.
Before any AWS use, design durable archives, transactional completion/outbox
recovery, explicit retention/capacity policies, indexed membership, deployment/
IAM and multi-instance event-result retry semantics. This change does not
silently enable an AWS event table by environment variable.

Implementation: `core/game/claims.py`, `duplicate.py`, `runtime.py`, normal rules/
archives/snapshot filters, targeted event lifecycle gates, the
`websocket_claims_duplicate` wrapper and local route/table registration.

Verified without bytecode writes or real AWS transport:

```sh
PYTHONDONTWRITEBYTECODE=1 AWS_EC2_METADATA_DISABLED=true \
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
AWS_DEFAULT_REGION=us-east-1 venv/bin/python -B -m pytest -q \
  tests/test_claims.py tests/test_duplicate_events.py \
  tests/test_claims_duplicate_local.py
```

Tests cover consent/partner veto, robot policy, exact rejection/cancel/expiry/
disconnect resumption, suspended clocks, forged votes/identity, bounded IDs,
idempotent score/archive and event transactions, two-board/two-table completion,
old-board embargo, authoritative deals, cross-table membership, three-table
ties, IMP thresholds, SOLO denial, and stale/last-board protection. The real
eight-client integration owns an isolated loopback server on ephemeral ports,
never the existing 3001/3002 server.
