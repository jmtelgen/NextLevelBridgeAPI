#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/plan_staging_foundation.sh"
PLAN_ROLE = "arn:aws:iam::851725597758:role/GitHubBridgeFoundationPlanStaging"
EXECUTION_ROLE = "arn:aws:iam::851725597758:role/BridgeStagingFoundationExecution"
SESSION_ARN = (
    "arn:aws:sts::851725597758:assumed-role/"
    "GitHubBridgeFoundationPlanStaging/BridgeFoundationPlan-12345-1"
)
CHANGE_SET_ARN = (
    "arn:aws:cloudformation:us-west-2:851725597758:"
    "changeSet/bridge-staging-foundation-12345-1/example-id"
)
TAG_ONLY_CHANGE = {
    "LogicalResourceId": "JwtSigningSecret",
    "ResourceType": "AWS::SecretsManager::Secret",
    "Action": "Modify",
    "Replacement": "False",
    "Scope": ["Tags"],
    "Details": [{
        "Evaluation": "Static",
        "Target": {"Attribute": "Tags", "RequiresRecreation": "Never"},
    }],
}
MOCK_AWS = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with Path(os.environ["MOCK_CALLS"]).open("a") as out:
    out.write(json.dumps(args) + "\\n")
action = args[:2]
fail_at = os.environ.get("MOCK_FAIL_AT")
if action == ["sts", "get-caller-identity"]:
    print(os.environ.get("MOCK_IDENTITY", os.environ["EXPECTED_IDENTITY"]))
elif action == ["cloudformation", "validate-template"]:
    if fail_at == "validate":
        sys.exit("Mock template validation denied")
    print("Review-only staging template")
elif action == ["cloudformation", "create-change-set"]:
    if fail_at == "create":
        sys.exit("Mock change-set creation denied")
    print(os.environ.get("MOCK_CHANGE_SET", os.environ["EXPECTED_CHANGE_SET"]))
elif action == ["cloudformation", "wait"]:
    if args[2] != "change-set-create-complete":
        sys.exit("Unexpected waiter")
    if fail_at == "wait":
        sys.exit("Mock change-set preparation failed")
elif action == ["cloudformation", "describe-change-set"]:
    if fail_at == "describe":
        sys.exit("Mock describe denied")
    print(os.environ.get("MOCK_PREVIEW", json.dumps({
        "Status": "CREATE_COMPLETE", "ExecutionStatus": "AVAILABLE", "Changes": []
    })))
else:
    sys.exit("Forbidden AWS action")
