# Authoritative bridge lifecycle contract

This is the current **source-level** game contract. It supersedes the gameplay
examples in `WEBSOCKET_API.md`. No AWS deployment or live multiplayer validation
was performed for this change. Do not describe the hosted application as updated
until the deployment and release gates below pass.

## Routes and commands

### Signed connection and guest bootstrap

Unsigned query-selected identities are no longer accepted. `$connect` verifies
the existing account HS256 access JWT (`type:"access"`) or a dedicated signed
anonymous session (`type:"guest"`), requiring valid `exp`, `iat`, `userId`, and
token type. Refresh tokens, missing claims, wrong keys/algorithms, tampering,
expired tokens and reserved robot identities are rejected. If a legacy query
`userId` is supplied it must match the signed subject; it is not an identity
source. Signed username claims, not query display names, populate connections.

Browser transport avoids putting bearer tokens in URLs:

```js
const socket = new WebSocket(socketUrl, [
  'bridge.v1',
  `bridge.auth.${accessToken}`,
]);
```

The successful upgrade echoes only `Sec-WebSocket-Protocol: bridge.v1`.
Native clients may alternatively send `Authorization: Bearer <access JWT>`.
Exactly one credential is accepted; do not send both. The Origin header is
required, including for native clients. Full connect events/protocol headers are
not logged by this handler. API Gateway access/execution logs and upstream
proxies must also redact authorization and subprotocol headers.

Anonymous gameplay remains available through **new HTTP POST `/auth/guest`**,
implemented by `lambdas/api/auth/guest_session.py` / `GuestSessionAPILambda`.
The coordinated frontend calls `/api/auth/guest` through its API proxy:

```json
{"username":"Guest display name"}
```

Response: `{userId,username,accessToken,expiresIn:86400,tokenType:"Bearer",isGuest:true}`.
The server chooses a random `guest_...` UUID and signs its 24-hour identity;
body `userId` never selects a subject. Guest JWTs are not account access tokens
and cannot be used in existing access-only protected APIs. Supplying
`Authorization: Bearer <still-valid guest JWT>` renews the same guest identity;
an invalid/expired supplied bearer yields 401, never a fresh fallback identity.
The frontend retains the guest credential in sessionStorage for reload
continuity. There is no recovery of an expired/lost guest credential or
automatic reassignment of its occupied seats. Clearing session storage is an
explicit new guest identity, not reconnecting to the old one.

Both `/auth/guest` and `$connect` require exact permitted frontend origins from
`WS_ALLOWED_ORIGINS` (comma-separated) or, if absent, `FRONTEND_URL`. Missing,
wildcard or malformed configuration fails closed with 503; mismatched/missing
Origin fails with 403. Use explicit HTTPS origins in production, HTTP localhost
only for local development. `/auth/guest` handles POST/OPTIONS with exact-origin
CORS, authorization/content-type allowed headers, credential support, and
`Cache-Control:no-store`. It issues no refresh cookie and does not depend on one.

Account login's existing access token remains in memory; the existing
HttpOnly `refresh_token` cookie/refresh endpoint restores it. That cookie is
currently **SameSite=Strict** (Secure when `ENVIRONMENT=production`): production
account refresh requires a same-site API/frontend setup or reverse proxy.
Cross-site default AWS hostnames may prevent refresh; do not silently downgrade
a failed account refresh into a new guest. Changing cookie policy requires a
separate CSRF/CORS review. Never send refresh tokens to `$connect`, expose
the JWT signing secret to the browser, or log/store tokens in room snapshots.
Browser-held guest tokens remain exposed to same-origin XSS; CSP and frontend
injection defenses remain necessary.

The login lookup now paginates filtered scans (including table fallback when
the username/email index is unavailable or has not caught up). The previous
`Limit=1` scanned-item limit could incorrectly reject every account except the
first scanned item. No login response, password verification or cookie contract
was changed.

Connection records store signed `authType` and `authExpiresAt`. Subsequent game/
lobby actions require a still-unexpired record for that connection. Expired and
old unsigned records are rejected, and are excluded from personalized broadcasts.
An account token expiring during a game yields 401; refresh account credentials,
reconnect and request a snapshot, rather than replaying the stale command.
Guest expiry requires explicit user-visible recovery/new-session choices.
Deploying this change requires all existing clients to reconnect with credentials.

API Gateway selects routes with `$request.body.action`. Commands may put fields
at the top level or in `data`:

