# Review-only staging foundation authority

**Source review only. Deployment remains paused.** These JSON contracts have not
been applied to IAM. Passing offline tests is not evidence of live authorization,
role existence, successful planning, or successful deployment. This work performed
only public documentation research and permitted read-only CloudFormation
`DescribeType` schema-metadata reads; no IAM, stack, change-set, resource, secret
value, GitHub, or deployment mutation was performed.

Read [staging-foundation.md](staging-foundation.md) for the exact resource
contracts, costs, retention, acceptance gates, and application release blockers.
That earlier runbook's execution-role placeholders are specified here; its
deployment pause and separate apply approval still apply.

## Two new roles; never extend the identity-check roles

Target account **851725597758**, application region **us-west-2**, stack
**bridge-staging-foundation**. Both role paths must be `/` (no additional path).

| New role | Trust source | Sole inline permissions source |
| --- | --- | --- |
| `GitHubBridgeFoundationPlanStaging` | `deployment/foundation-plan-trust.json` | `deployment/foundation-plan-policy.json` |
| `BridgeStagingFoundationExecution` | `deployment/foundation-execution-trust.json` | `deployment/foundation-execution-policy.json` |

Leave `GitHubBridgeAppStaging` and `GitHubNextLevelBridgeAPIStaging` unchanged:
they are identity-only roles with no attached or inline permissions.
Do not attach these new policies to either role. No application role, runtime
policy, artifact bucket, deployment identity, or resource ownership is added by
these source files.

### Planning role boundary

The only trusted federated principal is
`arn:aws:iam::851725597758:oidc-provider/token.actions.githubusercontent.com`,
with exact `StringEquals` audience `sts.amazonaws.com` and subject
`repo:jmtelgen/NextLevelBridgeAPI:environment:staging`.
This trusts the **staging environment, not one particular workflow or branch**.
Protect that GitHub environment with approved deployment branches and required
reviewers before enabling it; review workflow changes as authorization changes.
Do not widen to repository/branch wildcards or the frontend repository.

The parent ran AWS Access Analyzer **ValidatePolicy only**, not IAM application:
the planning permissions policy returned **zero findings**. Validation of the
exact OIDC trust returned the generic `CONFIRM_AUDIENCE_CLAIM_TYPE` suggestion
and `SPECIFIC_GITHUB_REPO_AND_BRANCH_RECOMMENDED` warning. The actual trust
already uses plain `StringEquals` (no set qualifier), exact audience
`sts.amazonaws.com`, and the exact staging environment subject above, with no
wildcard. Do not weaken that trust, replace the known-working environment
subject, or invent an unsupported `:ref` condition to silence these findings.
With an environment-based subject, **main is not an IAM subject restriction**:
it is enforced through the GitHub staging environment's approved deployment
branch rule plus the workflow's main-only job condition and the script's
pre-credential `refs/heads/main` check. Keep all those controls in place.
The identical environment-subject trust pattern succeeded for the existing
identity check on main; that does not prove live authorization for these new
roles. Access Analyzer findings are source validation, not an OIDC assumption
test or successful deployment. The parent will separately validate the final
execution policy/trust after the scoped provider-read change.

The permissions allow only:

1. `cloudformation:ValidateTemplate` in `us-west-2`. AWS defines no resource type
   for this action, so `Resource: "*"` is necessary. A `Null` condition rejects a
   supplied `TemplateUrl`.
2. `cloudformation:CreateChangeSet` on
   `arn:aws:cloudformation:us-west-2:851725597758:stack/bridge-staging-foundation/*`,
   requiring the exact execution `RoleArn`, requested region, no `TemplateUrl`,
   and a change-set name matching `bridge-staging-foundation-?*-?*`. It requires
   both exact request tags `Application=Bridge`, `Environment=staging` and
   prohibits additional tag keys.
