#!/usr/bin/env python3
"""Development-only HTTP/WebSocket transport for the unmodified Lambda handlers."""
import sys

sys.dont_write_bytecode = True

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
import importlib
import io
import ipaddress
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGINS = [
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in (4200, 4201)
]
HTTP_HANDLERS = {
    "/account": "account_create",
    "/account/login": "account_login",
    "/auth/refresh": "account_refresh_token",
    "/auth/guest": "guest_session",
    "/logout": "account_logout",
}
WS_HANDLERS = {
    "createRoom": "websocket_create_room",
    "joinRoom": "websocket_join_room",
    "changeSeat": "websocket_change_seat",
    "startRoom": "websocket_start_room",
    "getGameState": "websocket_start_room",
    "nextBoard": "websocket_start_room",
    "makeBid": "websocket_make_bid",
    "playCard": "websocket_play_card",
    "getBoardArchive": "websocket_board_records",
    "listBoardArchives": "websocket_board_records",
    "getAgreementCard": "websocket_board_records",
    "getMatchScoreboard": "websocket_board_records",
    "setPracticePace": "websocket_board_records",
    "leaveRoom": "websocket_leave_room",
    "replacePlayer": "websocket_replace_player",
    "transferOwnership": "websocket_room_controls",
    "setRoomLock": "websocket_room_controls",
    "createInvitation": "websocket_room_controls",
    "revokeInvitation": "websocket_room_controls",
    "getPracticeHint": "websocket_practice",
    "setComputerLevel": "websocket_practice",
    **{action: "websocket_claims_duplicate" for action in (
        "proposeClaim", "respondClaim", "cancelClaim", "createDuplicateEvent",
        "joinDuplicateEvent", "startDuplicateEvent", "getDuplicateEvent")},
    "$connect": "websocket_connect",
    "$disconnect": "websocket_disconnect",
}


class DiscardOutput(io.TextIOBase):
    def write(self, text):
        return len(text)