```json
{"action":"makeBid","data":{"roomId":"room-uuid","userId":"guest-uuid","bid":"1NT","revision":5}}
```

`userId` is optional for game routes; when provided it must equal the identity
stored for `requestContext.connectionId`. Room membership is required, including
for snapshots. The body cannot choose another seat or control a robot.

| Route | Fields beyond `roomId` | Existing Lambda/source |
| --- | --- | --- |
| `startRoom` | optional `userId`, `revision` | `WebSocketStartRoomLambda`, `websocket_start_room.py` |
| **`getGameState` (new)** | optional `userId` | same start-room Lambda |
| **`nextBoard` (new)** | optional `userId`, `revision` | same start-room Lambda |
| `makeBid` | `bid`, optional `userId`, `revision` | `WebSocketMakeBidLambda`, `websocket_make_bid.py` |
| `playCard` | `card`, optional `userId`, `revision` | `WebSocketPlayCardLambda`, `websocket_play_card.py` |

Only the owner can start a waiting room or advance a completed board. Empty seats
are filled with robots. Board 1 starts with North as dealer; subsequent boards
rotate clockwise and use the standard 16-board duplicate vulnerability cycle.
Four opening passes complete a passed-out board. There is no automatic redeal.
`joinRoom` and `changeSeat` lock when play starts; existing seated users reconnect
with `getGameState`, not `joinRoom`.

Seats are `North`, `East`, `South`, `West`. Cards are rank followed by suit:
`AS`, `TH`, `2C`; suits `C,D,H,S`, ranks `23456789TJQKA`. Calls are `pass`,
`double`, `redouble`, or levels `1..7` followed by `C,D,H,S,NT` (for example `3NT`).
The server rejects underbids, same-side doubles, invalid redoubles, out-of-turn
calls/cards, cards outside the acting hand, and failure to follow suit.

## Personalized server envelope

```json
{
  "action":"cardPlayed",
  "seat":"North",
  "message":"East played AH",
  "room":{
    "roomId":"room-uuid","ownerId":"guest-uuid","roomName":"Bridge",
    "isPrivate":false,"seats":{"North":"guest-uuid","East":"ROBOT_East","South":"other-guest","West":"ROBOT_West"},
    "state":"playing"
  },
  "publicState":{
    "currentPhase":"playing","turn":"South","dealer":"North","vulnerability":"None",
    "boardNumber":1,"revision":6,"bids":[],"contract":"1NT","contractMultiplier":1,
    "declarer":"North","dummy":"South","openingLeader":"East",
    "dummyRevealed":true,"dummyHand":["2C"],"currentTrick":[{"seat":"East","card":"AH","timestamp":1}],
    "tricks":[],"previousTrick":null,"trickWinner":null,
    "handCounts":{"North":13,"East":12,"South":13,"West":13},
    "result":null,"scores":{"NS":0,"EW":0},"robotPending":false,
    "completedTrick":null,"pendingAction":null,
    "pacing":{"robotCardDelayMs":700,"trickHoldMs":1200},"serverTimeMs":1770000000000
  },
  "privateState":{
    "seat":"North","hand":["AS"],"validBids":null,"isMyTurn":true,
    "isDeclarer":true,"isDummy":false,"partnerSeat":"South",
    "playSeat":"South","legalCards":["2C"]
  }
}
```

The example hands are abbreviated. Gameplay actions are `roomStarted`,
`boardStarted`, `bidMade`, `cardPlayed`, `trickCleared`, and `gameState`. Robot actions use the
same names as human actions. `room` contains only the listed metadata, **never
`gameData`**. Its seats are occupant IDs, not usernames.

`publicState` has no `hands` map. `privateState.hand` is only the recipient's own
remaining hand. Dummy becomes public immediately after the first opening-lead
card and remains public. Declarer, not dummy's occupant, controls dummy:
`isMyTurn`, `playSeat`, and `legalCards` represent the controller's actionable
hand. `validBids` is populated only for the current bidder. Completed tricks
persist as `{leader, plays:[{seat,card,timestamp}], winner}`, with the same shape
for `previousTrick`. Old `{cards,winner}` records are normalized on load.

### Authoritative card and collection timing

