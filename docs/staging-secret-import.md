# Preserve the existing staging signing secret by import

**Historical reference only. Superseded by the
[fresh CREATE recovery](staging-foundation-fresh-retry.md).**
Do not execute the phases below against the current foundation template.
The legacy import template intentionally retains the old secret name; the
current foundation template creates a different secret. The subsequent
tags-only UPDATE failed on UpdateSecret, and rollback failed on UntagResource.
The tags-only opt-in described below has been removed.

At the time of the original import record, IMPORT was complete and the
full-foundation UPDATE was pending.
The operator performed the import; its observed metadata is recorded below.
Do not repeat phases 0 and 1 for the already imported stack.
This is not approval to provision, delete, rotate, retrieve, or rewrite a secret.
The prior cleanup approval was withdrawn. Preserve the existing secret and all
signing material. Do not use the locally configured root profile for provisioning.
Only a separately authorized **non-root human administrator**, in the AWS console,
may perform the reviewed import below. No new IAM or runtime variables are needed.

## Fixed target and evidence boundary

| Setting | Required value |
| --- | --- |
| Account | `851725597758` |
| Region | `us-west-2` (Oregon) |
| New stack name | `bridge-staging-foundation` |
| Execution role | `arn:aws:iam::851725597758:role/BridgeStagingFoundationExecution` |
| Import template | `deployment/staging-secret-import.yaml` |
| Logical ID / type | `JwtSigningSecret` / `AWS::SecretsManager::Secret` |
| Identifier property | `Id` (not `Name`) |
| Identifier value | `arn:aws:secretsmanager:us-west-2:851725597758:secret:bridge-staging-jwt-LzSRSY` |
| Stack tags | `Application=Bridge`, `Environment=staging` |

The supplied historical inventory reported the original stack `DELETE_COMPLETE`,
no active stack with this name, all four table names and two queue names absent,
and this one retained secret. Its creation time was
`2026-10-27T01:12:31.205Z`, with no `DeletedDate` and unchanged `LastChangedDate`.
These are historical observations, **not current preflight clearance**.

For review, the exact resource mapping is shown here; it is not an executable
command and no separate manifest is required:

```json
[
  {
    "ResourceType": "AWS::SecretsManager::Secret",
    "LogicalResourceId": "JwtSigningSecret",
    "ResourceIdentifier": {
      "Id": "arn:aws:secretsmanager:us-west-2:851725597758:secret:bridge-staging-jwt-LzSRSY"
    }
  }
]
```

Template metadata records intent only; it does not enforce account, region,
stack name, role, tags, or import mode. The operator must verify them.

## Why the generator declaration must remain identical

Authoritative AWS evidence:

1. The [resource support table][support] lists `AWS::SecretsManager::Secret`
   as supporting **import**.
2. The [AWS-published Oregon provider schema archive][schema], linked from
   [CloudFormation resource provider schemas][schemas], was inspected directly
   in memory during preparation (archive Last-Modified:
   `Mon, 26 Oct 2026 21:01:49 GMT`). Its `aws-secretsmanager-secret.json` declares:
   - `primaryIdentifier: ["/properties/Id"]`; no additional identifiers.
   - `readOnlyProperties: ["/properties/Id"]`.
   - `writeOnlyProperties: ["/properties/SecretString",
     "/properties/GenerateSecretString"]`.
   - `createOnlyProperties: ["/properties/Name"]`.
   - Read handler permissions: `secretsmanager:DescribeSecret` and
     `secretsmanager:GetSecretValue`.
   - Update handler permissions include `secretsmanager:UpdateSecret`,
     `secretsmanager:GetRandomPassword`, `secretsmanager:GetSecretValue`,
     tagging/untagging and replication operations.
   The [Secret reference][secret] defines `Id` as the secret ARN.
   This is provider-schema evidence, not a guess based on the `Name` property.
   Before acting, confirm the console offers `Id`; if it differs, stop and have
   the reviewer verify `ResourceIdentifierSummaries` with read-only
   `GetTemplateSummary` against this template and the regional registry schema.