"""


class FoundationPlan(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bridge-foundation-plan-")
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name)
        aws = directory / "aws"
        aws.write_text(MOCK_AWS)
        aws.chmod(0o700)
        self.calls_path = directory / "calls.jsonl"
        self.summary = directory / "summary.md"
        self.env = {
            "PATH": f"{directory}{os.pathsep}{os.defpath}",
            "GITHUB_REPOSITORY": "jmtelgen/NextLevelBridgeAPI",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "12345",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_STEP_SUMMARY": str(self.summary),
            "AWS_ACCOUNT_ID": "851725597758",
            "AWS_REGION": "us-west-2",
            "AWS_FOUNDATION_PLAN_ROLE_ARN": PLAN_ROLE,
            "AWS_FOUNDATION_EXECUTION_ROLE_ARN": EXECUTION_ROLE,
            "FOUNDATION_CHANGE_SET_TYPE": "CREATE",
            "AWS_CONFIG_FILE": "/dev/null",
            "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
            "AWS_EC2_METADATA_DISABLED": "true",
            "MOCK_CALLS": str(self.calls_path),
            "EXPECTED_IDENTITY": f"851725597758\t{SESSION_ARN}",
            "EXPECTED_CHANGE_SET": CHANGE_SET_ARN,
        }

    def run_script(self, mode="plan", updates=None):
        self.calls_path.unlink(missing_ok=True)
        self.summary.unlink(missing_ok=True)
        return subprocess.run(
            ["bash", str(SCRIPT), mode],
            env=self.env | (updates or {}),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def calls(self):
        if not self.calls_path.exists():
            return []
        return [json.loads(line) for line in self.calls_path.read_text().splitlines()]

    def test_validate_never_calls_aws(self):
        result = self.run_script("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.summary.exists())

    def test_invalid_configuration_stops_before_aws(self):
        invalid = {
            "GITHUB_REPOSITORY": "someone/NextLevelBridgeAPI",
            "GITHUB_REF": "refs/heads/deployment/github-staging-bootstrap",
            "GITHUB_SHA": "not-a-commit",
            "GITHUB_RUN_ID": "-1",
            "GITHUB_RUN_ATTEMPT": "1; echo unsafe",
            "GITHUB_STEP_SUMMARY": "",
            "AWS_ACCOUNT_ID": "000000000000",
            "AWS_REGION": "us-east-1",
            "AWS_FOUNDATION_PLAN_ROLE_ARN": "arn:aws:iam::851725597758:root",
            "AWS_FOUNDATION_EXECUTION_ROLE_ARN": PLAN_ROLE,
            "FOUNDATION_CHANGE_SET_TYPE": "CREATE; echo unsafe",
            "FOUNDATION_ALLOW_SECRET_TAG_UPDATE": "yes",
        }
        for key, value in invalid.items():
            with self.subTest(key=key):
                result = self.run_script(updates={key: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("::error::", result.stderr)
                self.assertEqual(self.calls(), [])

    def test_unknown_mode_is_rejected(self):
        result = self.run_script("execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_missing_configuration_stops_before_credentials(self):
        for key in (
            "AWS_ACCOUNT_ID",
            "AWS_REGION",
            "AWS_FOUNDATION_PLAN_ROLE_ARN",
            "AWS_FOUNDATION_EXECUTION_ROLE_ARN",
            "GITHUB_REPOSITORY",
            "GITHUB_REF",
            "GITHUB_SHA",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_STEP_SUMMARY",
            "FOUNDATION_CHANGE_SET_TYPE",
        ):
            with self.subTest(key=key):
                result = self.run_script("validate", updates={key: ""})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("::error::", result.stderr)
                self.assertEqual(self.calls(), [])

    def test_create_plans_only_the_exact_stack_and_execution_role(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(
            [call[:2] for call in calls],
            [
                ["sts", "get-caller-identity"],
                ["cloudformation", "validate-template"],
                ["cloudformation", "create-change-set"],
                ["cloudformation", "wait"],
                ["cloudformation", "describe-change-set"],
            ],
        )
        for call in calls:
            self.assertEqual(call[call.index("--region") + 1], "us-west-2")
            self.assertIn("--no-cli-pager", call)
        create = calls[2]
        for flag, value in {
            "--stack-name": "bridge-staging-foundation",
            "--change-set-name": "bridge-staging-foundation-12345-1",
            "--client-token": "bridge-staging-foundation-12345-1",
            "--change-set-type": "CREATE",
            "--role-arn": EXECUTION_ROLE,
            "--template-body": "file://deployment/staging-foundation.yaml",
        }.items():
            self.assertEqual(create[create.index(flag) + 1], value)
        self.assertNotIn("--capabilities", create)
        digest = hashlib.sha256(
            (ROOT / "deployment/staging-foundation.yaml").read_bytes()
        ).hexdigest()
        summary = self.summary.read_text()
        self.assertIn(digest, summary)
        self.assertIn("a" * 40, summary)
        self.assertIn(CHANGE_SET_ARN, summary)
        self.assertIn("No change set was executed", summary)

    def test_update_must_be_explicit(self):
        result = self.run_script(updates={"FOUNDATION_CHANGE_SET_TYPE": "UPDATE"})
        self.assertEqual(result.returncode, 0, result.stderr)
        create = self.calls()[2]
        self.assertEqual(create[create.index("--change-set-type") + 1], "UPDATE")

    def test_update_rejects_changes_to_the_preserved_secret(self):
        for action in ("Add", "Modify", "Remove", "Import", "Dynamic"):
            with self.subTest(action=action):
                preview = {
                    "Status": "CREATE_COMPLETE",
                    "ExecutionStatus": "AVAILABLE",
                    "Changes": [{
                        "LogicalResourceId": "JwtSigningSecret",
                        "ResourceType": "AWS::SecretsManager::Secret",
                        "Action": action,
                    }],
                }
                result = self.run_script(updates={
                    "FOUNDATION_CHANGE_SET_TYPE": "UPDATE",
                    "MOCK_PREVIEW": json.dumps(preview),
                })
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("must preserve JwtSigningSecret", result.stderr)
                self.assertFalse(self.summary.exists())
                self.assertEqual(len(self.calls()), 5)

    def test_update_accepts_missing_resource_additions(self):
        preview = {
            "Status": "CREATE_COMPLETE",
            "ExecutionStatus": "AVAILABLE",
            "Changes": [
                {"LogicalResourceId": name, "Action": "Add"}
                for name in (
                    "RoomsTable", "UsersTable", "ConnectionsTable",
                    "DuplicateEventsTable", "TickQueue", "TickDeadLetterQueue",
                )
            ],
        }
        result = self.run_script(updates={
            "FOUNDATION_CHANGE_SET_TYPE": "UPDATE",
            "MOCK_PREVIEW": json.dumps(preview),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.summary.exists())

    def test_secret_tags_only_metadata_requires_explicit_opt_in(self):
        preview = {
            "Status": "CREATE_COMPLETE",
            "ExecutionStatus": "AVAILABLE",
            "Changes": [TAG_ONLY_CHANGE],
        }
        for opt_in in ("false", "", "true"):
            with self.subTest(opt_in=opt_in):
                result = self.run_script(updates={
                    "FOUNDATION_CHANGE_SET_TYPE": "UPDATE",
                    "FOUNDATION_ALLOW_SECRET_TAG_UPDATE": opt_in,
                    "MOCK_PREVIEW": json.dumps(preview),
                })
                self.assertEqual(result.returncode == 0, opt_in == "true", result.stderr)
                self.assertEqual(self.summary.exists(), opt_in == "true")
                if opt_in == "true":
                    self.assertIn("tags-only metadata", result.stdout)
                    self.assertIn("metadata opt-in: true", self.summary.read_text())

    def test_opt_in_never_allows_secret_properties_or_ambiguous_changes(self):
        invalid = [
            {"Action": action} for action in ("Add", "Remove", "Import", "Dynamic")
        ] + [
            {"Replacement": value} for value in ("True", "Conditional", None, False)
        ] + [
            {"Scope": scope} for scope in (
                [], ["Properties"], ["Tags", "Properties"], ["Tags", "Tags"], None,
            )
        ] + [
            {"Details": details} for details in (
                None, [], {}, "Tags", [None], [{}],
                [{"Evaluation": "Dynamic", "Target": {"Attribute": "Tags", "RequiresRecreation": "Never"}}],
                [{"Target": {"Attribute": "Tags", "RequiresRecreation": "Never"}}],
                [{"Evaluation": "Static", "Target": None}],
                [{"Evaluation": "Static", "Target": {"Attribute": "Tags"}}],
                [{"Evaluation": "Static", "Target": {"RequiresRecreation": "Never"}}],
                [{"Evaluation": "Static", "Target": {"Attribute": "Properties", "RequiresRecreation": "Never"}}],
                [{"Evaluation": "Static", "Target": {"Attribute": "Tags", "RequiresRecreation": "Conditionally"}}],
                TAG_ONLY_CHANGE["Details"] + [{"Evaluation": "Dynamic"}],
            )
        ] + [{"ResourceType": "AWS::SSM::Parameter"}]
        invalid_changes = [TAG_ONLY_CHANGE | changes for changes in invalid]
        for key in ("Action", "ResourceType", "Replacement", "Scope", "Details"):
            invalid_changes.append({
                name: value for name, value in TAG_ONLY_CHANGE.items() if name != key
            })
        for change in invalid_changes:
            with self.subTest(change=change):
                preview = {
                    "Status": "CREATE_COMPLETE",
                    "ExecutionStatus": "AVAILABLE",
                    "Changes": [change],
                }
                result = self.run_script(updates={
                    "FOUNDATION_CHANGE_SET_TYPE": "UPDATE",
                    "FOUNDATION_ALLOW_SECRET_TAG_UPDATE": "true",
                    "MOCK_PREVIEW": json.dumps(preview),
                })
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("must preserve JwtSigningSecret", result.stderr)
                self.assertFalse(self.summary.exists())

    def test_invalid_or_unavailable_previews_are_not_successful(self):
        for preview in (
            "not JSON", "null", "{}",
            '{"Status":"FAILED","ExecutionStatus":"UNAVAILABLE","Changes":[]}',
            '{"Status":"CREATE_COMPLETE","ExecutionStatus":"AVAILABLE","Changes":null}',
            '{"Status":"CREATE_COMPLETE","ExecutionStatus":"AVAILABLE","Changes":[{}]}',
        ):
            with self.subTest(preview=preview):
                result = self.run_script(updates={"MOCK_PREVIEW": preview})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("::error::", result.stderr)
                self.assertFalse(self.summary.exists())

    def test_unexpected_identity_stops_before_cloudformation(self):
        for identity in (
            "851725597758\tarn:aws:iam::851725597758:root",
            f"000000000000\t{SESSION_ARN}",
            f"851725597758\t{SESSION_ARN.replace('-12345-1', '-12345-2')}",
            f"851725597758\t{SESSION_ARN.replace('FoundationPlanStaging', 'AppStaging')}",
        ):
            with self.subTest(identity=identity):
                result = self.run_script(updates={"MOCK_IDENTITY": identity})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(
                    [call[:2] for call in self.calls()], [["sts", "get-caller-identity"]]
                )

    def test_unexpected_change_set_arn_stops_before_waiting(self):
        for arn in (
            "None",
            CHANGE_SET_ARN.replace("us-west-2", "us-east-1"),
            CHANGE_SET_ARN.replace("851725597758", "000000000000"),
            CHANGE_SET_ARN.replace("foundation-12345-1", "foundation-other"),
            CHANGE_SET_ARN.rsplit("/", 1)[0] + "/",
        ):
            with self.subTest(arn=arn):
                result = self.run_script(updates={"MOCK_CHANGE_SET": arn})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.calls()), 3)
                self.assertFalse(self.summary.exists())

    def test_aws_failures_are_not_successful_plans(self):
        for failure in ("validate", "create", "wait", "describe"):
            with self.subTest(failure=failure):
                result = self.run_script(updates={"MOCK_FAIL_AT": failure})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.summary.exists())
                self.assertFalse(
                    any("execute-change-set" in call for call in self.calls())
                )

    def test_manual_workflow_has_main_only_environment_and_precise_permissions(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/staging-foundation-plan.yml").read_text(),
            Loader=yaml.BaseLoader,
        )
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {})
        self.assertEqual(
            workflow["on"]["workflow_dispatch"]["inputs"]["change_set_type"]["options"],
            ["CREATE", "UPDATE"],
        )
        tag_opt_in = workflow["on"]["workflow_dispatch"]["inputs"]["allow_secret_tag_update"]
        self.assertEqual(tag_opt_in["type"], "boolean")
        self.assertEqual(tag_opt_in["default"], "false")
        job = workflow["jobs"]["plan"]
        self.assertEqual(
            job["if"],
            "github.repository == 'jmtelgen/NextLevelBridgeAPI' && github.ref == 'refs/heads/main'",
        )
        self.assertEqual(job["environment"], "staging")
        self.assertEqual(job["permissions"], {"contents": "read", "id-token": "write"})
        self.assertNotIn("AWS_STAGING_ROLE_ARN", job["env"])
        steps = job["steps"]
        self.assertEqual(
            steps[1]["run"], "bash .github/scripts/plan_staging_foundation.sh validate"
        )
        self.assertTrue(steps[2]["uses"].startswith("aws-actions/configure-aws-credentials@"))
        self.assertEqual(steps[2]["with"]["output-credentials"], "false")
        self.assertEqual(
            steps[3]["run"], "bash .github/scripts/plan_staging_foundation.sh plan"
        )
        for step in steps:
            if "uses" in step:
                self.assertRegex(step["uses"], r"^[^@]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