3. `cloudformation:DescribeChangeSet` on the **same stack ARN**, including AWS CLI
   `change-set-create-complete` waiter calls, restricted by requested region
   only. Do not copy the creation-only role/tag requirements or the name
   condition into this read statement. AWS's reference lists ChangeSetName
   support, but the live ARN-based waiter failed authorization with both the
   name and ARN patterns configured. Stack and region scope is the supported
   recovery here; this does not grant reads of other stacks or execution rights.
   Specify the stack name explicitly for describe/wait calls.
4. Dependent `cloudformation:TagResource` and `cloudformation:UntagResource`
   authorizations on only the fixed stack and prefixed change-set ARNs. Both
   require requested region and `cloudformation:CreateAction = CreateChangeSet`;
   they cannot be used as standalone tagging APIs or while executing a change
   set. TagResource requires both exact tag values and only their keys.
   UntagResource permits only those two keys with a nonempty tag-key context.
   It has no request-tag-value or RoleArn condition: those are not supported
   for that action. AWS's current API authorization map lists both dependencies,
   including tag reconciliation on an UPDATE preview. Removing other existing
   tag keys fails closed and needs separate review, not expanded scope.
5. `iam:PassRole` on only
   `arn:aws:iam::851725597758:role/BridgeStagingFoundationExecution`, with
   `iam:PassedToService` exactly `cloudformation.amazonaws.com`. Do not add a
   requested-region restriction to this IAM permission: IAM is a global service;
   region is enforced on CloudFormation and downstream regional service calls.

AWS's action-specific authorization reference lists **stack**, not **changeset**,
as the resource type for both CreateChangeSet and DescribeChangeSet. Putting only
a change-set ARN in `Resource` would not authorize those calls. Change-set ARN
patterns are retained only for the tagging dependency, not describe access.
`ValidateTemplate` does not accept a role parameter, so it has no RoleArn condition.

### Recovering the first preview's describe denial

