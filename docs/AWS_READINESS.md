# AWS readiness and isolated staging plan

## Deployment status: paused

The user approved **isolated staging before any public-site change**, but asked
to hold deployment until they create a scoped deployment identity. Do not
create infrastructure, roles, policies, upload artifacts, or deploy while paused.
Resume only after the user supplies the identity and confirms the staging
account, region, names, origins, and intended mutations.

**Refuse deployment using account-root credentials.** Before any mutation, check
`aws sts get-caller-identity` using the explicit approved profile and region.
An ARN ending in `:root`, an unexpected account, or an unexpected role is a stop
condition. Do not print credentials, tokens, signing keys, or secret values.

## Recommended deployment model

Planning does not resume deployment or authorize IAM changes. Keep local
development independent and introduce isolated staging before touching the
existing public site.

- Use `us-west-2` for application resources; CloudFront certificates remain in
  `us-east-1`.
- Prefer separate staging and production AWS accounts. If staging initially uses
  the existing account, isolate every resource, secret and role with a staging
  prefix and explicit permissions. A separate API stage backed by public tables
  is not an isolated environment.
- Manage infrastructure with AWS SAM/CloudFormation, including explicit
  API Gateway V2 WebSocket resources and non-SAM resources where needed.
  Keep the infrastructure source in `BridgeLambdas`; frontend release jobs use
  its environment outputs rather than hardcoded public identifiers.
- Separate a privileged, reviewed bootstrap from routine application releases.
  Routine deployers must not be able to modify their own trust/permissions or
  pass arbitrary execution roles.
- Build immutable release artifacts and record both repositories' commit IDs,
  artifact digests, configuration versions and infrastructure change sets.

### Human access and the IAM user

AWS recommends IAM Identity Center/federation for human access. The preferred
operator signs in with MFA and uses short-lived role credentials, including
`aws configure sso` / `aws sso login` for the CLI. This does not require an IAM
user access key.

If a traditional IAM user is preferred, the proposed user is `bridge-operator`:

1. Create a named, console-enabled user through a trusted administrator; require
   an initial password change and enroll phishing-resistant MFA where available.
2. Grant narrow self-service password/MFA permissions and permission to assume
   the approved staging operator role. The role trust policy must also name the
   exact user and require MFA. Do not attach `AdministratorAccess` or broad
   application/IAM permissions to the user.
3. Use a separate approval path for production. The ordinary staging user must
   not gain production access simply by changing a profile or stack parameter.
4. Do not create access keys by default. If CLI SSO is unavailable and keys are
   genuinely required, constrain the base user's permissions to the approved
   role assumption, use MFA-backed temporary role sessions, and store keys only
   in an appropriate local credential store. Never paste them into chat, commit
   them, or place them in GitHub Actions secrets.
5. After replacement access has been tested, retire any account-root API keys
   and remove root credentials from the workstation's deployment profiles.
   Keep root for account recovery/bootstrap, protected with MFA, not deployments.

No user, role or policy described here has been created.

### GitHub Actions and role boundaries

Use GitHub OIDC, not an IAM deployment user/access key. Create separate
staging/production roles for the frontend and backend repositories.
Trust must match `aud=sts.amazonaws.com` and the exact repository/environment
subject; inspect the actual subject format, including immutable repository IDs
where applicable. Do not use wildcard repository trust.

Protect the GitHub environments and allowed release branches/tags. Production
requires explicit approval; pull-request jobs receive no deployment credentials.
Grant `id-token: write` only to deployment jobs, pin external actions to reviewed
commit SHAs, and serialize deployments per environment.

| Principal | Intended scope |
| --- | --- |
| Human operator | Approved environment visibility and narrowly approved role actions |
| Frontend release role | Its artifact prefix, frontend bucket objects and distribution invalidations |
| Backend release role | Its artifact prefix and approved CloudFormation change sets/stacks |
| CloudFormation execution role | Approved environment resources; no modification of its own authority |
| Lambda execution roles | Only required tables, secret, connections, queue/stream and logs |