The server persists each pending deadline as
`publicState.pendingAction:{kind,dueAt}`, where `dueAt` is Unix epoch
**milliseconds** and `kind` is `robotCard`, `clearTrick`, or `robotBid`.
`pendingAction:null` means no autonomous work is queued. The legacy
`robotPending` flag is true for any such work, including collection when the
next leader is human. `serverTimeMs` is the current server clock at snapshot
serialization; `pacing` describes the configuration used to plan that transition.
These are minimum delays, not promises of exact delivery time.

* A robot card gets a fresh deadline **700 ms after the preceding transition**,
  including the opening lead and robot-controlled dummy. Robots never play
  before this deadline. A late worker plays only one due card and plans the next
  from the actual current time; it does not rapidly catch up missed deadlines.
  Auction bidding retains its existing immediate, bounded progression.
* The fourth `cardPlayed` snapshot has `currentTrick:[]` and a non-null
  `completedTrick:{leader,plays:[four cards],winner}`. It also appends the trick
  to `tricks`/`previousTrick`, sets `turn` to its winner, and schedules
  `clearTrick` **1200 ms later**. This interval includes the frontend's
  presentation and collection animation (currently 400 ms hold + 800 ms
  collection). Render `completedTrick`, not historical `previousTrick`, as
  the table's collecting cards.
* While `completedTrick` is non-null, **all** human/robot next leads are blocked:
  `privateState.isMyTurn:false`, `legalCards:[]`, `playSeat:null`. Direct
  `playCard` attempts return 400 even if the collection deadline has passed but
  its clear transition has not yet committed. Reaching a browser timer deadline
  does not grant permission to play.
* The separate persisted **`trickCleared`** snapshot sets `completedTrick:null`.
  Only then can a human leader act. A robot leader receives a **new 700 ms**
  deadline after this clear, so its next card never appears during collection.
  Keep `previousTrick` as history, without reanimating it on reconnect.
* On the final trick, phase remains `playing`, with no `result` or score update,
  while the four cards collect. Only final `trickCleared` finalizes scoring,
  sets phase/room state `completed`, clears `turn`/`pendingAction`, and exposes
  results. `nextBoard` is rejected before that transition.

The frontend must disable hands while collection is authoritative, use stable
revision snapshots rather than synthesize card plays, and gate result overlays
on the final clear. `dueAt-serverTimeMs` permits a reconnecting client to animate
only the remaining collection interval without assuming its device clock agrees
with the server. Equal-revision snapshots must not restart the animation.
Delayed/out-of-order delivery cannot extend the authoritative deadline; ignore
older revisions. Human declarers retain control of dummy even when dummy's seat
is occupied by a robot: no robot deadline is created for that human action.

On completion, `turn` is null; `result` contains `passedOut`, `scoreNS`, and
`scoreEW`. Played contracts also include `contract`, `multiplier`,
`declarerTricks`, `target`, and boolean `made`. Scores are signed duplicate-board
points, including vulnerability, doubles/redoubles, over/undertricks, partscore,
game, slam and insult bonuses. `scores.NS/EW` accumulate board points in the
room; they are **not IMPs, matchpoints, rubber scores, or tournament results**.

## Concurrency, recovery, and delivery

Every accepted transition uses conditional DynamoDB `PutItem` against the
room's integer `revision`, then publishes personalized state. The actual next
turn is recomputed after every call/card and completed trick. Robots use the
same legal mutations, including declarer-controlled dummy, and their changes
are persisted individually before publication. A stale write cannot overwrite a
human or robot move. `revision` is also exposed in `publicState`; clients should
send their observed revision for mutations and ignore older incoming revisions.

The server explicitly sends responses with the Management API, including to the
caller, rather than depending on an API Gateway route response. A caller can
receive the same revision twice; treat updates as state snapshots, not commands
to apply twice. Multiple active tabs receive personalized updates. A broadcast
failure does not roll back a durable move; reconnect and request `getGameState`.

`getGameState` returns waiting, bidding, playing, or completed state with the
same persisted timing on reconnect. It can resume **at most one due timed
transition**, never a not-yet-due card or collection. Multiple tabs polling do not
reduce delays. Bidding work is bounded to 128 actions and stops when a real
Lambda context reports under 2 seconds remaining; `robotBid` with an immediate
deadline permits continuation by the worker. Old playing rooms without a
deadline acquire and persist one before their first resumed robot card.

Normal production progression **requires the autonomous worker below**, not an
active requesting browser. Deadline-aware snapshot retries (remaining server
delay plus modest backoff, not a tight loop) are optional delivery/reconnect
recovery; they do not replace worker deployment. Snapshot requests may advance
the revision when they recover due work. No caller-controlled hidden hands
enter broadcasts.

