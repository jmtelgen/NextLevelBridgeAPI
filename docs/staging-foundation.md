# Review-only staging storage foundation

**Deployment remains paused.** `deployment/staging-foundation.yaml` is native
CloudFormation source for review, not permission to create anything. No SAM
transform, application functions, routes, event-source mappings, IAM, DNS,
frontend distribution, bucket, or deployment workflow is included. This
foundation alone is **not a working application deployment**, and does not
make archives, duplicate events, or robot pacing durable in the running app.
The successful GitHub access-check workflows prove OIDC identity only, not
resource permissions or application readiness. Read-only IAM review found
both access-check identity roles have zero attached and zero inline policies;
they are not deployment identities with resource permissions.

The only intended initial target is account **851725597758**, application region
**us-west-2**, stack name **bridge-staging-foundation**. Names have a fixed
`bridge-staging-` prefix; there are no name/production parameters, external
imports, resource imports or existing-resource targets. Account/region checks
are an operator gate, not template-enforced authorization. `Metadata.StagingTarget`
records intent only. Explicit IAM scope
must prevent creation in other accounts/regions. Never reuse existing public
resources or copy public-site data/signing material.

The foundation PR is merged, and the backend staging `AWS_REGION` variable is
now `us-west-2`. The operator reran the access check successfully:
[verified run](https://github.com/jmtelgen/NextLevelBridgeAPI/actions/runs/40427443686).
The offline regression test checks the tracked guard, not GitHub's live variable.
This proves identity in the corrected region, not resource permissions.

The separate [foundation authority](foundation-authority.md) contracts and
main-only planning workflow prepare a change set for human review. They do not
execute it, provision this foundation, or change either identity-check role.
Running that workflow requires separately reviewed roles, configuration and
approval; creating a change set is itself a cloud metadata mutation.

See [AWS_READINESS.md](AWS_READINESS.md) for the deployment pause, role boundaries
and full release prerequisites. This file does not supersede that approval gate.

## Exact resource and integration contracts

All key attributes below are DynamoDB strings. Non-key game/user/session fields
remain schemaless; the template must not declare them as key attributes.

| Logical resource | Isolated name | Partition / sort key | Other contract |
| --- | --- | --- | --- |
| `RoomsTable` | `bridge-staging-rooms` | `roomId` / `ownerId` | Only table with a `NEW_IMAGE` stream |
| `UsersTable` | `bridge-staging-users` | `userId` / `username` | GSI `username-email-index`: `username` / `email`, projection `ALL` |
| `ConnectionsTable` | `bridge-staging-connections` | `connectionId` / `currentRoomId` | Includes `not-joined` sentinel records |
| `DuplicateEventsTable` | `bridge-staging-duplicate-events` | `eventId` / none | Revision-conditional event and room transaction adapter |
| `TickQueue` | `bridge-staging-game-tick` | Standard SQS | Four-day retention, 360-second visibility, long polling 20 seconds |
| `TickDeadLetterQueue` | `bridge-staging-game-tick-dlq` | Standard SQS | Fourteen-day retention, 360-second visibility |
| `JwtSigningSecret` | `bridge-staging-jwt` | Secrets Manager | Generated JSON `jwt_secret`, 64 alphanumeric characters |

Contract evidence and deliberate limitations:

- `lambdas/models/room.py` and `user.py` describe item fields, **not database
  keys**. Preserve the composite live key contracts recorded in
  `AWS_READINESS.md`; the local adapter's user table has only `userId` and is
  not evidence for changing the live user schema.
- `shared/database/db_utils.py` (under `lambdas/`) reads names through
  `ROOM_TABLE`, `USER_TABLE`, `WEBSOCKET_CONNECTIONS_TABLE`; it scans rooms/users
  when the full key is unavailable. Room ownership transfers transactionally
  move the composite key. Connection room changes delete/recreate records
  because `currentRoomId` is the sort key. Do not silently drop either sort key.
  Scan costs, pagination, username uniqueness races, and read-after-signup
  consistency remain application review/acceptance concerns, not schema fixes.
- `api/auth/account_create.py` and `account_login.py` scan
  `username-email-index`; login needs password hash and salt as well as identity.
  `ALL` projection is an explicit staging integration choice for those reads,
  not a claim that the inventory verified the existing index's projection.
  A GSI is eventually consistent and does not enforce unique usernames/emails.
- `core/game/duplicate.py:DynamoEventStore` really uses DynamoDB: strongly
  consistent `GetItem` by `eventId`, revision-conditioned `TransactWriteItems`
  including composite-key rooms. The local adapter provisions this same
  event key. However, `duplicate.store` defaults to `None`, and only
  `scripts/local_server.py` currently installs the adapter. **There is no
  application event-table environment variable or deployed initialization
  contract yet.** The output is a future wiring input, not a feature switch.
  Do not invent an environment variable or claim provisioning enables events.
- `core/game/archives.py` uses `MemoryArchiveStore`, not a DynamoDB repository.
  No archive table or guessed pagination index is included. Durable conditional
  writes, paging and atomic completion/result/archive publication or an
  idempotent outbox require a separately reviewed application/storage design.
- Tables use on-demand capacity, encryption at rest (AWS-managed DynamoDB
  encryption, no customer-managed key), PITR and deletion protection. No TTL is
  enabled: there is no approved expiry contract, and auth expiry must remain
  enforced by application checks, not asynchronous DynamoDB deletion.
- Both queues use SQS-managed encryption, not a customer-managed KMS key.
  `maxReceiveCount=5` redrives the tick queue to its own DLQ; the DLQ accepts
  redrive only from the same-account/region fixed tick queue ARN. This does
  not grant a sender/consumer permissions. There is no queue access policy.
- All seven resources have `DeletionPolicy: Retain` and
  `UpdateReplacePolicy: Retain`, including queues and secret. Retention is not
  indefinite message durability: SQS messages still expire. No bucket is
  necessary for this inline template; artifact storage is deferred until the
  packaging/release design is reviewed. Any later artifact bucket must use
  an account+region-qualified staging name, encryption, versioning, public
  access blocks and a TLS-only policy.

### Tick scheduling and future worker budget

`lambdas/api/game/game_tick.py` consumes room `NewImage` records and SQS
messages with `roomId`, `revision`, `kind`, `dueAt`. It ignores stream deletes,
uses persisted deadlines, rounds delays up to whole seconds and caps each
per-message delay at 900 seconds. Queue default delay is zero; **do not use a
FIFO queue**, which does not support these per-message delays.

The four-day source and fourteen-day DLQ retention leave a larger diagnostic
window in the DLQ. For a standard queue the original enqueue timestamp
continues to govern expiry after redrive; time spent in the source reduces the
remaining DLQ lifetime.

Both standard queues deliberately omit `FifoQueue` and all other FIFO-only
properties. The first execution failed on `TickDeadLetterQueue` with
`Unknown Attribute FifoQueue` when the template explicitly sent `false`.
[AWS documents omission as the standard-queue default](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-sqs-queue.html).
Do not set it to `true`: the worker needs standard-queue per-message delays.
Schema validation alone did not catch this live provider/API failure.

### Recovering the first execution failure

The initial execution entered rollback after the SQS failure. Because every
resource is retained, cancelled creations can leave real named resources
outside the final stack's management. `DELETE_SKIPPED` is not proof of deletion,
and a missing physical ID in stack events is not proof that creation never
reached the service.

Wait for rollback to reach a terminal state, then inventory metadata for all
four fixed table names, both fixed queue names and `bridge-staging-jwt`; never
read signing material or application items. Do not rerun `CREATE` against a
`ROLLBACK_COMPLETE` stack or assume a fresh stack can recreate retained names.
Do not regenerate the secret, remove deletion protection, broaden the execution
role, or delete resources to make the retry pass.

Recovery requires a separately approved choice: preserve/import retained
resources with an appropriate import-only template and reviewed identifiers,
or explicitly approve targeted cleanup of the newly created staging resources.
Resource import and creation of missing resources are separate operations;
the existing plan workflow accepts only CREATE/UPDATE and must not be used as
an import or cleanup workaround. No recovery mutation is authorized by this
source fix. Leave the existing public resources untouched.

The subsequent metadata inventory found the original stack `DELETE_COMPLETE`,
all four table names and both queue names absent, and `bridge-staging-jwt`
still present without scheduled deletion. No value was read. A fresh CREATE
with all seven names would therefore collide with that secret. This is only
a point-in-time inventory: recheck before recovery and obtain explicit approval
for importing the existing secret or any targeted cleanup. The assistant did
not delete the stack, tables, queues or secret.

The selected recovery is now [preserve and import the existing secret](staging-secret-import.md).
The earlier cleanup approval was withdrawn; do not delete, rotate or regenerate
it. Import only the secret into the new stack, wait for `IMPORT_COMPLETE`, then
use an UPDATE preview to add the six missing resources. The updated planning
script rejects signing-secret changes by default. A separate explicit opt-in
allows only fully verified static, non-replacing tags-only metadata updates;
secret property/value changes remain blocked. See the import runbook for the
post-import stack-tag mismatch and precise review conditions.

The 360-second source visibility is a **provisional integration limit**, not a
measured worker timeout. Before connecting a consumer, test native DDS and
select a worker timeout **at most 60 seconds with a zero batch window**, so
visibility is at least six times the timeout. If timeout or batch window grows,
review visibility using `visibility >= 6 * timeout + batch_window`; if the
measured work does not fit, change this foundation contract in review first.
The handler does not prescribe retention, retry count or visibility itself.

Future stream and SQS mappings must both enable `ReportBatchItemFailures`.
Decide stream start position, filters for relevant INSERT/MODIFY images,
bounded retries, record age, failure destination, batch size and concurrency.
DynamoDB Streams retains records for only 24 hours: this foundation creates
the stream but **no consumer**, so events can age out. Do not put active games
into the foundation expecting later consumer activation to recover all ticks.
Design a pending-room reconciliation/recovery procedure first.

### Future environment inputs (not set by this stack)

| Application setting | Future isolated value / source |
| --- | --- |
| `ROOM_TABLE` | `RoomTableName` output |
| `USER_TABLE` | `UserTableName` output |
| `WEBSOCKET_CONNECTIONS_TABLE` | `ConnectionsTableName` output |
| `GAME_TICK_QUEUE_URL` | `GameTickQueueUrl` output |
| `JWT_SECRET_ID` | Literal `bridge-staging-jwt`, never the signing value |
| `AWS_DEFAULT_REGION` | Explicit `us-west-2` until secret-helper region fallback is repaired |
| `AWS_REGION` | Lambda-provided reserved variable; do not override it |
| `WEBSOCKET_ENDPOINT` | Future isolated management endpoint; not available yet |
| `WS_ALLOWED_ORIGINS` | Future exact approved origins; no wildcard/public-site fallback |

`shared/security/aws_secrets.py` currently ignores Lambda's `AWS_REGION` in its
fallback and otherwise defaults to another region. `jwt_utils.py` and the
secret helper recognize JSON `jwt_secret`; a new generated secret is compatible
without copying signing material. Do not expose a secret dynamic reference,
secret value, or secret identifier through stack outputs. The fixed secret
name is intentionally documented here rather than output. Rotation is not
configured; later rotation must address cached keys and existing token lifetimes.

## Offline validation

Run from the repository root. Tests import no application code, start no servers,
call no AWS SDK/CLI and do not need credentials. No existing CloudFormation
validator was found on PATH or in the application venv during implementation,
so `requirements-infrastructure.txt` adds only isolated validation tooling.
Its direct versions are pinned; it is not an application dependency manifest
or a fully locked transitive dependency closure.

Use an approved session directory under the working home (not `/tmp`), separate
from the application venv. The following are **manual offline commands**; replace
the session directory with your own existing Copilot session's `files` directory:

```bash
REPO="$PWD"
SESSION_FILES="$HOME/.copilot/session-state/<session-id>/files"
python3 -m venv "$SESSION_FILES/.venv-infrastructure"
TMPDIR="$SESSION_FILES" PIP_CACHE_DIR="$SESSION_FILES/.pip-cache-infrastructure" \
  "$SESSION_FILES/.venv-infrastructure/bin/python" -m pip install \
  -r "$REPO/requirements-infrastructure.txt"
PYTHONDONTWRITEBYTECODE=1 "$SESSION_FILES/.venv-infrastructure/bin/python" \
  .github/scripts/test_staging_foundation.py
AWS_EC2_METADATA_DISABLED=true "$SESSION_FILES/.venv-infrastructure/bin/cfn-lint" \
  --region us-west-2 --template deployment/staging-foundation.yaml
git diff --check
```

The eight offline tests assert the backend access guard's agreement with the
foundation region, exact allowlisted inventory, names, live
composite keys/GSI, stream, queue settings/redrive relation, data protection and
generated-secret/output exclusions. No S3 resource is allowlisted. `cfn-lint`
validates real CloudFormation resource schemas and intrinsic references.
Neither establishes IAM authorization, service quotas, name availability,
real transaction/consumer behavior or a successful cloud deployment.

## Operator runbook: review first, cloud work only after separate approval

**Nothing below was executed as part of this source-only work.** The current
workstation's ambient CLI identity is account-root and is forbidden for this
handoff. Do not use it even for convenience. Do not run legacy deployment
scripts, `sam deploy`, `aws cloudformation deploy`, GitHub publication, artifact
uploads or automatic stack creation. Persistent local servers must stay stopped.

1. Keep the pause until a human confirms account, region, exact seven names,
   expected costs, scoped identity, execution role and intended cloud mutations.
   Both OIDC checks succeeding is insufficient approval. Review source and
   offline results on the main-based branch; parent handles CI/publication.
2. Obtain an explicitly approved short-lived **non-root** operator profile.
   A separately reviewed CloudFormation execution role must permit only this
   staging scope (including table PITR/deletion protection, queues, and secret
   generation). This template creates no IAM role/policy and requires **no IAM
   capabilities acknowledgement**. Do not add `CAPABILITY_IAM` to bypass a
   surprise change. Bound `iam:PassRole` to that exact execution role/service.
3. Before any future cloud mutation, manually run the following using the
   approved profile, never ambient credentials:

   ```bash
   aws sts get-caller-identity --profile <approved-non-root-profile> \
     --region us-west-2 --no-cli-pager
   aws configure get region --profile <approved-non-root-profile>
   ```

   Require account `851725597758`, an approved role/session ARN, and the intended
   region; stop on `:root`, wrong account, unexpected principal, credential or
   endpoint overrides, or unapproved region. STS output does not prove service
   region, so retain explicit `--region us-west-2` on **every** cloud command.
   Resolve any profile/default-region discrepancy before proceeding.
4. With separate permission for metadata reads, validate in the target service:

   ```bash
   aws cloudformation validate-template --profile <approved-non-root-profile> \
     --region us-west-2 --template-body file://deployment/staging-foundation.yaml \
     --no-cli-pager
   ```

   Confirm no existing stack/resource already occupies any fixed name via
   approved **metadata-only** reads. Do not inspect secret values or any
   application items. If a collision or retained resource exists, stop; do not
   delete/adopt/import it or rename around it without a separate plan.
5. After explicit approval to create a **preview change set**, an operator may
   manually prepare the following **future mutation**, replacing placeholders
   with separately approved values. This is not an executable deployment script
   or authorization to run it now:

   ```bash
   aws cloudformation create-change-set --profile <approved-non-root-profile> \
     --region us-west-2 --stack-name bridge-staging-foundation \
     --change-set-name <unique-reviewed-preview-name> --change-set-type CREATE \
     --template-body file://deployment/staging-foundation.yaml \
     --role-arn <exact-approved-cloudformation-execution-role-arn> --no-cli-pager
   ```

   No artifact bucket or IAM capabilities flag is needed. This creates a preview
   and may leave an initial stack in `REVIEW_IN_PROGRESS`, but does not execute
   the seven resource creations. Do not substitute `deploy`/`create-stack`.
   Record template digest, source commit, role ARN, change set ID and approval.
6. Inspect the change set with replacement/property details, execution role and
   resource scope, for example using this metadata-only command after the
   preview exists:

   ```bash
   aws cloudformation describe-change-set --profile <approved-non-root-profile> \
     --region us-west-2 --stack-name bridge-staging-foundation \
     --change-set-name <reviewed-change-set-id> --include-property-values \
     --no-cli-pager
   ```

   Expect exactly **seven Adds**, no Modify/Remove/import,
   IAM, custom resources, macros, functions, mappings, public policies or
   existing identifiers. Inspect all names, key schemas, GSI, stream,
   encryption, PITR, deletion protection, generated secret and retention/redrive
   settings against the table above. Service validation/change sets do not
   guarantee resource creation succeeds. **Stop for separate apply approval.**
7. Only the approved non-root operator may later execute that exact change set.
   Then inspect stack events/status, non-secret outputs and service metadata;
   verify tables ACTIVE, composite keys/index, room-only NEW_IMAGE stream,
   PITR/encryption/deletion protection, queue attributes and secret
   **metadata only**. Never retrieve/log secret values for acceptance.
   Record failed creation or rollback and diagnose before another mutation.
   Do not send test messages, insert user/game data or attach consumers yet.

### Rollback, retention and costs

- Stop on any update that replaces/removes persistent resources. Fixed names
  make replacement awkward; Retain does not make replacement safe or guarantee
  CloudFormation can recreate the same name.
- Initial failure/rollback can leave retained resources and charges. Stack
  deletion also leaves tables, queues and secret, and deletion protection blocks
  direct table deletion. Inventory retained resources before retrying. Do not
  issue automated cleanup, disable protection, purge queues, schedule secret
  deletion or delete the stack as a diagnostic step.
- Teardown needs separate approval, a staged-data/export and recovery decision,
  explicit scoped cleanup and acceptance of irreversible message/secret loss.
  PITR is not cross-region backup; restoration creates another table and needs
  a separately reviewed integration/name plan. Removing this source does not
  remove retained cloud resources.
- On-demand is not free or a spending cap. Budget table/GSI read/write and
  storage charges, transactional writes, scan amplification, PITR storage,
  stream reads, SQS requests/payloads, and Secrets Manager per-secret/API
  charges (commonly around $0.40/secret-month before API calls; verify current
  regional pricing). Empty PITR-protected tables and a retained secret may
  still incur charges. There is no CMK, artifact bucket or paid function
  created here. No numeric total is defensible without traffic/data volume.
- DynamoDB items (including duplicate-event boards/results) must fit 400 KiB;
  transactions have 100-action/4 MiB limits. Current duplicate events are
  bounded at 2–4 tables/1–8 boards in code, not by this template. Measure actual
  item/transaction size and concurrency. Check service quotas and budgets
  before enabling any traffic.

## Remaining release blockers (separate work)

1. Durable archive repository/pagination and transactional/outbox publication;
   no process-memory state or lock may be the source of cross-Lambda truth.
2. Explicit duplicate adapter initialization, table configuration, scoped
   transaction permissions, cross-invocation/cold-start conflict recovery and
   membership/result/embargo acceptance. Provisioning alone enables none of it.
3. Measured Lambda-compatible Python/native DDS build, architecture/memory/
   timeout budgets and immutable artifacts. No archives/native code changed here.
4. Reviewed runtime/deployment/CloudFormation roles, narrow secret/table/index/
   stream/SQS and WebSocket-management permissions. Existing OIDC identity tests
   do not establish those grants; no policies/roles are supplied here.
5. Complete auth/presence/invitation/archive/agreement/practice/claim/event route
   manifest and API integrations/invocation permissions, guest and logout paths,
   cookie propagation, exact origins/signed socket subprotocols, explicit secret
   region, session revocation decision and non-cacheable API responses.
6. Worker functions/mappings, retries/failure destination, timeout visibility
   agreement, reconciliation/redrive runbook and alarms for stream age, queue
   age/DLQ, errors and throttling. DLQ redrive must be authorized and deliberate:
   pause consumers as appropriate, fix the cause, validate revision/schema and
   replay safety, use a small bounded staging replay, observe, then resume.
   Do not bulk replay expired/stale game actions or assume queue retention is
   recovery. These controls are **not implemented** by this foundation.
7. Isolated frontend/artifact hosting, production `/api` mapping and immutable
   releases/rollback; no existing public route/origin/DNS change is authorized.
8. Real AWS multi-client auth/gameplay/tick/claim/duplicate/replay-embargo tests,
   concurrent CAS/transactions and crash recovery across Lambda instances.
   Offline validation is necessary but cannot substitute for cloud acceptance
   or the separate production promotion approval.
