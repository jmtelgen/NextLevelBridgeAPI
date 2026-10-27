#!/usr/bin/env python3
"""Offline staging platform, application and review-gate contracts."""
import copy
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import zipfile

import yaml


ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load("application_template", "deployment/application_template.py")
planner = load("application_planner", ".github/scripts/plan_staging_application.py")


class ApplicationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.platform = yaml.safe_load((ROOT / "deployment/staging-platform.yaml").read_text())
        cls.app = generator.application_template("a" * 64)
        cls.scheduling = yaml.safe_load((ROOT / "deployment/staging-scheduling.yaml").read_text())

    def test_private_versioned_buckets_and_no_public_alias(self):
        for name in ("WebBucket", "ArtifactBucket"):
            props = self.platform["Resources"][name]["Properties"]
            self.assertEqual(props["VersioningConfiguration"], {"Status": "Enabled"})
            self.assertTrue(all(props["PublicAccessBlockConfiguration"].values()))
        distribution = self.platform["Resources"]["Distribution"]["Properties"]["DistributionConfig"]
        self.assertNotIn("Aliases", distribution)
        for error in distribution["CustomErrorResponses"]:
            self.assertEqual(error["ErrorCachingMinTTL"], 0)
            self.assertNotIn("ResponsePagePath", error)
            self.assertNotIn("ResponseCode", error)
        self.assertEqual(distribution["ViewerCertificate"], {"CloudFrontDefaultCertificate": True})
        self.assertEqual(distribution["DefaultCacheBehavior"]["FunctionAssociations"][0]["EventType"], "viewer-request")
        for behavior in distribution["CacheBehaviors"]:
            self.assertNotIn("FunctionAssociations", behavior)
            self.assertEqual(behavior["CachePolicyId"], {"Ref": "ApiCache"})
        cache = self.platform["Resources"]["ApiCache"]["Properties"]["CachePolicyConfig"]
        self.assertEqual([cache[key] for key in ("MinTTL", "DefaultTTL", "MaxTTL")], [0, 0, 0])

    def test_archive_table_is_retained_and_matches_transaction_adapter(self):
        resource = self.platform["Resources"]["BoardArchives"]
        self.assertEqual(resource["DeletionPolicy"], "Retain")
        self.assertEqual(resource["Properties"]["TableName"], "bridge-staging-board-archives")
        self.assertEqual(resource["Properties"]["AttributeDefinitions"], [
            {"AttributeName": "roomId", "AttributeType": "S"},
            {"AttributeName": "boardNumber", "AttributeType": "N"},
        ])
        self.assertTrue(resource["Properties"]["DeletionProtectionEnabled"])
        self.assertNotIn("TimeToLiveSpecification", resource["Properties"])

    def test_every_handler_has_code_logs_and_no_reserved_environment_override(self):
        functions = [resource for resource in self.app["Resources"].values() if resource["Type"] == "AWS::Lambda::Function"]
        self.assertEqual(len(functions), 22)
        for function in functions:
            props = function["Properties"]
            self.assertEqual(props["Runtime"], "python3.12")
            self.assertEqual(props["Architectures"], ["x86_64"])
            self.assertEqual(props["Code"]["S3ObjectVersion"], {"Ref": "ArtifactVersion"})
            variables = props["Environment"]["Variables"]
            self.assertEqual(variables["JWT_SECRET_ID"], "bridge-staging-jwt-v2")
            self.assertEqual(variables["ENVIRONMENT"], "production")
            self.assertNotIn("AWS_REGION", variables)
            self.assertNotIn("AWS_DEFAULT_REGION", variables)
            self.assertTrue(function["DependsOn"])
        encoded = json.dumps(self.app)
        for forbidden in ('"AWS::IAM::', '"AWS::SecretsManager::', '"AWS::DynamoDB::', '"AWS::Lambda::EventSourceMapping"'):
            self.assertNotIn(forbidden, encoded)

    def test_exact_routes_and_one_way_websocket_responses(self):
        resources = list(self.app["Resources"].values())
        methods = [resource["Properties"] for resource in resources if resource["Type"] == "AWS::ApiGateway::Method"]
        self.assertEqual(sum(method["HttpMethod"] != "OPTIONS" for method in methods), 6)
        self.assertEqual(sum(resource["Type"] == "AWS::ApiGatewayV2::Route" for resource in resources), 30)
        self.assertFalse(any(resource["Type"] == "AWS::ApiGatewayV2::RouteResponse" for resource in resources))
        for method in methods:
            if method["HttpMethod"] != "OPTIONS":
                self.assertEqual(method["Integration"]["Type"], "AWS_PROXY")

    def test_scheduling_is_opt_in_bounded_and_separate(self):
        self.assertEqual(self.scheduling["Parameters"]["ConsumersEnabled"]["Default"], "false")
        mappings = self.scheduling["Resources"]
        stream = mappings["RoomTickDispatcher"]["Properties"]
        worker = mappings["GameTickWorker"]["Properties"]
        self.assertEqual(stream["StartingPosition"], "LATEST")
        self.assertEqual(stream["MaximumRetryAttempts"], 3)
        self.assertIn("OnFailure", stream["DestinationConfig"])
        self.assertEqual(worker["MaximumBatchingWindowInSeconds"], 0)
        self.assertEqual(worker["BatchSize"], 1)
        for mapping in mappings.values():
            self.assertEqual(mapping["Properties"]["FunctionResponseTypes"], ["ReportBatchItemFailures"])

    def test_plan_and_executor_cannot_escalate_or_read_signing_material(self):
        resources = self.platform["Resources"]
        for name in ("ApplicationPlanRole", "ApplicationExecutionRole"):
            statements = resources[name]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
            actions = {
                action for statement in statements
                for action in (statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]])
            }
            self.assertNotIn("cloudformation:ExecuteChangeSet", actions)
            self.assertFalse(any(action.startswith("secretsmanager:") for action in actions))
            self.assertEqual({action for action in actions if action.startswith("iam:")}, {"iam:PassRole"})
            self.assertFalse(any("EventSourceMapping" in action for action in actions))

    def test_create_preview_is_complete_and_correctly_typed(self):
        changes = [
            {"LogicalResourceId": name, "ResourceType": resource["Type"], "Action": "Add"}
            for name, resource in self.app["Resources"].items()
        ]
        planner.validate_preview(changes, self.app, "CREATE")
        invalid = [changes[:-1], changes + changes[:1]]
        for field, value in (("Action", "Modify"), ("ResourceType", "AWS::IAM::Role"), ("Replacement", "True")):
            altered = copy.deepcopy(changes)
            altered[0][field] = value
            invalid.append(altered)
        for preview in invalid:
            with self.assertRaises(ValueError):
                planner.validate_preview(preview, self.app, "CREATE")

    def test_only_retained_api_snapshots_can_leave_stack(self):
        removal = {
            "LogicalResourceId": "RestDeployment" + "b" * 16,
            "ResourceType": "AWS::ApiGateway::Deployment", "Action": "Remove", "PolicyAction": "Retain",
        }
        planner.validate_preview([removal], self.app, "UPDATE")
        for overrides in ({"PolicyAction": "Delete"}, {"PolicyAction": None}, {"LogicalResourceId": "OldFunction"}):
            with self.assertRaises(ValueError):
                planner.validate_preview([removal | overrides], self.app, "UPDATE")

    def test_invalid_release_digest_rejected(self):
        for digest in ("", "a" * 63, "Z" * 64):
            with self.assertRaises(ValueError):
                generator.application_template(digest)

    def test_artifact_receipt_and_root_session_fail_before_writes(self):
        manifest_path = ROOT / "deployment/runtime-routes.json"
        manifest = json.loads(manifest_path.read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            package = path / "initial.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("marker.txt", "x")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            package = package.rename(path / f"bridge-staging-{digest}.zip")
            metadata = {
                "sha256": digest, "artifact": package.name,
                "codeSha256": base64.b64encode(bytes.fromhex(digest)).decode(),
                "uncompressedBytes": 1, "memberCount": 1,
                "routeManifestSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "dependencyLockSha256": hashlib.sha256((ROOT / "deployment/package/requirements.lock").read_bytes()).hexdigest(),
                "nativeSourceSha256": hashlib.sha256((ROOT / "deployment/package/native-source.json").read_bytes()).hexdigest(),
            }
            report = {
                "artifactSha256": digest, "runtime": "python3.12", "architecture": "x86_64",
                "os": "AL2023", "receiptVerified": True, "durableBootstrap": True,
                "network": "denied", "nativeSolve": {"card": "SA", "tricks": 1},
                "runtimeImage": "test@sha256:" + "a" * 64,
                "entrypoints": sorted({
                    function[key] for function in manifest["functions"].values()
                    for key in ("handler", "entrypoint") if key in function
                }),
            }
            package.with_suffix(".json").write_text(json.dumps(metadata))
            receipt = package.with_suffix(".validation.json")
            receipt.write_text(json.dumps(report))
            self.assertEqual(planner.verified_artifact(path), (package, digest))
            for overrides in ({"receiptVerified": False}, {"receiptVerified": 1}, {"entrypoints": []},
                              {"artifactSha256": "b" * 64}, {"os": "Ubuntu"}):
                receipt.write_text(json.dumps(report | overrides))
                with self.assertRaises(ValueError):
                    planner.verified_artifact(path)
            receipt.write_text(json.dumps(report))
            environment = {
                "AWS_ACCOUNT_ID": planner.ACCOUNT, "AWS_REGION": planner.REGION,
                "AWS_APPLICATION_PLAN_ROLE_ARN": planner.ROLE,
                "GITHUB_REPOSITORY": "jmtelgen/NextLevelBridgeAPI",
                "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "22",
                "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "1" * 40,
                "APPLICATION_CHANGE_SET_TYPE": "CREATE", "GITHUB_STEP_SUMMARY": str(path / "summary"),
            }
            with patch.object(planner, "aws", return_value={
                "Account": planner.ACCOUNT, "Arn": "arn:aws:iam::851725597758:root",
            }) as aws:
                with patch.object(planner, "put_version") as put:
                    with self.assertRaisesRegex(ValueError, "root and other roles"):
                        planner.plan(environment, path)
                put.assert_not_called()
                self.assertEqual(aws.call_count, 1)


if __name__ == "__main__":
    unittest.main()
