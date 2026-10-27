#!/usr/bin/env python3
"""Publish a verified runtime artifact and prepare an application change set; never execute."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse
import zipfile


ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = "851725597758"
REGION = "us-west-2"
BUCKET = "bridge-staging-artifacts-851725597758-us-west-2"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/GitHubBridgeApplicationPlanStaging"
EXECUTION_ROLE = f"arn:aws:iam::{ACCOUNT}:role/BridgeStagingApplicationExecution"
STACK = "bridge-staging-application"
HEALTHY = {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_environment(environment):
    expected = {
        "AWS_ACCOUNT_ID": ACCOUNT, "AWS_REGION": REGION,
        "AWS_APPLICATION_PLAN_ROLE_ARN": ROLE,
        "GITHUB_REPOSITORY": "jmtelgen/NextLevelBridgeAPI", "GITHUB_REF": "refs/heads/main",
    }
    for key, value in expected.items():
        require(environment.get(key) == value, f"Unexpected or missing {key}.")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch(r"[1-9][0-9]*", environment.get(key, "")), f"Invalid {key}.")
    require(re.fullmatch(r"[a-f0-9]{40}", environment.get("GITHUB_SHA", "")), "Invalid source SHA.")
    require(environment.get("APPLICATION_CHANGE_SET_TYPE") in {"CREATE", "UPDATE"}, "Select CREATE or UPDATE.")
    require(environment.get("GITHUB_STEP_SUMMARY"), "Missing summary destination.")


def verified_artifact(directory):
    packages = list(directory.glob("bridge-staging-*.zip"))
    require(len(packages) == 1, "Exactly one target-validated Lambda ZIP is required.")
    package = packages[0]
    metadata = json.loads(package.with_suffix(".json").read_text())
    report = json.loads(package.with_suffix(".validation.json").read_text())
    require(isinstance(metadata, dict) and isinstance(report, dict), "Invalid artifact receipt shape.")
    with package.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    require(package.name == f"bridge-staging-{digest}.zip", "Artifact filename/hash mismatch.")
    require(metadata.get("sha256") == digest and metadata.get("artifact") == package.name, "Artifact receipt mismatch.")
    require(metadata.get("codeSha256") == base64.b64encode(bytes.fromhex(digest)).decode(), "Invalid Lambda code digest.")
    require(report.get("artifactSha256") == digest, "Validation report belongs to another artifact.")
    for key, value in {
        "runtime": "python3.12", "architecture": "x86_64", "os": "AL2023",
        "receiptVerified": True, "durableBootstrap": True, "network": "denied",
        "nativeSolve": {"card": "SA", "tricks": 1},
    }.items():
        require(report.get(key) is value if isinstance(value, bool) else report.get(key) == value,
                f"Missing target validation: {key}.")
    require(re.search(r"@sha256:[a-f0-9]{64}$", report.get("runtimeImage", "")), "Unpinned target image.")
    manifest_path = ROOT / "deployment/runtime-routes.json"
    manifest = json.loads(manifest_path.read_text())
    entrypoints = {
        function[key] for function in manifest["functions"].values()
        for key in ("handler", "entrypoint") if key in function
    }
    require(set(report.get("entrypoints", [])) == entrypoints, "Incomplete handler validation.")
    for field, path in {
        "routeManifestSha256": manifest_path,
        "dependencyLockSha256": ROOT / "deployment/package/requirements.lock",
        "nativeSourceSha256": ROOT / "deployment/package/native-source.json",
    }.items():
        require(metadata.get(field) == hashlib.sha256(path.read_bytes()).hexdigest(),
                f"Artifact does not match reviewed {field}.")
    with zipfile.ZipFile(package) as archive:
        members = archive.infolist()
        size = sum(member.file_size for member in members)
        require(size == metadata.get("uncompressedBytes") and len(members) == metadata.get("memberCount"),
                "ZIP inventory does not match its receipt.")
        require(size <= 250 * 1024 * 1024, "Uncompressed package exceeds Lambda limit.")
        for member in members:
            path = Path(member.filename)
            require(not path.is_absolute() and ".." not in path.parts, "Unsafe ZIP member.")
    return package, digest


def aws(*arguments):
    result = subprocess.run(
        ["aws", *arguments, "--region", REGION, "--no-cli-pager", "--output", "json"],
        check=True, text=True, capture_output=True,
    )
    return json.loads(result.stdout)


def stack_outputs(name):
    stacks = aws("cloudformation", "describe-stacks", "--stack-name", name)["Stacks"]
    require(len(stacks) == 1 and stacks[0]["StackStatus"] in HEALTHY, f"{name} is not healthy.")
    return {entry["OutputKey"]: entry["OutputValue"] for entry in stacks[0].get("Outputs", [])}


def parameters_from_platform(platform, foundation):
    require(platform.get("ArtifactBucketName") == BUCKET, "Unexpected artifact bucket.")
    require(platform.get("ApplicationExecutionRoleArn") == EXECUTION_ROLE, "Unexpected execution role.")
    require(platform.get("ApplicationPlanRoleArn") == ROLE, "Unexpected planning role.")
    require(foundation.get("RoomTableName") == "bridge-staging-rooms", "Unexpected foundation.")
    require(platform.get("RoomStreamArn") == foundation.get("RoomStreamArn"), "Room stream binding differs.")
    require(platform.get("BoardArchivesTableName") == "bridge-staging-board-archives", "Missing archive table.")
    values = {key: platform.get(key, "") for key in (
        "RestApiId", "RestApiRootResourceId", "WebSocketApiId", "StagingOrigin",
    )}
    for key in ("RestApiId", "WebSocketApiId"):
        require(re.fullmatch(r"[a-z0-9]{10}", values[key]), f"Invalid {key}.")
    require(values["RestApiId"] != "e2jrh99dbc" and values["WebSocketApiId"] != "ipp77av3oi", "Public API is forbidden.")
    require(re.fullmatch(r"[a-z0-9]+", values["RestApiRootResourceId"]), "Invalid REST root.")
    require(re.fullmatch(r"https://d[a-z0-9]+\.cloudfront\.net", values["StagingOrigin"]), "Invalid staging origin.")
    require(values["StagingOrigin"] != "https://d1h54yowalg875.cloudfront.net", "Public distribution is forbidden.")
    return values


def put_version(path, key, digest):
    result = aws(
        "s3api", "put-object", "--bucket", BUCKET, "--key", key,
        "--body", str(path), "--if-none-match", "*",
        "--checksum-sha256", base64.b64encode(bytes.fromhex(digest)).decode(),
        "--metadata", f"sha256={digest}", "--server-side-encryption", "AES256",
    )
    version = result.get("VersionId")
    require(isinstance(version, str) and version not in {"", "null"}, "S3 did not return an immutable version.")
    return version


def plan(environment, directory):
    validate_environment(environment)
    package, digest = verified_artifact(directory)
    identity = aws("sts", "get-caller-identity")
    session = f"BridgeApplicationPlan-{environment['GITHUB_RUN_ID']}-{environment['GITHUB_RUN_ATTEMPT']}"
    require(identity.get("Account") == ACCOUNT and identity.get("Arn") ==
            f"arn:aws:sts::{ACCOUNT}:assumed-role/GitHubBridgeApplicationPlanStaging/{session}",
            "Unexpected AWS session; root and other roles are forbidden.")
    values = parameters_from_platform(
        stack_outputs("bridge-staging-platform"), stack_outputs("bridge-staging-foundation")
    )
    require(aws("s3api", "get-bucket-versioning", "--bucket", BUCKET).get("Status") == "Enabled",
            "Artifact bucket must have versioning enabled.")
    tags = {tag["Key"]: tag["Value"] for tag in aws("s3api", "get-bucket-tagging", "--bucket", BUCKET)["TagSet"]}
    require(tags.get("Application") == "Bridge" and tags.get("Environment") == "staging", "Wrong bucket isolation tags.")
    prefix = f"releases/{environment['GITHUB_SHA']}/{digest}/{environment['GITHUB_RUN_ID']}-{environment['GITHUB_RUN_ATTEMPT']}"
    key = prefix + "/" + package.name
    values.update({
        "ArtifactKey": key, "ArtifactVersion": put_version(package, key, digest),
        "SourceCommit": environment["GITHUB_SHA"],
    })
    spec = importlib.util.spec_from_file_location("application_template", ROOT / "deployment/application_template.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template = directory / "application.json"
    rendered = module.application_template(digest)
    template.write_text(json.dumps(rendered, sort_keys=True, indent=2) + "\n")
    template_digest = hashlib.sha256(template.read_bytes()).hexdigest()
    template_key = prefix + "/" + template_digest + ".json"
    template_version = put_version(template, template_key, template_digest)
    url = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{template_key}?versionId={urllib.parse.quote(template_version, safe='')}"
    aws("cloudformation", "validate-template", "--template-url", url)
    name = f"{STACK}-{environment['GITHUB_RUN_ID']}-{environment['GITHUB_RUN_ATTEMPT']}"
    change_set = aws(
        "cloudformation", "create-change-set", "--stack-name", STACK,
        "--change-set-name", name, "--change-set-type", environment["APPLICATION_CHANGE_SET_TYPE"],
        "--role-arn", EXECUTION_ROLE, "--template-url", url,
        "--parameters", json.dumps([{"ParameterKey": key, "ParameterValue": value} for key, value in values.items()]),
        "--tags", "Key=Application,Value=Bridge", "Key=Environment,Value=staging",
    )
    subprocess.run([
        "aws", "cloudformation", "wait", "change-set-create-complete",
        "--region", REGION, "--no-cli-pager", "--stack-name", STACK, "--change-set-name", change_set["Id"],
    ], check=True)
    preview = aws("cloudformation", "describe-change-set", "--stack-name", STACK,
                  "--change-set-name", change_set["Id"],
                  "--query", "{Status:Status,ExecutionStatus:ExecutionStatus,Changes:Changes[].ResourceChange.{Action:Action,LogicalResourceId:LogicalResourceId,ResourceType:ResourceType,Replacement:Replacement,PolicyAction:PolicyAction}}")
    require(preview.get("Status") == "CREATE_COMPLETE" and preview.get("ExecutionStatus") == "AVAILABLE",
            "Change set is not available for review.")
    changes = preview.get("Changes")
    require(isinstance(changes, list) and bool(changes), "Missing resource preview.")
    validate_preview(changes, rendered, environment["APPLICATION_CHANGE_SET_TYPE"])
    print(json.dumps(preview, indent=2))
    with Path(environment["GITHUB_STEP_SUMMARY"]).open("a") as summary:
        summary.write(
            f"## Staging application preview ONLY\n\nSource: `{environment['GITHUB_SHA']}`\n\n"
            f"Artifact SHA-256: `{digest}`\n\nTemplate SHA-256: `{template_digest}`\n\n"
            f"Change set: `{change_set['Id']}`\n\n"
            "No change set was executed. Scheduling and frontend publication are separate gates.\n"
        )


def validate_preview(changes, rendered, change_set_type):
    seen = set()
    for change in changes:
        require(isinstance(change, dict), "Invalid resource preview.")
        name = change.get("LogicalResourceId")
        require(isinstance(name, str) and name not in seen, "Missing or duplicate logical ID.")
        seen.add(name)
        if change.get("Action") == "Remove":
            require(
                change_set_type == "UPDATE"
                and re.fullmatch(r"(RestDeployment|WebSocketDeployment)[a-f0-9]{16}", name)
                and change.get("ResourceType") in {"AWS::ApiGateway::Deployment", "AWS::ApiGatewayV2::Deployment"}
                and change.get("PolicyAction") == "Retain",
                "Only retained historical API deployment snapshots may leave the stack.",
            )
            continue
        require(name in rendered["Resources"], "Unexpected resource in preview.")
        require(change.get("ResourceType") == rendered["Resources"][name]["Type"], "Unexpected resource type.")
        require(change.get("Action") in ({"Add"} if change_set_type == "CREATE" else {"Add", "Modify"}),
                "Unexpected resource action.")
        require(change.get("Replacement") in {None, "False"}, "Replacement requires separate review.")
    if change_set_type == "CREATE":
        require(seen == set(rendered["Resources"]), "Incomplete CREATE preview.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["validate", "plan"])
    parser.add_argument("artifact_directory", type=Path)
    args = parser.parse_args()
    try:
        validate_environment(os.environ)
        verified_artifact(args.artifact_directory)
        if args.mode == "plan":
            plan(os.environ, args.artifact_directory)
    except (ValueError, KeyError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, end="")
        raise SystemExit(f"::error::{error}")