class LocalRuntime:
    """Single-process Moto store and API Gateway delivery shim, with no wire AWS."""

    def __init__(self, origins):
        self.origins = set(origins)
        self.stack = ExitStack()
        self.sockets = {}
        self.local = threading.local()
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="local-lambda"
        )
        self.loop = None
        self.tick_timers = {}
        self.tick_revisions = {}
        self.tick_tasks = set()
        self.closing = False

    def start(self):
        # Ignore ambient AWS profiles, endpoint overrides, and credential providers.
        for name in list(os.environ):
            if name.startswith("AWS_"):
                del os.environ[name]
        os.environ.update(
            {
                "AWS_ACCESS_KEY_ID": "local-development-only",
                "AWS_SECRET_ACCESS_KEY": "local-development-only",
                "AWS_SESSION_TOKEN": "local-development-only",
                "AWS_DEFAULT_REGION": "us-east-1",
                "AWS_REGION": "us-east-1",
                "AWS_EC2_METADATA_DISABLED": "true",
                "ENVIRONMENT": "development",
                "USER_TABLE": "local-users",
                "ROOM_TABLE": "local-rooms",
                "WEBSOCKET_CONNECTIONS_TABLE": "local-connections",
                "JWT_SECRET_ID": "Bridge/JWT",
                "WS_ALLOWED_ORIGINS": ",".join(sorted(self.origins)),
                "FRONTEND_URL": sorted(self.origins)[0],
                "WEBSOCKET_ENDPOINT": "http://127.0.0.1:9/local-management",
            }
        )
        from moto import mock_aws

        self.stack.enter_context(mock_aws())
        # Moto intercepts before botocore's wire transport. Any missed mock fails
        # closed here, including an accidental new AWS service or custom endpoint.
        self.stack.enter_context(
            patch(
                "botocore.httpsession.URLLib3Session.send",
                side_effect=RuntimeError(
                    "Real network access through AWS SDK is disabled locally"
                ),
            )
        )
        import boto3

        boto3.setup_default_session()
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        for name, keys in (
            ("local-users", ("userId",)),
            ("local-rooms", ("roomId", "ownerId")),
            ("local-connections", ("connectionId", "currentRoomId")),
            ("local-duplicate-events", ("eventId",)),
        ):
            dynamodb.create_table(
                TableName=name,
                BillingMode="PAY_PER_REQUEST",
                KeySchema=[
                    {"AttributeName": key, "KeyType": kind}
                    for key, kind in zip(keys, ("HASH", "RANGE"))
                ],
                AttributeDefinitions=[
                    {"AttributeName": key, "AttributeType": "S"} for key in keys
                ],
            )
        boto3.client("secretsmanager").create_secret(
            Name="Bridge/JWT",
            SecretString=json.dumps({"jwt_secret": secrets.token_urlsafe(64)}),
        )
        original_client = boto3.client

        def client(service_name, *args, **kwargs):
            if service_name == "apigatewaymanagementapi":
                return self
            if service_name not in ("dynamodb", "secretsmanager"):
                raise RuntimeError(f"Unsupported local AWS service: {service_name}")
            return original_client(service_name, *args, **kwargs)

        self.stack.enter_context(patch("boto3.client", side_effect=client))
        sys.path.insert(0, str(ROOT))
        self.http_handlers = {
            route: importlib.import_module(f"lambdas.api.auth.{module}").lambda_handler
            for route, module in HTTP_HANDLERS.items()
        }
        self.http_handlers["/connections"] = importlib.import_module(
            "lambdas.api.game.connection_count"
        ).lambda_handler
        self.ws_handlers = {
            route: importlib.import_module(
                f"lambdas.api.websocket.{module}"
            ).lambda_handler
            for route, module in WS_HANDLERS.items()
        }
        from lambdas.core.game import runtime as game_runtime
        from lambdas.core.game import archives
        from lambdas.core.game import duplicate
        from lambdas.api.game.game_tick import tick_for_room

        self.stack.enter_context(patch.object(archives, "store", archives.MemoryArchiveStore()))
        self.stack.enter_context(patch.object(
            duplicate, "store", duplicate.DynamoEventStore(dynamodb.Table("local-duplicate-events"))))
        persist = game_runtime.save_room

        def save_and_schedule(table, room):
            persist(table, room)
            if self.loop is not None and not self.closing:
                tick = tick_for_room(room)
                self.loop.call_soon_threadsafe(
                    self.schedule_tick, room["roomId"], int(room["revision"]), tick
                )

        self.stack.enter_context(
            patch("lambdas.core.game.runtime.save_room", side_effect=save_and_schedule)
        )

    def schedule_tick(self, room_id, revision, tick):
        if self.closing or revision < self.tick_revisions.get(room_id, -1):
            return
        self.tick_revisions[room_id] = revision
        previous = self.tick_timers.pop(room_id, None)
        if previous:
            previous.cancel()
        if tick is not None:
            delay = max(0.01, (tick["dueAt"] - int(time.time() * 1000)) / 1000)
            self.tick_timers[room_id] = self.loop.call_later(
                delay, self.launch_tick, tick
            )

    def launch_tick(self, tick):
        if self.closing:
            return
        task = self.loop.create_task(self.run_tick(tick))
        self.tick_tasks.add(task)
        task.add_done_callback(self.tick_tasks.discard)

    async def run_tick(self, tick):
        from lambdas.core.game.runtime import process_due_tick
        from lambdas.shared.database.db_utils import db_utils
        from lambdas.shared.utils.websocket_utils import broadcast_to_connection

        def handler(event, context):
            return process_due_tick(db_utils, broadcast_to_connection, event, context)

        retry, _ = await self.invoke(handler, tick)
        if retry:
            self.schedule_tick(tick["roomId"], tick["revision"], retry)

    def post_to_connection(self, ConnectionId, Data):
        from botocore.exceptions import ClientError

        socket = self.sockets.get(ConnectionId)
        if socket is None or socket.closed:
            raise ClientError(
                {"Error": {"Code": "GoneException", "Message": "Disconnected"}},
                "PostToConnection",
            )
        text = Data.decode("utf-8") if isinstance(Data, bytes) else Data
        asyncio.run_coroutine_threadsafe(socket.send_str(text), self.loop).result(
            timeout=10
        )
        self.local.delivered.add(ConnectionId)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def invoke_sync(self, handler, event):
        self.local.delivered = set()
        context = SimpleNamespace(
            aws_request_id=str(uuid.uuid4()),
            function_name="local-development",
            function_version="$LOCAL",
            memory_limit_in_mb=1024,
            invoked_function_arn="local:development",
            get_remaining_time_in_millis=lambda: 900000,
        )
        # Existing account handlers print credentials in debug output. Never emit
        # those logs from this adapter, even during local development.
        with redirect_stdout(DiscardOutput()):
            result = handler(event, context)
        return result, self.local.delivered

    async def invoke(self, handler, event):
        return await asyncio.get_running_loop().run_in_executor(
            self.executor, self.invoke_sync, handler, event
        )

    async def close(self):
        self.closing = True
        for timer in self.tick_timers.values():
            timer.cancel()
        await asyncio.gather(*self.tick_tasks, return_exceptions=True)
        await asyncio.gather(
            *(socket.close() for socket in list(self.sockets.values()))
        )
        await asyncio.to_thread(self.executor.shutdown, wait=True)
        self.stack.close()


