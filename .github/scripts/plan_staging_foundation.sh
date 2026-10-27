#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 1
}

[[ $# == 1 ]] || fail "Expected exactly one mode: validate or plan."
case "$1" in
  validate|plan) ;;
  *) fail "Unknown mode; expected validate or plan." ;;
esac

[[ "${GITHUB_REPOSITORY:-}" == "jmtelgen/NextLevelBridgeAPI" ]] || fail "Unexpected repository."
[[ "${GITHUB_REF:-}" == "refs/heads/main" ]] || fail "Only main may prepare staging plans."
[[ "${AWS_ACCOUNT_ID:-}" == "851725597758" ]] || fail "Unexpected AWS account."
[[ "${AWS_REGION:-}" == "us-west-2" ]] || fail "Expected staging AWS_REGION us-west-2."
[[ "${AWS_FOUNDATION_PLAN_ROLE_ARN:-}" == "arn:aws:iam::851725597758:role/GitHubBridgeFoundationPlanStaging" ]] || fail "Create and review the separate foundation plan role before setting its ARN."
[[ "${AWS_FOUNDATION_EXECUTION_ROLE_ARN:-}" == "arn:aws:iam::851725597758:role/BridgeStagingFoundationExecution" ]] || fail "Create and review the separate foundation execution role before setting its ARN."
[[ "${GITHUB_RUN_ID:-}" =~ ^[1-9][0-9]*$ ]] || fail "Missing or invalid GitHub run ID."
[[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[1-9][0-9]*$ ]] || fail "Missing or invalid GitHub run attempt."
[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || fail "Missing or invalid source commit."
[[ -n "${GITHUB_STEP_SUMMARY:-}" ]] || fail "Missing GitHub step summary path."
case "${FOUNDATION_CHANGE_SET_TYPE:-}" in
  CREATE|UPDATE) ;;
  *) fail "Select CREATE or UPDATE explicitly." ;;
esac

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
template=deployment/staging-foundation.yaml
[[ -f "$template" ]] || fail "Staging foundation template is missing."
[[ "$1" == plan ]] || exit 0

region=us-west-2
stack_name=bridge-staging-foundation
change_set_name="bridge-staging-foundation-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
session_name="BridgeFoundationPlan-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
identity="$(aws sts get-caller-identity --region "$region" --no-cli-pager --query '[Account,Arn]' --output text)"
read -r account arn <<< "$identity"
[[ "$account" == "851725597758" && "$arn" == "arn:aws:sts::851725597758:assumed-role/GitHubBridgeFoundationPlanStaging/${session_name}" ]] || fail "STS did not return this run's dedicated planning-role session."

aws cloudformation validate-template --region "$region" --no-cli-pager \
  --template-body "file://${template}" --query Description --output text

change_set_arn="$(aws cloudformation create-change-set \
  --region "$region" --no-cli-pager \
  --stack-name "$stack_name" \
  --change-set-name "$change_set_name" \
  --change-set-type "$FOUNDATION_CHANGE_SET_TYPE" \
  --client-token "$change_set_name" \
  --description "Review-only staging foundation plan for ${GITHUB_SHA}" \
  --template-body "file://${template}" \
  --role-arn "$AWS_FOUNDATION_EXECUTION_ROLE_ARN" \
  --tags Key=Application,Value=Bridge Key=Environment,Value=staging \
  --query Id --output text)"

expected_prefix="arn:aws:cloudformation:us-west-2:851725597758:changeSet/${change_set_name}/"
[[ "$change_set_arn" == "$expected_prefix"?* ]] || fail "CloudFormation returned an unexpected change-set ARN."

if ! aws cloudformation wait change-set-create-complete \
  --region "$region" --no-cli-pager \
  --stack-name "$stack_name" --change-set-name "$change_set_arn"; then
  aws cloudformation describe-change-set \
    --region "$region" --no-cli-pager \
    --stack-name "$stack_name" --change-set-name "$change_set_arn" \
    --query '{Status:Status,Reason:StatusReason,ExecutionStatus:ExecutionStatus}' --output json
  fail "Change-set preparation failed (including a possible no-change update); inspect its status. Nothing was executed."
fi

preview="$(aws cloudformation describe-change-set \
  --region "$region" --no-cli-pager \
  --stack-name "$stack_name" --change-set-name "$change_set_arn" \
  --query '{Id:ChangeSetId,Stack:StackId,Status:Status,ExecutionStatus:ExecutionStatus,Changes:Changes[].ResourceChange.{Action:Action,LogicalResourceId:LogicalResourceId,ResourceType:ResourceType,Replacement:Replacement,Scope:Scope,Details:Details[].{Evaluation:Evaluation,Target:{Attribute:Target.Attribute,RequiresRecreation:Target.RequiresRecreation}}}}' \
  --output json)"
printf '%s\n' "$preview"
printf '%s\n' "$preview" | python3 -c '
import json
import sys

try:
    preview = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit("::error::CloudFormation returned an invalid preview.")
if not isinstance(preview, dict) or preview.get("Status") != "CREATE_COMPLETE" or preview.get("ExecutionStatus") != "AVAILABLE":
    sys.exit("::error::The change set is not available for review.")
changes = preview.get("Changes")
if not isinstance(changes, list) or any(
    not isinstance(change, dict) or not isinstance(change.get("LogicalResourceId"), str)
    for change in changes
):
    sys.exit("::error::CloudFormation returned invalid resource-change metadata.")
if sys.argv[1] == "UPDATE" and any(
    change["LogicalResourceId"] == "JwtSigningSecret" for change in changes
):
    sys.exit("::error::UPDATE must preserve JwtSigningSecret unchanged. Even tags-only changes invoke a provider update outside the execution role permissions; nothing was executed.")
' "$FOUNDATION_CHANGE_SET_TYPE"

digest="$(sha256sum "$template")"
{
  echo "## Staging foundation plan only"
  echo "Account: 851725597758; region: us-west-2; stack: $stack_name"
  echo "Source commit: $GITHUB_SHA"
  echo "Template SHA-256: ${digest%% *}"
  echo "Change set: $change_set_arn"
  echo "No change set was executed. A separately authorized human must review it before any resource provisioning."
  echo "A CREATE plan can leave a REVIEW_IN_PROGRESS stack; failed or timed-out plans require manual inspection."
} >> "${GITHUB_STEP_SUMMARY:?Missing GitHub step summary path.}"
