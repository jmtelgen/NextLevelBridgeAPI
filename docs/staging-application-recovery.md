# Resource-preserving staging application recovery

This is operator-only recovery of **bridge-staging-application** in account
**851725597758**, region **us-west-2**. It is not a fresh application release.
The user approved preserving resources, not cleaning them up.

## What is being preserved

The failed CREATE reached `ROLLBACK_COMPLETE`. Its governing template has
`DeletionPolicy: Retain` on all 132 resources, but only 129 physically exist:

| Existing type | Count |
| --- | ---: |
| Lambda functions | 22 |
| CloudWatch log groups | 22 |
| Lambda invoke permissions | 20 |
| REST methods, including OPTIONS | 12 |
| REST path resources | 8 |
| REST deployment | 1 |
| WebSocket integrations | 14 |
| WebSocket routes | 30 |

The REST stage, WebSocket deployment and WebSocket stage do not exist. The REST
stage's `DELETE_SKIPPED` history entry is not proof of physical existence.
These three resources must be created **after** the import, in a separate UPDATE.
Manual IMPORT cannot also create new resources or alter existing properties.

The REST tagging permission correction is already applied to the separate
platform stack **bridge-staging-platfor**. Never delete that stack, the foundation
stack, any physical application resource, or any public-site resource.

## Download and verify before deleting the failed record

Use the operator recovery kit from the [repository's draft release](https://github.com/jmtelgen/NextLevelBridgeAPI/releases).
Download `application-import-recovery.zip` and
`application-import-recovery.zip.sha256` while signed into GitHub as an authorized
repository user. Upload both to an approved non-root AWS CloudShell session, or
use an approved local non-root AWS profile. No long-lived credentials belong in
the kit, repository, chat or GitHub Actions secrets.

The ZIP SHA-256 is
`2e4a497534db0f8fefe387303e4a8bfdd4b7c6ede91398a70260a9019734db2c`.
Verify the ZIP checksum before extraction and use a new directory:

```bash
sha256sum -c application-import-recovery.zip.sha256
mkdir bridge-application-recovery
unzip application-import-recovery.zip -d bridge-application-recovery
cd bridge-application-recovery
sha256sum -c SHA256SUMS
python3 application_import_recovery.py validate --directory .
aws sts get-caller-identity --region us-west-2 --no-cli-pager
```

Confirm account `851725597758` and a non-root identity. The script's plan modes
must reject root before any S3 upload or CloudFormation write. The workstation's
root identity may export metadata only and must not run a mutation mode.

The kit preserves the original release source
`a625ea62b2b16410c244607d85de9fe97c9146db`, artifact digest
`4ae761aef2b50faa7ad6a9e5e6962db516ea61d5e88c5c8e60a8a41536bb548c`,
and exact versioned code object. It is not rebuilt from current `main`.
Keep the frozen parameters unchanged.

## Remove only the failed stack record

Only after the kit passes offline validation, use the authorized non-root
CloudFormation console to select exactly **bridge-staging-application**.
Confirm it is still `ROLLBACK_COMPLETE`, then delete that failed stack record.
The verified Retain policies preserve the existing physical resources.

Wait until deletion completes and the active stack name is absent. Do not use
the ordinary CREATE workflow: it would collide with retained resources. If
anything differs from this expected state, stop rather than deleting resources
or broadening permissions.

## Prepare and review the import

In the extracted kit directory, using the same authorized non-root session:

```bash
python3 application_import_recovery.py plan --directory . \
  --change-set-name bridge-staging-application-import-recovery-1
```

This prepares a change set only. It must not delete resources or execute the
change set. The template is uploaded immutably to the isolated versioned
artifact bucket, with the exact object version in the template URL.
The execution role remains **BridgeStagingApplicationExecution**.

Review the change set in `us-west-2`: expect **129 Import actions only**, with no
Add, Modify, Remove or replacement. Verify the exact isolated API IDs
`pukawa2m43` and `m58xz54ub0`, original parameters and original artifact binding.
Then execute through the approved non-root console and wait for
`IMPORT_COMPLETE`. Stop on any failure; do not delete or blindly retry.

The import mapping uses separate keys for composite identifiers, as in the
[official AWS CDK importer](https://github.com/aws/aws-cdk-cli/blob/5fa3b0fe61fc6b0ace61cceddf3949a4699e581e/packages/%40aws-cdk/toolkit-lib/lib/api/resource-import/importer.ts#L332-L453).
All permission SIDs and resource identifiers are matched against live metadata.

## Complete the three missing resources

After `IMPORT_COMPLETE`, from the extracted kit directory:

```bash
python3 application_import_recovery.py plan-completion --directory . \
  --change-set-name bridge-staging-application-completion-recovery-1
```

This prepares but does not execute a separate UPDATE using the kit's original
`full-template.json` and `parameters.json`. The full template exceeds the inline
CloudFormation limit; the script uploads an immutable version rather than using
`--template-body`. Review for exactly three Add actions: `RestStage`,
`WebSocketDeployment4ae761aef2b50faa`, and `WebSocketStage`. No existing resource
should be modified, removed or replaced; no Lambda code is being redeployed.
Execute through the non-root console only after that review, then wait for
`UPDATE_COMPLETE`.

Only after that UPDATE completes should robot scheduling, frontend publication
and live acceptance resume. The deployed backend SourceCommit remains the
original `a625ea62b2b16410c244607d85de9fe97c9146db`; use that output, not the
recovery-tooling commit, when publishing the frontend.
