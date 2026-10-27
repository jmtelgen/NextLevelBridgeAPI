# Staging Lambda packaging

This is preparation, not deployment. No AWS calls, legacy deployment scripts,
tracked deployment ZIPs, or developer-machine DDS binaries are used by this build.
The deployment entrypoint contract is `deployment/runtime-routes.json`.

## Route and runtime contract

The manifest lists **6 REST routes, 30 WebSocket routes, and 2 event mappings**
backed by **22 Lambda functions**. All functions use one immutable ZIP, Python
3.12, x86_64, and the `bridge-staging-` function-name prefix. Default memory is
1024 MiB; API handlers have 29-second timeouts. Handler strings are executable
Lambda `module.attribute` paths, not filesystem paths.

CloudFront preserves `/api` on the request. Its REST origin path is `/staging`;
therefore REST **resources include `/api`**, not just the unprefixed local paths.
Forward all cookies/query strings and viewer headers except Host; never cache
`/api` or `/api/*`. `FRONTEND_URL` is the exact HTTPS CloudFront origin.

| REST method/path | Existing handler module (`.lambda_handler`) |
| --- | --- |
| POST `/api/account` | `lambdas.api.auth.account_create` |
| POST `/api/account/login` | `lambdas.api.auth.account_login` |
| POST `/api/auth/refresh` | `lambdas.api.auth.account_refresh_token` |
| POST `/api/auth/guest` | `lambdas.api.auth.guest_session` |
| POST `/api/logout` | `lambdas.api.auth.account_logout` |
| GET `/api/connections` | `lambdas.api.game.connection_count` |

Use REST API **v1 Lambda proxy** integrations: existing cookie responses require
`multiValueHeaders.Set-Cookie`. Add unauthenticated OPTIONS preflight responses
for these resources and CORS on gateway-generated errors. Production handler
headers remain unchanged; verify their CORS behavior end-to-end before release.
No new HTTP events, archives, or agreements API is invented.

WebSocket route selection is `$request.body.action`, with stage `staging`.
Each entry below uses `staging_runtime.<module>`, which delegates to
`lambdas.api.websocket.<module>.lambda_handler`:

| Module | Route keys |
| --- | --- |
| `websocket_connect` | `$connect` (also synchronizes presence) |
| `websocket_disconnect` | `$disconnect` (presence/grace handling) |
| `websocket_create_room` | `createRoom` |
| `websocket_join_room` | `joinRoom` |
| `websocket_change_seat` | `changeSeat` |
| `websocket_start_room` | `startRoom`, `getGameState`, `nextBoard` |
| `websocket_make_bid` | `makeBid` |
| `websocket_play_card` | `playCard` |
| `websocket_board_records` | `getBoardArchive`, `listBoardArchives`, `getAgreementCard`, `getMatchScoreboard`, `setPracticePace` |
| `websocket_leave_room` | `leaveRoom` |
| `websocket_replace_player` | `replacePlayer` |
| `websocket_room_controls` | `transferOwnership`, `setRoomLock`, `createInvitation`, `revokeInvitation` |
| `websocket_practice` | `getPracticeHint`, `setComputerLevel` |
| `websocket_claims_duplicate` | `proposeClaim`, `respondClaim`, `cancelClaim`, `createDuplicateEvent`, `joinDuplicateEvent`, `startDuplicateEvent`, `getDuplicateEvent` |

The current handlers explicitly deliver replies and errors with the management
API. **Do not add two-way application route responses**, which duplicate replies.
Preserve the connect handshake's `Sec-WebSocket-Protocol: bridge.v1` response.
There is deliberately no invented `$default` application handler.

Both tick functions use `staging_runtime.game_tick`, delegating to
`lambdas.api.game.game_tick.lambda_handler`:

* Dispatcher: room stream `NEW_IMAGE`, INSERT/MODIFY filter, 30-second timeout,
  batch size 10, partial-batch failures, bisect on error.
* Worker: standard SQS, 60-second timeout, batch size 1, partial-batch failures,
  visibility timeout at least 360 seconds, DLQ required.

The manifest also supplies suggested IAM role groupings: accounts, guest,
logout, connections, gameplay, tickDispatcher, tickWorker. Every function needs
its own appropriately scoped logging permissions. Dependency groups describe
services, not an authorization policy. The infrastructure owner must scope the
actual resources/actions and verify stream retry, DLQ and retention policies.

## Durable bootstrap and environment

Before any WebSocket handler or tick invocation, `staging_runtime.initialize()`
executes once successfully per execution environment:

```python
duplicate.store = duplicate.DynamoEventStore(
    boto3.resource("dynamodb").Table(os.environ["DUPLICATE_EVENTS_TABLE"])
)
archives.configure_from_environment()
```

Both table environment variables must be nonempty; missing configuration fails
closed before calling the existing handler. Duplicate initialization **must
precede** archive initialization. The wrapper changes no routing, event, context,
response, or solver semantics.

* `DUPLICATE_EVENTS_TABLE`: dedicated table, `eventId` string partition key.
* `BOARD_ARCHIVES_TABLE`: `bridge-staging-board-archives`, partition key `roomId`
  string, sort key `boardNumber` number; no index or TTL. See
  [archive durability](board-archive-durability.md).
* `USER_TABLE`, `ROOM_TABLE`, `WEBSOCKET_CONNECTIONS_TABLE`: isolated staging
  tables with the existing schema, not production tables.