If CloudFormation uses an execution role, the backend deployer may pass only that
role to `cloudformation.amazonaws.com`. That execution role may pass only approved
Lambda roles to `lambda.amazonaws.com`. Pre-create runtime roles in the reviewed
bootstrap, or constrain creation to an approved path and permissions boundary.
Do not treat broad `iam:PassRole` as a harmless deployment permission.

## New release blockers after the local feature roadmap

The inventory below predates the full local roadmap and authentication repair.
Reconcile all current feature contracts, not only the older missing routes:

- Completed-board archives currently use a process-memory repository. Replace
  it with durable DynamoDB storage and a pagination index before a full AWS
  release. Completion, scores and archive publication need transactional writes
  or a durable idempotent outbox; a post-commit in-memory side effect is not
  reliable across Lambda crashes.
- Duplicate events currently run against local Moto DynamoDB. Provision a real,
  isolated event table and validate its transaction, membership and archive
  embargo paths across concurrent Lambda invocations/cold starts. Never depend
  on a process-local lock for correctness.
- Create an explicit route manifest for all current auth, presence/invitation,
  archive/agreement, practice, claims and event actions. The local adapter's
  Python routing dictionary does not create API Gateway routes.
- Include `POST /logout` and correct Set-Cookie propagation. Use the repaired
  signup/login/refresh handlers without credential logging. See
  [authentication.md](authentication.md). Cookie expiry is not token revocation;
  document that limit and decide whether durable revocable refresh sessions are
  required before public release.
- Verify exactly one intended mapping between browser `/api/*` paths and REST
  resources. Vite's development proxy/prefix rewrite is not production routing.
- Preserve exact origins, signed WebSocket subprotocols, no-cache auth/API
  behavior, request revision checks and the durable tick path.

### Release pipeline and promotion

1. **Pull requests:** isolated tests, type/build checks, browser flows, policy/
   template validation and Lambda-compatible native DDS builds. No cloud
   deployment credentials.
2. **Staging:** publish versioned artifacts, review/apply an infrastructure change
   set, deploy compatible backend versions/aliases, then frontend assets. Execute
   real AWS multi-client auth/gameplay/claim/event/replay-embargo acceptance.
3. **Production:** require separate approval and promote tested artifact digests.
   Introduce public runtime frontend configuration if the same frontend bundle is
   to be promoted unchanged: the current compiled WebSocket endpoint differs by
   environment. Runtime configuration must contain no secrets.
4. **Static publication:** upload hashed assets first with immutable caching,
   publish the entry document/configuration last with revalidation, and retain
   prior assets. Enable S3 versioning and restore prior entry/config versions for
   rollback; do not use the current public-bucket `sync --delete` script.
5. **Observe and roll back:** version/alias Lambda releases and retain API
   deployments. Monitor errors, connection failures, latency, stale ticks and DLQ
   messages. Pause background consumers when a rollback would otherwise mix
   incompatible state schemas; code rollback does not roll back data.

Do not automatically promote by rebuilding untested source, copying production
secrets into staging, exposing archive storage publicly, or switching the
existing public origin before staging acceptance and separate release approval.

## Read-only inventory

Inventory date: 2026-10-26 UTC. These are existing-resource hints, **not staging
deployment targets**. Revalidate metadata after the deployment pause.

| Component | Existing identifier / connection |
| --- | --- |
| Region | `us-west-2` |
| Public frontend | `https://next-level-bridge.com/`, with `www.next-level-bridge.com` alias |
| CloudFront | `E1HX0HXMLYUF2Z`, `d1h54yowalg875.cloudfront.net` |
| Private frontend S3 origin | `nextlevelbridgeassetdistributionbucket`, public access blocked |
| Origin access control | `E3S5KBSDQ0MV8J` |
| REST API | `BridgeAPIs`, `e2jrh99dbc`, stage `dev` |
| Frontend API behavior | `/api/*` routes to the REST origin with origin path `/dev` |
| WebSocket API | `BridgeRealTimeGameAPI`, `ipp77av3oi`, stage `dev` |
| WebSocket endpoint | `wss://ipp77av3oi.execute-api.us-west-2.amazonaws.com/dev` |
| Signing secret | `Bridge/JWT` in `us-west-2`; metadata inspected only |
| Frontend certificate region | ACM `us-east-1`, required for CloudFront |