3. AWS [manual import semantics][manual] state that imports do not allow
   resource creation, deletion, or property-configuration changes. Import
   validates existence/schema/ownership, but **does not validate actual property
   equality**. The template establishes the desired configuration; it is not a
   request to generate another password during IMPORT.
4. AWS [write-only schema semantics][schema-semantics] mean the generation
   instructions cannot be recovered by a read handler. AWS explicitly permits
   [supplying write-only properties during import][write-only]. The generator
   declaration here is copied from the original foundation source, not inferred
   from secret material. Do not omit it for import and reintroduce it later.
5. The [Secret property reference][secret] states that **changing**
   `GenerateSecretString` creates a new secret version. CloudFormation
   [updates only changed resources][updates]. Both templates therefore declare
   exactly the same resource, including logical ID, retention, description,
   name, and generation metadata. An identical declaration and identical stack
   tags are intended to leave this secret unchanged in the later UPDATE.
   “No interruption” does **not** mean no new version if generation metadata
   changes.

These documented semantics support this import-only design; no documented
prohibition on the identical write-only declaration was found. They do not prove
the behavior of an unexecuted live recovery. No secret value was inspected, so
generation history/material equality cannot be independently established here.
Drift detection cannot establish equality of write-only generation properties.
The subsequent UPDATE preview is a mandatory safety gate, not a formality.

**Provider-only read exception:** the existing CloudFormation execution policy's
`GetSecretValue` permission is necessary for the provider's read/stabilization
handler. Preserve it; it does not authorize an operator, script, workflow, or
this preparation to retrieve values. Never call `GetSecretValue`, open
**Retrieve secret value**, or export/log secret payloads. No template output or
dynamic secret reference is present.

The execution policy intentionally lacks `UpdateSecret` and `PutSecretValue`.
Keep it unchanged. The schema's update-handler permission list is not proof
that a no-change secret needs an update. If import/read/tag stabilization
actually demands a missing permission, or a secret property/value change is
proposed, **stop**, record only sanitized event/error metadata, and obtain a
separately reviewed resolution. Do not grant permissions, change generation properties, remove
retention, or retry using a different identity/mode to bypass a blocker.

## Phase 0 — fresh read-only operator preflight

Immediately before any import preparation, using the non-root console session:

1. Confirm account `851725597758` and region `us-west-2`. Confirm the existing
   execution role above is available to pass to CloudFormation; do not create or
   modify a role/policy.
2. In CloudFormation, inspect current stacks including failed and
   `REVIEW_IN_PROGRESS` entries. The old stack must be `DELETE_COMPLETE`, and
   **no active stack** may occupy `bridge-staging-foundation`. A conflicting
   review-only shell is still a blocker; do not delete it automatically.
3. In Secrets Manager, inspect **metadata only**. Confirm the full exact ARN,
   name `bridge-staging-jwt`, creation time, current last-changed metadata,
   description and tags; `DeletedDate` must be absent (not pending deletion).
   Compare current metadata with the original inventory; any unexplained
   difference requires review. Do not restore, delete, regenerate or rotate it.
4. Establish that **no active stack owns the secret**. Inspect any stack IDs in
   its CloudFormation tag metadata and their current stack/resource status;
   verify no live stack lists this exact physical ARN. A separately authorized
   reviewer may use read-only `DescribeStackResources` with the exact physical
   ID and inspect returned stack IDs/statuses if console ownership is unclear.
   Old deleted-stack tags alone neither prove active ownership nor prove
   importability. Incomplete/denied ownership evidence is a stop condition,
   not an excuse to assume the resource is free.
5. Recheck that `bridge-staging-rooms`, `bridge-staging-users`,
   `bridge-staging-connections`, `bridge-staging-duplicate-events`,
   `bridge-staging-game-tick`, and `bridge-staging-game-tick-dlq` remain absent
   in their service consoles. Unexpected resources require review, not cleanup.
