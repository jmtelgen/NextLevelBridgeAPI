#!/usr/bin/env python3
"""Export staging recovery; prepare (never execute) IMPORT or three-add completion UPDATE."""
import argparse
import base64
import copy
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import quote
import zipfile


ACCOUNT = "851725597758"
REGION = "us-west-2"
STACK = "bridge-staging-application"
BUCKET = f"bridge-staging-artifacts-{ACCOUNT}-{REGION}"
EXECUTION_ROLE = f"arn:aws:iam::{ACCOUNT}:role/BridgeStagingApplicationExecution"
SOURCE = "a625ea62b2b16410c244607d85de9fe97c9146db"
ARTIFACT = "4ae761aef2b50faa7ad6a9e5e6962db516ea61d5e88c5c8e60a8a41536bb548c"
ABSENT = {"RestStage", "WebSocketStage", "WebSocketDeployment" + ARTIFACT[:16]}
COUNTS = {
    "AWS::Lambda::Function": 22, "AWS::Logs::LogGroup": 22,
    "AWS::Lambda::Permission": 20, "AWS::ApiGateway::Method": 12,
    "AWS::ApiGateway::Resource": 8, "AWS::ApiGateway::Deployment": 1,
    "AWS::ApiGatewayV2::Integration": 14, "AWS::ApiGatewayV2::Route": 30,
}
SCHEMA = {
    "AWS::Lambda::Function": ["FunctionName"],
    "AWS::Logs::LogGroup": ["LogGroupName"],
    "AWS::Lambda::Permission": ["FunctionName,Id"],
    "AWS::ApiGateway::Method": ["RestApiId,ResourceId,HttpMethod"],
    "AWS::ApiGateway::Resource": ["RestApiId,ResourceId"],
    "AWS::ApiGateway::Deployment": ["DeploymentId,RestApiId"],
    "AWS::ApiGatewayV2::Integration": ["ApiId,IntegrationId"],
    "AWS::ApiGatewayV2::Route": ["ApiId,RouteId"],
    "AWS::ApiGateway::Stage": ["RestApiId,StageName"],
    "AWS::ApiGatewayV2::Stage": ["ApiId,StageName"],
    "AWS::ApiGatewayV2::Deployment": ["ApiId,DeploymentId"],
}
PARAMETERS = {
    "ArtifactKey": f"releases/{SOURCE}/{ARTIFACT}/40504492529-1/bridge-staging-{ARTIFACT}.zip",
    "ArtifactVersion": "RsyO2kHzc8xdcYE65STka4KoYZZA299Y",
    "SourceCommit": SOURCE, "RestApiId": "pukawa2m43",
    "RestApiRootResourceId": "vkjiwfpmli", "WebSocketApiId": "m58xz54ub0",
    "StagingOrigin": "https://d2l5s3st0lpzfi.cloudfront.net",
}
FORBIDDEN = ("e2jrh99dbc", "ipp77av3oi", "E1HX0HXMLYUF2Z",
             "nextlevelbridgeassetdistributionbucket")
FILES = ("full-template.json", "import-template.json", "resources-to-import.json",
         "parameters.json", "snapshot.json")