The existing `dev` APIs serve the public site. Their name does **not** make them
safe staging resources.

Existing DynamoDB tables are on-demand, with no streams:

| Table | Partition key | Sort key | Index |
| --- | --- | --- | --- |
| `GameRooms` | `roomId` | `ownerId` | None |
| `WebSocketConnections` | `connectionId` | `currentRoomId` | None |
| `UsersTable` | `userId` | `username` | `username-email-index`: `username`, `email` |

Preserve these schemas in staging unless a separately reviewed migration is
approved. Do not copy production user records, sessions, signing secrets, or
active rooms into staging.

## Verified deployment gaps

- `GuestSessionAPILambda` and REST `POST /api/auth/guest` were absent. The
  frontend calls that path through same-origin `/api`; create the staging
  integration, CORS/OPTIONS handling where required, invocation permission, and
  stage deployment together.
- WebSocket `getGameState` and `nextBoard` were absent. Both use the current
  `websocket_start_room` handler. Existing start-room invocation permission
  covers only `startRoom`; adding routes alone is insufficient.
- Existing `$connect` configuration lacks explicit allowed origins and JWT
  secret mapping, and its execution role lacks secret-read permission. Deploy
  the signed connection flow together with the guest endpoint. It requires
  `bridge.v1` plus `bridge.auth.<token>` WebSocket subprotocols, not URL tokens.
- Configure `JWT_SECRET_ID` and exact `WS_ALLOWED_ORIGINS` for staging guest and
  connection handlers. Never allow wildcard origins or reuse production signing
  material. Verify the API passes Origin/subprotocol headers and returns the
  negotiated `bridge.v1` protocol.
- The secret helper currently defaults to `us-east-1` when
  `AWS_DEFAULT_REGION` is absent, ignoring Lambda's `AWS_REGION`. Correct region
  selection or explicitly configure `AWS_DEFAULT_REGION=us-west-2` before
  relying on the regional secret.
- Existing change-seat Lambda has no environment configuration; create-room
  lacks `WEBSOCKET_ENDPOINT`. Set staging table names and management endpoint on
  every handler that needs them. A `wss://` endpoint is converted to `https://`
  by the existing messaging helper.
- Existing WebSocket functions use Python 3.12 / x86_64, 128 MB memory and a
  3-second timeout. Measure DDS execution and choose tested staging settings;
  do not assume these limits suffice.
- `deploy-aws.sh` references a nonexistent shared `lambda-execution-role`.
  Existing functions have individual execution roles. Its update mode changes
  code only, not IAM, environment, routes, or event-source mappings. Neither
  deployment script constitutes a complete infrastructure deployment.
- Existing `/api/*` CloudFront cache policy is `SetCookieCachingPolicy`, with
  minimum TTL 1 second and default TTL 86400 seconds. Use caching disabled for
  staging authenticated/guest API behavior; verify authorization forwarding,
  allowed methods, origin path, and non-cacheable responses. Review the public
  configuration separately before any later production rollout.
- Frontend variable names are `VITE_WS_ENDPOINT` and `VITE_API_BASE_URL`.
  The latter controls the Vite development proxy, not production API routing.
  Production builds use same-origin `/api`, so staging needs its own
  CloudFront API behavior. Do not publish real environment values in this file.

## Durable robot pacing: mandatory AWS infrastructure

The backend worker is `lambdas.api.game.game_tick.lambda_handler`, proposed
function name `GameTickLambda`. It handles both DynamoDB Streams and SQS:

