"""Staging-only durable-store bootstrap; preserve each existing handler unchanged."""
import importlib
import json
import os
from pathlib import Path
import threading

_initialized = False
_lock = threading.Lock()


def initialize():
    global _initialized
    with _lock:
        if _initialized:
            return
        import boto3
        from lambdas.core.game import archives, duplicate

        # Fail before serving traffic, rather than silently using process-local state.
        table_name = os.environ.get("DUPLICATE_EVENTS_TABLE", "").strip()
        archive_name = os.environ.get("BOARD_ARCHIVES_TABLE", "").strip()
        if not table_name or not archive_name:
            raise RuntimeError(
                "DUPLICATE_EVENTS_TABLE and BOARD_ARCHIVES_TABLE must be nonempty"
            )
        duplicate.store = duplicate.DynamoEventStore(
            boto3.resource("dynamodb").Table(table_name)
        )
        archives.configure_from_environment()
        _initialized = True


def _entrypoint(target):
    module, attribute = target.rsplit(".", 1)

    def invoke(event, context):
        initialize()
        return getattr(importlib.import_module(module), attribute)(event, context)

    return invoke


_manifest = json.loads(
    (Path(__file__).parent / "deployment" / "runtime-routes.json").read_text()
)
for _function in _manifest["functions"].values():
    if _function["handler"].startswith("staging_runtime."):
        globals()[_function["handler"].split(".")[1]] = _entrypoint(
            _function["entrypoint"]
        )
