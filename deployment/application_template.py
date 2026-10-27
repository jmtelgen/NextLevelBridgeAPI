#!/usr/bin/env python3
"""Render the application-only stack from the reviewed runtime route manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def ref(name):
    return {"Ref": name}


def sub(value):
    return {"Fn::Sub": value}


def att(name, attribute="Arn"):
    return {"Fn::GetAtt": [name, attribute]}


def logical(prefix, value):
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:16]


def application_template(release_digest):
    if not re.fullmatch(r"[a-f0-9]{64}", release_digest):
        raise ValueError("A lowercase artifact SHA-256 is required.")
    manifest = json.loads((ROOT / "deployment/runtime-routes.json").read_text())
    parameters = {
        "ArtifactKey": {
            "Type": "String",
            "AllowedPattern": r"^releases/[a-f0-9]{40}/[a-f0-9]{64}/[0-9]+-[0-9]+/bridge-staging-[a-f0-9]{64}\.zip$",
        },
        "ArtifactVersion": {"Type": "String", "MinLength": 1},
        "SourceCommit": {"Type": "String", "AllowedPattern": "^[a-f0-9]{40}$"},
        "RestApiId": {"Type": "String", "AllowedPattern": "^(?!e2jrh99dbc$)[a-z0-9]{10}$"},
        "RestApiRootResourceId": {"Type": "String", "AllowedPattern": "^[a-z0-9]+$"},
        "WebSocketApiId": {"Type": "String", "AllowedPattern": "^(?!ipp77av3oi$)[a-z0-9]{10}$"},
        "StagingOrigin": {
            "Type": "String",
            "AllowedPattern": r"^(?!https://d1h54yowalg875\.cloudfront\.net$)https://d[a-z0-9]+\.cloudfront\.net$",
        },
    }
    environment = {
        **manifest["environment"]["fixed"],
        "USER_TABLE": "bridge-staging-users",
        "ROOM_TABLE": "bridge-staging-rooms",
        "WEBSOCKET_CONNECTIONS_TABLE": "bridge-staging-connections",
        "DUPLICATE_EVENTS_TABLE": "bridge-staging-duplicate-events",
        "BOARD_ARCHIVES_TABLE": "bridge-staging-board-archives",
        "JWT_SECRET_ID": "bridge-staging-jwt-v2",
        "FRONTEND_URL": ref("StagingOrigin"),
        "WS_ALLOWED_ORIGINS": ref("StagingOrigin"),
        "WEBSOCKET_ENDPOINT": sub("https://${WebSocketApiId}.execute-api.${AWS::Region}.${AWS::URLSuffix}/staging"),
        "GAME_TICK_QUEUE_URL": "https://sqs.us-west-2.amazonaws.com/851725597758/bridge-staging-game-tick",
        "BRIDGE_RELEASE_SHA": ref("SourceCommit"),
    }
    if not set(manifest["environment"]["required"]) <= set(environment):
        raise ValueError("Runtime manifest requires unconfigured environment variables.")
    tags = [{"Key": "Application", "Value": "Bridge"}, {"Key": "Environment", "Value": "staging"}]
    resources = {}

    def add(name, kind, properties, depends=()):
        resource = {
            "Type": kind, "DeletionPolicy": "Retain", "UpdateReplacePolicy": "Retain",
            "Properties": properties,
        }
        if depends:
            resource["DependsOn"] = list(depends)
        resources[name] = resource
        return name

    functions = {}
    for name, function in manifest["functions"].items():
        function_id = logical("Function", name)
        physical_name = manifest["functionNamePrefix"] + name.replace("_", "-")
        role = (
            "BridgeStagingTickDispatchRuntime" if name == "game_tick_dispatcher"
            else "BridgeStagingTickRuntime" if name == "game_tick_worker"
            else "BridgeStagingApplicationRuntime"
        )
        log_id = add(logical("Logs", name), "AWS::Logs::LogGroup", {
            "LogGroupName": "/aws/lambda/" + physical_name,
            "RetentionInDays": 14, "Tags": tags,
        })
        add(function_id, "AWS::Lambda::Function", {
            "FunctionName": physical_name,
            "Description": sub("Bridge staging release ${SourceCommit}"),
            "Runtime": manifest["runtime"],
            "Architectures": [manifest["architecture"]],
            "Handler": function["handler"],
            "Role": sub("arn:${AWS::Partition}:iam::${AWS::AccountId}:role/" + role),
            "Timeout": function.get("timeoutSeconds", manifest["defaults"]["timeoutSeconds"]),
            "MemorySize": manifest["defaults"]["memorySizeMB"],
            "Code": {
                "S3Bucket": "bridge-staging-artifacts-851725597758-us-west-2",
                "S3Key": ref("ArtifactKey"), "S3ObjectVersion": ref("ArtifactVersion"),
            },
            "Environment": {"Variables": environment},
            "Tags": tags,
        }, [log_id])
        functions[name] = function_id

    path_ids = {"/": ref("RestApiRootResourceId")}
    method_ids = []
    cors_paths = set()
    for route in manifest["http"]["routes"]:
        parent = path_ids["/"]
        current = ""
        for component in route["path"].strip("/").split("/"):
            current += "/" + component
            if current not in path_ids:
                resource_id = add(logical("Path", current), "AWS::ApiGateway::Resource", {
                    "RestApiId": ref("RestApiId"), "ParentId": parent, "PathPart": component,
                })
                path_ids[current] = ref(resource_id)
            parent = path_ids[current]
        function_id = functions[route["function"]]
        permission = add(logical("HttpPermission", route["method"] + route["path"]),
                         "AWS::Lambda::Permission", {
            "Action": "lambda:InvokeFunction", "FunctionName": att(function_id),
            "Principal": "apigateway.amazonaws.com", "SourceAccount": ref("AWS::AccountId"),
            "SourceArn": sub("arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${RestApiId}/staging/"
                             + route["method"] + route["path"]),
        })
        method_id = add(logical("Method", route["method"] + route["path"]),
                        "AWS::ApiGateway::Method", {
            "RestApiId": ref("RestApiId"), "ResourceId": parent,
            "HttpMethod": route["method"], "AuthorizationType": "NONE",
            "Integration": {
                "Type": "AWS_PROXY", "IntegrationHttpMethod": "POST",
                "TimeoutInMillis": 29000,
                "Uri": sub("arn:${AWS::Partition}:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${"
                           + function_id + ".Arn}/invocations"),
            },
        }, [permission])
        method_ids.append(method_id)
        cors_paths.add(route["path"])

    for path in sorted(cors_paths):
        headers = {
            "Access-Control-Allow-Origin": {"Fn::Join": ["", ["'", ref("StagingOrigin"), "'"]]},
            "Access-Control-Allow-Credentials": "'true'",
            "Access-Control-Allow-Methods": "'" + ",".join(manifest["http"]["cors"]["methods"]) + "'",
            "Access-Control-Allow-Headers": "'" + ",".join(manifest["http"]["cors"]["headers"]) + "'",
        }
        method_ids.append(add(logical("Cors", path), "AWS::ApiGateway::Method", {
            "RestApiId": ref("RestApiId"), "ResourceId": path_ids[path],
            "HttpMethod": "OPTIONS", "AuthorizationType": "NONE",
            "Integration": {
                "Type": "MOCK",
                "RequestTemplates": {"application/json": '{"statusCode":200}'},
                "IntegrationResponses": [{
                    "StatusCode": "200",
                    "ResponseParameters": {"method.response.header." + key: value for key, value in headers.items()},
                }],
            },
            "MethodResponses": [{
                "StatusCode": "200",
                "ResponseParameters": {"method.response.header." + key: True for key in headers},
            }],
        }))

    rest_deployment = add("RestDeployment" + release_digest[:16], "AWS::ApiGateway::Deployment", {
        "RestApiId": ref("RestApiId"), "Description": sub("Release ${SourceCommit}"),
    }, method_ids)
    add("RestStage", "AWS::ApiGateway::Stage", {
        "RestApiId": ref("RestApiId"), "DeploymentId": ref(rest_deployment),
        "StageName": "staging", "Tags": tags,
        "MethodSettings": [{
            "ResourcePath": "/*", "HttpMethod": "*", "DataTraceEnabled": False,
            "MetricsEnabled": True, "ThrottlingBurstLimit": 100, "ThrottlingRateLimit": 50,
        }],
    })

    integrations = {}
    ws_routes = []
    for route in manifest["websocket"]["routes"]:
        name = route["function"]
        function_id = functions[name]
        if name not in integrations:
            permission = add(logical("WsPermission", name), "AWS::Lambda::Permission", {
                "Action": "lambda:InvokeFunction", "FunctionName": att(function_id),
                "Principal": "apigateway.amazonaws.com", "SourceAccount": ref("AWS::AccountId"),
                "SourceArn": sub("arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${WebSocketApiId}/staging/*"),
            })
            integrations[name] = add(logical("Integration", name), "AWS::ApiGatewayV2::Integration", {
                "ApiId": ref("WebSocketApiId"), "IntegrationType": "AWS_PROXY",
                "IntegrationMethod": "POST", "TimeoutInMillis": 29000,
                "IntegrationUri": sub("arn:${AWS::Partition}:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${"
                                      + function_id + ".Arn}/invocations"),
            }, [permission])
        ws_routes.append(add(logical("Route", route["routeKey"]), "AWS::ApiGatewayV2::Route", {
            "ApiId": ref("WebSocketApiId"), "RouteKey": route["routeKey"],
            "AuthorizationType": "NONE",
            "Target": {"Fn::Join": ["/", ["integrations", ref(integrations[name])]]},
        }))
    ws_deployment = add("WebSocketDeployment" + release_digest[:16], "AWS::ApiGatewayV2::Deployment", {
        "ApiId": ref("WebSocketApiId"), "Description": sub("Release ${SourceCommit}"),
    }, ws_routes)
    add("WebSocketStage", "AWS::ApiGatewayV2::Stage", {
        "ApiId": ref("WebSocketApiId"), "DeploymentId": ref(ws_deployment),
        "StageName": "staging", "AutoDeploy": False,
        "DefaultRouteSettings": {
            "DetailedMetricsEnabled": True, "ThrottlingBurstLimit": 100, "ThrottlingRateLimit": 50,
        },
        "Tags": {"Application": "Bridge", "Environment": "staging"},
    })
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Bridge staging application only; pre-created platform/runtime authority required.",
        "Parameters": parameters,
        "Metadata": {"ArtifactSha256": release_digest},
        "Resources": resources,
        "Outputs": {
            "SourceCommit": {"Value": ref("SourceCommit")},
            "ArtifactSha256": {"Value": release_digest},
            "StagingOrigin": {"Value": ref("StagingOrigin")},
            "TickWorkerFunctionArn": {"Value": att(functions["game_tick_worker"])},
            "TickDispatchFunctionArn": {"Value": att(functions["game_tick_dispatcher"])},
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(application_template(args.artifact_sha256), indent=2) + "\n")