6. Review the exact template and offline equality tests. Record only nonsecret
   metadata and the reviewed source/template digest. Secure separate approval
   for the privileged IMPORT metadata/ownership and stack-tag changes.

## Phase 1 — human console IMPORT of one resource

Follow AWS's [new stack from existing resources procedure][new-stack], not the
standard create-resources wizard:

1. Open CloudFormation in Oregon. Choose **Create stack**, then
   **With existing resources (import resources)**. Do not select the standard
   new-resources path, automatic import, IaC generation, or the full foundation
   template.
2. Read the import overview. Upload **only**
   `deployment/staging-secret-import.yaml`. Console upload stores the template
   in S3 and can create a CloudFormation template bucket if none exists; review
   that artifact handling separately. If new bucket creation is not authorized,
   use a separately approved existing S3 template URL instead, or stop.
3. On **Identify resources**, there must be exactly one row:
   `JwtSigningSecret`, `AWS::SecretsManager::Secret`. Choose **Id** and paste
   the full exact ARN from the table above. A name, partial ARN, another ARN,
   or another identifier property is not acceptable.
4. Set the **new stack name** to `bridge-staging-foundation`. In stack
   configuration/options, set exactly the two user stack tags
   `Application=Bridge` and `Environment=staging`, and select the existing
   execution role
   `arn:aws:iam::851725597758:role/BridgeStagingFoundationExecution`.
   Do not add extra user tags, parameters, resources or IAM capabilities.
   Verify these settings on the final review; if this console flow cannot
   supply/review the required role and tags, **stop before execution** and
   escalate for a separately reviewed procedure. Do not fall back to CLI/root.
5. Advancing the wizard prepares an **IMPORT** change set. Review it and its
   stack settings before execution: exactly one **Import** action on
   `JwtSigningSecret`, matching the exact existing ARN; no Add, Modify,
   Replace, Remove/Delete, other resource, output or secret reference.
   IMPORT associates ownership and may apply stack/system tags; it is not
   a promise of zero metadata writes. Matching user stack tags now prevents
   a later tag-only secret update. Do not strip old tags manually.
6. Only after separate human approval, choose **Import resources**. AWS documents
   that this button executes the prepared change set. Wait for stack
   **IMPORT_COMPLETE**; verify its Resources tab maps `JwtSigningSecret` to
   the exact ARN and the saved template/tags/role match the reviewed settings.
   Recheck metadata-only `LastChangedDate` and `VersionIdsToStages` against
   preflight if available; any unexpected version/last-changed difference
   requires investigation. Do not retrieve values to compare them.

If anything fails, remains in progress unexpectedly, or enters
`IMPORT_ROLLBACK_*`, stop and retain all resources and sanitized event metadata
for review. Do not auto-clean up, delete the stack/secret, retry-as-CREATE,
re-import under another name, or change permissions. A historical
`DELETE_COMPLETE` stack does not authorize deleting this new stack.

## Phase 2 — separate full-foundation UPDATE preview

