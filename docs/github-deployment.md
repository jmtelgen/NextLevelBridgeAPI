# GitHub backend CI and staging identity bootstrap

This is **not application deployment**. It adds selected offline backend tests
and a manually dispatched, environment-protected OIDC identity check. It does
not run the existing deployment scripts or create/change AWS resources.

The bootstrap PR is merged. The operator completed the identity check on
`main`: [successful run](https://github.com/jmtelgen/NextLevelBridgeAPI/actions/runs/40426083892).
That first run used `us-east-1` for STS. The region correction is now merged,
the staging `AWS_REGION` variable is `us-west-2`, and the operator completed a
[successful corrected run](https://github.com/jmtelgen/NextLevelBridgeAPI/actions/runs/40427443686).
The deleted bootstrap branch's staging environment allowance has been removed.

Keep `AWS_STAGING_ROLE_ARN` bound to this identity-only role. The proposed
[foundation planning authority](foundation-authority.md) uses separate roles
and variables; it does not broaden this access-check role.

## What runs

`.github/workflows/backend-ci.yml` runs on pushes, pull requests, and manual
dispatch, using Python 3.12 on Ubuntu 24.04 x86_64. Its token has only
`contents: read`; neither job can request an OIDC token. Official actions are
pinned to commit SHAs resolved through GitHub's API.

`requirements-ci.txt` pins the direct and transitive CI dependencies from the
verified working environment, including Boto3, Moto, pytest, bcrypt, PyJWT,
Pydantic and aiohttp. It is a CI manifest, **not** a production dependency lock
or Lambda layer manifest. Existing runtime/local/test manifests are unchanged.

The explicit selectors live in `.github/scripts/test_backend.py`:

| Gate | Coverage | Explicit boundary |
| --- | --- | --- |
| `core` | Account creation/auth flows; socket sessions; bidding handlers; bridge and room lifecycle; board records; claims and duplicate events; pacing and game ticks; robot fair play, bidding/SAYC boundaries, benchmarks with mocked solvers; practice policies/handlers; SAYC opening bids | Loading native DDS is deliberately disabled and three native-specific tests are deselected. This gate alone does not establish native solver availability. |
| `native` | Three native tests: partial-trick/side known answer, complete sampled deal conserving 52 cards, and native benchmark CLI smoke | Uses the existing tracked Linux x86_64 library, **not** an external binary or a new source build; not Lambda ABI validation. |

Locally verified results: **486 passed, 3 deselected** in `core`; **3 passed**
in `native`. These are selected tests, not the whole repository's test suite.
The runner is independent of locally installed pytest plugins and blocks the
Botocore HTTP transport, so unexpected real AWS SDK requests fail rather than
reach AWS. Tests use Moto/in-memory collaborators, dummy AWS credentials,
`us-east-1`, disabled instance metadata, no credential/profile files, and no
bytecode/cache output. It does not start helper servers.

The native job first verifies SHA-256
`155e9b4835eb28b88f46f522aa8794b242b17a808037b1140823e70e62e5dff8`
for `lambdas/dds/libdds.so.2.9.0`, changes into its directory to accommodate the
existing wrapper's search paths, and requires the solver to initialize.
Missing/incompatible DDS **fails** this separate gate; it is not quietly
treated as successful native coverage. No DDS C++ source/build recipe is
tracked, so this bootstrap does not claim a reproducible native source build.
Changing the binary requires provenance review, digest update and revalidation.
Its observed GLIBC requirements reach 2.29. An Ubuntu success is not proof of
compatibility with the chosen AWS Lambda runtime, architecture, memory or ABI.

### Deliberately not covered

- `tests/test_local_server.py`, `tests/test_room_lifecycle_local.py`,
  `tests/test_claims_duplicate_local.py`, and `tests/test_practice_local.py`
  exercise loopback HTTP/WebSocket server subprocesses. They are outside these
  gates, including their DDS-dependent startup and real transport behavior.
- Legacy tests using removed paths such as `lambdas.account_login`,
  `lambdas.websocket_connect`, `lambdas.utils.*`, `models.*`, and `web_crawler`
  are not collected. They have stale import/contract failures; a broad
  `pytest` command is not a valid green CI gate. Other historical bidding tests
  and root-level deployment/network test scripts are also not selected.
- No AWS service integration, IAM authorization beyond identity, native source
  compilation, Lambda packaging/ABI, SAM/CloudFormation validation, deployed
  authentication/cookies/CORS, cloud load testing, or durable cross-instance
  archives/events is established by these checks.

Reproduce without starting servers:

```bash
# In a Python 3.12 virtual environment, if dependencies are not already present:
python -m pip install -r requirements-ci.txt
PYTHONDONTWRITEBYTECODE=1 python -B .github/scripts/test_backend.py core
PYTHONDONTWRITEBYTECODE=1 python -B .github/scripts/test_backend.py native
```

In the existing checkout substitute `venv/bin/python` for `python`.
The runner enforces the dummy AWS/region/metadata settings itself.

On successful `main` pushes, the core job uploads a seven-day
`backend-source-NOT-LAMBDA-<commit>` artifact containing only Python source
under `lambdas/` and `scripts/`, plus requirements manifests. It contains no
installed dependencies, native DDS library, credentials, dumps, existing ZIPs
or bytecode. **It cannot be deployed as a working Lambda ZIP.**
PRs do not upload this artifact or receive AWS credentials.

## Reviewed GitHub/AWS identity

Read-only GitHub inspection confirmed:

- Repository: `jmtelgen/NextLevelBridgeAPI` (public); default branch: `main`.
- Repository ID: `1027323092`; owner ID: `96450410`.
- Repository creation date: 2025-07-27.
- OIDC subject settings: `use_default: true`,
  `use_immutable_subject: false`,
  `sub_claim_prefix: repo:jmtelgen/NextLevelBridgeAPI`.
- AWS account: `851725597758`; application/access-check region: `us-west-2`.
- Existing provider:
  `arn:aws:iam::851725597758:oidc-provider/token.actions.githubusercontent.com`.
- Proposed dedicated role:
  `arn:aws:iam::851725597758:role/GitHubNextLevelBridgeAPIStaging`.
  This role was absent at inspection; the existing GameSignal role is unrelated
  and must not be reused or modified.

`deployment/github-oidc-trust.json` is the exact trust document for the proposed
role. It requires audience `sts.amazonaws.com` and the **single exact** subject:

```text
repo:jmtelgen/NextLevelBridgeAPI:environment:staging
```

There are no wildcard repository, branch or environment subjects. This
repository currently uses the legacy name-based subject; do not substitute
repository/owner IDs or an immutable subject without first reviewing the
actual emitted claim and changing the policy accordingly. Renaming,
transferring, or changing OIDC customization requires a trust review.
An environment subject does not include a branch: branch restrictions belong
in the GitHub environment and workflow guards, not an invented IAM subject.

## One-time manual setup (human administrator)

**Do not use the locally configured AWS root CLI for this work.** Sign in to
the AWS console with an MFA-protected, non-root administrative identity in the
reviewed account. This bootstrap makes no AWS changes automatically.

1. In IAM, inspect the existing GitHub OIDC provider above. Confirm issuer
   `https://token.actions.githubusercontent.com` and audience
   `sts.amazonaws.com`. Do not replace a provider or change unrelated roles.
2. Create the dedicated IAM role named **GitHubNextLevelBridgeAPIStaging**
   (no IAM path). Choose the existing web-identity provider, then set the
   role's trust policy to the complete contents of
   `deployment/github-oidc-trust.json`. Confirm both exact `StringEquals`
   conditions after saving.
3. **Attach no permissions policies** for this identity-only bootstrap. In
   particular, do not attach AdministratorAccess, PowerUserAccess, deployment
   policies, or copy GameSignal permissions. `sts:GetCallerIdentity` requires
   no identity-based allow policy; a successful identity check does not imply
   permission to deploy anything.
4. In GitHub Settings → Environments → **staging**, restrict deployment branches
   to `main` only.
   Require a reviewer and prevent self-review if available for this account.
   Review protection settings before permitting any AWS role assumption.
   Keep both environment rules and workflow conditions restricted to `main`.
   Deleting a branch does not remove its environment allowance automatically.
5. Set these **environment variables** (not long-lived credential secrets):

   | Variable | Value |
   | --- | --- |
   | `AWS_ACCOUNT_ID` | `851725597758` |
   | `AWS_REGION` | `us-west-2` |
   | `AWS_STAGING_ROLE_ARN` | `arn:aws:iam::851725597758:role/GitHubNextLevelBridgeAPIStaging` |

   Account and region can be configured first; **leave the ARN unset until the
   human creates and verifies the role**. Never add AWS access keys, root
   credentials or raw OIDC tokens to GitHub variables/secrets, files or logs.
6. Once the workflow is on the default branch, use Actions →
   **Staging AWS access check (NO deployment)** → **Run workflow**, selecting
   `main`.
   GitHub only offers `workflow_dispatch` workflows after they exist on the
   default branch. Approve the environment deployment if prompted.
7. Verify the run shows the expected account and assumed-role ARN. Preserve
   the run URL as identity-proof evidence; do not print or copy session
   credentials or the GitHub OIDC JWT.

The manual workflow checks all three variables against the reviewed values
**before** requesting credentials, restricts repository/ref, and binds its job
to `staging`. Only that job gets `id-token: write`; it has no repository-content
permission and does not check out or execute application/deployment code.
The pinned AWS action exchanges the GitHub token via
`sts:AssumeRoleWithWebIdentity` for a 15-minute session restricted to the
expected account. The only subsequent AWS API call is
`sts:GetCallerIdentity`; the account and dedicated role ARN are checked again.
There is no automatic cloud resource mutation.

If variables are absent, the check intentionally fails with a setup message.
An assumption failure requires checking audience, exact subject, role ARN and
environment protections—not broadening trust or attaching an admin policy.

## Before actual application deployment

Follow [AWS_READINESS.md](AWS_READINESS.md) for the application-specific gaps.
Later work must provide reviewed least-privilege deployment and Lambda
execution roles (separate from this identity-proof role), cloud-ready
SAM/CloudFormation stacks, real endpoint/route/table configuration, secret
management, rollback and cost controls, and a tested Lambda-compatible native
DDS build/package. Archives and duplicate-event state currently include
process-memory storage and require durable, concurrency-safe cloud storage
before multi-instance operation. Loopback behavior is not a cloud deployment.

The ignore rules prevent new credentials, caches, dumps and build bundles from
being added accidentally. They do **not** remove, revert or sanitize existing
tracked artifacts; inspect previously tracked ZIPs/bytecode separately before
publishing or deploying.