# Official CDK importer splits ResourceIdentifiers on commas and passes expanded
# property dictionaries to ResourcesToImport. Actual AWS preview remains separate.
IDENTIFIER_SYNTAX_VERIFIED = True
IDENTIFIER_EVIDENCE = (
    "https://github.com/aws/aws-cdk-cli/blob/"
    "5fa3b0fe61fc6b0ace61cceddf3949a4699e581e/"
    "packages/%40aws-cdk/toolkit-lib/lib/api/resource-import/importer.ts#L332-L453"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


class AWS:
    """A deliberately allowlisted CLI transport; export cannot perform writes."""

    READS = {
        ("sts", "get-caller-identity"), ("cloudformation", "describe-stacks"),
        ("cloudformation", "get-template"), ("cloudformation", "get-template-summary"),
        ("cloudformation", "list-stack-resources"),
        ("lambda", "list-functions"), ("lambda", "get-policy"),
        ("logs", "describe-log-groups"), ("apigateway", "get-rest-api"),
        ("apigateway", "get-resources"), ("apigateway", "get-deployments"),
        ("apigateway", "get-stages"), ("apigateway", "get-method"),
        ("apigatewayv2", "get-api"), ("apigatewayv2", "get-integrations"),
        ("apigatewayv2", "get-routes"), ("apigatewayv2", "get-deployments"),
        ("apigatewayv2", "get-stages"), ("s3api", "get-bucket-versioning"),
        ("s3api", "get-bucket-tagging"), ("iam", "get-role"),
        ("cloudformation", "describe-change-set"),
    }
    WRITES = {("s3api", "put-object"), ("cloudformation", "create-change-set")}

    def __init__(self):
        self.allow_writes = False

    def __call__(self, service, operation, *arguments):
        key = (service, operation)
        require(key in self.READS or self.allow_writes and key in self.WRITES,
                f"Forbidden AWS operation: {service} {operation}")
        result = subprocess.run(
            ["aws", service, operation, *arguments, "--region", REGION,
             "--output", "json", "--no-cli-pager"],
            check=True, capture_output=True, text=True,
        )
        return json.loads(result.stdout)


def check_identity(identity, nonroot=False):
    require(identity.get("Account") == ACCOUNT, "Unexpected AWS account.")
    arn = identity.get("Arn", "")
    require(arn.startswith((f"arn:aws:iam::{ACCOUNT}:",
                            f"arn:aws:sts::{ACCOUNT}:")), "Unexpected identity ARN.")
    if nonroot:
        require(re.fullmatch(
            rf"arn:aws:(?:iam::{ACCOUNT}:user/[A-Za-z0-9+=,.@_/-]+"
            rf"|sts::{ACCOUNT}:assumed-role/[^/]+/[^/]+)", arn),
            "Plan requires an exact-account non-root IAM-user or assumed-role operator session.")


def parameters(stack):
    entries = stack["Parameters"]
    values = {entry["ParameterKey"]: entry["ParameterValue"] for entry in entries}
    require(len(values) == len(entries) and values == PARAMETERS,
            "Original release parameters changed; refuse recovery.")
    return [{"ParameterKey": key, "ParameterValue": values[key]} for key in sorted(values)]


def check_references(template):
    names = set(template["Resources"]) | set(template.get("Parameters", {}))
    pseudo = {"AWS::AccountId", "AWS::Region", "AWS::Partition", "AWS::URLSuffix",
              "AWS::StackId", "AWS::StackName", "AWS::NoValue", "AWS::NotificationARNs"}

    def walk(value, locals_=frozenset()):
        if isinstance(value, list):
            for item in value:
                walk(item, locals_)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key == "Ref":
                    require(item in names | pseudo | set(locals_), f"Dangling Ref: {item}")
                elif key == "Fn::GetAtt":
                    target = item.split(".")[0] if isinstance(item, str) else item[0]
                    require(target in template["Resources"], f"Dangling GetAtt: {target}")
                elif key == "DependsOn":
                    for target in [item] if isinstance(item, str) else item:
                        require(target in template["Resources"], f"Dangling DependsOn: {target}")
                elif key == "Fn::Sub":
                    text, bindings = (item, {}) if isinstance(item, str) else item
                    for symbol in re.findall(r"\$\{([^}]+)\}", text):
                        if symbol.startswith("!"):
                            continue
                        require(symbol in bindings or symbol.split(".")[0] in names | pseudo,
                                f"Dangling Sub: {symbol}")
                    walk(bindings, locals_)
                else:
                    walk(item, locals_)
    walk(template)


def validate_templates(full, imported):
    resources = full["Resources"]
    require(len(resources) == 132, "Expected original 132-resource template.")
    require(set(resources) - set(imported["Resources"]) == ABSENT,
            "Import must exclude exactly the three absent resources.")
    expected = copy.deepcopy(full)
    for logical in ABSENT:
        del expected["Resources"][logical]
    require(expected == imported, "Import changed original properties, metadata or parameters.")
    require(Counter(r["Type"] for r in imported["Resources"].values()) == COUNTS,
            "Unexpected retained resource graph.")
    require(resources["RestStage"]["Type"] == "AWS::ApiGateway::Stage"
            and resources["WebSocketStage"]["Type"] == "AWS::ApiGatewayV2::Stage"
            and resources["WebSocketDeployment" + ARTIFACT[:16]]["Type"]
            == "AWS::ApiGatewayV2::Deployment", "Unexpected excluded resource types.")
    require(set(full["Parameters"]) == set(PARAMETERS), "Unexpected template parameters.")
    for resource in resources.values():
        require(resource.get("DeletionPolicy") == "Retain"
                and resource.get("UpdateReplacePolicy") == "Retain",
                "Every original resource must retain on deletion and replacement.")
    # Forbidden IDs may occur only inside the original negative AllowedPattern guards.
    for value in (full["Resources"], full.get("Outputs", {}), full.get("Metadata", {})):
        text = json.dumps(value)
        require(not any(item in text for item in FORBIDDEN), "Public resource binding forbidden.")
    require(full.get("Outputs", {}).get("ArtifactSha256", {}).get("Value") == ARTIFACT,
            "Unexpected original artifact.")
    check_references(full)
    check_references(imported)


def validate_summary(full, summary):
    groups = summary["ResourceIdentifierSummaries"]
    require(len(groups) == len(SCHEMA), "Unexpected identifier summary groups.")
    seen = set()
    for group in groups:
        kind = group["ResourceType"]
        require(kind in SCHEMA and kind not in seen, "Unknown or duplicate identifier type.")
        seen.add(kind)
        require(group["ResourceIdentifiers"] == SCHEMA[kind],
                f"Live identifier schema changed for {kind}.")
        require(set(group["LogicalResourceIds"]) == {
            key for key, value in full["Resources"].items() if value["Type"] == kind
        }, f"Identifier logical IDs differ for {kind}.")
    require(seen == set(SCHEMA), "Incomplete identifier summary.")


def resolve(value, physical):
    pseudo = {"AWS::AccountId": ACCOUNT, "AWS::Region": REGION,
              "AWS::Partition": "aws", "AWS::URLSuffix": "amazonaws.com"}
    refs = {**PARAMETERS, **physical, **pseudo}
    if isinstance(value, list):
        return [resolve(item, physical) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"Ref"}:
        return refs[value["Ref"]]
    if set(value) == {"Fn::GetAtt"}:
        logical, attr = value["Fn::GetAtt"]
        require(attr == "Arn" and physical[logical].startswith("bridge-staging-"),
                "Unexpected GetAtt in identity binding.")
        return f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{physical[logical]}"
    if set(value) == {"Fn::Join"}:
        separator, parts = value["Fn::Join"]
        return separator.join(resolve(item, physical) for item in parts)
    if set(value) == {"Fn::Sub"}:
        text = value["Fn::Sub"]
        require(isinstance(text, str), "Unexpected substitution bindings.")
        def substitute(match):
            key = match[1]
            if "." in key:
                return resolve({"Fn::GetAtt": key.split(".")}, physical)
            return refs[key]
        return re.sub(r"\$\{([^}]+)\}", substitute, text)
    return {key: resolve(item, physical) for key, item in value.items()}


def validate_permission(statement, props, logical):
    require(statement["Effect"] == "Allow"
            and statement["Principal"] == {"Service": props["Principal"]}
            and statement["Action"] == props["Action"]
            and statement["Resource"] == props["FunctionName"]
            and statement.get("Condition") == {
                "StringEquals": {"AWS:SourceAccount": props["SourceAccount"]},
                "ArnLike": {"AWS:SourceArn": props["SourceArn"]}},
            f"Permission policy does not match original: {logical}")


def collect_inventory(aws, full, recorded, cached=None):
    physical = {r["LogicalResourceId"]: r["PhysicalResourceId"] for r in recorded
                if r.get("PhysicalResourceId")}
    require(len({r["LogicalResourceId"] for r in recorded}) == len(recorded),
            "Duplicate stack logical resources.")
    require(set(physical) - set(full["Resources"]) == set(), "Unknown recorded resource.")
    for logical, resource in full["Resources"].items():
        matches = [r for r in recorded if r["LogicalResourceId"] == logical]
        if logical not in ABSENT:
            require(len(matches) == 1 and logical in physical
                    and matches[0]["ResourceType"] == resource["Type"],
                    f"Missing or mismatched stack record: {logical}")
    rest, ws = PARAMETERS["RestApiId"], PARAMETERS["WebSocketApiId"]
    inventory = cached if cached is not None else {
        "restApi": aws("apigateway", "get-rest-api", "--rest-api-id", rest),
        "webSocketApi": aws("apigatewayv2", "get-api", "--api-id", ws),
        "restResources": aws("apigateway", "get-resources", "--rest-api-id", rest)["items"],
        "restDeployments": aws("apigateway", "get-deployments", "--rest-api-id", rest)["items"],
        "restStages": aws("apigateway", "get-stages", "--rest-api-id", rest).get("item", []),
        "integrations": aws("apigatewayv2", "get-integrations", "--api-id", ws).get("Items", []),
        "routes": aws("apigatewayv2", "get-routes", "--api-id", ws).get("Items", []),
        "webSocketDeployments": aws("apigatewayv2", "get-deployments", "--api-id", ws).get("Items", []),
        "webSocketStages": aws("apigatewayv2", "get-stages", "--api-id", ws).get("Items", []),
        "functions": aws("lambda", "list-functions", "--query",
                         "Functions[?starts_with(FunctionName, `bridge-staging-`)]."
                         "{FunctionName:FunctionName,FunctionArn:FunctionArn,CodeSha256:CodeSha256,"
                         "Role:Role,Runtime:Runtime,Handler:Handler,Architectures:Architectures}") ,
        "logGroups": aws("logs", "describe-log-groups", "--log-group-name-prefix",
                         "/aws/lambda/bridge-staging-")["logGroups"],
        "policies": {}, "methods": {},
    }
    require(inventory["restApi"]["id"] == rest
            and inventory["restApi"]["name"].startswith("bridge-staging")
            and inventory["webSocketApi"]["ApiId"] == ws
            and inventory["webSocketApi"]["Name"].startswith("bridge-staging")
            and inventory["webSocketApi"]["ProtocolType"] == "WEBSOCKET",
            "Unexpected API identity.")
    require(any(r["id"] == PARAMETERS["RestApiRootResourceId"] and r["path"] == "/"
                for r in inventory["restResources"]), "Unexpected REST root.")
    require(not inventory["restStages"] and not inventory["webSocketStages"]
            and not inventory["webSocketDeployments"], "Absent stages/deployment now exist.")
    functions = {item["FunctionName"]: item for item in inventory["functions"]}
    logs = {item["logGroupName"]: item for item in inventory["logGroups"]}
    paths = {item["id"]: item for item in inventory["restResources"]}
    integrations = {item["IntegrationId"]: item for item in inventory["integrations"]}
    routes = {item["RouteId"]: item for item in inventory["routes"]}
    deployments = {item["id"]: item for item in inventory["restDeployments"]}
    def expected_ids(kind):
        return {physical[key] for key, value in full["Resources"].items()
                if value["Type"] == kind and key not in ABSENT}

    for actual, kind in (
        (set(functions), "AWS::Lambda::Function"),
        (set(logs), "AWS::Logs::LogGroup"),
        (set(integrations), "AWS::ApiGatewayV2::Integration"),
        (set(routes), "AWS::ApiGatewayV2::Route"),
        (set(deployments), "AWS::ApiGateway::Deployment"),
    ):
        require(actual == expected_ids(kind), f"Unexpected physical inventory set: {kind}")
    require(set(paths) == expected_ids("AWS::ApiGateway::Resource")
            | {PARAMETERS["RestApiRootResourceId"]},
            "REST paths must contain all eight application paths and only the platform root.")
    expected_methods = {
        (resolve(value["Properties"]["ResourceId"], physical),
         value["Properties"]["HttpMethod"])
        for value in full["Resources"].values() if value["Type"] == "AWS::ApiGateway::Method"
    }
    require({(path["id"], method) for path in paths.values()
             for method in path.get("resourceMethods", {})} == expected_methods,
            "Unexpected physical REST method inventory.")
    mapping = []
    for logical, resource in sorted(full["Resources"].items()):
        if logical in ABSENT:
            continue
        kind, identifier = resource["Type"], physical[logical]
        props = resolve(resource["Properties"], physical)
        values = {}
        if kind == "AWS::Lambda::Function":
            require(identifier == props["FunctionName"] and identifier.startswith("bridge-staging-"),
                    f"Function prefix/identity mismatch: {logical}")
            actual = functions.get(identifier)
            require(actual is not None, f"Missing physical function: {logical}")
            for key in ("FunctionName", "Role", "Runtime", "Handler", "Architectures"):
                require(actual[key] == props[key], f"Function {key} mismatch: {logical}")
            require(actual["CodeSha256"] == base64.b64encode(bytes.fromhex(ARTIFACT)).decode(),
                    f"Function release hash mismatch: {logical}")
            values = {"FunctionName": identifier}
        elif kind == "AWS::Logs::LogGroup":
            require(identifier == props["LogGroupName"] and identifier in logs
                    and logs[identifier].get("retentionInDays") == props["RetentionInDays"],
                    f"Missing/mismatched physical log group: {logical}")
            values = {"LogGroupName": identifier}
        elif kind == "AWS::Lambda::Permission":
            function = props["FunctionName"].split(":function:")[-1]
            require(function in functions, f"Permission refers to unknown function: {logical}")
            if function not in inventory["policies"]:
                require(cached is None, f"Missing cached permission policy: {logical}")
                inventory["policies"][function] = json.loads(
                    aws("lambda", "get-policy", "--function-name", function)["Policy"])
            statements = [s for s in inventory["policies"][function]["Statement"]
                          if s["Sid"] == identifier]
            require(len(statements) == 1, f"Missing/ambiguous permission Sid: {logical}")
            validate_permission(statements[0], props, logical)
            values = {"FunctionName": function, "Id": identifier}
        elif kind == "AWS::ApiGateway::Resource":
            require(props["RestApiId"] == rest and identifier in paths
                    and paths[identifier]["parentId"] == props["ParentId"]
                    and paths[identifier]["pathPart"] == props["PathPart"],
                    f"REST resource mismatch: {logical}")
            values = {"RestApiId": rest, "ResourceId": identifier}
        elif kind == "AWS::ApiGateway::Method":
            require(identifier == f'{rest}|{props["ResourceId"]}|{props["HttpMethod"]}',
                    f"REST method recorded binding mismatch: {logical}")
            actual = (inventory["methods"][logical] if cached is not None else
                      aws("apigateway", "get-method", "--rest-api-id", rest,
                          "--resource-id", props["ResourceId"], "--http-method", props["HttpMethod"]))
            inventory["methods"][logical] = actual
            require(actual["httpMethod"] == props["HttpMethod"]
                    and actual["authorizationType"] == props["AuthorizationType"]
                    and actual["methodIntegration"]["type"] == props["Integration"]["Type"],
                    f"REST method physical mismatch: {logical}")
            if "Uri" in props["Integration"]:
                require(actual["methodIntegration"]["uri"] == props["Integration"]["Uri"],
                        f"REST method Lambda binding mismatch: {logical}")
            values = {"RestApiId": rest, "ResourceId": props["ResourceId"],
                      "HttpMethod": props["HttpMethod"]}
        elif kind == "AWS::ApiGateway::Deployment":
            require(identifier == "2k9ooc" and identifier in deployments
                    and props["RestApiId"] == rest, "Original REST deployment missing.")
            values = {"DeploymentId": identifier, "RestApiId": rest}
        elif kind == "AWS::ApiGatewayV2::Integration":
            actual = integrations.get(identifier)
            require(actual is not None and props["ApiId"] == ws,
                    f"WebSocket integration absent: {logical}")
            for key in ("IntegrationType", "IntegrationMethod", "IntegrationUri", "TimeoutInMillis"):
                require(actual[key] == props[key], f"Integration {key} mismatch: {logical}")
            values = {"ApiId": ws, "IntegrationId": identifier}
        elif kind == "AWS::ApiGatewayV2::Route":
            actual = routes.get(identifier)
            require(actual is not None and props["ApiId"] == ws,
                    f"WebSocket route absent: {logical}")
            for key in ("RouteKey", "Target", "AuthorizationType"):
                require(actual[key] == props[key], f"Route {key} mismatch: {logical}")
            values = {"ApiId": ws, "RouteId": identifier}
        else:
            raise ValueError(f"Unexpected import type: {kind}")
        require(set(values) == set(SCHEMA[kind][0].split(",")),
                f"Identifier properties differ from live summary: {logical}")
        mapping.append({"ResourceType": kind, "LogicalResourceId": logical,
                        "ResourceIdentifier": values})
    return inventory, mapping


def export_bundle(aws, directory):
    require(not directory.exists(), "Use a new bundle directory; existing evidence is immutable.")
    identity = aws("sts", "get-caller-identity")
    check_identity(identity)
    stacks = aws("cloudformation", "describe-stacks", "--stack-name", STACK)["Stacks"]
    require(len(stacks) == 1, "Expected exactly one application stack.")
    stack = stacks[0]
    require(stack["StackName"] == STACK and stack["StackStatus"] == "ROLLBACK_COMPLETE"
            and stack["StackId"].startswith(f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/"),
            "Unexpected stack identity/state.")
    require(stack.get("RoleARN") == EXECUTION_ROLE, "Unexpected execution role.")
    tags = {t["Key"]: t["Value"] for t in stack.get("Tags", [])}
    require(tags.get("Application") == "Bridge" and tags.get("Environment") == "staging",
            "Unexpected application stack tags.")
    original_parameters = parameters(stack)
    template = aws("cloudformation", "get-template", "--stack-name", STACK,
                   "--template-stage", "Original")["TemplateBody"]
    full = json.loads(template) if isinstance(template, str) else template
    imported = copy.deepcopy(full)
    for logical in ABSENT:
        require(logical in imported["Resources"], f"Missing expected excluded resource: {logical}")
        del imported["Resources"][logical]
    validate_templates(full, imported)
    summary = aws("cloudformation", "get-template-summary", "--stack-name", STACK)
    validate_summary(full, summary)
    recorded = aws("cloudformation", "list-stack-resources",
                   "--stack-name", STACK)["StackResourceSummaries"]
    inventory, mapping = collect_inventory(aws, full, recorded)
    final_stack = aws("cloudformation", "describe-stacks", "--stack-name", STACK)["Stacks"]
    require(len(final_stack) == 1 and final_stack[0]["StackId"] == stack["StackId"]
            and final_stack[0]["StackStatus"] == "ROLLBACK_COMPLETE"
            and parameters(final_stack[0]) == original_parameters,
            "Application stack changed during export.")
    snapshot = {"identity": identity, "stack": stack, "summary": summary,
                "recorded": recorded, "inventory": inventory}
    payloads = dict(zip(FILES, (full, imported, mapping, original_parameters, snapshot)))
    receipt = {
        "formatVersion": 1, "account": ACCOUNT, "region": REGION, "stackName": STACK,
        "stackId": stack["StackId"], "executionRole": EXECUTION_ROLE,
        "exportedAt": datetime.now(timezone.utc).isoformat(), "identity": identity,
        "sourceCommit": SOURCE, "artifactSha256": ARTIFACT,
        "importCount": 129, "fullCount": 132, "excludedLogicalIds": sorted(ABSENT),
        "identifierSchema": SCHEMA,
        "identifierSyntaxVerified": IDENTIFIER_SYNTAX_VERIFIED,
        "identifierSyntaxEvidence": {
            "encoding": "expanded-property-dictionary",
            "officialImplementation": IDENTIFIER_EVIDENCE,
            "rawGetTemplateSummaryCaptured": True,
            "awsImportPreviewAccepted": False,
        },
        "operatorScriptSha256": digest(Path(__file__).read_bytes()),
        "sha256": {name: digest(encoded(value)) for name, value in payloads.items()},
    }
    directory.mkdir(parents=True)
    for name, value in {**payloads, "receipt.json": receipt}.items():
        (directory / name).write_bytes(encoded(value))
    validate_bundle(directory)
    with zipfile.ZipFile(directory / "application-import-recovery.zip", "w",
                         compression=zipfile.ZIP_DEFLATED) as archive:
        for name in (*FILES, "receipt.json"):
            archive.write(directory / name, name)
        archive.write(Path(__file__), "application_import_recovery.py")
        sums = {**receipt["sha256"], "receipt.json": digest(encoded(receipt)),
                "application_import_recovery.py": receipt["operatorScriptSha256"]}
        checksums = "".join(f"{sha}  {name}\n" for name, sha in sorted(sums.items()))
        (directory / "SHA256SUMS").write_text(checksums)
        archive.writestr("SHA256SUMS", checksums)
    package = directory / "application-import-recovery.zip"
    package.with_suffix(".zip.sha256").write_text(
        f"{digest(package.read_bytes())}  {package.name}\n")
    return receipt


def validate_bundle(directory):
    receipt = json.loads((directory / "receipt.json").read_text())
    require(receipt["formatVersion"] == 1 and receipt["account"] == ACCOUNT
            and receipt["region"] == REGION and receipt["stackName"] == STACK
            and receipt["executionRole"] == EXECUTION_ROLE
            and receipt["sourceCommit"] == SOURCE and receipt["artifactSha256"] == ARTIFACT
            and receipt["identifierSchema"] == SCHEMA and receipt["importCount"] == 129
            and receipt["fullCount"] == 132 and receipt["excludedLogicalIds"] == sorted(ABSENT),
            "Unexpected receipt identity.")
    require(receipt["identifierSyntaxVerified"] is True
            and receipt["identifierSyntaxEvidence"] == {
                "encoding": "expanded-property-dictionary",
                "officialImplementation": IDENTIFIER_EVIDENCE,
                "rawGetTemplateSummaryCaptured": True,
                "awsImportPreviewAccepted": False,
            }, "Unexpected identifier implementation evidence.")
    require(set(receipt["sha256"]) == set(FILES), "Incomplete bundle hashes.")
    payloads = {}
    for name in FILES:
        data = (directory / name).read_bytes()
        require(digest(data) == receipt["sha256"][name], f"Bundle hash mismatch: {name}")
        payloads[name] = json.loads(data)
    full, imported = payloads["full-template.json"], payloads["import-template.json"]
    validate_templates(full, imported)
    snapshot = payloads["snapshot.json"]
    check_identity(snapshot["identity"])
    require(snapshot["stack"]["StackId"] == receipt["stackId"]
            and snapshot["stack"]["StackStatus"] == "ROLLBACK_COMPLETE"
            and snapshot["stack"]["RoleARN"] == EXECUTION_ROLE,
            "Snapshot stack differs from receipt.")
    validate_summary(full, snapshot["summary"])
    require(payloads["parameters.json"] == parameters(snapshot["stack"]),
            "Parameter bundle differs from original release.")
    mapping = payloads["resources-to-import.json"]
    require(len(mapping) == 129 and len({m["LogicalResourceId"] for m in mapping}) == 129
            and {m["LogicalResourceId"] for m in mapping} == set(imported["Resources"]),
            "Incomplete or duplicate import mapping.")
    identifiers = set()
    for item in mapping:
        logical, kind = item["LogicalResourceId"], item["ResourceType"]
        require(kind == imported["Resources"][logical]["Type"]
                and set(item["ResourceIdentifier"]) == set(SCHEMA[kind][0].split(",")),
                f"Incorrect import identifier syntax: {logical}")
        require(all(isinstance(value, str) and value and "," not in value
                    for value in item["ResourceIdentifier"].values()),
                f"Invalid primary identifier values: {logical}")
        identity = (kind, tuple(sorted(item["ResourceIdentifier"].items())))
        require(identity not in identifiers, f"Duplicate physical import: {logical}")
        identifiers.add(identity)
    _, checked_mapping = collect_inventory(
        None, full, snapshot["recorded"], cached=snapshot["inventory"])
    require(checked_mapping == mapping, "Import mapping differs from physical inventory evidence.")
    return receipt, payloads


def require_stack_absent(aws):
    # List filters avoid treating AccessDenied or any other Describe error as absence.
    stacks = aws("cloudformation", "describe-stacks")["Stacks"]
    require(not any(s["StackName"] == STACK for s in stacks),
            "Failed application stack record still exists; do not prepare IMPORT.")


def validate_preview(preview, mapping, completion=False):
    require(preview["Status"] == "CREATE_COMPLETE"
            and preview["ExecutionStatus"] == "AVAILABLE"
            and preview["StackName"] == STACK
            and preview["StackId"].startswith(
                f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/"),
            "Recovery change set not available.")
    changes = [entry["ResourceChange"] for entry in preview.get("Changes", [])]
    expected = {(m["LogicalResourceId"], m["ResourceType"]) for m in mapping}
    count, action = (3, "Add") if completion else (129, "Import")
    require(len(changes) == count and {
        (c["LogicalResourceId"], c["ResourceType"]) for c in changes
    } == expected and all(c["Action"] == action
                         and c.get("Replacement", "False") == "False" for c in changes),
            ("Preview must contain exactly three expected Adds and no Modify/Remove/Replace."
             if completion else
             "Preview must contain exactly 129 Imports and no Adds/Modifies/Removes."))


def plan_bundle(aws, directory, change_set_name, completion=False):
    identity = aws("sts", "get-caller-identity")
    check_identity(identity, nonroot=True)
    receipt, payloads = validate_bundle(directory)
    require(IDENTIFIER_SYNTAX_VERIFIED and receipt.get("identifierSyntaxVerified") is True,
            "Manual IMPORT identifier syntax has not been authoritatively verified; planning blocked.")
    require(digest(Path(__file__).read_bytes()) == receipt["operatorScriptSha256"],
            "Operator script does not match reviewed bundle.")
    prefix = "completion" if completion else "import"
    require(re.fullmatch(rf"bridge-staging-application-{prefix}-[a-zA-Z0-9-]+", change_set_name),
            "Unexpected change set name.")
    destination = directory / f"{change_set_name}.json"
    require(not destination.exists(), "Use a fresh change set name; preserve prior planning evidence.")
    if completion:
        managed = validate_managed_import(aws, payloads)
    else:
        require_stack_absent(aws)
        managed = payloads["snapshot.json"]["recorded"]
    require(aws("s3api", "get-bucket-versioning", "--bucket", BUCKET).get("Status") == "Enabled",
            "Artifact bucket versioning must be enabled.")
    tags = {tag["Key"]: tag["Value"] for tag in
            aws("s3api", "get-bucket-tagging", "--bucket", BUCKET)["TagSet"]}
    require(tags.get("Application") == "Bridge" and tags.get("Environment") == "staging",
            "Unexpected artifact bucket tags.")
    require(aws("iam", "get-role", "--role-name", "BridgeStagingApplicationExecution")
            ["Role"]["Arn"] == EXECUTION_ROLE, "Unexpected execution role.")
    inventory, mapping = collect_inventory(
        aws, payloads["full-template.json"], managed)
    require(mapping == payloads["resources-to-import.json"], "Live physical bindings changed.")
    # Identity, stack state, bundle and live physical bindings must pass before writes.
    aws.allow_writes = True
    filename = "full-template.json" if completion else "import-template.json"
    change_set_type = "UPDATE" if completion else "IMPORT"
    template_digest = receipt["sha256"][filename]
    key = f"releases/application-import/{template_digest}/{filename}"
    uploaded = aws("s3api", "put-object", "--bucket", BUCKET, "--key", key,
                   "--body", str(directory / filename), "--if-none-match", "*",
                   "--checksum-sha256", base64.b64encode(bytes.fromhex(template_digest)).decode(),
                   "--metadata", f"sha256={template_digest}", "--server-side-encryption", "AES256")
    version = uploaded.get("VersionId")
    require(isinstance(version, str) and version not in {"", "null"},
            "S3 did not return an immutable template version.")
    url = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{key}?versionId={quote(version, safe='')}"
    resources = () if completion else ("--resources-to-import", json.dumps(mapping))
    change_set = aws(
        "cloudformation", "create-change-set", "--stack-name", STACK,
        "--change-set-name", change_set_name, "--change-set-type", change_set_type,
        "--role-arn", EXECUTION_ROLE, "--template-url", url,
        *resources,
        "--parameters", json.dumps(payloads["parameters.json"]),
        "--tags", "Key=Application,Value=Bridge", "Key=Environment,Value=staging",
    )
    pending = {"identity": identity, "templateURL": url, "templateVersion": version,
               "requestedChangeSetType": change_set_type,
               "changeSetCreated": change_set, "execution": "NOT EXECUTED"}
    with destination.open("x") as output:
        output.write(encoded(pending).decode())
    for _ in range(120):
        preview = aws("cloudformation", "describe-change-set",
                      "--stack-name", STACK, "--change-set-name", change_set["Id"])
        if preview["Status"] not in {"CREATE_PENDING", "CREATE_IN_PROGRESS"}:
            break
        time.sleep(5)
    result = {"identity": identity, "templateURL": url, "templateVersion": version,
              "requestedChangeSetType": change_set_type,
              "changeSet": preview, "liveInventorySha256": digest(encoded(inventory)),
              "execution": "NOT EXECUTED"}
    destination.write_bytes(encoded(result))
    expected = ([{"LogicalResourceId": logical,
                  "ResourceType": payloads["full-template.json"]["Resources"][logical]["Type"]}
                 for logical in sorted(ABSENT)] if completion else mapping)
    validate_preview(preview, expected, completion=completion)
    return result


def validate_managed_import(aws, payloads):
    stacks = aws("cloudformation", "describe-stacks", "--stack-name", STACK)["Stacks"]
    require(len(stacks) == 1, "Expected exactly one imported application stack.")
    stack = stacks[0]
    require(stack["StackName"] == STACK and stack["StackStatus"] == "IMPORT_COMPLETE"
            and stack["StackId"].startswith(
                f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/")
            and stack.get("RoleARN") == EXECUTION_ROLE,
            "Completion requires application IMPORT_COMPLETE with the original execution role.")
    require(parameters(stack) == payloads["parameters.json"], "Imported release parameters changed.")
    tags = {tag["Key"]: tag["Value"] for tag in stack.get("Tags", [])}
    require(tags.get("Application") == "Bridge" and tags.get("Environment") == "staging",
            "Unexpected imported application stack tags.")
    template = aws("cloudformation", "get-template", "--stack-name", STACK,
                   "--template-stage", "Original")["TemplateBody"]
    template = json.loads(template) if isinstance(template, str) else template
    require(template == payloads["import-template.json"],
            "Managed import template differs from the frozen 129-resource template.")
    recorded = aws("cloudformation", "list-stack-resources",
                   "--stack-name", STACK)["StackResourceSummaries"]
    expected = {
        r["LogicalResourceId"]: (r["ResourceType"], r["PhysicalResourceId"])
        for r in payloads["snapshot.json"]["recorded"] if r["LogicalResourceId"] not in ABSENT
    }
    actual = {r["LogicalResourceId"]: (r["ResourceType"], r.get("PhysicalResourceId"))
              for r in recorded}
    require(len(recorded) == 129 and actual == expected,
            "Managed 129 logical/type/physical bindings differ from the recovery bundle.")
    return recorded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("export", "validate", "plan", "plan-completion"):
        sub = commands.add_parser(command)
        sub.add_argument("--directory", type=Path, required=True)
        if command in {"plan", "plan-completion"}:
            sub.add_argument("--change-set-name", required=True)
    args = parser.parse_args()
    if args.command == "export":
        receipt = export_bundle(AWS(), args.directory)
        print(json.dumps({"directory": str(args.directory), "sha256": receipt["sha256"],
                          "importCount": 129, "fullCount": 132}, indent=2))
    elif args.command == "validate":
        receipt, _ = validate_bundle(args.directory)
        print(json.dumps({"validated": True, "sha256": receipt["sha256"]}, indent=2))
    else:
        completion = args.command == "plan-completion"
        result = plan_bundle(AWS(), args.directory, args.change_set_name, completion=completion)
        print(json.dumps({"changeSetId": result["changeSet"]["ChangeSetId"],
                          "adds" if completion else "imports": 3 if completion else 129,
                          "execution": "NOT EXECUTED"}, indent=2))


if __name__ == "__main__":
    main()