def request_event(request, route=None, connection_id=None, body=""):
    return {
        "httpMethod": request.method,
        "path": request.path,
        "headers": dict(request.headers),
        "queryStringParameters": dict(request.query),
        "body": body,
        "isBase64Encoded": False,
        "requestContext": {
            "routeKey": route,
            "connectionId": connection_id,
            "requestId": str(uuid.uuid4()),
            "requestTimeEpoch": int(time.time() * 1000),
            "domainName": request.host,
            "stage": "local",
            "identity": {"sourceIp": request.remote},
        },
    }


async def start_servers(runtime, host, http_port, ws_port):
    from aiohttp import WSMsgType, web

    runtime.loop = asyncio.get_running_loop()

    @web.middleware
    async def cors(request, handler):
        origin = request.headers.get("Origin")
        if origin and origin not in runtime.origins:
            return web.json_response({"error": "Origin is not allowed"}, status=403)
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            response = await handler(request)
        for name in list(response.headers):
            if name.lower().startswith("access-control-"):
                del response.headers[name]
        if origin:
            response.headers.update(
                {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization",
                    "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
                    "Vary": "Origin",
                }
            )
        response.headers["Cache-Control"] = "no-store"
        return response

    async def health(request):
        return web.json_response(
            {
                "status": "ready",
                "mode": "local-development",
                "aws": "in-memory-moto",
                "persistent": False,
            }
        )

    async def http(request):
        path = request.path.removeprefix("/api")
        method = "GET" if path == "/connections" else "POST"
        if request.method != method:
            raise web.HTTPMethodNotAllowed(request.method, [method, "OPTIONS"])
        handler = runtime.http_handlers.get(path)
        if handler is None:
            raise web.HTTPNotFound()
        event = request_event(request, body=await request.text())
        result, _ = await runtime.invoke(handler, event)
        response = web.Response(
            status=result["statusCode"], text=result.get("body", "")
        )
        for name, value in result.get("headers", {}).items():
            if name.lower() != "set-cookie":
                response.headers[name] = value
        cookie_headers = result.get("multiValueHeaders", {}).get("Set-Cookie", [])
        single_cookie = result.get("headers", {}).get("Set-Cookie")
        if single_cookie:
            cookie_headers += (
                single_cookie if isinstance(single_cookie, list) else [single_cookie]
            )
        for cookie in cookie_headers:
            # Only the loopback HTTP transport removes Secure from cookies;
            # production handlers and JWT verification are unchanged.
            cookie = "; ".join(
                part.strip()
                for part in cookie.split(";")
                if part.strip().lower() != "secure"
            )
            response.headers.add("Set-Cookie", cookie)
        return response

    async def websocket(request):
        connection_id = str(uuid.uuid4())
        event = request_event(request, "$connect", connection_id)
        result, _ = await runtime.invoke(runtime.ws_handlers["$connect"], event)
        if result["statusCode"] != 200:
            return web.Response(
                status=result["statusCode"], text=result.get("body", "")
            )
        socket = web.WebSocketResponse(
            protocols=("bridge.v1",), heartbeat=30, max_msg_size=65536
        )
        try:
            await socket.prepare(request)
            runtime.sockets[connection_id] = socket
            async for message in socket:
                if message.type != WSMsgType.TEXT:
                    continue
                try:
                    body = json.loads(message.data)
                    action = body.get("action") if isinstance(body, dict) else None
                    if not isinstance(action, str) or action.startswith("$"):
                        raise ValueError("A supported action is required")
                    handler = runtime.ws_handlers.get(action)
                    if handler is None:
                        raise ValueError("Unknown action")
                except (ValueError, TypeError):
                    await socket.send_json(
                        {
                            "action": "error",
                            "statusCode": 400,
                            "error": "Invalid WebSocket action",
                        }
                    )
                    continue
                result, delivered = await runtime.invoke(
                    handler, request_event(request, action, connection_id, message.data)
                )
                if (
                    connection_id not in delivered
                    and result.get("body")
                    and not socket.closed
                ):
                    payload = json.loads(result["body"])
                    if result["statusCode"] >= 400:
                        payload.update(
                            {"action": "error", "statusCode": result["statusCode"]}
                        )
                    await socket.send_json(payload)
        finally:
            runtime.sockets.pop(connection_id, None)
            await runtime.invoke(
                runtime.ws_handlers["$disconnect"],
                request_event(request, "$disconnect", connection_id),
            )
        return socket

    http_app = web.Application(middlewares=[cors], client_max_size=65536)
    http_app.router.add_get("/health", health)
    http_app.router.add_route("*", "/{path:.*}", http)
    ws_app = web.Application()
    ws_app.router.add_get("/", websocket)
    ws_app.router.add_get("/ws", websocket)
    runners = []
    try:
        for app, port in ((http_app, http_port), (ws_app, ws_port)):
            runner = web.AppRunner(app, access_log=None)
            runners.append(runner)
            await runner.setup()
            await web.TCPSite(runner, host, port).start()
    except BaseException:
        for runner in reversed(runners):
            await runner.cleanup()
        raise
    return runners


async def run(args):
    runtime = LocalRuntime(args.origin or DEFAULT_ORIGINS)
    runners = []
    try:
        runtime.start()
        runners = await start_servers(runtime, args.host, args.http_port, args.ws_port)
        print(
            f"DEV ONLY ready: http://{args.host}:{args.http_port}/health "
            f"ws://{args.host}:{args.ws_port} (in-memory; no AWS network)",
            flush=True,
        )
        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stopped.set)
        await stopped.wait()
    finally:
        await asyncio.gather(
            *(socket.close() for socket in list(runtime.sockets.values()))
        )
        for runner in reversed(runners):
            await runner.cleanup()
        await runtime.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=3001)
    parser.add_argument("--ws-port", type=int, default=3002)
    parser.add_argument(
        "--origin", action="append", help="Exact allowed browser origin (repeatable)"
    )
    args = parser.parse_args()
    if args.host != "localhost":
        try:
            loopback = ipaddress.ip_address(args.host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            parser.error(
                "--host must be a loopback address; this server is development-only"
            )
    if args.http_port == args.ws_port:
        parser.error("--http-port and --ws-port must differ")
    # Production handlers log complete events at various levels.
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
