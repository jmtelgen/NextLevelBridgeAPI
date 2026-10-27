#!/usr/bin/env python3
"""Stdlib-only packaging tests: no AWS access, native loading, or /tmp usage."""
import ast
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "deployment/runtime-routes.json").read_text())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("staging_zip_builder", Path(__file__).parent / "build_zip.py")
native_builder = load("staging_native_builder", Path(__file__).parent / "build_dds.py")
verifier = load("staging_package_verifier", Path(__file__).parent / "verify_package.py")
runtime = load("staging_runtime_test", ROOT / "staging_runtime.py")


class RouteManifestTests(unittest.TestCase):
    def test_exact_local_route_coverage(self):
        source = ast.parse((ROOT / "scripts/local_server.py").read_text())
        values = {}
        for node in source.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in (
                        "HTTP_HANDLERS", "WS_HANDLERS"
                    ):
                        values[target.id] = eval(
                            compile(ast.Expression(node.value), "<local-routes>", "eval"),
                            {"__builtins__": {}},
                        )
        expected_http = {
            ("POST", "/api" + path): handler
            for path, handler in values["HTTP_HANDLERS"].items()
        }
        expected_http[("GET", "/api/connections")] = "connection_count"
        actual_http = {
            (route["method"], route["path"]): route["function"]
            for route in MANIFEST["http"]["routes"]
        }
        actual_ws = {
            route["routeKey"]: route["function"]
            for route in MANIFEST["websocket"]["routes"]
        }
        self.assertEqual(expected_http, actual_http)
        self.assertEqual(values["WS_HANDLERS"], actual_ws)
        self.assertEqual(len(actual_http), len(MANIFEST["http"]["routes"]))
        self.assertEqual(len(actual_ws), len(MANIFEST["websocket"]["routes"]))

    def test_handlers_exist_and_wrappers_are_callable(self):
        referenced = {route["function"] for group in ("http", "websocket")
                      for route in MANIFEST[group]["routes"]}
        referenced.update(source["function"] for source in MANIFEST["eventSources"])
        self.assertEqual(referenced, set(MANIFEST["functions"]))
        for function in MANIFEST["functions"].values():
            target = function.get("entrypoint", function["handler"])
            module, attribute = target.rsplit(".", 1)
            path = ROOT / (module.replace(".", "/") + ".py")
            source = ast.parse(path.read_text())
            exported = {
                node.name for node in source.body if isinstance(node, ast.FunctionDef)
            }
            exported.update(
                alias.asname or alias.name for node in source.body
                if isinstance(node, ast.ImportFrom) for alias in node.names
            )
            self.assertIn(attribute, exported, target)
            if "entrypoint" in function:
                self.assertEqual("staging_runtime", function["handler"].split(".")[0])
                self.assertTrue(callable(getattr(runtime, function["handler"].split(".")[1])))

    def test_gateway_and_tick_contract(self):
        self.assertEqual("REST", MANIFEST["http"]["apiType"])
        self.assertEqual("1.0", MANIFEST["http"]["payloadFormatVersion"])
        self.assertEqual("/api", MANIFEST["http"]["basePath"])
        self.assertEqual("$request.body.action", MANIFEST["websocket"]["routeSelectionExpression"])
        self.assertIsNone(MANIFEST["websocket"]["applicationRouteResponseKey"])
        self.assertEqual("production", MANIFEST["environment"]["fixed"]["ENVIRONMENT"])
        self.assertEqual("NEW_IMAGE", MANIFEST["eventSources"][0]["streamViewType"])
        for source in MANIFEST["eventSources"]:
            self.assertIn("ReportBatchItemFailures", source["functionResponseTypes"])
        worker = MANIFEST["functions"]["game_tick_worker"]
        self.assertGreaterEqual(
            MANIFEST["eventSources"][1]["visibilityTimeoutSeconds"],
            worker["timeoutSeconds"] * 6,
        )
        grouped = [name for group in MANIFEST["roleGroups"].values()
                   for name in group["functions"]]
        self.assertCountEqual(grouped, MANIFEST["functions"])

    def test_native_image_and_dependency_pins(self):
        package = ROOT / "deployment/package"
        pins = json.loads((package / "native-source.json").read_text())
        dockerfile = (package / "staging.Dockerfile").read_text()
        for key in ("builderImage", "runtimeImage"):
            self.assertRegex(pins[key], r"@sha256:[0-9a-f]{64}$")
            self.assertIn(pins[key], dockerfile)
        self.assertRegex(pins["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn(pins["commit"], pins["archive"])
        lines = [line for line in (package / "requirements.lock").read_text().splitlines()
                 if line and not line.startswith("#")]
        self.assertEqual(12, len(lines))
        for line in lines:
            self.assertRegex(line, r"^[A-Za-z0-9_-]+==[0-9.]+(?:post[0-9]+)? --hash=sha256:[0-9a-f]{64}$")

    def test_native_patch_is_narrow_and_fail_closed(self):
        source = '''before
  FILE * fifo = popen(
    "free -k | tail -n+3 | head -n1 | awk '{print $NF}'", "r");
  int ignore = fscanf(fifo, "%llu", &kilobytesFree);
  fclose(fifo);

  ncores = sysconf(_SC_NPROCESSORS_ONLN);
  return;
after'''
        patched = native_builder.patch_linux_resources(source)
        self.assertTrue(patched.startswith("before\n"))
        self.assertTrue(patched.endswith("\nafter"))
        self.assertNotIn("popen", patched)
        self.assertIn("kilobytesFree = 256ULL * 1024ULL;", patched)
        self.assertIn("ncores = 1;", patched)
        with self.assertRaisesRegex(ValueError, "changed"):
            native_builder.patch_linux_resources("unexpected source")

    def test_native_links_shared_target_runtime_without_static_archives(self):
        flags = native_builder.LINK_FLAGS.split()
        self.assertIn("-shared", flags)
        self.assertIn("-Wl,-soname,libdds.so.2", flags)
        self.assertIn("-pthread", flags)
        self.assertFalse(any(flag.startswith("-static") for flag in flags))
        pins = json.loads((ROOT / "deployment/package/native-source.json").read_text())
        self.assertIn("dynamic libstdc++.so.6, libgcc_s.so.1", pins["linking"])

    def test_native_lifecycle_orders_cleanup_before_singleton_destruction(self):
        dds = '''static void __attribute__ ((constructor)) libInit(void)
{
  SetMaxThreads(0);
}


static void __attribute__ ((destructor)) libEnd(void)
{
  CloseDebugFiles();
  FreeMemory();
}'''
        init = '''System sysdep;
Memory memory;
Scheduler scheduler;
ThreadMgr threadMgr;'''
        patched_dds, patched_init = native_builder.patch_linux_lifecycle(dds, init)
        self.assertNotIn("__attribute__", patched_dds)
        self.assertGreater(
            patched_init.index("DDSLibraryLifecycle ddsLibraryLifecycle;"),
            patched_init.index("ThreadMgr threadMgr;"),
        )
        self.assertIn("DDSLibraryLifecycle() { SetMaxThreads(0); }", patched_init)
        self.assertIn("~DDSLibraryLifecycle()", patched_init)
        self.assertIn("CloseDebugFiles();\n    FreeMemory();", patched_init)
        with self.assertRaisesRegex(ValueError, "lifecycle changed"):
            native_builder.patch_linux_lifecycle("unexpected source", init)


class NamespaceTests(unittest.TestCase):
    def setUp(self):
        self.modules = {}
        self.game = types.ModuleType("lambdas.core.game.runtime")
        for name in ("duplicate", "archives"):
            module = types.ModuleType("lambdas.core.game." + name)
            self.modules[module.__name__] = module
            setattr(self.game, name, module)
        for name in ("process_game_request", "connection_user", "GameRequestError"):
            setattr(self.game, name, object())
        self.modules[self.game.__name__] = self.game
        self.add("lambdas.core.rooms.lifecycle", runtime=self.game, sync_user_presence=object())
        self.add("lambdas.api.game.game_tick", runtime=self.game)
        socket = "lambdas.api.websocket."
        for name in ("websocket_start_room", "websocket_make_bid", "websocket_play_card",
                     "websocket_board_records", "websocket_claims_duplicate"):
            self.add(socket + name, process_game_request=self.game.process_game_request)
        self.modules[socket + "websocket_claims_duplicate"].duplicate = self.game.duplicate
        self.add(socket + "websocket_room_controls", runtime=self.game, lambda_handler=object())
        self.add(socket + "websocket_practice", runtime=self.game)
        for name in ("websocket_leave_room", "websocket_replace_player"):
            self.add(socket + name, lambda_handler=self.modules[socket + "websocket_room_controls"].lambda_handler)
        for name in ("websocket_create_room", "websocket_join_room", "websocket_change_seat"):
            self.add(socket + name, connection_user=self.game.connection_user)
        self.add(socket + "websocket_connect", GameRequestError=self.game.GameRequestError)
        self.add(socket + "websocket_disconnect", sync_user_presence=self.modules["lambdas.core.rooms.lifecycle"].sync_user_presence)
        self.importer = patch.object(verifier.importlib, "import_module", side_effect=self.modules.__getitem__)
        self.importer.start()

    def tearDown(self):
        self.importer.stop()

    def add(self, name, **attributes):
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        self.modules[name] = module

    def test_actual_delegated_namespaces_reference_configured_singletons(self):
        result = verifier.verify_store_namespaces()
        self.assertEqual("lambdas.core.game.duplicate", result["duplicate"])
        self.assertEqual("lambdas.core.game.archives", result["archives"])
        self.assertEqual(16, len(result["handlers"]))

    def test_rejects_handler_using_unrelated_runtime_copy(self):
        self.modules["lambdas.api.game.game_tick"].runtime = object()
        with self.assertRaisesRegex(RuntimeError, "namespace mismatch"):
            verifier.verify_store_namespaces()

    def test_rejects_duplicate_core_game_module_copy(self):
        with patch.dict(sys.modules, {"core.game.duplicate": types.ModuleType("core.game.duplicate")}):
            with self.assertRaisesRegex(RuntimeError, "Alternate core.game.duplicate"):
                verifier.verify_store_namespaces()

    def test_rejects_runtime_using_an_unconfigured_store_module(self):
        self.game.archives = object()
        with self.assertRaisesRegex(RuntimeError, "different archives"):
            verifier.verify_store_namespaces()


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.work = ROOT / "build" / "packaging-tests" / uuid.uuid4().hex
        self.work.mkdir(parents=True)
        self.dependencies = self.work / "dependencies"
        self.native = self.work / "native"
        self.dependencies.mkdir()
        self.native.mkdir()
        (self.dependencies / "dependency.py").write_text("value = 1\n")
        (self.dependencies / "discard.pyc").write_bytes(b"not bytecode")
        # A header fixture exercises architecture rejection, not ABI execution.
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", header, 18, 62)
        (self.native / "libdds.so.2").write_bytes(header)
        (self.native / "DDS-LICENSE").write_text("synthetic license fixture\n")
        (self.native / "DDS-NOTICE").write_text("synthetic notice fixture\n")

    def tearDown(self):
        shutil.rmtree(self.work)

    def build(self, output):
        with redirect_stdout(io.StringIO()):
            return builder.build(ROOT, self.dependencies, self.native, self.work / output)

    def test_reproducibility_layout_and_receipt(self):
        first = self.build("one")
        os.utime(self.dependencies / "dependency.py", (1000000, 1000000))
        second = self.build("two")
        self.assertEqual(first.name, second.name)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first, self.build("one"))
        with zipfile.ZipFile(first) as archive:
            names = archive.namelist()
            self.assertEqual(sorted(names), names)
            self.assertIn("libdds.so.2", names)
            self.assertIn("lambdas/dds/working_dds_wrapper.py", names)
            self.assertIn("lambdas/dds/bridge_bidding_alg.txt", names)
            self.assertIn("staging_runtime.py", names)
            self.assertIn("dependency.py", names)
            self.assertFalse(any(re.search(r"(__pycache__|\.pyc$|dump\.txt|\.env|\.zip$)", name) for name in names))
            self.assertFalse(any("/tests/" in name or "/test_" in name for name in names))
            self.assertNotIn("lambdas/dds/libdds.so.2.9.0", names)
            receipt = json.loads(archive.read("PACKAGE-RECEIPT.json"))
            self.assertEqual(set(names) - {"PACKAGE-RECEIPT.json"}, set(receipt["files"]))
            for name, digest in receipt["files"].items():
                self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())
            self.assertTrue(all(info.date_time == builder.EPOCH for info in archive.infolist()))
        metadata = json.loads(first.with_suffix(".json").read_text())
        self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), metadata["sha256"])
        self.assertEqual(first.name, "bridge-staging-" + metadata["sha256"] + ".zip")

    def test_source_change_changes_artifact_digest(self):
        first = self.build("one")
        (self.dependencies / "dependency.py").write_text("value = 2\n")
        self.assertNotEqual(first.name, self.build("two").name)

    def test_wrong_native_architecture_rejected(self):
        path = self.native / "libdds.so.2"
        data = bytearray(path.read_bytes())
        struct.pack_into("<H", data, 18, 183)
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "x86_64"):
            self.build("wrong-arch")

    def test_dependency_symlink_rejected(self):
        (self.dependencies / "alias").symlink_to("dependency.py")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.build("symlink")

    def test_application_collision_rejected(self):
        (self.dependencies / "staging_runtime.py").write_text("shadow = True\n")
        with self.assertRaisesRegex(ValueError, "collision"):
            self.build("collision")


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        runtime._initialized = False
        self.boto = types.ModuleType("boto3")
        self.boto.resource = MagicMock()
        self.game = types.ModuleType("lambdas.core.game")
        self.duplicate = types.SimpleNamespace(
            DynamoEventStore=MagicMock(side_effect=lambda table: ("durable", table)),
            store=None,
        )
        self.archives = types.SimpleNamespace(configure_from_environment=MagicMock())
        self.game.duplicate = self.duplicate
        self.game.archives = self.archives
        self.modules = patch.dict(sys.modules, {
            "boto3": self.boto, "lambdas.core.game": self.game,
        })
        self.environment = patch.dict(os.environ, {
            "DUPLICATE_EVENTS_TABLE": "staging-events",
            "BOARD_ARCHIVES_TABLE": "staging-archives",
        })
        self.modules.start()
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.modules.stop()
        runtime._initialized = False

    def test_initializes_once_with_duplicate_before_archive(self):
        observed = []
        self.archives.configure_from_environment.side_effect = lambda: observed.append(
            self.duplicate.store
        )
        runtime.initialize()
        runtime.initialize()
        self.boto.resource.assert_called_once_with("dynamodb")
        self.boto.resource.return_value.Table.assert_called_once_with("staging-events")
        self.archives.configure_from_environment.assert_called_once_with()
        self.assertEqual("durable", observed[0][0])

    def test_fails_closed_for_each_missing_or_empty_table(self):
        for key in ("DUPLICATE_EVENTS_TABLE", "BOARD_ARCHIVES_TABLE"):
            for value in ("", "  "):
                with patch.dict(os.environ, {key: value}):
                    with self.assertRaisesRegex(RuntimeError, "must be nonempty"):
                        runtime.initialize()
                    self.assertFalse(runtime._initialized)
        self.boto.resource.assert_not_called()

    def test_archive_setup_failure_does_not_mark_initialized(self):
        self.archives.configure_from_environment.side_effect = ValueError("configuration")
        with self.assertRaisesRegex(ValueError, "configuration"):
            runtime.initialize()
        self.assertFalse(runtime._initialized)

    def test_wrapper_preserves_event_context_and_result(self):
        expected = {"statusCode": 409, "body": '{"error":"room changed"}'}
        target = types.SimpleNamespace(lambda_handler=MagicMock(return_value=expected))
        event, context = {"requestContext": {"routeKey": "makeBid"}}, object()
        with patch.object(runtime.importlib, "import_module", return_value=target) as importer:
            result = runtime.websocket_make_bid(event, context)
        importer.assert_called_once_with("lambdas.api.websocket.websocket_make_bid")
        target.lambda_handler.assert_called_once_with(event, context)
        self.assertIs(expected, result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