Errors sent on the socket:

```json
{"action":"error","statusCode":409,"error":"Stale revision; request getGameState","message":"Stale revision; request getGameState"}
```

Expect 400 for illegal actions/state, 401 for unknown connections, 403 for
identity/membership/owner violations, 404 for missing rooms, and 409 for stale
state. On 409 request a new snapshot before offering a new move. Do not
automatically replay the old command. There is no request-ID deduplication:
revision-aware clients prevent accidental repeat actions.

## Environment, tables, and deployment

Game/lobby functions need `ROOM_TABLE`, `WEBSOCKET_CONNECTIONS_TABLE`,
`WEBSOCKET_ENDPOINT` (full `wss://.../stage` or HTTPS equivalent). Existing lobby
username conversion also needs `USER_TABLE`. `$connect`/`$disconnect` need
`WEBSOCKET_CONNECTIONS_TABLE`; `$connect` additionally needs `JWT_SECRET_ID`
(same Secrets Manager signing key as account login) and `WS_ALLOWED_ORIGINS`.
`guest-session` needs those latter two settings, but no DynamoDB table.
IAM must allow `secretsmanager:GetSecretValue` for the configured secret on
connect/guest (and KMS decrypt if the secret uses a customer-managed key),
plus required DynamoDB
`Query/Scan/PutItem/DeleteItem` and `execute-api:ManageConnections` for the stage.
Use Python 3.12-compatible dependencies; native DDS must match Lambda OS/CPU.
Start-room now also runs robots; its package must include DDS like bid/play.

Game-route functions and the tick worker support `ROBOT_CARD_DELAY_MS`
(default `700`, integer `100..10000`) and `TRICK_HOLD_MS` (default `1200`,
integer `1000..10000`). Invalid/empty/fractional/out-of-range settings fail game
requests with 503 before mutation; the worker fails its record for retry.
Keep settings equal across game functions and worker. Existing persisted
deadlines are not retroactively changed when configuration changes.

### Autonomous game-clock worker (required new infrastructure)

`lambdas.api.game.game_tick.lambda_handler` is **not a public WebSocket route**.
Deploy it as a private worker (proposed function name `GameTickLambda`) with
the same runtime/native robot package as bid/play/start. Two event sources target
this handler:

1. Enable `NEW_IMAGE` (or `NEW_AND_OLD_IMAGES`) **DynamoDB Streams on the room
   table**, and attach a stream event-source mapping. Each persisted room image
   with `gameData.pendingAction` enqueues `{roomId,revision,kind,dueAt}` on a
   **standard SQS queue**. Enqueue happens from the durable stream, not as a
   fragile second write from the game request. A request crash after saving
   therefore cannot lose scheduling. Preserve/replay failed stream records.
2. Attach that queue as an SQS event source for the worker. It strongly loads the
   room, checks the exact revision and pending action, then uses the same
   conditional-write transition as game routes. Stale/duplicate/out-of-order
   deliveries do nothing. Early delivery re-enqueues the original deadline;
   a budget-limited/no-progress retry has at least one second of queue backoff.
   completed due transitions rely on their new room stream record to schedule
   continuation. No Lambda invocation sleeps to wait for a deadline.

Set **`GAME_TICK_QUEUE_URL`** on the worker, in addition to `ROOM_TABLE`,
`WEBSOCKET_CONNECTIONS_TABLE`, and `WEBSOCKET_ENDPOINT`. Missing queue config,
enqueue failure, malformed events, or runtime errors are reported via
`batchItemFailures`, not swallowed. Enable **`ReportBatchItemFailures` on BOTH
event-source mappings** (stream identifiers are sequence numbers, SQS
identifiers are message IDs). Configure retry limits, stream failure destination/
replay, queue redrive DLQ, alarms on failures/oldest messages/stream iterator
age, and a visibility timeout adequate for the worker timeout and batching.
Use a small stream batching window and SQS batch size; a 30-second worker
timeout is an initial setting, not a measured SLA. A configuration/IAM error must
fail release verification rather than silently depend on client polling.