* `JWT_SECRET_ID`: staging secret identifier, never secret material.
* `FRONTEND_URL`, `WS_ALLOWED_ORIGINS`: exact HTTPS frontend origin(s).
* `WEBSOCKET_ENDPOINT`: **https** management URL including `/staging`, not `wss`.
* `GAME_TICK_QUEUE_URL`: isolated standard queue.
* `ENVIRONMENT=production`: intentionally required even in staging; existing
  handlers add `Secure` to cookies only for this exact value.
* `PYTHONDONTWRITEBYTECODE=1`; AWS supplies the matching runtime region.

Archive completion atomically writes room/archive/duplicate results; no extra
archive worker or outbox is required. The stream dispatcher only reads stream
records and sends SQS messages, so it does not need gameplay table permissions
merely to construct the bootstrap's local Table resource objects.

## Build

Prerequisite: Docker with BuildKit on an x86_64 Linux runner. No host package
installation is needed. From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B deployment/package/test_packaging.py
bash deployment/package/build_staging.sh build/staging-package
```

The output directory must be absent or empty. The script pulls public inputs,
but never accesses or mutates AWS. It fails if Docker is unavailable; there is
no fallback to a developer-host binary. A hosted GitHub Linux runner may run the
same command before any AWS authentication step.

The SAM build image and Lambda runtime image are pinned by **linux/amd64 image
digest** in `native-source.json` and the Dockerfile. The SAM image already
contains the compiler: no `dnf`, host compiler installation, or mutable RPM
resolution is performed. Python wheels use a complete 12-package,
hash-locked closure, downloaded for `manylinux2014_x86_64`/Python 3.12.
Pydantic 1.10.13 intentionally uses its pure-Python wheel; bcrypt uses its
compatible ABI3 wheel.

DDS 2.9.0 source is fixed to commit
`8d75755c8df81999557758c9757514edb94017bc` and archive SHA-256
`5443dd51a539747192344223ee8726b72e272176226a98d57ac9ae98560336d8`.
The build replaces only its Linux shell-based `free` probe with a conservative
256 MiB/one-core resource bound, since the minimal Lambda image need not have
procps utilities and host core/memory counts are inappropriate. The adapter then
applies `SetResources(32, 1)`. It compiles with STL threading and dynamically
links libstdc++, libgcc and glibc from the pinned AL2023 Lambda runtime.
The pinned SAM image does not include static libstdc++ archives; requesting
`-static-libstdc++` fails at link time. The exact pinned Lambda runtime contains
`/usr/lib64/libstdc++.so.6` and `/usr/lib64/libgcc_s.so.1`; its required native
solve gate verifies actual load and symbol compatibility before export.
No compiler runtime libraries are redistributed in the ZIP. The solver
algorithm and application wrapper are unchanged.

## Package layout and immutable outputs

```text
libdds.so.2                     # compiled for AL2023 x86_64, never copied from host
DDS-LICENSE, DDS-NOTICE
staging_runtime.py
lambdas/                       # existing Python package tree, no tests/pycs/host .so
  api/, core/, models/, shared/
  dds/working_dds_wrapper.py
  dds/bridge_bidding_alg.txt
  dds/bridge_bidding_sayc.txt
boto3/, botocore/, bcrypt/, ... # locked runtime dependencies and license metadata
deployment/runtime-routes.json
deployment/package/{requirements.lock,native-source.json,build_dds.py,staging.Dockerfile}
PACKAGE-RECEIPT.json            # SHA-256 for every other included member
```

Output names:

* `bridge-staging-<ZIP-SHA256>.zip`: sorted members, fixed timestamps/modes, stored
  without compression to avoid zlib-version variation.
* `bridge-staging-<ZIP-SHA256>.json`: ZIP/native/manifest/lock/source-pin SHA-256,
  base64 `codeSha256` for comparison with Lambda `CodeSha256`, size/member count.
* `bridge-staging-<ZIP-SHA256>.sha256`: standard checksum file.
* `bridge-staging-<ZIP-SHA256>.validation.json`: **only produced after** successful
  validation in the pinned Lambda image, bound to the exact ZIP hash.

Use an immutable S3 key containing the ZIP hash and preserve the S3 object
version. The stored ZIP may exceed Lambda's direct 50 MiB upload limit; S3
deployment is expected. The builder rejects the 250 MiB uncompressed limit.
Do not treat a git SHA, source-only ZIP, synthetic test fixture, or host DDS
smoke result as proof of a deployable artifact.

The export stage requires real Python 3.12 AL2023 x86_64 imports for every
manifest Handler and delegated entrypoint, per-file receipt verification,
durable-store initialization in Lambda mode, bcrypt hashing, a Pydantic model,
a Secure logout cookie, and an actual DDS solve (`SA` wins a one-trick deal).
AWS SDK and socket network transport are blocked during validation.

## Remaining release gates

Local stdlib tests verify exhaustive route coverage, callable exports, required
environment/bootstrap ordering, immutable package names, normalized ZIP
metadata, content receipts, native ELF architecture rejection, and absence of
developer artifacts. Hash-locked wheels and actual handler imports/bootstrap
were also checked on the host's Python 3.12 with network denied.

**Docker was unavailable in the preparation environment. No AL2023 DDS build,
target-runtime solve, deployable ZIP digest, or `.validation.json` has yet been
produced.** Run the hosted container build before uploading or deploying.
For a clean reproducibility check, repeat the Docker build with `--no-cache`
into a separate empty output directory and compare ZIP hashes.

Even a successful target-image validation does not prove live IAM, cookie/CORS
behavior, connect subprotocol negotiation, API Gateway reply delivery,
JWT secret retrieval, DynamoDB transactions, stream/SQS/DLQ recovery, or full
gameplay. Verify those in isolated staging after the infrastructure owner
deploys the same immutable artifact. No AWS deployment is performed here.
