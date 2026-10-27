# Fresh staging foundation CREATE after failed import/update recovery

The user chose a new signing-secret resource and will delete the failed
`bridge-staging-foundation` stack. This does not authorize deleting retained
resources, retrieving signing material, or provisioning with the local root
profile. All operator mutations below require an authorized non-root session
in account `851725597758`, region `us-west-2`.

## What changes

| Resource | New CREATE target | Retained legacy resource: leave untouched |
| --- | --- | --- |
| Signing secret | `bridge-staging-jwt-v2` | `bridge-staging-jwt` |
| Robot tick DLQ | `bridge-staging-game-tick-dlq-v2` | `bridge-staging-game-tick-dlq` |

The four table names and source queue `bridge-staging-game-tick` are unchanged.
The source queue references the new DLQ through CloudFormation, and the new
DLQ still accepts redrive only from that source queue. Both remain standard,
encrypted queues with the existing visibility and retention settings.

The original signing-secret version was unchanged after the failed update.
The new CREATE generates independent signing material; it does not rotate,
overwrite or delete the original secret. Future staging application settings
must use `JWT_SECRET_ID=bridge-staging-jwt-v2`. No application uses this new
secret merely because the foundation exists.

## Operator sequence

1. Delete only the failed **stack** through the non-root CloudFormation console.
   Its resources have `DeletionPolicy: Retain`; do not delete the old secret or
   DLQ separately. Wait for `DELETE_COMPLETE`. If deletion fails, stop and retain
   event metadata rather than force-deleting resources.
2. In IAM, open role **BridgeStagingFoundationExecution**, then inline policy
   **BridgeStagingFoundationExecutionPolicy**, and replace its JSON with
   [`deployment/foundation-execution-policy.json`](../deployment/foundation-execution-policy.json)
   from the newly merged `main`. This retargets the existing secret and queue
   permissions to the two new names. It adds no actions and does not grant
   UpdateSecret, PutSecretValue, UntagResource, RotateSecret or DeleteSecret.
   The trust policy, planning role, GitHub variables and other roles do not change.
3. Inventory metadata before CREATE. There must be no active stack with this name,
   and all seven **new target names** must be absent: `bridge-staging-rooms`,
   `bridge-staging-users`, `bridge-staging-connections`,
   `bridge-staging-duplicate-events`, `bridge-staging-game-tick`,
   `bridge-staging-game-tick-dlq-v2`, and `bridge-staging-jwt-v2`.
   Old-name retained resources are expected and are not collisions. Any resource
   occupying a new target name is a blocker; do not delete it or retry blindly.
4. Start a **new** foundation planning workflow on updated `main`, choosing
   **CREATE**, not UPDATE. Do not rerun an older job: it checks out older source.
   The secret-tag exception input is removed.
5. Review exactly **seven Add actions**, with the two new physical names in the
   reviewed template and the exact existing CloudFormation execution role.
   No Import, Modify, Remove or replacement action is expected.
   Planning creates a preview only; separate non-root approval/execution is
   still required.
6. After approved execution, wait for `CREATE_COMPLETE` and inspect resource
   metadata and stack outputs. Confirm the new secret exists without retrieving
   its value, and confirm the old secret remains unchanged. This provisions
   storage/queues/signing material only, not the application or frontend.

## Why not add the missing secret permissions?

The tags-only UPDATE invoked UpdateSecret; rollback then invoked UntagResource.
Adding only the latter would not solve the original failure. UpdateSecret can
write signing values, so it remains outside this execution contract. The
planner now blocks **all** `JwtSigningSecret` changes during UPDATE, including
static tags-only changes and attempts to reuse the removed opt-in.

The legacy import template/runbook are historical references only. Do not use
them to import the old secret into this new CREATE or combine IMPORT with it.