Worker IAM needs DynamoDB stream reads (`DescribeStream`, `GetShardIterator`,
`GetRecords`, `ListStreams`), `sqs:SendMessage`, queue consumption
(`ReceiveMessage`, `DeleteMessage`, `GetQueueAttributes`), the existing room
`Scan/PutItem`/connection lookup permissions, and stage-scoped
`execute-api:ManageConnections`. Preserve the deployed table's full key
(including `ownerId` where applicable); there is no new table/index requirement.
Provision appropriate KMS rights if queues/streams use customer-managed keys.

SQS delay resolution is whole seconds: the dispatcher rounds the remaining
delay **up**, so default 700 ms cards commonly arrive around **1 second** and
1200 ms collection around **2 seconds**, plus stream/queue/compute/network
latency. These may be late but never early. This is not a subsecond SLA.
The local adapter uses event-loop timers with the same durable-state transition
and configured minimums; no SQS or real AWS transport is enabled there.
This worker/infrastructure is source-only until explicitly provisioned, mapped,
and validated in staging; updating only the three game Lambdas is insufficient.

Source-derived schema facts:

* `WebSocketConnections`: string partition key `connectionId`, string sort key
  `currentRoomId`; fields `userId`, `status:"connected"`, `authType:"access"|"guest"`,
  numeric `authExpiresAt` (Unix seconds). Connection identity is
  resolved with a strongly consistent partition query.
* `GameRooms`: full room item including `roomId` and whatever existing key fields
  the installation requires. The repository **does not define its deployed key
  schema/IaC**; lookup retains the existing paginated, strongly consistent scan
  because an unknown sort key is referenced by the old implementation. No table
  or key migration was attempted. Conditional writes preserve the full item.
* `UsersTable`: existing user lookup scans by `userId`; deployed key schema is
  likewise not defined here. Inventory both table schemas before rollout.

New room writes initialize revision lazily: existing items without `revision`
can transition once using `attribute_not_exists(revision)`, then all writes
require the observed revision. No data backfill is required for that field.

**Operator-only deployment steps, not executed by this change:**

1. Preserve existing ZIPs/worktree changes. In a separate clean release checkout,
   build packages for `websocket-start-room`, `websocket-make-bid`,
   `websocket-play-card`, `websocket-create-room`, `websocket-join-room`,
   `websocket-change-seat`, **`websocket-connect`**, new **`guest-session`**,
   and the new game-clock worker (`lambdas.api.game.game_tick.lambda_handler`);
   all contain the common `lambdas` package. Existing
   `deploy.sh` overwrites its deployment ZIP: do not run it on preserved artifacts.
2. Set/check the environment above on **existing as well as new functions**.
   `deploy-aws.sh create` now includes socket dependencies for game/lobby
   functions and requires `WEBSOCKET_ENDPOINT`; connect/guest creation requires
   explicit allowed origins and configures the shared `JWT_SECRET_ID`.
   `update` does not migrate config.
   Allow sufficient Lambda timeout for bounded robot work (30 seconds is an
   initial setting, not a measured production SLA).
3. Reuse the start-room Lambda's existing API Gateway AWS_PROXY integration.
   Create **`getGameState` and `nextBoard`** routes targeting that integration;
   `startRoom`, `makeBid`, and `playCard` retain their current integration names.
   Add Lambda invoke permission if its source ARN is restricted to `startRoom`
   rather than the entire WebSocket API. Deploy the API stage (unless auto-deploy
   is enabled). No new table or WebSocket route-response mapping is needed.
4. Create the **GuestSessionAPILambda** function using the `guest-session`
   deployment selector; wire **POST and OPTIONS `/auth/guest`** with REST/HTTP
   Lambda proxy integration. Forward `Origin`, `Authorization` and JSON bodies;
   do not configure conflicting wildcard/credential CORS. Map the frontend's
   `/api/auth/guest` proxy to this path. On the WebSocket API, forward
   `Sec-WebSocket-Protocol` and `Origin` to `$connect` and preserve the successful
   `Sec-WebSocket-Protocol:bridge.v1` integration-response header. This handler
   authenticates the upgrade itself; do not add an authorizer that trusts raw
   `userId`. Disable/redact sensitive execution/request headers in gateway logs.
5. Provision the room stream, standard queue, worker, **both** partial-failure
   event-source mappings, permissions, redrive/replay and alarms described above.
   There is not yet a game-tick deployment selector/IaC in the legacy scripts;
   package/map this new handler explicitly in a reviewed release configuration.
   Test autonomous progression with **all browsers disconnected**, then
   reconnect and verify the authoritative deadline/current trick/result.
