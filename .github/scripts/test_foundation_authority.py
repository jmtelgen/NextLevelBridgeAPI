#!/usr/bin/env python3
"""Offline IAM contract checks; not an IAM simulator or a live authorization test."""
from collections import defaultdict
from fnmatch import fnmatchcase
import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = "851725597758"
REGION = "us-west-2"
STACK = f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/bridge-staging-foundation/*"
CHANGE_NAME = "bridge-staging-foundation-?*-?*"
CHANGE_ARN = (
    f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:changeSet/{CHANGE_NAME}/*"
)
EXECUTION_ROLE = f"arn:aws:iam::{ACCOUNT}:role/BridgeStagingFoundationExecution"
SECRET = f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:bridge-staging-jwt-v2-??????"
INDEX = (
    f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/"
    "bridge-staging-users/index/username-email-index"
)
TABLES = {
    f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/bridge-staging-{suffix}"
    for suffix in ("rooms", "users", "connections", "duplicate-events")
}
QUEUES = {
    f"arn:aws:sqs:{REGION}:{ACCOUNT}:bridge-staging-game-tick{suffix}"
    for suffix in ("", "-dlq-v2")
}
TABLE_ACTIONS = {
    "dynamodb:CreateTable",
    "dynamodb:UpdateTable",
    "dynamodb:UpdateContinuousBackups",
    "dynamodb:DescribeTable",
    "dynamodb:DescribeContinuousBackups",
    "dynamodb:DescribeContributorInsights",
    "dynamodb:DescribeKinesisStreamingDestination",
    "dynamodb:DescribeTimeToLive",
    "dynamodb:GetResourcePolicy",
    "dynamodb:ListTagsOfResource",
    "dynamodb:TagResource",
}
QUEUE_ACTIONS = {
    "sqs:CreateQueue",
    "sqs:GetQueueUrl",
    "sqs:GetQueueAttributes",
    "sqs:SetQueueAttributes",
    "sqs:ListQueueTags",
    "sqs:TagQueue",
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_contract(name):
    return json.loads(
        (ROOT / "deployment" / f"foundation-{name}.json").read_text(),
        object_pairs_hook=unique_object,
    )


def as_list(value):
    return value if isinstance(value, list) else [value]


class FoundationAuthority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = {
            name: load_contract(name)
            for name in (
                "plan-trust", "plan-policy", "execution-trust", "execution-policy"
            )
        }
        cls.template = yaml.safe_load(
            (ROOT / "deployment/staging-foundation.yaml").read_text()
        )

    def statements(self, name):
        return self.contracts[name]["Statement"]

    def grants(self, name):
        grants = defaultdict(set)
        for statement in self.statements(name):
            for action in as_list(statement["Action"]):
                grants[action].update(as_list(statement["Resource"]))
        return dict(grants)

    def test_strict_json_and_allow_only_policy_structure(self):
        for name, contract in self.contracts.items():
            with self.subTest(contract=name):
                self.assertEqual(set(contract), {"Version", "Statement"})
                self.assertEqual(contract["Version"], "2012-10-17")
                self.assertIsInstance(contract["Statement"], list)
                self.assertTrue(contract["Statement"])
                self.assertNotIn("${", json.dumps(contract))
                if name.endswith("trust"):
                    continue
                sids = []
                for statement in contract["Statement"]:
                    self.assertEqual(
                        set(statement),
                        {"Sid", "Effect", "Action", "Resource", "Condition"},
                    )
                    sids.append(statement["Sid"])
                    self.assertEqual(statement["Effect"], "Allow")
                    for field in ("Action", "Resource"):
                        values = as_list(statement[field])
                        self.assertTrue(values)
                        self.assertEqual(len(values), len(set(values)))
                        self.assertTrue(all(isinstance(v, str) for v in values))
                    for action in as_list(statement["Action"]):
                        self.assertNotRegex(action, r"[*?]")
                self.assertEqual(len(sids), len(set(sids)))

    def test_exact_github_oidc_trust(self):
        self.assertEqual(self.statements("plan-trust"), [{
            "Effect": "Allow",
            "Principal": {
                "Federated": f"arn:aws:iam::{ACCOUNT}:oidc-provider/"
                             "token.actions.githubusercontent.com",
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    "token.actions.githubusercontent.com:sub":
                        "repo:jmtelgen/NextLevelBridgeAPI:environment:staging",
                },
            },
        }])

    def test_exact_cloudformation_service_trust_without_guessed_context(self):
        self.assertEqual(self.statements("execution-trust"), [{
            "Effect": "Allow",
            "Principal": {"Service": "cloudformation.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }])

    def test_plan_has_only_required_actions_and_correct_resource_types(self):
        self.assertEqual(self.grants("plan-policy"), {
            "cloudformation:ValidateTemplate": {"*"},
            "cloudformation:CreateChangeSet": {STACK},
            "cloudformation:DescribeChangeSet": {STACK},
            "cloudformation:TagResource": {STACK, CHANGE_ARN},
            "cloudformation:UntagResource": {STACK, CHANGE_ARN},
            "iam:PassRole": {EXECUTION_ROLE},
        })
        self.assertEqual(len(self.statements("plan-policy")), 6)

    def test_plan_conditions_are_action_specific(self):
        expected = {
            "cloudformation:ValidateTemplate": {
                "StringEquals": {"aws:RequestedRegion": REGION},
                "Null": {"cloudformation:TemplateUrl": "true"},
            },
            "cloudformation:CreateChangeSet": {
                "StringEquals": {
                    "aws:RequestedRegion": REGION,
                    "cloudformation:RoleArn": EXECUTION_ROLE,
                    "aws:RequestTag/Application": "Bridge",
                    "aws:RequestTag/Environment": "staging",
                },
                "StringLike": {"cloudformation:ChangeSetName": CHANGE_NAME},
                "ForAllValues:StringEquals": {
                    "aws:TagKeys": ["Application", "Environment"],
                },
                "Null": {"cloudformation:TemplateUrl": "true"},
            },
            "cloudformation:TagResource": {
                "StringEquals": {
                    "aws:RequestedRegion": REGION,
                    "cloudformation:CreateAction": "CreateChangeSet",
                    "aws:RequestTag/Application": "Bridge",
                    "aws:RequestTag/Environment": "staging",
                },
                "ForAllValues:StringEquals": {
                    "aws:TagKeys": ["Application", "Environment"],
                },
            },
            "cloudformation:UntagResource": {
                "StringEquals": {
                    "aws:RequestedRegion": REGION,
                    "cloudformation:CreateAction": "CreateChangeSet",
                },
                "ForAllValues:StringEquals": {
                    "aws:TagKeys": ["Application", "Environment"],
                },
                "Null": {"aws:TagKeys": "false"},
            },
            "cloudformation:DescribeChangeSet": {
                "StringEquals": {"aws:RequestedRegion": REGION},
            },
            "iam:PassRole": {
                "StringEquals": {"iam:PassedToService": "cloudformation.amazonaws.com"},
            },
        }
        for statement in self.statements("plan-policy"):
            for action in as_list(statement["Action"]):
                with self.subTest(action=action):
                    self.assertEqual(statement["Condition"], expected[action])

    def test_waiter_describe_requires_only_stack_and_region_context(self):
        statements = [
            statement for statement in self.statements("plan-policy")
            if "cloudformation:DescribeChangeSet" in as_list(statement["Action"])
        ]
        self.assertEqual(len(statements), 1)
        statement = statements[0]
        self.assertEqual(statement["Resource"], STACK)
        self.assertEqual(
            statement["Condition"],
            {"StringEquals": {"aws:RequestedRegion": REGION}},
        )
        self.assertNotIn("ChangeSetName", json.dumps(statement))
        self.assertNotIn("RoleArn", json.dumps(statement))

    def test_execution_has_only_management_metadata_and_scoped_provider_read(self):
        expected = {action: TABLES.copy() for action in TABLE_ACTIONS}
        expected["dynamodb:DescribeContributorInsights"].add(INDEX)
        expected.update({action: QUEUES.copy() for action in QUEUE_ACTIONS})
        expected.update({
            "secretsmanager:CreateSecret": {SECRET},
            "secretsmanager:DescribeSecret": {SECRET},
            "secretsmanager:TagResource": {SECRET},
            "secretsmanager:GetSecretValue": {SECRET},
            "secretsmanager:GetRandomPassword": {"*"},
        })
        self.assertEqual(self.grants("execution-policy"), expected)
        self.assertEqual(len(self.statements("execution-policy")), 7)

    def test_secret_value_read_is_only_a_service_trusted_provider_permission(self):
        matching = [
            statement for statement in self.statements("execution-policy")
            if "secretsmanager:GetSecretValue" in as_list(statement["Action"])
        ]
        self.assertEqual(matching, [{
            "Sid": "AllowCloudFormationProviderReadOfOnlyFoundationSecret",
            "Effect": "Allow",
            "Action": "secretsmanager:GetSecretValue",
            "Resource": SECRET,
            "Condition": {"StringEquals": {"aws:RequestedRegion": REGION}},
        }])
        self.assertFalse(any(
            action.startswith("secretsmanager:")
            for action in self.grants("plan-policy")
        ))
        self.assertEqual(self.statements("execution-trust"), [{
            "Effect": "Allow",
            "Principal": {"Service": "cloudformation.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }])
        for name in ("plan-policy", "execution-policy"):
            self.assertNotIn("sts:AssumeRole", self.grants(name))
        for other in (
            SECRET.replace("bridge-staging-jwt", "bridge-staging-jwt-other"),
            SECRET.replace(REGION, "us-east-1"),
            SECRET.replace(ACCOUNT, "111122223333"),
        ):
            self.assertFalse(fnmatchcase(other, SECRET))

    def test_execution_conditions_and_wildcard_exceptions(self):
        for statement in self.statements("execution-policy"):
            actions = as_list(statement["Action"])
            conditions = {"StringEquals": {"aws:RequestedRegion": REGION}}
            if "secretsmanager:CreateSecret" in actions:
                self.assertEqual(actions, ["secretsmanager:CreateSecret"])
                conditions["StringEquals"]["secretsmanager:Name"] = "bridge-staging-jwt-v2"
            self.assertEqual(statement["Condition"], conditions)
            for resource in as_list(statement["Resource"]):
                if resource == "*":
                    self.assertEqual(actions, ["secretsmanager:GetRandomPassword"])
                else:
                    self.assertIn(f":{REGION}:{ACCOUNT}:", resource)
                    self.assertNotIn("*", resource)
                    if "?" in resource:
                        self.assertEqual(resource, SECRET)
        for name in ("plan-policy", "execution-policy"):
            for statement in self.statements(name):
                if "*" in as_list(statement["Resource"]):
                    self.assertEqual(
                        as_list(statement["Action"]),
                        ["cloudformation:ValidateTemplate"]
                        if name == "plan-policy"
                        else ["secretsmanager:GetRandomPassword"],
                    )

    def test_retained_legacy_secret_and_dlq_are_outside_execution_scope(self):
        grants = self.grants("execution-policy")
        legacy_secret = (
            f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:"
            "secret:bridge-staging-jwt-LzSRSY"
        )
        for action in (
            "secretsmanager:CreateSecret", "secretsmanager:DescribeSecret",
            "secretsmanager:TagResource", "secretsmanager:GetSecretValue",
        ):
            self.assertFalse(any(
                fnmatchcase(legacy_secret, resource) for resource in grants[action]
            ))
        legacy_dlq = f"arn:aws:sqs:{REGION}:{ACCOUNT}:bridge-staging-game-tick-dlq"
        for action in QUEUE_ACTIONS:
            self.assertNotIn(legacy_dlq, grants[action])

    def test_no_execution_deletion_other_data_plane_or_escalation_grants(self):
        forbidden = {
            "cloudformation:ExecuteChangeSet", "cloudformation:CreateStack",
            "cloudformation:UpdateStack", "cloudformation:DeleteStack",
            "cloudformation:DeleteChangeSet",
            "dynamodb:Scan", "dynamodb:Query", "dynamodb:GetItem", "dynamodb:PutItem",
            "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchGetItem",
            "dynamodb:BatchWriteItem", "dynamodb:TransactGetItems",
            "dynamodb:TransactWriteItems", "dynamodb:DeleteTable",
            "dynamodb:RestoreTableToPointInTime", "dynamodb:PutResourcePolicy",
            "dynamodb:GetRecords", "dynamodb:GetShardIterator",
            "sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage",
            "sqs:PurgeQueue", "sqs:DeleteQueue", "sqs:StartMessageMoveTask",
            "secretsmanager:BatchGetSecretValue",
            "secretsmanager:PutSecretValue", "secretsmanager:UpdateSecret",
            "secretsmanager:DeleteSecret", "secretsmanager:PutResourcePolicy",
            "secretsmanager:ReplicateSecretToRegions", "iam:CreateRole",
            "iam:AttachRolePolicy", "iam:PutRolePolicy", "sts:AssumeRole",
        }
        for name in ("plan-policy", "execution-policy"):
            actions = set(self.grants(name))
            self.assertFalse(actions & forbidden)
            self.assertFalse(any(
                action.startswith(("kms:", "s3:", "lambda:", "apigateway:", "execute-api:"))
                for action in actions
            ))
            for action in actions:
                self.assertFalse(action.split(":")[1].startswith(("Delete", "Purge")))
            self.assertEqual(
                {action for action in actions if action.startswith("iam:")},
                {"iam:PassRole"} if name == "plan-policy" else set(),
            )

    def test_arn_patterns_do_not_match_other_targets(self):
        self.assertTrue(fnmatchcase(
            f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/"
            "bridge-staging-foundation/stack-id", STACK,
        ))
        for other in (
            STACK.replace("bridge-staging-foundation/", "bridge-staging-foundation-other/"),
            STACK.replace(REGION, "us-east-1"),
            STACK.replace(ACCOUNT, "111122223333"),
        ):
            self.assertFalse(fnmatchcase(other, STACK))
        self.assertTrue(fnmatchcase("bridge-staging-foundation-123456-2", CHANGE_NAME))
        self.assertTrue(fnmatchcase(
            f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:changeSet/"
            "bridge-staging-foundation-123456-2/id", CHANGE_ARN,
        ))
        for other in ("another-stack-123456-2", "bridge-staging-foundation-123456"):
            self.assertFalse(fnmatchcase(other, CHANGE_NAME))
        self.assertTrue(fnmatchcase(SECRET.replace("??????", "Ab12Cd"), SECRET))
        for suffix in ("Ab12C", "Ab12CdE", "other-Ab12Cd"):
            self.assertFalse(fnmatchcase(SECRET.replace("??????", suffix), SECRET))

    def test_agreement_with_exact_retained_template_inventory(self):
        resources = self.template["Resources"]
        expected = {
            "RoomsTable": ("AWS::DynamoDB::Table", "TableName", "bridge-staging-rooms"),
            "UsersTable": ("AWS::DynamoDB::Table", "TableName", "bridge-staging-users"),
            "ConnectionsTable": (
                "AWS::DynamoDB::Table", "TableName", "bridge-staging-connections",
            ),
            "DuplicateEventsTable": (
                "AWS::DynamoDB::Table", "TableName", "bridge-staging-duplicate-events",
            ),
            "TickQueue": ("AWS::SQS::Queue", "QueueName", "bridge-staging-game-tick"),
            "TickDeadLetterQueue": (
                "AWS::SQS::Queue", "QueueName", "bridge-staging-game-tick-dlq-v2",
            ),
            "JwtSigningSecret": (
                "AWS::SecretsManager::Secret", "Name", "bridge-staging-jwt-v2",
            ),
        }
        self.assertEqual(set(resources), set(expected))
        for logical_id, (kind, name_key, name) in expected.items():
            resource = resources[logical_id]
            self.assertEqual(resource["Type"], kind)
            self.assertEqual(resource["Properties"][name_key], name)
            self.assertEqual(resource["DeletionPolicy"], "Retain")
            self.assertEqual(resource["UpdateReplacePolicy"], "Retain")
        self.assertEqual(
            self.template["Metadata"]["StagingTarget"],
            {"AccountId": ACCOUNT, "Region": REGION, "ReviewOnly": True},
        )
        tables = {
            f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{r['Properties']['TableName']}"
            for r in resources.values() if r["Type"] == "AWS::DynamoDB::Table"
        }
        queues = {
            f"arn:aws:sqs:{REGION}:{ACCOUNT}:{r['Properties']['QueueName']}"
            for r in resources.values() if r["Type"] == "AWS::SQS::Queue"
        }
        self.assertEqual(tables, TABLES)
        self.assertEqual(queues, QUEUES)
        users = resources["UsersTable"]["Properties"]
        self.assertEqual(
            [index["IndexName"] for index in users["GlobalSecondaryIndexes"]],
            ["username-email-index"],
        )
        self.assertEqual(
            {name for name, resource in resources.items()
             if "StreamSpecification" in resource["Properties"]},
            {"RoomsTable"},
        )
        self.assertEqual(
            resources["RoomsTable"]["Properties"]["StreamSpecification"],
            {"StreamViewType": "NEW_IMAGE"},
        )

    def test_json_duplicate_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"Action":"safe","Action":"*"}', object_pairs_hook=unique_object)


if __name__ == "__main__":
    unittest.main(verbosity=2)
