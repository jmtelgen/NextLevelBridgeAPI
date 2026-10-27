"""Explicit offline CI suites; legacy tests and local-server fixtures are not collected."""

import argparse
import ctypes
import hashlib
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CORE_FILES = (
    "tests/test_account_create.py",
    "tests/test_auth_flow.py",
    "tests/test_socket_sessions.py",
    "tests/test_websocket_make_bid.py",
    "tests/test_bridge_lifecycle.py",
    "tests/test_room_lifecycle.py",
    "tests/test_board_records.py",
    "tests/test_claims.py",
    "tests/test_duplicate_events.py",
    "tests/test_game_pacing.py",
    "tests/test_game_tick.py",
    "tests/test_robot_fair_play.py",
    "tests/test_robot_bidder_fair.py",
    "tests/test_robot_sayc_boundaries.py",
    "tests/test_robot_benchmark.py",
    "tests/test_practice_computer_levels.py",
    "tests/test_websocket_practice.py",
    "lambdas/tests/unit/test_sayc_opening_bids.py",
)
NATIVE_TESTS = (
    "tests/test_robot_fair_play.py::test_native_dds_known_answer_partial_leader_and_side",
    "tests/test_robot_fair_play.py::test_native_sampled_full_deal_with_authoritative_rules",
    "tests/test_robot_benchmark.py::test_native_benchmark_cli_smoke",
)
DDS_SHA256 = "155e9b4835eb28b88f46f522aa8794b242b17a808037b1140823e70e62e5dff8"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=("core", "native"))
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    for key in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_WEB_IDENTITY_TOKEN_FILE",
                "AWS_ROLE_ARN", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
                "AWS_CONTAINER_CREDENTIALS_FULL_URI", "AWS_ENDPOINT_URL",
                "AWS_ENDPOINT_URL_DYNAMODB", "AWS_ENDPOINT_URL_SECRETS_MANAGER"):
        os.environ.pop(key, None)
    os.environ.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_REGION": "us-east-1",
        "AWS_CONFIG_FILE": os.devnull,
        "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
    })

    import botocore.httpsession
    import pytest

    def deny_aws_transport(*_args, **_kwargs):
        raise AssertionError("CI forbids real AWS SDK network traffic; use Moto or mocks")

    botocore.httpsession.URLLib3Session.send = deny_aws_transport
    selectors = [str(ROOT / path) for path in CORE_FILES]
    options = ["-q", "-ra", "--tb=short", "-p", "no:cacheprovider"]
    if args.suite == "native":
        library = ROOT / "lambdas/dds/libdds.so.2.9.0"
        if hashlib.sha256(library.read_bytes()).hexdigest() != DDS_SHA256:
            raise RuntimeError("Tracked DDS binary changed: review provenance and update its digest")
        # The existing wrapper searches the working directory, not its package.
        os.chdir(library.parent)
        from lambdas.core.robot.fair_play import default_solver

        default_solver()  # Fail this gate rather than silently skipping missing DDS.
        selectors = [str(ROOT / node) for node in NATIVE_TESTS]
        print("Native DDS gate: tracked x86_64 Linux binary; NOT Lambda ABI validation.")
    else:
        os.chdir(ROOT)
        load_library = ctypes.cdll.LoadLibrary

        def without_dds(name):
            if "libdds" in str(name):
                raise OSError("Native DDS is deliberately unavailable in the core CI gate")
            return load_library(name)

        ctypes.cdll.LoadLibrary = without_dds
        options.extend(f"--deselect={node}" for node in NATIVE_TESTS)
        print("Core gate: DDS disabled; native tests and loopback integration excluded.")
    return pytest.main([*options, *selectors])


if __name__ == "__main__":
    raise SystemExit(main())