6. Verify route selection `$request.body.action`, Management API endpoint,
   stage permissions, native loading, and all release gates below in staging.
   Deploy coordinated frontend/backend; old clients expecting raw hands are
   intentionally incompatible.

## Local verification and follow-on release gates

Use the existing virtualenv; no dependencies need installation:

```sh
PYTHONDONTWRITEBYTECODE=1 AWS_EC2_METADATA_DISABLED=true \
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing AWS_DEFAULT_REGION=us-east-1 \
venv/bin/python -m pytest tests/test_websocket_make_bid.py tests/test_bridge_lifecycle.py tests/test_game_pacing.py tests/test_game_tick.py tests/test_local_server.py tests/test_socket_sessions.py tests/test_robot_fair_play.py tests/test_robot_bidder_fair.py tests/test_robot_benchmark.py -q -p no:cacheprovider
bash -n deploy.sh deploy-aws.sh
```

The offline suite checks complete 1/2/3/4-human games, robot-controlled human
dummy, real fair robot selection, 52-card conservation, winner-led tricks,
serialization, bidding/double legality, scoring, privacy, reconnect/resume,
multiple tabs, owner-only next boards and stale-write rejection. Moto tests also
exercise real DynamoDB conditional-expression parsing, composite-key retention,
deleted-item protection, Decimal round-trips and complete persisted games.
These are local emulations, not staging concurrency/load evidence, and make no
external AWS calls. All 58 user-added `tests/test_websocket_make_bid.py` cases
remain present and now use signed connection records, real privacy filtering,
conditional-write snapshots and current authoritative robot state rather than
stale refresh/static-sequence internals. Vacuous conditional opening-lead checks
are strengthened to require actual legal persisted plays. Signed-session tests
cover tampered/expired/missing/mismatched identities, rejected refresh tokens,
strict origins, guest issue/renewal and fail-closed configuration. Other legacy
utility tests still fail collection against obsolete `lambdas.utils` imports.

Remaining tasks for future agents (acceptance criteria):

1. **Credential operations/private-room ACLs:** signed guest/account upgrade
   authentication is implemented and locally tested, but not deployed.
   Acceptance: staging verifies exact-origin CORS/subprotocol forwarding,
   account-cookie restoration, guest renewal, expiry/reconnect and denied
   impersonation. Add rate limits for guest issuance, credential revocation/
   logout policy and key rotation tests. Private-room authorization remains a
   separate release blocker: `isPrivate` alone is not ACLs.
2. **Staging multiplayer/privacy release gate:** in independent browser sessions,
   finish boards with 1–4 humans, both partnerships, double/redouble and dummy;
   reconnect mid-auction/trick, force concurrent duplicate/stale writes and
   timeout/resume, and verify every socket/network/log payload reveals only own
   hand and exposed dummy. Capture observed results, not just local mocks.
3. **Inventory infrastructure and REST exposure (release blocker):** version exact
   table keys, route mappings, environment/IAM and native architecture in IaC.
   Audit every separate room/list/detail service; acceptance: no REST/lobby
   response or logs return active `gameData.hands`, and both new routes work.
4. **Remaining regression modernization:** repair unrelated stale import paths
   in a separate scoped task; the 58 user-added auction regressions are migrated.
   Acceptance: full suite collects and all relevant old behavior/security
   assertions have corresponding behavioral tests, not blanket skips.
5. **Lifecycle operations:** implement explicit leave, owner transfer, room expiry,
   stale connection cleanup, bot replacement policy and crash/abandoned-room
   recovery. Currently disconnect only drops connection records and retains seats.
   Acceptance: deterministic tested policies, no hidden-hand leakage or mid-board
   seat takeover, bounded storage and connection scans.
6. **Scale and operations:** replace scans with schema-backed indexed access,
   remove reconnect's delete/reinsert identity window, add durable event/outbox or
   equivalent delivery recovery, metrics, idempotency and concurrency/load tests.
   Acceptance: fault injection demonstrates no lost accepted move, double score,
   overwritten turn or unbounded robot run.
7. **Bridge strength/tournaments:** measure AI against reproducible external
   baselines with confidence intervals before any strength claims. Add IMP/
   matchpoint competitions, conventions/configuration, claims/concessions and
   full adjudication only with their own rule tests. Current scoring is ordinary
   duplicate board points; no tournament/pro-level maturity is claimed.
