# Isolated staging application deployment

The foundation is deployed and verified `CREATE_COMPLETE`. Continue only in
account **851725597758**, application region **us-west-2**. The current local
CLI is account root: the assistant must not apply these stacks, upload AWS
artifacts, or change IAM with that identity. Operator steps below require an
authorized **non-root** console/federated session.

The existing public domain, distribution `E1HX0HXMLYUF2Z`, bucket
`nextlevelbridgeassetdistributionbucket`, and API IDs `e2jrh99dbc` /
`ipp77av3oi` are never deployment targets. No DNS or public-site configuration
changes are included.

## Deployment boundaries

| Phase | Authority and contents |
| --- | --- |
| Existing `bridge-staging-foundation` | Four isolated tables, standard tick queue/DLQ, new independent signing secret; leave unchanged |
| New `bridge-staging-platform` | Non-root operator bootstraps private versioned web/artifact buckets, generated-domain CloudFront, bare REST/WebSocket APIs, durable archive table, separate stream-failure queue and reviewed named IAM |
| New `bridge-staging-application` | Main-only GitHub OIDC publishes a target-validated immutable ZIP and prepares a change set; a separate human executes functions, log groups, HTTP/WS routes and stages |
| New `bridge-staging-scheduling` | Non-root operator explicitly enables two narrowly specified stream/queue mappings after application deployment |
| Frontend publication | Main-only frontend OIDC verifies the deployed backend commit/origin, then uploads immutable assets before the no-cache entry document |

Platform is a privileged, reviewed bootstrap, not a routine CI release.
Its named IAM acknowledgment is required. The application CloudFormation role
cannot create/edit IAM, read signing values, change foundation storage, or
execute change sets. Its PassRole grant names only the three staging Lambda
roles. Runtime data access and secret reads belong only to Lambda service roles.
The backend GitHub role cannot execute its prepared change set.

Scheduling remains a separate operator stack because new event-source mapping
IDs are not known in advance. This avoids granting the routine application
executor wildcard tagging/control over unrelated existing mappings.

## 1. Operator platform bootstrap

1. Confirm the console account, region and **non-root identity**. Open the
   successful foundation stack and copy its `RoomStreamArn` output.
2. Review [`deployment/staging-platform.yaml`](../deployment/staging-platform.yaml)
   from merged `main`. Create stack **bridge-staging-platform** with that
   template, supplying the exact stream ARN. Console template upload may store
   the template in a CloudFormation-managed S3 bucket; authorize that handling.
3. Add stack tags `Application=Bridge`, `Environment=staging`. Review the named
   IAM capability. Use your approved operator authority; **do not select
   BridgeStagingFoundationExecution**, which intentionally cannot create this
   platform or IAM. Do not grant the foundation role broader permissions.
4. Review the change set, then execute only through the approved non-root
   session. Wait for `CREATE_COMPLETE`. Stop on any failure; retained names must
   be inventoried, not deleted or blindly retried.

The platform creates `bridge-staging-board-archives` with `roomId` String and
`boardNumber` Number keys, PITR, encryption, deletion protection and no TTL.
It also creates `bridge-staging-room-stream-failures`, separate from the robot
queue DLQ because stream failure envelopes are not robot tick messages.

Its new frontend policy attaches to the existing `GitHubBridgeAppStaging` role,
granting only the **new** web bucket/distribution/cache-policy targets and
read-only backend-stack provenance. Existing public resources receive no grant.
Other new roles are named `GitHubBridgeApplicationPlanStaging`,
`BridgeStagingApplicationExecution`, `BridgeStagingApplicationRuntime`,
`BridgeStagingTickRuntime`, and `BridgeStagingTickDispatchRuntime`.

The generated CloudFront URL is the staging origin. `/api` and `/api/*` go to
the new regional REST API at `/staging`, with all viewer headers except Host,
all cookies/query strings, and zero cache TTLs. Error responses retain their
status/body and have zero error-cache TTL. Only static SPA navigation is
rewritten to `index.html`; API failures never become successful HTML.
At this phase APIs have no deployed application stages and the web bucket has
no application entry document. Those endpoints are not ready to play yet.

### Existing shortened stack name

The current operator-created platform stack is **bridge-staging-platfor**
(missing the final `m`). Keep it; do not delete, recreate or import its retained
resources. The template now binds planning-role read access to `AWS::StackId`,
so it authorizes the actual owning stack rather than a hard-coded name.

After its initial `CREATE_COMPLETE`, update that same stack using the latest
merged platform template. Preserve parameters and tags. Review the change set:
only `ApplicationPlanRole` should be modified, without replacement, to correct
its inline `DescribeStacks` resource. Do not execute unexpected resource changes.
Use approved non-root authority and acknowledge named IAM as before.

Set backend staging variable `STAGING_PLATFORM_STACK=bridge-staging-platfor`.
The workflow accepts this known existing name or the canonical
`bridge-staging-platform` default; resource names and public-site exclusions
remain unchanged.

## 2. Configure GitHub from verified platform outputs

Keep existing account/region/foundation variables. Add backend staging variable:

| Backend variable | Platform output |
| --- | --- |
| `AWS_APPLICATION_PLAN_ROLE_ARN` | `ApplicationPlanRoleArn` |
| `STAGING_PLATFORM_STACK` | `bridge-staging-platfor` for the current existing stack; otherwise defaults to `bridge-staging-platform` |

Frontend staging variables:

