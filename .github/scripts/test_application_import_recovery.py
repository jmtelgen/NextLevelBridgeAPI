#!/usr/bin/env python3
"""Offline regression tests; optionally verify the exported bundle via RECOVERY_BUNDLE."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import mock_open, patch


SPEC = importlib.util.spec_from_file_location(
    "recovery", Path(__file__).with_name("application_import_recovery.py"))
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def template_pair():
    resources = {}
    for kind, count in recovery.COUNTS.items():
        for index in range(count):
            resources[f"Resource{len(resources)}"] = {
                "Type": kind, "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain", "Properties": {"Name": str(index)}}
    for logical, kind in (
        ("RestStage", "AWS::ApiGateway::Stage"),
        ("WebSocketStage", "AWS::ApiGatewayV2::Stage"),
        ("WebSocketDeployment" + recovery.ARTIFACT[:16], "AWS::ApiGatewayV2::Deployment"),
    ):
        resources[logical] = {
            "Type": kind, "DeletionPolicy": "Retain",
            "UpdateReplacePolicy": "Retain", "Properties": {}}
    full = {"Parameters": {key: {"Type": "String"} for key in recovery.PARAMETERS},
            "Resources": resources,
            "Outputs": {"ArtifactSha256": {"Value": recovery.ARTIFACT}}}
    imported = copy.deepcopy(full)
    for logical in recovery.ABSENT:
        del imported["Resources"][logical]
    return full, imported


def managed_fixture():
    full, imported = template_pair()
    recorded = [{"LogicalResourceId": key, "ResourceType": value["Type"],
                 "PhysicalResourceId": "physical-" + key}
                for key, value in full["Resources"].items()]
    values = [{"ParameterKey": key, "ParameterValue": value}
              for key, value in sorted(recovery.PARAMETERS.items())]
    payloads = {"full-template.json": full, "import-template.json": imported,
                "parameters.json": values, "snapshot.json": {"recorded": recorded}}
    stack = {"StackName": recovery.STACK, "StackStatus": "IMPORT_COMPLETE",
             "StackId": f"arn:aws:cloudformation:{recovery.REGION}:{recovery.ACCOUNT}:stack/{recovery.STACK}/new",
             "RoleARN": recovery.EXECUTION_ROLE, "Parameters": values,
             "Tags": [{"Key": "Application", "Value": "Bridge"},
                      {"Key": "Environment", "Value": "staging"}]}
    responses = {
        "describe-stacks": {"Stacks": [stack]},
        "get-template": {"TemplateBody": imported},
        "list-stack-resources": {"StackResourceSummaries": [
            item for item in recorded if item["LogicalResourceId"] not in recovery.ABSENT]},
    }
    return payloads, responses


class RecoveryTests(unittest.TestCase):
    def test_exact_three_resource_removal(self):
        recovery.validate_templates(*template_pair())

    def test_no_property_or_metadata_changes(self):
        full, imported = template_pair()
        imported["Resources"]["Resource0"]["Properties"]["Name"] = "changed"
        with self.assertRaisesRegex(ValueError, "changed original"):
            recovery.validate_templates(full, imported)

    def test_no_retention_weakening(self):
        full, imported = template_pair()
        full["Resources"]["Resource0"]["DeletionPolicy"] = "Delete"
        imported["Resources"]["Resource0"]["DeletionPolicy"] = "Delete"
        with self.assertRaisesRegex(ValueError, "retain"):
            recovery.validate_templates(full, imported)

    def test_no_unknown_types(self):
        full, imported = template_pair()
        for template in (full, imported):
            template["Resources"]["Resource0"]["Type"] = "AWS::IAM::Role"
        with self.assertRaisesRegex(ValueError, "resource graph"):
            recovery.validate_templates(full, imported)

    def test_no_public_resource_ids(self):
        for forbidden in recovery.FORBIDDEN:
            with self.subTest(forbidden=forbidden):
                full, imported = template_pair()
                for template in (full, imported):
                    template["Resources"]["Resource0"]["Properties"]["Name"] = forbidden
                with self.assertRaisesRegex(ValueError, "Public resource"):
                    recovery.validate_templates(full, imported)

    def test_dangling_references(self):
        for binding in ({"Ref": "RestStage"}, {"Fn::GetAtt": ["RestStage", "Arn"]},
                        {"Fn::Sub": "${RestStage.Arn}"}, {"DependsOn": "RestStage"}):
            full, imported = template_pair()
            for template in (full, imported):
                template["Resources"]["Resource0"]["Properties"]["Binding"] = binding
            with self.subTest(binding=binding), self.assertRaisesRegex(ValueError, "Dangling"):
                recovery.validate_templates(full, imported)

    def test_parameter_values_frozen(self):
        stack = {"Parameters": [{"ParameterKey": key, "ParameterValue": value}
                                for key, value in recovery.PARAMETERS.items()]}
        self.assertEqual(len(recovery.parameters(stack)), 7)
        stack["Parameters"][0]["ParameterValue"] = "different-release"
        with self.assertRaisesRegex(ValueError, "parameters changed"):
            recovery.parameters(stack)

    def test_identity_root_export_allowed(self):
        recovery.check_identity({"Account": recovery.ACCOUNT,
                                 "Arn": f"arn:aws:iam::{recovery.ACCOUNT}:root"})

    def test_wrong_account_rejected(self):
        with self.assertRaisesRegex(ValueError, "account"):
            recovery.check_identity({"Account": "000000000000", "Arn": "unexpected"})

    def test_plan_accepts_exact_account_iam_users_and_assumed_roles(self):
        for suffix in (
            f"iam::{recovery.ACCOUNT}:user/operator",
            f"iam::{recovery.ACCOUNT}:user/team/recovery.operator",
            f"sts::{recovery.ACCOUNT}:assumed-role/operator/CloudShell-session",
        ):
            with self.subTest(suffix=suffix):
                recovery.check_identity({"Account": recovery.ACCOUNT,
                                         "Arn": "arn:aws:" + suffix}, nonroot=True)

    def test_plan_rejects_root_federated_users_and_non_session_role_arns(self):
        for suffix in (
            f"iam::{recovery.ACCOUNT}:root",
            f"iam::{recovery.ACCOUNT}:role/operator",
            f"sts::{recovery.ACCOUNT}:federated-user/operator",
            f"iam::000000000000:user/operator",
            f"sts::000000000000:assumed-role/operator/session",
        ):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                recovery.check_identity({"Account": recovery.ACCOUNT,
                                         "Arn": "arn:aws:" + suffix}, nonroot=True)

    def test_plan_rejects_root_before_other_calls_or_writes(self):
        calls = []

        def aws(*args):
            calls.append(args)
            return {"Account": recovery.ACCOUNT,
                    "Arn": f"arn:aws:iam::{recovery.ACCOUNT}:root"}

        with self.assertRaisesRegex(ValueError, "non-root"):
            recovery.plan_bundle(aws, Path("does-not-exist"), "never-written")
        self.assertEqual(calls, [("sts", "get-caller-identity")])
        calls.clear()
        with self.assertRaisesRegex(ValueError, "non-root"):
            recovery.plan_bundle(aws, Path("does-not-exist"), "never-written", completion=True)
        self.assertEqual(calls, [("sts", "get-caller-identity")])

    def test_plan_rejects_other_account_before_other_calls(self):
        calls = []

        def aws(*args):
            calls.append(args)
            return {"Account": "000000000000",
                    "Arn": "arn:aws:sts::000000000000:assumed-role/operator/session"}

        with self.assertRaisesRegex(ValueError, "account"):
            recovery.plan_bundle(aws, Path("does-not-exist"), "never-written")
        self.assertEqual(calls, [("sts", "get-caller-identity")])

    def test_transport_no_writes_by_default(self):
        aws = recovery.AWS()
        with patch.object(subprocess, "run") as run:
            for service, operation in recovery.AWS.WRITES:
                with self.assertRaisesRegex(ValueError, "Forbidden"):
                    aws(service, operation)
            run.assert_not_called()

    def test_no_execute_or_delete_transport_even_when_enabled(self):
        aws = recovery.AWS()
        aws.allow_writes = True
        with patch.object(subprocess, "run") as run:
            for operation in ("delete-stack", "execute-change-set", "update-stack"):
                with self.assertRaisesRegex(ValueError, "Forbidden"):
                    aws("cloudformation", operation)
            run.assert_not_called()

    def test_absence_does_not_swallow_access_denied(self):
        error = subprocess.CalledProcessError(254, ["aws"], stderr="AccessDenied")
        with self.assertRaises(subprocess.CalledProcessError):
            recovery.require_stack_absent(lambda *args: (_ for _ in ()).throw(error))

    def test_failed_stack_record_blocks_plan(self):
        with self.assertRaisesRegex(ValueError, "still exists"):
            recovery.require_stack_absent(lambda *args: {
                "Stacks": [{"StackName": recovery.STACK, "StackStatus": "ROLLBACK_COMPLETE"}]})

    def test_permission_requires_exact_function_statement_semantics(self):
        props = {"Principal": "apigateway.amazonaws.com", "Action": "lambda:InvokeFunction",
                 "FunctionName": f"arn:aws:lambda:{recovery.REGION}:{recovery.ACCOUNT}:function:bridge-staging-test",
                 "SourceAccount": recovery.ACCOUNT,
                 "SourceArn": f"arn:aws:execute-api:{recovery.REGION}:{recovery.ACCOUNT}:pukawa2m43/staging/POST/api/test"}
        statement = {
            "Sid": "actual-policy-sid", "Effect": "Allow",
            "Principal": {"Service": props["Principal"]}, "Action": props["Action"],
            "Resource": props["FunctionName"],
            "Condition": {"StringEquals": {"AWS:SourceAccount": props["SourceAccount"]},
                          "ArnLike": {"AWS:SourceArn": props["SourceArn"]}}}
        recovery.validate_permission(statement, props, "Permission")
        for key in ("Resource", "Action", "Principal", "Condition"):
            altered = copy.deepcopy(statement)
            altered[key] = "incorrect"
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "policy"):
                recovery.validate_permission(altered, props, "Permission")

    def test_summary_raw_composite_keys_preserved(self):
        self.assertEqual(recovery.SCHEMA["AWS::Lambda::Permission"], ["FunctionName,Id"])
        self.assertEqual(recovery.SCHEMA["AWS::ApiGateway::Method"],
                         ["RestApiId,ResourceId,HttpMethod"])
        self.assertIn("aws/aws-cdk-cli/blob/5fa3b0fe", recovery.IDENTIFIER_EVIDENCE)

    def test_summary_schema_change_rejected(self):
        full, _ = template_pair()
        groups = [{
            "ResourceType": kind, "ResourceIdentifiers": schema,
            "LogicalResourceIds": [key for key, value in full["Resources"].items()
                                   if value["Type"] == kind],
        } for kind, schema in recovery.SCHEMA.items()]
        summary = {"ResourceIdentifierSummaries": groups}
        recovery.validate_summary(full, summary)
        summary = copy.deepcopy(summary)
        summary["ResourceIdentifierSummaries"][2]["ResourceIdentifiers"] = ["FunctionName", "Id"]
        with self.assertRaisesRegex(ValueError, "schema changed"):
            recovery.validate_summary(full, summary)

    def test_preview_import_only(self):
        mapping = [{"LogicalResourceId": f"Resource{i}", "ResourceType": "AWS::Lambda::Function"}
                   for i in range(129)]
        preview = {"Status": "CREATE_COMPLETE", "ExecutionStatus": "AVAILABLE",
                   "StackName": recovery.STACK,
                   "StackId": f"arn:aws:cloudformation:{recovery.REGION}:{recovery.ACCOUNT}:stack/{recovery.STACK}/new",
                   "Changes": [
                       {"ResourceChange": {**item, "Action": "Import"}} for item in mapping]}
        recovery.validate_preview(preview, mapping)
        for action in ("Add", "Modify", "Remove"):
            preview["Changes"][0]["ResourceChange"]["Action"] = action
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "exactly 129"):
                recovery.validate_preview(preview, mapping)
        preview["Changes"] = []
        with self.assertRaises(ValueError):
            recovery.validate_preview(preview, mapping)

    def test_completion_requires_managed_original_129(self):
        payloads, responses = managed_fixture()
        result = recovery.validate_managed_import(
            lambda service, operation, *args: responses[operation], payloads)
        self.assertEqual(len(result), 129)

    def test_completion_rejects_wrong_status_role_parameters_template_or_bindings(self):
        for field in ("status", "role", "parameters", "template", "bindings", "missing", "extra"):
            payloads, responses = managed_fixture()
            responses = copy.deepcopy(responses)
            stack = responses["describe-stacks"]["Stacks"][0]
            if field == "status":
                stack["StackStatus"] = "UPDATE_COMPLETE"
            elif field == "role":
                stack["RoleARN"] = "wrong-role"
            elif field == "parameters":
                stack["Parameters"][0]["ParameterValue"] = "new-release"
            elif field == "template":
                responses["get-template"]["TemplateBody"]["Description"] = "changed"
            elif field == "bindings":
                responses["list-stack-resources"]["StackResourceSummaries"][0]["PhysicalResourceId"] = "wrong"
            elif field == "missing":
                responses["list-stack-resources"]["StackResourceSummaries"].pop()
            else:
                responses["list-stack-resources"]["StackResourceSummaries"].append(
                    {"LogicalResourceId": "Extra", "PhysicalResourceId": "extra",
                     "ResourceType": "AWS::Lambda::Function"})
            with self.subTest(field=field), self.assertRaises(ValueError):
                recovery.validate_managed_import(
                    lambda service, operation, *args: responses[operation], payloads)

    def test_completion_preview_only_exact_three_adds_no_replacements(self):
        full, _ = template_pair()
        mapping = [{"LogicalResourceId": logical,
                    "ResourceType": full["Resources"][logical]["Type"]}
                   for logical in sorted(recovery.ABSENT)]
        preview = {"Status": "CREATE_COMPLETE", "ExecutionStatus": "AVAILABLE",
                   "StackName": recovery.STACK,
                   "StackId": f"arn:aws:cloudformation:{recovery.REGION}:{recovery.ACCOUNT}:stack/{recovery.STACK}/new",
                   "Changes": [{"ResourceChange": {**item, "Action": "Add"}} for item in mapping]}
        recovery.validate_preview(preview, mapping, completion=True)
        for field, value in (("Action", "Modify"), ("Action", "Remove"), ("Action", "Import"),
                             ("Replacement", "True"), ("Replacement", "Conditional"),
                             ("LogicalResourceId", "FunctionUnrelated")):
            altered = copy.deepcopy(preview)
            altered["Changes"][0]["ResourceChange"][field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "three"):
                recovery.validate_preview(altered, mapping, completion=True)

    def test_completion_transport_requests_update_not_import_with_versioned_full_template(self):
        payloads, responses = managed_fixture()
        payloads["resources-to-import.json"] = []
        source_bytes = Path(recovery.__file__).read_bytes()
        receipt = {"identifierSyntaxVerified": True,
                   "operatorScriptSha256": recovery.digest(source_bytes),
                   "sha256": {"full-template.json": "0" * 64}}
        changes = [{"ResourceChange": {
            "LogicalResourceId": logical,
            "ResourceType": payloads["full-template.json"]["Resources"][logical]["Type"],
            "Action": "Add"}} for logical in sorted(recovery.ABSENT)]
        responses.update({
            "get-caller-identity": {"Account": recovery.ACCOUNT,
                                   "Arn": f"arn:aws:iam::{recovery.ACCOUNT}:user/operator"},
            "get-bucket-versioning": {"Status": "Enabled"},
            "get-bucket-tagging": {"TagSet": responses["describe-stacks"]["Stacks"][0]["Tags"]},
            "get-role": {"Role": {"Arn": recovery.EXECUTION_ROLE}},
            "put-object": {"VersionId": "version+/="},
            "create-change-set": {"Id": "created-change-set"},
            "describe-change-set": {
                "Status": "CREATE_COMPLETE", "ExecutionStatus": "AVAILABLE",
                "StackName": recovery.STACK,
                "StackId": responses["describe-stacks"]["Stacks"][0]["StackId"],
                "Changes": changes},
        })

        class FakeAWS:
            allow_writes = False

            def __init__(self):
                self.calls = []

            def __call__(self, service, operation, *arguments):
                self.calls.append((service, operation, arguments))
                if (service, operation) in recovery.AWS.WRITES:
                    self_test.assertTrue(self.allow_writes)
                return responses[operation]

        self_test = self
        aws = FakeAWS()
        with patch.object(recovery, "validate_bundle", return_value=(receipt, payloads)), \
                patch.object(recovery, "collect_inventory", return_value=({}, [])), \
                patch.object(Path, "exists", return_value=False), \
                patch.object(Path, "read_bytes", return_value=source_bytes), \
                patch.object(Path, "open", mock_open()), patch.object(Path, "write_bytes"):
            result = recovery.plan_bundle(
                aws, Path("offline-bundle"), "bridge-staging-application-completion-test",
                completion=True)
        writes = [call for call in aws.calls if call[:2] in recovery.AWS.WRITES]
        self.assertEqual([call[:2] for call in writes], [
            ("s3api", "put-object"), ("cloudformation", "create-change-set")])
        self.assertIn("offline-bundle/full-template.json", writes[0][2])
        arguments = writes[1][2]
        self.assertEqual(arguments[arguments.index("--change-set-type") + 1], "UPDATE")
        self.assertNotIn("--resources-to-import", arguments)
        self.assertIn("?versionId=version%2B%2F%3D", result["templateURL"])
        self.assertEqual(result["execution"], "NOT EXECUTED")

    @unittest.skipUnless(os.environ.get("RECOVERY_BUNDLE"), "Set RECOVERY_BUNDLE to exported evidence.")
    def test_actual_exported_bundle_offline(self):
        directory = Path(os.environ["RECOVERY_BUNDLE"])
        receipt, payloads = recovery.validate_bundle(directory)
        self.assertEqual(receipt["importCount"], 129)
        self.assertEqual(len(payloads["resources-to-import.json"]), 129)
        for item in payloads["resources-to-import.json"]:
            self.assertEqual(set(item["ResourceIdentifier"]),
                             set(recovery.SCHEMA[item["ResourceType"]][0].split(",")))
        self.assertFalse(receipt["identifierSyntaxEvidence"]["awsImportPreviewAccepted"])
        self.assertFalse(payloads["snapshot.json"]["inventory"]["restStages"])
        self.assertFalse(payloads["snapshot.json"]["inventory"]["webSocketStages"])

    @unittest.skipUnless(os.environ.get("RECOVERY_BUNDLE"), "Set RECOVERY_BUNDLE to exported evidence.")
    def test_actual_bundle_policy_sid_mismatch_rejected_offline(self):
        directory = Path(os.environ["RECOVERY_BUNDLE"])
        _, payloads = recovery.validate_bundle(directory)
        snapshot = copy.deepcopy(payloads["snapshot.json"])
        function = next(iter(snapshot["inventory"]["policies"]))
        for statement in snapshot["inventory"]["policies"][function]["Statement"]:
            statement["Sid"] = "not-the-recorded-real-sid"
        with self.assertRaisesRegex(ValueError, "permission Sid"):
            recovery.collect_inventory(None, payloads["full-template.json"], snapshot["recorded"],
                                       cached=snapshot["inventory"])

    @unittest.skipUnless(os.environ.get("RECOVERY_BUNDLE"), "Set RECOVERY_BUNDLE to exported evidence.")
    def test_stage_status_is_not_existence_proof(self):
        directory = Path(os.environ["RECOVERY_BUNDLE"])
        _, payloads = recovery.validate_bundle(directory)
        snapshot = copy.deepcopy(payloads["snapshot.json"])
        snapshot["inventory"]["restStages"] = [{"stageName": "staging"}]
        with self.assertRaisesRegex(ValueError, "now exist"):
            recovery.collect_inventory(None, payloads["full-template.json"], snapshot["recorded"],
                                       cached=snapshot["inventory"])

    @unittest.skipUnless(os.environ.get("RECOVERY_BUNDLE"), "Set RECOVERY_BUNDLE to exported evidence.")
    def test_extra_physical_mapping_rejected(self):
        directory = Path(os.environ["RECOVERY_BUNDLE"])
        _, payloads = recovery.validate_bundle(directory)
        snapshot = copy.deepcopy(payloads["snapshot.json"])
        snapshot["inventory"]["routes"].append({"RouteId": "unexpected"})
        with self.assertRaisesRegex(ValueError, "inventory set"):
            recovery.collect_inventory(None, payloads["full-template.json"], snapshot["recorded"],
                                       cached=snapshot["inventory"])

    @unittest.skipUnless(os.environ.get("RECOVERY_BUNDLE"), "Set RECOVERY_BUNDLE to exported evidence.")
    def test_function_code_hash_change_rejected(self):
        directory = Path(os.environ["RECOVERY_BUNDLE"])
        _, payloads = recovery.validate_bundle(directory)
        snapshot = copy.deepcopy(payloads["snapshot.json"])
        snapshot["inventory"]["functions"][0]["CodeSha256"] = "changed"
        with self.assertRaisesRegex(ValueError, "release hash"):
            recovery.collect_inventory(None, payloads["full-template.json"], snapshot["recorded"],
                                       cached=snapshot["inventory"])


if __name__ == "__main__":
    unittest.main()