1. Persist `gameData.pendingAction` and the room revision.
2. A room-table **NEW_IMAGE** stream dispatches pending transitions to a
   **standard SQS queue** using a rounded-up per-message delay.
3. The SQS consumer strongly reloads the room and compares revision, deadline,
   and action kind before advancing at most one transition.
4. Conditional `PutItem` protects against duplicate/stale concurrent work; the
   resulting stream record schedules the next transition.

Create staging-specific queue/DLQ and worker names. `GameTickLambda` and the
candidate `BridgeGameTickQueue` were absent during inventory; no resources have
been created. Do not enable a stream on the existing public `GameRooms`.

Worker configuration:

- `GAME_TICK_QUEUE_URL`
- `ROOM_TABLE`, `WEBSOCKET_CONNECTIONS_TABLE`, `WEBSOCKET_ENDPOINT`
- SDK region configuration; let Lambda provide reserved `AWS_REGION`
- Optional `ROBOT_CARD_DELAY_MS`: default 700, accepted 100–10000
- Optional `TRICK_HOLD_MS`: default 1200, accepted 1000–10000

Configure both event-source mappings to report partial batch failures
(`ReportBatchItemFailures`). Set queue visibility above the tested worker
processing/retry budget; configure a redrive policy and DLQ retention. Configure
bounded stream retries, an appropriate failure destination, and alarms for
stream iterator age, Lambda errors/throttles, oldest queued message, and DLQ
messages. Document redrive/replay procedure before enabling live test traffic.
Filter stream events to relevant new/modified room images where appropriate.

SQS uses whole-second delays: defaults typically yield approximately one-second
robot cards and two-second trick holds, never intentionally earlier than the
stored deadline. No Lambda sleep or browser polling is a substitute for this
durable trigger. Existing CAS uses `PutItem`, not `UpdateItem`.

See [WEBSOCKET_CONTRACT.md](WEBSOCKET_CONTRACT.md) and
[robot-engine-contract.md](robot-engine-contract.md).

## Scoped identity and permissions checklist

The user creates/approves the deployment identity. A future worker must use that
identity, not bootstrap broader permissions or create an admin role. Prefer
short-lived role credentials and explicit profile/region arguments.

Before writing policy JSON, choose a staging resource prefix and enumerate the
exact ARNs. Separate deployment permissions from runtime execution permissions;
the following is a review checklist, not an approved policy:

- **Deployment:** Lambda create/update/configure/version/alias, resource-policy
  permissions and event-source mapping management, restricted to staging
  functions and approved sources. API Gateway management restricted to staging
  REST/WebSocket APIs and their routes, integrations, deployments and stages.
- **IAM:** Prefer pre-created staging execution roles. Allow `iam:PassRole` only
  for those exact role ARNs, conditioned on `iam:PassedToService =
  lambda.amazonaws.com`. Role/policy creation or modification needs separate
  user approval; do not request account-wide IAM administration.
- **Storage/messaging:** DynamoDB create/describe/configure-stream permissions
  for staging tables only; SQS create/configure/read metadata for staging queues
  and DLQs only. Grant deletion only if separately approved for teardown.
- **Frontend:** S3 list on the staging bucket and object operations only on its
  intended prefix; CloudFront configuration/invalidation only for the staging
  distribution. Keep S3 private with OAC; do not follow legacy public-bucket
  guidance. Custom-domain/ACM/Route 53 changes require explicit approval;
  a dedicated CloudFront hostname can avoid DNS changes initially.
- **Secrets:** Pre-create or explicitly approve creation of a staging signing
  secret. Runtime roles need `secretsmanager:GetSecretValue` only on that exact
  secret ARN, plus constrained KMS decrypt if a customer-managed key is used.
  The deployment worker does not need to render/read its value.
