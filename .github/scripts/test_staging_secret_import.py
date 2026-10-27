#!/usr/bin/env python3
"""Offline recovery contracts; never access AWS, credentials, or secret values."""
import json
from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = "851725597758"
REGION = "us-west-2"
STACK = "bridge-staging-foundation"
SECRET_ARN = (
    "arn:aws:secretsmanager:us-west-2:851725597758:"
    "secret:bridge-staging-jwt-LzSRSY"
)


class SecretImportContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = yaml.safe_load(
            (ROOT / "deployment/staging-secret-import.yaml").read_text()
        )
        cls.foundation = yaml.safe_load(
            (ROOT / "deployment/staging-foundation.yaml").read_text()
        )
        cls.runbook = (ROOT / "docs/staging-secret-import.md").read_text()

    def test_exact_one_resource_and_no_executable_extensions(self):
        self.assertEqual(set(self.template), {
            "AWSTemplateFormatVersion", "Description", "Metadata", "Resources",
        })
        self.assertEqual(self.template["AWSTemplateFormatVersion"], "2010-09-09")
        self.assertEqual(set(self.template["Resources"]), {"JwtSigningSecret"})
        self.assertEqual(self.template["Metadata"], {
            "StagingTarget": {
                "AccountId": ACCOUNT, "Region": REGION, "ReviewOnly": True,
            },
        })
        secret = self.template["Resources"]["JwtSigningSecret"]
        self.assertEqual(set(secret), {
            "Type", "DeletionPolicy", "UpdateReplacePolicy", "Properties",
        })
        self.assertEqual(secret["Type"], "AWS::SecretsManager::Secret")
        self.assertEqual(secret["DeletionPolicy"], "Retain")
        self.assertEqual(secret["UpdateReplacePolicy"], "Retain")

    def test_secret_is_identical_in_both_phases(self):
        secret = self.template["Resources"]["JwtSigningSecret"]
        self.assertEqual(secret, self.foundation["Resources"]["JwtSigningSecret"])
        self.assertEqual(secret["Properties"], {
            "Name": "bridge-staging-jwt",
            "Description": (
                "Independent staging-only HS256 signing material; never output the value."
            ),
            "GenerateSecretString": {
                "SecretStringTemplate": "{}",
                "GenerateStringKey": "jwt_secret",
                "PasswordLength": 64,
                "ExcludePunctuation": True,
            },
        })

    def test_no_values_outputs_dynamic_references_or_permissions(self):
        encoded = json.dumps(self.template)
        for forbidden in (
            '"SecretString"', '"SecretBinary"', "{{resolve:", '"Outputs"',
            '"Parameters"', '"Transform"', '"Conditions"', '"Fn::', '"Ref"',
            '"PolicyDocument"', "GetSecretValue", "PutSecretValue", "UpdateSecret",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

    def test_exact_console_identifier_mapping(self):
        mappings = re.findall(r"```json\n(.*?)\n```", self.runbook, re.S)
        self.assertEqual(len(mappings), 1)
        self.assertEqual(json.loads(mappings[0]), [{
            "ResourceType": "AWS::SecretsManager::Secret",
            "LogicalResourceId": "JwtSigningSecret",
            "ResourceIdentifier": {"Id": SECRET_ARN},
        }])
        for expected in (
            ACCOUNT, REGION, STACK,
            f"arn:aws:iam::{ACCOUNT}:role/BridgeStagingFoundationExecution",
            "**With existing resources (import resources)**",
            "Application=Bridge", "Environment=staging",
            "IMPORT_COMPLETE", "Do not use CREATE after import",
            "No live import was performed or validated",
            "No Modify, Replace, Remove/Delete",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.runbook)

    def test_full_update_adds_only_four_tables_and_two_standard_queues(self):
        remaining = {
            name: value["Type"]
            for name, value in self.foundation["Resources"].items()
            if name != "JwtSigningSecret"
        }
        self.assertEqual(remaining, {
            "RoomsTable": "AWS::DynamoDB::Table",
            "UsersTable": "AWS::DynamoDB::Table",
            "ConnectionsTable": "AWS::DynamoDB::Table",
            "DuplicateEventsTable": "AWS::DynamoDB::Table",
            "TickDeadLetterQueue": "AWS::SQS::Queue",
            "TickQueue": "AWS::SQS::Queue",
        })
        for name in ("TickQueue", "TickDeadLetterQueue"):
            self.assertNotIn("FifoQueue", self.foundation["Resources"][name]["Properties"])

    def test_plan_remains_create_update_only_with_matching_tags(self):
        plan = (ROOT / ".github/scripts/plan_staging_foundation.sh").read_text()
        mode = re.search(
            r'case "\$\{FOUNDATION_CHANGE_SET_TYPE:-\}" in\n(.*?)\nesac',
            plan, re.S,
        )
        self.assertIsNotNone(mode)
        self.assertIn("CREATE|UPDATE) ;;", mode.group(1))
        self.assertNotIn("IMPORT", mode.group(1))
        self.assertIn(
            "--tags Key=Application,Value=Bridge Key=Environment,Value=staging",
            plan,
        )
        self.assertNotRegex(
            plan, r"aws\s+\S+\s+(execute-change-set|delete-stack|import-stacks)\b"
        )
        policy = json.loads((ROOT / "deployment/foundation-plan-policy.json").read_text())
        actions = set()
        for statement in policy["Statement"]:
            value = statement["Action"]
            actions.update([value] if isinstance(value, str) else value)
        self.assertFalse(actions & {
            "cloudformation:ExecuteChangeSet", "cloudformation:DeleteStack",
            "cloudformation:ImportStacksToStackSet", "secretsmanager:GetSecretValue",
        })

    def test_provider_read_does_not_authorize_secret_rewrite(self):
        policy = json.loads(
            (ROOT / "deployment/foundation-execution-policy.json").read_text()
        )
        actions = set()
        for statement in policy["Statement"]:
            value = statement["Action"]
            actions.update([value] if isinstance(value, str) else value)
        self.assertIn("secretsmanager:GetSecretValue", actions)
        self.assertIn("secretsmanager:DescribeSecret", actions)
        self.assertNotIn("secretsmanager:UpdateSecret", actions)
        self.assertNotIn("secretsmanager:PutSecretValue", actions)


if __name__ == "__main__":
    unittest.main()