[Run 40429724861](https://github.com/jmtelgen/NextLevelBridgeAPI/actions/runs/40429724861)
created `bridge-staging-foundation-40429724861-1`, but its waiter and preview
were denied by the earlier name-conditioned read statement. A metadata-only
inspection confirmed the change set is `CREATE_COMPLETE` and `AVAILABLE`, with
exactly the seven expected additions; it has not been executed.

Using an authorized non-root administrator, open IAM role
`GitHubBridgeFoundationPlanStaging`, edit inline policy
`GitHubBridgeFoundationPlanStagingPolicy`, and replace its DescribeChangeSet
statement with the corrected statement in `deployment/foundation-plan-policy.json`.
Keep the exact stack resource and `us-west-2` restriction. Do not attach a
managed administrator policy, add ExecuteChangeSet, or alter either role's trust.
Merging a source fix does not update an already attached IAM policy.

For that original preview failure, rerunning `CREATE` was appropriate while
the stack was only a review placeholder. That retry subsequently succeeded.
It is not the current recovery for the later SQS execution failure: the failed
stack was deleted and its signing secret remains. Follow the
[secret-preserving import runbook](staging-secret-import.md) instead. After
`IMPORT_COMPLETE`, use `UPDATE`, expecting six additions and no secret changes.
The planning script rejects any UPDATE change to `JwtSigningSecret`; do not
remove that guard or broaden secret permissions to force an update through.

The workflow must construct the exact name
`bridge-staging-foundation-<GitHub run ID>-<attempt>` using numeric GitHub
metadata. IAM glob syntax cannot enforce numeric fields or prove which run made
the request; the glob only enforces the name envelope. The workflow must choose
`CREATE` or `UPDATE` explicitly, use the reviewed inline template, and never
use imports, previous-template shortcuts, nested stacks, drift-aware modes,
macros, capabilities, resource discovery, additional tags, or automatic execution.
`Null TemplateUrl` blocks URL input; it does **not** authenticate template content
or prohibit `UsePreviousTemplate` by itself. Template digest/source review and
workflow controls remain necessary. No unsupported condition key for
ChangeSetType or a template digest has been invented.

No DescribeStacks, DescribeStackEvents, ListStacks, GetTemplate or DeleteChangeSet
is granted: the bounded workflow does not need them. Dependent tagging grants
are not permission to execute a change set or change resource configuration.
If the actual tagged request requires an additional permission, **stop and
review evidence**, rather than attaching a broad fallback. No cleanup is
automatic, including for no-change/failed previews.
`sts:GetCallerIdentity` requires no identity-policy allow.

**Plan-only is not zero mutations.** CreateChangeSet creates persistent metadata
and, for `CREATE`, can create an empty `REVIEW_IN_PROGRESS` stack. It cannot
provision the seven foundation resources without separately privileged execution.
This role cannot ExecuteChangeSet, CreateStack, UpdateStack, DeleteStack, assume
the execution role directly, or call any foundation resource/data API.
These are narrowly scoped **allow policies**, not permission boundaries or
explicit-deny guardrails: attaching other grants can invalidate that claim.

### Execution role boundary and provider evidence

The role trusts only the documented CloudFormation service principal,
`cloudformation.amazonaws.com`, via `sts:AssumeRole`. No `SourceAccount`,
`SourceArn`, external ID, or guessed stack restriction is added to the trust:
the cited CloudFormation service-role contract does not establish that those
source keys are supplied on this AssumeRole path. An unsupported required
condition could silently make the role unusable. Consequently the trust itself
does not bind the role to one stack. Control **all** identities that can pass
this role and all stack-operation permissions in the account.

The execution policy scopes the current seven fixed resource names, not an
arbitrary `bridge-staging-*` namespace:

| Scope | Allowed operations / reason |
| --- | --- |
| `bridge-staging-rooms`, `bridge-staging-users`, `bridge-staging-connections`, `bridge-staging-duplicate-events` table ARNs | CreateTable, UpdateTable, UpdateContinuousBackups; DescribeTable, DescribeContinuousBackups, DescribeContributorInsights, DescribeKinesisStreamingDestination, DescribeTimeToLive, GetResourcePolicy, ListTagsOfResource, TagResource |
| Only the users table's `username-email-index` ARN | DescribeContributorInsights metadata only; not Query/Scan or index writes |
| `bridge-staging-game-tick` and `bridge-staging-game-tick-dlq` queue ARNs | CreateQueue, GetQueueUrl, GetQueueAttributes, SetQueueAttributes, ListQueueTags, TagQueue |
| `bridge-staging-jwt-??????` secret ARN | CreateSecret in a separate statement requiring `secretsmanager:Name` exactly `bridge-staging-jwt`; DescribeSecret and TagResource without that create-only condition |
| Same exact `bridge-staging-jwt-??????` secret ARN, execution role only | GetSecretValue in a separate statement, required by the registered CloudFormation provider's read handler; never granted to the GitHub planner or a human |
| `Resource: "*"` in `us-west-2` only | GetRandomPassword, which has no resource-level authorization; generates new random material, never reads a stored secret |

Every execution statement requires `aws:RequestedRegion = us-west-2`; every
resource ARN fixes the account and region. Secrets Manager appends six random
characters to the secret ARN; six `?` match exactly that suffix, unlike a broad
`bridge-staging-jwt-*` prefix. CreateSecret necessarily writes the **new generated**
secret as part of provisioning; this is not runtime data access. There is no
PutSecretValue, UpdateSecret, rotation, replication, resource policy write, or
access to existing application signing material. The **only stored-value read
exception** is the CloudFormation provider's GetSecretValue on the exact new
staging secret, verified below. It is not a permission for a tool, CLI, GitHub
workflow, human, or application to retrieve values. The execution role's sole
trusted principal remains `cloudformation.amazonaws.com`; no GitHub/human
principal can assume it directly, and the planner has no secret API permission.

The action selection was checked against official service authorization
references and the current `us-west-2` public CloudFormation resource provider
schemas, obtained with these **read-only metadata** API requests:

```bash
aws cloudformation describe-type --type RESOURCE --type-name AWS::DynamoDB::Table \
  --region us-west-2 --query Schema --output text --no-cli-pager
aws cloudformation describe-type --type RESOURCE --type-name AWS::SQS::Queue \
  --region us-west-2 --query Schema --output text --no-cli-pager
aws cloudformation describe-type --type RESOURCE --type-name AWS::SecretsManager::Secret \
  --region us-west-2 --query Schema --output text --no-cli-pager
```

These are public provider schemas, not stack/resource or secret-value reads.
Future operators should use an explicitly authorized non-root read-only session.
The offline tests intentionally do not rerun these calls or require AWS credentials.

- DynamoDB's create/update schemas list a large **superset** for optional imports,
  replicas, custom keys, Kinesis integration, policies, TTL and data operations.
  Do not blindly copy it. Current properties need table creation, PITR management
  and table updates; schema read metadata includes the disabled/absent TTL,
  Contributor Insights, Kinesis and policy fields. The policy includes only these
  scoped metadata reads and table-management operations, plus creation tags.
  CreateTable/UpdateTable manage the GSI and room stream through the table ARN;
  DescribeTable returns stream metadata/StreamArn. No stream wildcard,
  DescribeStream, ListStreams, GetRecords or GetShardIterator is needed.
- The SQS schema's create/read permissions are covered, and SetQueueAttributes
  supports bounded queue configuration updates. No ListQueues, DeleteQueue,
  PurgeQueue, message movement, SendMessage, ReceiveMessage or DeleteMessage.
- The secret create schema lists DescribeSecret, GetRandomPassword, CreateSecret,
  TagResource and optional replication. Replication is excluded. **The registered
  read handler explicitly requires GetSecretValue**, so the execution role now
  supplies that single, exact-secret permission rather than knowingly omitting a
  declared provider dependency. See the verified handler evidence below.
  UpdateSecret remains omitted because it can write a new signing value, not
  just metadata: the current template's generated secret can be created/read,
  but changing that secret remains outside this authority contract.
- AWS-managed encryption is used; there is no customer-managed KMS key grant,
  IAM/service-linked-role creation, S3, Lambda, API Gateway, resource-policy
  attachment, application item access, or runtime consumer permission.
  Any unexpected mandatory provider dependency is a **stop**, not justification
  for broad IAM/KMS/data access.

**Limitations are deliberate.** Provider schemas describe possible handler
permissions, not a proof of which calls each property combination makes, and may
change. Ordinary inline previews are not proof that resource handlers will
succeed later. The verified secret read dependency is covered; drift-aware
planning is still outside this handoff's workflow. No
UntagResource/UntagQueue or generic list permissions are granted. Updating tags,
secret metadata/material, optional properties, or recovery operations may fail.
Resolve such failures by a new reviewed contract or a separate authorized human
recovery plan, never by widening secret reads or granting administrator access.

### Verified Secrets Manager handler requirement

A fresh, **read-only** `DescribeType` of `AWS::SecretsManager::Secret` in
`us-west-2` returned the registered type ARN
`arn:aws:cloudformation:us-west-2::type/resource/AWS-SecretsManager-Secret`.
The authoritative response's `Schema` has these exact handler declarations:

```json
{
  "create": {
    "permissions": [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetRandomPassword",
      "secretsmanager:CreateSecret",
      "secretsmanager:TagResource",
      "secretsmanager:ReplicateSecretToRegions"
    ]
  },
  "read": {
    "permissions": [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue"
    ]
  },
  "update": {
    "permissions": [
      "secretsmanager:UpdateSecret",
      "secretsmanager:TagResource",
      "secretsmanager:UntagResource",
      "secretsmanager:GetRandomPassword",
      "secretsmanager:GetSecretValue",
      "secretsmanager:ReplicateSecretToRegions",
      "secretsmanager:RemoveRegionsFromReplication"
    ]
  }
}
```

Specifically, `/handlers/read/permissions` requires DescribeSecret **and**
GetSecretValue. `/handlers/update/permissions` also includes GetSecretValue;
`/handlers/create/permissions` does **not** list it. This establishes the
registered read-handler contract, not an invented claim that the create handler
itself necessarily reads a value. Granting the scoped provider read covers this
declared dependency if CloudFormation invokes read/stabilization for the current
resource. It does not authorize secret mutation/update features or replication.
The same schema marks `/properties/SecretString` and
`/properties/GenerateSecretString` as write-only; provider permission to read the
stored secret is not permission to publish it in a resource model or preview.
The [DescribeType API's Schema field](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeType.html)
and [handler permissions schema contract](https://docs.aws.amazon.com/cloudformation-cli/latest/userguide/resource-type-schema.html)
are the authoritative basis. Reproduce the metadata check with:

```bash
aws cloudformation describe-type --type RESOURCE --type-name AWS::SecretsManager::Secret \
  --region us-west-2 --query Schema --output text --no-cli-pager
```

The response's SourceUrl names
`https://github.com/aws-cloudformation/aws-cloudformation-resource-providers-secretsmanager.git`,
but that repository returned HTTP 404 during review; no claim of implementation
inspection is made. The registered schema, not inaccessible source or a generic
example policy, is the evidence. No version identifier was returned, so this is
a point-in-time regional registry observation, not a pinned implementation.
No GetSecretValue API was invoked, and no secret value was retrieved or logged.
The provider-only scoped read is an explicit approved exception to the earlier
blanket prohibition, **not** a global secret read or runtime data-access grant.

All seven resources have both retention policies; no DeleteTable, DeleteQueue
or DeleteSecret is granted. Retention does not guarantee a rollback will complete,
remove all charges, or make fixed-name retries/replacements safe. Failed create
or rollback can leave retained resources or a stuck stack. Do not remove
protection or delete resources to make a retry pass.
UpdateTable can change indexes/streams/deletion protection/PITR-related settings;
SetQueueAttributes can alter retention/redrive/encryption and queue access policy.
Resource scoping does **not** enforce every property or prevent every destructive
configuration update. Separate human review of exact change-set properties is
required; removal, replacement, reduced protection or unexpected policy changes
are a stop. The approved template currently requests none of those unsafe changes.

## Future authorized console bootstrap (not executed)

Do not run the following using the workstation's ambient AWS CLI identity:
it is account-root. **Root is never used for mutations**, including IAM setup,
stack metadata mutations, change sets, resource cleanup, or execution.
No AWS mutation is authorized by this document alone.

1. Obtain separate approval for **creating only these two roles and their inline
   policies**. Sign in to the AWS console through an explicitly authorized,
   short-lived **non-root administrative role/session**. Check the console
   account menu shows account `851725597758` and the approved role. Stop if it
   shows root, the wrong account, an unexpected identity, or an unapproved
   permissions boundary/SCP requirement. IAM is global; use `us-west-2` for later
   CloudFormation operations. Do not create access keys or use ambient CLI
   credentials as a shortcut.
2. In **IAM → Identity providers**, inspect the existing
   `token.actions.githubusercontent.com` provider and audience
   `sts.amazonaws.com`. Do not edit/recreate it. Stop if it does not match.
   In **IAM → Roles**, check neither proposed role name already exists.
   If one exists, stop for ownership/trust/permission review; do not overwrite.
3. Create **execution role first**: **IAM → Roles → Create role → Custom trust
   policy**. Replace the editor contents with the entire reviewed
   `deployment/foundation-execution-trust.json`. Choose **Next**; select **no
   managed permission policies**. On the role details page enter exactly
   `BridgeStagingFoundationExecution`, no additional path (ARN must end
   `role/BridgeStagingFoundationExecution`), and a staging-foundation-only
   description. Leave session duration at the default one hour. Follow an
   already approved organizational boundary if required; do not bypass it.
   Review the trust and **Create role**.
4. Open that role → **Permissions → Add permissions → Create inline policy →
   JSON**. Replace the entire editor with
   `deployment/foundation-execution-policy.json`. Choose **Next** (or **Review
   policy**), use policy name **BridgeStagingFoundationExecutionPolicy**, review
   every action/resource/condition, and choose **Create policy**. Do not attach
   AdministratorAccess, PowerUserAccess, AWSCloudFormationFullAccess, or an
   AWS-managed service-role policy.
5. Repeat **Create role → Custom trust policy** with
   `deployment/foundation-plan-trust.json`, no managed policies, exact name
   **GitHubBridgeFoundationPlanStaging**, path `/`, and default one-hour session.
   Add one inline policy using the complete
   `deployment/foundation-plan-policy.json`, named
   **GitHubBridgeFoundationPlanStagingPolicy**.
6. On both roles, independently review **Trust relationships** and **Permissions**:
   exact JSON conditions/principals, exactly the intended one inline policy,
   zero attached managed policies, expected boundaries and no unintended grants.
   Confirm the two exact ARNs below. Record the reviewed source commit/digest,
   approving administrator, time, role ARNs and any boundary/SCP constraints;
   never record credentials, tokens, or signing values. Leave the two existing
   OIDC identity-check roles unchanged.
7. **Leave the new GitHub variables unset until the roles are reviewed and a
   separate human authorizes enabling the manual planning workflow.** A later
   authorized repository administrator uses
   **jmtelgen/NextLevelBridgeAPI → Settings → Environments → staging →
   Environment variables → Add variable**:

   | New variable | Exact future value |
   | --- | --- |
   | `AWS_FOUNDATION_PLAN_ROLE_ARN` | `arn:aws:iam::851725597758:role/GitHubBridgeFoundationPlanStaging` |
   | `AWS_FOUNDATION_EXECUTION_ROLE_ARN` | `arn:aws:iam::851725597758:role/BridgeStagingFoundationExecution` |

   These are role identifiers, not secrets. **Do not replace, delete or repurpose
   `AWS_STAGING_ROLE_ARN`**, and do not change frontend environment variables.
   Verify the backend staging region is explicitly `us-west-2`, environment
   protection is approved, and the separately reviewed manual workflow uses
   only these foundation variables. No GitHub changes are made in this task.
8. A future dispatch of **Actions → Plan staging foundation (NO execution) →
   Run workflow** (`.github/workflows/staging-foundation-plan.yml`, calling
   `.github/scripts/plan_staging_foundation.sh`) requires approval for its real
   metadata mutations. Select **main** and choose **CREATE** for the first,
   nonexistent stack; choose **UPDATE** only for an existing reviewed stack.
   Do not guess/retry the opposite type after failure. The workflow uses a
   900-second session named `BridgeFoundationPlan-<run ID>-<attempt>` and a
   **10-minute job timeout**; check the resulting OIDC caller is the
   **new planning role**, account and region, before the first mutation. Stop
   on missing variables, wrong identity/region, access denial or name collision.
   Do not fall back to `AWS_STAGING_ROLE_ARN`, root, a deployment role, or relaxed
   policies. No auto-delete/retry-as-another-type/deploy/apply fallback.
   A timeout or waiter failure does not cancel/delete the AWS change set.
   Manually inspect the recorded deterministic name/ARN and stack state using
   a separately approved metadata-reading identity; do not assume nothing
   happened. CREATE can leave `REVIEW_IN_PROGRESS` even after a failed job.
   The workflow emits a summary preview, not full property-level approval.

### Separate human apply approval and persisted service role

After an approved preview, a separately authorized **non-root human operator**
must inspect the exact change-set ARN, template digest/source commit, stack,
region, execution role, resource property differences, costs and retained-name
collisions. Initial CREATE must contain exactly the seven approved Adds and
nothing else. An UPDATE needs separate property-by-property approval; no
unreviewed removals, replacements, imports, policy additions or protection
reductions. Record approval of the **specific** change set. This handoff grants
neither the human's ExecuteChangeSet permission nor permission to execute now.

CloudFormation persists its service role for subsequent stack operations; it
cannot simply be removed from a stack. AWS warns that another principal with
stack-operation permissions can use the persisted role **without iam:PassRole**.
The planning role therefore remains safe only while it has no execution/update/
delete permissions and other stack operators are tightly governed. Passing the
role is not a permanent per-operation approval boundary. Review live stack
ownership, existing service role, all operators and possible authority changes
before an UPDATE preview as well as before execution. Do not reuse this role for
another stack or attach runtime grants.

No source-only test establishes live SCP/boundary/session-policy behavior,
OIDC/environment protection, name availability, quotas, provider stabilization,
rollback success or real deployment. If safe authorization cannot be established
without forbidden permissions, leave planning/execution paused and return for
review.

## Offline validation

From the repository root, using the existing isolated infrastructure venv:

```bash
PYTHONDONTWRITEBYTECODE=1 \
  /home/jatelgen/.copilot/session-state/c13503ef-f7e6-4842-bb2f-9b59944aad17/files/.venv-infrastructure/bin/python \
  .github/scripts/test_foundation_authority.py
PYTHONDONTWRITEBYTECODE=1 \
  /home/jatelgen/.copilot/session-state/c13503ef-f7e6-4842-bb2f-9b59944aad17/files/.venv-infrastructure/bin/python \
  .github/scripts/test_staging_foundation.py
git diff --check
```

The authority tests parse strict JSON (duplicate keys fail), inspect trust,
allowlisted action/resource pairs and action-specific conditions, test ARN
envelopes, prohibit execution/destruction/IAM escalation and other data-plane
grants, explicitly isolate the one exact-secret provider read from the planner,
and compare all seven names, retention, region, GSI and stream scope to the
existing template. Glob checks are offline contract checks, **not an IAM
simulator**. Existing foundation tests separately preserve exact property/key
contracts. Tests import no app code, call no network/AWS and start no servers.
The parent task owns workflow/CI integration and publication.

## Authoritative references

- [CloudFormation actions, resources and condition keys](https://docs.aws.amazon.com/service-authorization/latest/reference/list_cloudformation.html)
  and its [AWS programmatic action reference](https://servicereference.us-east-1.amazonaws.com/v1/cloudformation/cloudformation.json):
  stack resource scope, action-specific ChangeSetName/RoleArn/TemplateUrl support,
  dependent TagResource/UntagResource and CreateAction support.
- [AWS's SecretsManagerReadWrite policy](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/SecretsManagerReadWrite.html):
  independently demonstrates `cloudformation:CreateAction = CreateChangeSet`
  on TagResource/UntagResource. **Do not attach this broad managed policy**;
  it is cited only as evidence for that condition's supported API value.
- [CloudFormation IAM access control](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/control-access-with-iam.html):
  conditions apply to corresponding API parameters, not template content.
- [CreateChangeSet API](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateChangeSet.html):
  CREATE/UPDATE semantics, REVIEW_IN_PROGRESS and separate execution.
- [CloudFormation service role](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html):
  service principal, persistence and stack-operator/PassRole escalation caveat.
- [DescribeType API](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeType.html):
  authoritative regional provider `Schema` and handler permissions; checked for
  AWS::DynamoDB::Table, AWS::SQS::Queue and AWS::SecretsManager::Secret during this review.
- [DynamoDB authorization](https://docs.aws.amazon.com/service-authorization/latest/reference/list_dynamodb.html),
  [SQS authorization](https://docs.aws.amazon.com/service-authorization/latest/reference/list_sqs.html),
  [Secrets Manager authorization](https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html):
  supported action/resource/condition combinations.
- [Secret ARN suffix matching](https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_iam-policies.html):
  six-character wildcard scoping.
- [IAM global condition keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-requestedregion):
  RequestedRegion controls endpoint requests, not all cross-region side effects.
- [GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html):
  no permission grant required.
- [Access Analyzer ValidatePolicy](https://docs.aws.amazon.com/access-analyzer/latest/APIReference/API_ValidatePolicy.html):
  policy findings are validation feedback, not policy application or proof of
  live IAM/OIDC authorization.