- **Runtime DynamoDB:** Grant only operations exercised by handlers on staging
  tables/indexes, including room `GetItem`/`Query`/`Scan`/conditional `PutItem`
  and connection lifecycle read/write/delete operations as needed.
- **Runtime messaging:** Scope `execute-api:ManageConnections` to
  `arn:aws:execute-api:<region>:<account>:<staging-ws-api>/<stage>/POST/@connections/*`.
  Give the dispatcher `sqs:SendMessage` on its queue; consumer
  `ReceiveMessage`/`DeleteMessage`/`GetQueueAttributes`; stream reader
  `DescribeStream`/`GetRecords`/`GetShardIterator`/`ListStreams` as required.
  Include scoped failure-destination writes.
- **Operations:** Staging CloudWatch Logs and alarms only. Review resource
  scoping for AWS operations that require `Resource: "*"`; do not silently
  substitute broad administrator policies.

Existing public-policy hints, not policies to reuse unchanged:
`GetJWTSecretValue`, `DynamoUserAndRoomAccess`,
`DynamoDbWebSocketConnectionsPut`, `WebsocketManageConnectionsPolicy`.
Existing `DynamoUserAndRoomAccess` includes
`PutItem`/`GetItem`/`Scan`/`Query`; connect's table policy includes `PutItem`
only. Derive staging grants from tested paths, not policy names.

## Native packaging and validation gates

DDS is an x86_64 ELF shared library with GLIBC requirements through 2.29 and
dependencies on the C++/GCC runtime libraries. Build dependencies and run import
and solver smoke tests in **Python 3.12 / Amazon Linux 2023 / x86_64** matching
Lambda. A host-machine `pip install` or successful local board is not evidence
of Lambda ABI compatibility. Include the same validated native DDS artifacts in
start-room, bidding, card-play and tick-worker packages as required by imports.
Inspect package contents, size, native dependencies and handler importability.
Preserve unrelated dirty source files and existing artifacts.

## Isolated rollout and rollback

After explicit user authorization:

1. Revalidate approved non-root identity and region. Review the exact resource
   list/change plan, expected charges, and rollback artifacts with the user.
2. Create only separately named staging tables, secret, roles, queues, worker,
   API stages/APIs, private frontend bucket and distribution. Do not point any
   staging configuration at public tables, queues, signing secret, or APIs.
3. Build immutable, compatible backend/frontend artifacts. Record version/hash,
   configuration and previous staging deployment IDs without secret values.
4. Install staging routes/invocation permissions and runtime configuration.
   Enable and verify stream-to-queue-to-worker processing, partial failures,
   DLQ and alarms before gameplay traffic.
5. Publish only to the staging bucket/distribution. Verify `VITE_WS_ENDPOINT`,
   same-origin `/api`, exact origins, disabled API caching and TLS.
6. Run staging guest authentication, rejected-origin/invalid-token checks,
   signed connect, personalized reconnect (`getGameState`), bidding, complete
   paced board, trick hold, robot lead, `nextBoard`, duplicate/stale tick,
   reconnect and DLQ/retry smoke tests. Confirm private hands remain private.
7. Report results and staging URL. **Public-site rollout requires a separate
   user decision**, even if staging passes.

Rollback stays within staging: stop test traffic, disable tick event mappings
to prevent incompatible background writes, restore compatible Lambda versions,
API deployment/configuration and frontend artifacts, then revalidate before
resuming processing. Retain queues/DLQs and tables for diagnosis; do not purge
or delete data automatically. Schema changes require their own rollback plan.
Never run the current frontend script against the public bucket: it uses
`s3 sync --delete`, which can remove existing objects.

Costs remain usage-dependent: Lambda invocations/duration, SQS requests, stream
processing, DynamoDB reads/writes/storage, WebSocket connection minutes/messages,
CloudFront/S3 transfer/requests, secrets, logs and alarms. Configure retention
and approved budget alerts; queue retries or stream loops can amplify costs.
No monetary estimate or public deployment approval is implied by this plan.