| Frontend variable | Source |
| --- | --- |
| `STAGING_WEB_BUCKET` | `WebBucketName` |
| `STAGING_DISTRIBUTION_ID` | `DistributionId` |
| `STAGING_ORIGIN` | `StagingOrigin` |
| `STAGING_WEBSOCKET_URL` | `WebSocketEndpoint` |

The existing frontend `AWS_STAGING_ROLE_ARN` still names
`GitHubBridgeAppStaging`; do not replace it with a backend/foundation role.
There are no new GitHub secrets or long-lived access keys. These variables
contain public resource identifiers only.

## 3. Package and plan the application

Run **Package and plan staging application (NO execution)** on backend `main`,
choosing **CREATE** for the first application stack. Later code releases use
UPDATE on the same stack. Never rerun an older failed job to obtain new source.

The credential-free first job builds inside a pinned Python 3.12 AL2023
x86_64 environment, imports every handler and solves a native DDS fixture with
network access denied. It emits a receipt binding native/library/dependency/
route hashes to the deterministic ZIP. A source-only CI artifact is not accepted
as a Lambda deployment package.

Only after verifying the receipt does the OIDC job check its exact assumed
session, read the two completed foundation/platform stacks, verify bucket
versioning/tags and upload new objects with conditional non-overwrite writes.
The code/template keys include commit, digest and run attempt; the application
template references the exact S3 **object version**. The workflow records
source/artifact/template digests and creates a preview only.

Review the change set before separate non-root execution. The initial template
contains 22 functions, 6 HTTP routes plus preflights, 30 WebSocket routes, and
their logs/permissions/stages. No IAM, foundation, or scheduling resource is
part of this application stack. HTTP uses Lambda proxy v1 to preserve cookies.
WebSocket application responses remain one-way because handlers explicitly
deliver replies through the management API.

For a future initial CREATE, choose **Preserve successfully provisioned
resources** (disable rollback) when executing. If creation fails, preserve that
managed `CREATE_FAILED` state for diagnosis/retry rather than rolling back into
orphaned retained resources. Do not retry until the cause is corrected.

All runtime tables, exact origin, management endpoint and queue are configured.
Staging uses `ENVIRONMENT=production` solely for the existing Secure-cookie
contract; it still has independent staging data and signing material.
AWS supplies reserved region variables; the secret helper now honors
`AWS_REGION` without attempting to override reserved Lambda environment keys.
Completed room state, archive and duplicate result commit atomically.

During later releases only retained historical API deployment snapshots may
leave stack management. Other removals and replacements require separate
review and are rejected by the plan workflow. This staging pipeline does not
establish atomic multi-function promotion or production schema migrations.

### Failed first application CREATE: REST stage tagging

The first application execution failed because API Gateway authorizes REST
stage tagging through `/tags/<URL-encoded-resource-ARN>`, not through the
existing `/restapis/<id>/*` statement. The corrected platform template grants
only GET/PUT/DELETE on that exact REST API's `staging` tag endpoint. WebSocket
tagging uses the existing API-specific management authorization.
See the [REST tagging API](https://docs.aws.amazon.com/apigateway/latest/api/API_TagResource.html)
and [IAM Tags resource](https://docs.aws.amazon.com/service-authorization/latest/reference/list_apigateway.html#list_apigateway-resource-Tags).

Update the existing **bridge-staging-platfor** stack from the latest merged
template using authorized non-root authority. Expect only
`ApplicationExecutionRole` to change, without replacement. This does not
change IAM permissions on public APIs, foundation resources or signing values.

The application stack is now `ROLLBACK_COMPLETE` with 130 resource entries
marked `DELETE_SKIPPED`. Do not delete the stack, rerun CREATE, or assume the
permission fix alone recovers it. Retained physical resources must be
inventoried and an explicit recovery plan reviewed before another release.

## 4. Enable scheduling through the operator stack

After application `CREATE_COMPLETE`, create **bridge-staging-scheduling** from
[`deployment/staging-scheduling.yaml`](../deployment/staging-scheduling.yaml),
using the application `TickDispatchFunctionArn` / `TickWorkerFunctionArn` outputs
and foundation `RoomStreamArn`. Use approved non-root operator authority, not
the restricted application/foundation execution roles.

`ConsumersEnabled` defaults to **false**. Explicitly choose **true** only after
the verified application artifact is deployed and you approve background work.
The room stream starts at LATEST; do not create active games before this step.
It filters INSERT/MODIFY, reports partial failures, bisects failures, bounds
retries/age, and sends exhausted batches to the separate stream-failure queue.
The standard SQS worker processes one message at a time, reports partial
failures, has zero batch window and maximum concurrency two. Its 60-second
timeout fits the existing 360-second visibility. The worker may send delayed
follow-up ticks to the same queue.

Inspect both mapping states and failure queues before publishing the frontend.
If paused later, in-flight messages and expired stream records require explicit
reconciliation; re-enabling is not proof every missed tick was recovered.

## 5. Publish frontend, then run real AWS acceptance

In the frontend repository, run its new manual staging publication workflow on
`main`, providing the **deployed backend SourceCommit output**. Publication
requires healthy application-stack provenance and exact matching staging origin.
See the frontend `docs/staging-frontend.md` for publication and rollback.

Verify guest/account auth and refresh/logout cookies; two-browser joining,
dummy/turn enforcement, bidding, full play/scoring, delayed computer tricks,
reconnect/claims, replay embargo and duplicate events across cold starts.
Confirm archive persistence and conditional conflicts in AWS, native solver
execution, DLQ/stream failures, and no credentials/tokens in logs. Source tests
and target-container receipts do not substitute for this live acceptance.

Do not point the public custom domain at staging or claim production readiness
until those gates and separate promotion approval are complete.