Only after verified `IMPORT_COMPLETE`, and after PR
[#5](https://github.com/jmtelgen/NextLevelBridgeAPI/pull/5) is merged to `main`
with the standard-queue fix (commit `0f0c15b`, `FifoQueue` omitted on both queues):

1. Prepare the existing GitHub foundation plan from the merged full
   `deployment/staging-foundation.yaml`, explicitly selecting **UPDATE**.
   **Do not use CREATE after import.** Retain the same stack name, region,
   execution role and two stack tags.
2. Review the preview before any separate human execution. Expect exactly
   **SIX Add actions**:

   | Logical ID | Type |
   | --- | --- |
   | `RoomsTable` | `AWS::DynamoDB::Table` |
   | `UsersTable` | `AWS::DynamoDB::Table` |
   | `ConnectionsTable` | `AWS::DynamoDB::Table` |
   | `DuplicateEventsTable` | `AWS::DynamoDB::Table` |
   | `TickDeadLetterQueue` | `AWS::SQS::Queue` |
   | `TickQueue` | `AWS::SQS::Queue` |

   Ideally `JwtSigningSecret` is absent from resource-change actions. An import
   without the two **stack-level** tags can instead produce one tags-only Modify
   while leaving the secret properties identical. The default guard still
   rejects this. For this verified case only, start a **new workflow run** on
   the corrected `main` and explicitly enable **Allow verified tags-only secret
   metadata changes**. Rerunning the older failed job uses its older source and
   will not pick up the corrected guard or new input.

   The opt-in permits only `Modify`, resource type `AWS::SecretsManager::Secret`,
   `Replacement: "False"`, scope exactly `["Tags"]`, and nonempty change details
   that are all `Static`, target `Tags`, and require recreation `Never`. Missing,
   mixed, dynamic, property-changing or replacement metadata still fails closed.
   Add/Remove/Import actions for the secret remain blocked. Review six Adds plus,
   only when opted in, this one metadata-only Modify. Do not remove the guard or
   broaden execution permissions; signing material must remain unchanged.
3. The GitHub planning workflow remains **CREATE/UPDATE only**, preparing
   previews only. It must not gain IMPORT, execute, delete, or secret-read
   permissions; import authority is separate human authority. Preparing these
   source changes does not execute the preview or provision resources.
   Any eventual UPDATE execution requires its own approval.

### Observed post-import tagging difference

The stack reached `IMPORT_COMPLETE`. Its stored secret declaration exactly
matches the reviewed template, and metadata still reports original
`AWSCURRENT` version `4f3bd6b7-f22f-7de5-f225-e2c2ef3b8892`. The imported stack's
tag list was empty, although the physical secret already carried
`Application=Bridge` and `Environment=staging`. These are different metadata
layers: adding the workflow's required stack tags proposes a tags-only secret
Modify even when the physical tags already have those values.

[Run 40433460308](https://github.com/jmtelgen/NextLevelBridgeAPI/actions/runs/40433460308)
was stopped by the original blanket guard. Its ready preview contained the six
expected Adds plus a single static, non-replacing tags-only secret Modify.
No signing value was read or changed by the inspection. The live execution
role remains CloudFormation-only, permits TagResource, and has no UpdateSecret,
PutSecretValue, RotateSecret or DeleteSecret grant. The opt-in changes no IAM
permissions and grants no execution capability.

Do not delete/re-import the secret or regenerate it to fix a stack-tag mismatch.
After separately approved execution, compare `VersionIdsToStages` with the
baseline again. `LastChangedDate` alone is not evidence of key rotation:
importing or tagging can change metadata timestamps without changing a version.

## Offline validation

From the repository root, using the existing infrastructure venv:

```bash
/home/jatelgen/.copilot/session-state/c13503ef-f7e6-4842-bb2f-9b59944aad17/files/.venv-infrastructure/bin/python .github/scripts/test_staging_secret_import.py
/home/jatelgen/.copilot/session-state/c13503ef-f7e6-4842-bb2f-9b59944aad17/files/.venv-infrastructure/bin/cfn-lint --region us-west-2 --template deployment/staging-secret-import.yaml
```

These checks assert static scope, equality and phase contracts; they cannot
validate live ownership, current regional import behavior, effective IAM, or
successful preservation through a live operation. No dependencies need changing.

[support]: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resource-import-supported-resources.html
[schemas]: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/resource-type-schemas.html
[schema]: https://schema.cloudformation.us-west-2.amazonaws.com/CloudformationSchema.zip
[schema-semantics]: https://docs.aws.amazon.com/cloudformation-cli/latest/userguide/resource-type-schema.html
[manual]: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/import-resources-manually.html
[new-stack]: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resource-import-new-stack.html
[secret]: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-secretsmanager-secret.html
[write-only]: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/generate-IaC-write-only-properties.html
[updates]: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacks.html
