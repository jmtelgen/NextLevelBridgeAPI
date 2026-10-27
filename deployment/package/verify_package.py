#!/usr/bin/env python3
"""Required target-runtime import, durable bootstrap, and native DDS solve gate."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import socket
import sys
import zipfile


def fail_network(*args, **kwargs):
    raise AssertionError("Package smoke tests must not access the network")


def verify_store_namespaces():
    prefix = "lambdas.core.game."
    modules = {
        name: importlib.import_module(prefix + name)
        for name in ("runtime", "duplicate", "archives")
    }
    game = modules["runtime"]
    for name in ("duplicate", "archives"):
        if getattr(game, name) is not modules[name]:
            raise RuntimeError(f"Game runtime uses a different {name} module singleton")
    for name, canonical in modules.items():
        alternate = sys.modules.get("core.game." + name)
        if alternate is not None and alternate is not canonical:
            raise RuntimeError(f"Alternate core.game.{name} module copy was loaded")
    checked = []

    def check(module_name, attribute, expected):
        module = importlib.import_module(module_name)
        if getattr(module, attribute) is not expected:
            raise RuntimeError(f"Handler namespace mismatch: {module_name}.{attribute}")
        checked.append(module_name)
        return module

    check("lambdas.core.rooms.lifecycle", "runtime", game)
    check("lambdas.api.game.game_tick", "runtime", game)
    socket = "lambdas.api.websocket."
    for name in ("websocket_start_room", "websocket_make_bid", "websocket_play_card",
                 "websocket_board_records", "websocket_claims_duplicate"):
        check(socket + name, "process_game_request", game.process_game_request)
    check(socket + "websocket_claims_duplicate", "duplicate", modules["duplicate"])
    controls = check(socket + "websocket_room_controls", "runtime", game)
    check(socket + "websocket_practice", "runtime", game)
    for name in ("websocket_leave_room", "websocket_replace_player"):
        check(socket + name, "lambda_handler", controls.lambda_handler)
    for name in ("websocket_create_room", "websocket_join_room", "websocket_change_seat"):
        check(socket + name, "connection_user", game.connection_user)
    check(socket + "websocket_connect", "GameRequestError", game.GameRequestError)
    lifecycle = importlib.import_module("lambdas.core.rooms.lifecycle")
    check(socket + "websocket_disconnect", "sync_user_presence", lifecycle.sync_user_presence)
    return {
        "runtime": prefix + "runtime",
        "duplicate": prefix + "duplicate",
        "archives": prefix + "archives",
        "handlers": sorted(set(checked)),
        "alternateModuleCopies": False,
    }


def verify(artifacts, extract_to):
    if sys.version_info[:2] != (3, 12) or platform.machine() != "x86_64":
        raise RuntimeError("Package validation requires CPython 3.12 x86_64")
    release = Path("/etc/os-release").read_text()
    if 'ID="amzn"' not in release or 'VERSION_ID="2023"' not in release:
        raise RuntimeError("Package validation requires the AL2023 Lambda runtime")
    packages = list(artifacts.glob("bridge-staging-*.zip"))
    if len(packages) != 1:
        raise RuntimeError("Validation requires exactly one package")
    package = packages[0]
    sha = hashlib.sha256(package.read_bytes()).hexdigest()
    if package.name != f"bridge-staging-{sha}.zip":
        raise RuntimeError("Artifact filename does not match package digest")
    with zipfile.ZipFile(package) as archive:
        for name in archive.namelist():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                raise RuntimeError("Unsafe ZIP member")
        archive.extractall(extract_to)
    os.chdir(extract_to)
    sys.path.insert(0, str(extract_to))
    receipt = json.loads((extract_to / "PACKAGE-RECEIPT.json").read_text())
    for name, expected in receipt["files"].items():
        if hashlib.sha256((extract_to / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Package receipt mismatch: {name}")
    os.environ.update({
        "AWS_ACCESS_KEY_ID": "package-validation-only",
        "AWS_SECRET_ACCESS_KEY": "package-validation-only",
        "AWS_SESSION_TOKEN": "package-validation-only",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_DEFAULT_REGION": "us-west-2", "AWS_REGION": "us-west-2",
        "AWS_LAMBDA_FUNCTION_NAME": "bridge-staging-package-check",
        "AWS_SHARED_CREDENTIALS_FILE": "/dev/null", "AWS_CONFIG_FILE": "/dev/null",
        "USER_TABLE": "package-users", "ROOM_TABLE": "package-rooms",
        "WEBSOCKET_CONNECTIONS_TABLE": "package-connections",
        "DUPLICATE_EVENTS_TABLE": "package-events",
        "BOARD_ARCHIVES_TABLE": "package-archives",
        "JWT_SECRET_ID": "package-jwt", "ENVIRONMENT": "production",
        "FRONTEND_URL": "https://frontend.invalid",
        "WS_ALLOWED_ORIGINS": "https://frontend.invalid",
        "WEBSOCKET_ENDPOINT": "https://websocket.invalid/staging",
        "GAME_TICK_QUEUE_URL": "https://sqs.us-west-2.amazonaws.com/000000000000/ticks",
    })
    socket.socket.connect = fail_network
    socket.create_connection = fail_network
    import botocore.httpsession

    botocore.httpsession.URLLib3Session.send = fail_network
    manifest = json.loads((extract_to / "deployment/runtime-routes.json").read_text())
    imported = set()
    for function in manifest["functions"].values():
        for target in (function["handler"], function.get("entrypoint")):
            if target:
                module, name = target.rsplit(".", 1)
                if not callable(getattr(importlib.import_module(module), name)):
                    raise RuntimeError(f"Non-callable Lambda entrypoint: {target}")
                imported.add(target)
    import staging_runtime
    from lambdas.core.game import archives, duplicate
    from lambdas.dds.working_dds_wrapper import DDS
    import bcrypt
    from pydantic import BaseModel

    staging_runtime.initialize()
    if not isinstance(duplicate.store, duplicate.DynamoEventStore):
        raise RuntimeError("Duplicate event store was not durably initialized")
    if not isinstance(archives.store, archives.DynamoArchiveStore):
        raise RuntimeError("Board archive store was not durably initialized")
    if (duplicate.store.table.name != os.environ["DUPLICATE_EVENTS_TABLE"]
            or archives.store.table.name != os.environ["BOARD_ARCHIVES_TABLE"]):
        raise RuntimeError("Durable stores target the wrong staging tables")
    durable_namespace = verify_store_namespaces()
    hashed = bcrypt.hashpw(b"package-smoke", bcrypt.gensalt(rounds=4))
    if not bcrypt.checkpw(b"package-smoke", hashed):
        raise RuntimeError("bcrypt native wheel failed its smoke test")
    if BaseModel().dict() != {}:
        raise RuntimeError("Pydantic pure-Python wheel failed its smoke test")
    from lambdas.api.auth.account_logout import lambda_handler as logout

    cookies = logout({}, None)["multiValueHeaders"]["Set-Cookie"]
    if not cookies or not all("; Secure" in cookie for cookie in cookies):
        raise RuntimeError("Staging must retain production-compatible Secure cookies")
    solver = DDS(max_threads=1, max_memory=32)
    result = solver.solve_board(
        trump="N", first="N", current_trick=[],
        hands={"N": ["SA"], "E": ["SK"], "S": ["SQ"], "W": ["SJ"]},
        target=-1, solutions=1, mode=1, thread_index=0,
    )
    if result != [("SA", 1)]:
        raise RuntimeError(f"Unexpected DDS native solve result: {result!r}")
    pins = json.loads((extract_to / "deployment/package/native-source.json").read_text())
    report = {
        "artifactSha256": sha,
        "runtimeImage": pins["runtimeImage"],
        "runtime": "python3.12", "architecture": "x86_64", "os": "AL2023",
        "entrypoints": sorted(imported),
        "receiptVerified": True, "durableBootstrap": True,
        "durableNamespace": durable_namespace,
        "dependencySmoke": ["bcrypt native hash/check", "Pydantic model", "Secure logout cookie"],
        "nativeSolve": {"card": "SA", "tricks": 1},
        "network": "denied",
        "notValidated": ["Live AWS routes", "IAM", "JWT secret retrieval", "DynamoDB transactions", "end-to-end gameplay"],
    }
    (artifacts / f"bridge-staging-{sha}.validation.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(report, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--extract-to", type=Path, required=True)
    args = parser.parse_args()
    verify(args.artifacts.resolve(), args.extract_to.resolve())


if __name__ == "__main__":
    main()
