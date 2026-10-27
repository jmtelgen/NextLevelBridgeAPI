#!/usr/bin/env python3
"""Offline contract checks: no application imports, credentials, or AWS calls."""
import json
from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "deployment" / "staging-foundation.yaml"


class FoundationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = yaml.safe_load(TEMPLATE.read_text())
        cls.resources = cls.template["Resources"]

    def properties(self, name):
        return self.resources[name]["Properties"]

    def test_exact_unprivileged_resource_inventory(self):
        self.assertEqual(
            {name: resource["Type"] for name, resource in self.resources.items()},
            {
                "RoomsTable": "AWS::DynamoDB::Table",
                "UsersTable": "AWS::DynamoDB::Table",
                "ConnectionsTable": "AWS::DynamoDB::Table",
                "DuplicateEventsTable": "AWS::DynamoDB::Table",
                "TickQueue": "AWS::SQS::Queue",
                "TickDeadLetterQueue": "AWS::SQS::Queue",
                "JwtSigningSecret": "AWS::SecretsManager::Secret",
            },
        )
        self.assertEqual(
            set(self.template),
            {"AWSTemplateFormatVersion", "Description", "Metadata", "Resources", "Outputs"},
        )
        self.assertEqual(self.template["AWSTemplateFormatVersion"], "2010-09-09")
        for resource in self.resources.values():
            self.assertEqual(
                set(resource), {"Type", "DeletionPolicy", "UpdateReplacePolicy", "Properties"}
            )

    def test_application_region_agrees_with_backend_access_guard(self):
        self.assertEqual(self.template["Metadata"], {
            "StagingTarget": {
                "AccountId": "851725597758",
                "Region": "us-west-2",
                "ReviewOnly": True,
            },
        })
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/staging-access-check.yml").read_text()
        )
        scripts = "\n".join(
            step.get("run", "") for step in workflow["jobs"]["identity"]["steps"]
        )
        guards = re.findall(
            r'if \[\[ "\$AWS_REGION" != "([^"]+)" \]\]; then\s+'
            r'echo "[^\n]+"\s+exit 1\s+fi',
            scripts,
        )
        self.assertEqual(guards, [self.template["Metadata"]["StagingTarget"]["Region"]])

    def test_fixed_isolated_names(self):
        expected = {
            "RoomsTable": ("TableName", "bridge-staging-rooms"),
            "UsersTable": ("TableName", "bridge-staging-users"),
            "ConnectionsTable": ("TableName", "bridge-staging-connections"),
            "DuplicateEventsTable": ("TableName", "bridge-staging-duplicate-events"),
            "TickQueue": ("QueueName", "bridge-staging-game-tick"),
            "TickDeadLetterQueue": ("QueueName", "bridge-staging-game-tick-dlq"),
            "JwtSigningSecret": ("Name", "bridge-staging-jwt"),
        }
        for name, (key, value) in expected.items():
            with self.subTest(resource=name):
                self.assertEqual(self.properties(name)[key], value)
        # No cross-stack imports, literal external ARNs or secret dynamic references.
        encoded = json.dumps(self.template)
        self.assertNotIn("Fn::ImportValue", encoded)
        self.assertNotIn("{{resolve:", encoded)
        self.assertNotRegex(encoded, r"arn:aws(?:-[a-z]+)?:")

    def test_exact_table_key_and_index_contracts(self):
        expected = {
            "RoomsTable": ("roomId", "ownerId"),
            "UsersTable": ("userId", "username"),
            "ConnectionsTable": ("connectionId", "currentRoomId"),
            "DuplicateEventsTable": ("eventId",),
        }
        for name, keys in expected.items():
            with self.subTest(table=name):
                props = self.properties(name)
                self.assertEqual(
                    props["KeySchema"],
                    [{"AttributeName": key, "KeyType": kind}
                     for key, kind in zip(keys, ("HASH", "RANGE"))],
                )
                attributes = (*keys, "email") if name == "UsersTable" else keys
                self.assertEqual(
                    props["AttributeDefinitions"],
                    [{"AttributeName": key, "AttributeType": "S"} for key in attributes],
                )
                allowed = {
                    "TableName", "BillingMode", "AttributeDefinitions", "KeySchema",
                    "SSESpecification", "PointInTimeRecoverySpecification",
                    "DeletionProtectionEnabled",
                }
                if name == "UsersTable":
                    allowed.add("GlobalSecondaryIndexes")
                if name == "RoomsTable":
                    allowed.add("StreamSpecification")
                self.assertEqual(set(props), allowed)
                self.assertNotIn("TimeToLiveSpecification", props)
        self.assertEqual(
            self.properties("UsersTable")["GlobalSecondaryIndexes"],
            [{
                "IndexName": "username-email-index",
                "KeySchema": [
                    {"AttributeName": "username", "KeyType": "HASH"},
                    {"AttributeName": "email", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
        )

    def test_only_rooms_have_new_image_stream(self):
        self.assertEqual(
            {name: resource["Properties"]["StreamSpecification"]
             for name, resource in self.resources.items()
             if "StreamSpecification" in resource["Properties"]},
            {"RoomsTable": {"StreamViewType": "NEW_IMAGE"}},
        )

    def test_persistent_data_is_retained_and_tables_are_protected(self):
        for name, resource in self.resources.items():
            with self.subTest(resource=name):
                self.assertEqual(resource["DeletionPolicy"], "Retain")
                self.assertEqual(resource["UpdateReplacePolicy"], "Retain")
                props = resource["Properties"]
                if resource["Type"] == "AWS::DynamoDB::Table":
                    self.assertEqual(props["BillingMode"], "PAY_PER_REQUEST")
                    self.assertEqual(props["SSESpecification"], {"SSEEnabled": True})
                    self.assertEqual(
                        props["PointInTimeRecoverySpecification"],
                        {"PointInTimeRecoveryEnabled": True},
                    )
                    self.assertIs(props["DeletionProtectionEnabled"], True)

    def test_standard_encrypted_queue_and_restricted_dlq(self):
        self.assertEqual(self.properties("TickQueue"), {
            "QueueName": "bridge-staging-game-tick",
            "FifoQueue": False,
            "SqsManagedSseEnabled": True,
            "DelaySeconds": 0,
            "ReceiveMessageWaitTimeSeconds": 20,
            "MessageRetentionPeriod": 345600,
            "VisibilityTimeout": 360,
            "RedrivePolicy": {
                "deadLetterTargetArn": {"Fn::GetAtt": ["TickDeadLetterQueue", "Arn"]},
                "maxReceiveCount": 5,
            },
        })
        self.assertEqual(self.properties("TickDeadLetterQueue"), {
            "QueueName": "bridge-staging-game-tick-dlq",
            "FifoQueue": False,
            "SqsManagedSseEnabled": True,
            "MessageRetentionPeriod": 1209600,
            "VisibilityTimeout": 360,
            "RedriveAllowPolicy": {
                "redrivePermission": "byQueue",
                "sourceQueueArns": [{
                    "Fn::Sub": "arn:${AWS::Partition}:sqs:${AWS::Region}:"
                              "${AWS::AccountId}:bridge-staging-game-tick"
                }],
            },
        })

    def test_generated_secret_has_no_value_or_identifier_output(self):
        self.assertEqual(self.properties("JwtSigningSecret"), {
            "Name": "bridge-staging-jwt",
            "Description": "Independent staging-only HS256 signing material; never output the value.",
            "GenerateSecretString": {
                "SecretStringTemplate": "{}",
                "GenerateStringKey": "jwt_secret",
                "PasswordLength": 64,
                "ExcludePunctuation": True,
            },
        })
        self.assertEqual(self.template["Outputs"], {
            "RoomTableName": {"Value": {"Ref": "RoomsTable"}},
            "RoomStreamArn": {"Value": {"Fn::GetAtt": ["RoomsTable", "StreamArn"]}},
            "UserTableName": {"Value": {"Ref": "UsersTable"}},
            "ConnectionsTableName": {"Value": {"Ref": "ConnectionsTable"}},
            "DuplicateEventsTableName": {"Value": {"Ref": "DuplicateEventsTable"}},
            "GameTickQueueUrl": {"Value": {"Ref": "TickQueue"}},
            "GameTickQueueArn": {"Value": {"Fn::GetAtt": ["TickQueue", "Arn"]}},
            "GameTickDeadLetterQueueUrl": {"Value": {"Ref": "TickDeadLetterQueue"}},
        })
        self.assertNotIn("JwtSigningSecret", json.dumps(self.template["Outputs"]))
        self.assertNotIn("jwt_secret", json.dumps(self.template["Outputs"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
