"""Real loopback HTTP/WebSocket tests; the child process owns all Moto state."""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest

aiohttp = pytest.importorskip("aiohttp", reason="Install requirements-local.txt")
ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:4200"


@pytest.fixture(scope="module")
def local_server():
    ports = []
    reservations = []
    try:
        for _ in range(2):
            reservation = socket.socket()
            reservation.bind(("127.0.0.1", 0))
            reservations.append(reservation)
            ports.append(reservation.getsockname()[1])
    finally:
        for reservation in reservations:
            reservation.close()
    process = subprocess.Popen(
        [
            sys.executable,
            "scripts/local_server.py",
            "--http-port",
            str(ports[0]),
            "--ws-port",
            str(ports[1]),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={
            **os.environ,
            "AWS_PROFILE": "deliberately-nonexistent-local-profile",
            "AWS_ENDPOINT_URL": "http://127.0.0.1:9",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    base = f"http://127.0.0.1:{ports[0]}"
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"Local adapter exited: {process.communicate()[0]}")
            try:
                with urlopen(base + "/health", timeout=0.5) as response:
                    if json.load(response)["status"] == "ready":
                        break
            except (URLError, TimeoutError):
                time.sleep(0.1)
        else:
            pytest.fail("Local adapter did not become ready")
        yield {"http": base, "ws": f"ws://127.0.0.1:{ports[1]}"}
    finally:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
        assert process.returncode == 0, output


async def post(client, server, path, data, status=200, headers=None):
    async with client.post(
        server["http"] + path,
        json=data,
        headers=headers,
    ) as response:
        payload = await response.json()
        assert response.status == status, payload
        return payload


async def receive(socket, action):
    async with asyncio.timeout(90):
        while True:
            message = await socket.receive_json()
            if message.get("action") == "error" and action != "error":
                pytest.fail(f"Unexpected WebSocket error: {message}")
            if message.get("action") == action:
                return message


async def send(socket, action, **data):
    await socket.send_json({"action": action, "data": data})


async def snapshot(socket, room_id):
    await send(socket, "getGameState", roomId=room_id)
    return await receive(socket, "gameState")


async def receive_newer(socket, revision):
    async with asyncio.timeout(30):
        while True:
            message = await socket.receive_json()
            assert message.get("action") != "error", message
            if message.get("publicState", {}).get("revision", -1) > revision:
                return message


def test_health_auth_cors_and_upgrade_rejections(local_server):
    async def check():
        async with aiohttp.ClientSession(headers={"Origin": ORIGIN}) as client:
            async with client.get(local_server["http"] + "/health") as response:
                assert (await response.json())["aws"] == "in-memory-moto"
                assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
            async with client.options(
                local_server["http"] + "/api/auth/guest",
                headers={"Access-Control-Request-Headers": "content-type"},
            ) as response:
                assert response.status == 204
                assert response.headers["Access-Control-Allow-Credentials"] == "true"
            async with client.get(
                local_server["http"] + "/api/connections"
            ) as response:
                assert response.status == 401
            await post(
                client,
                local_server,
                "/auth/guest",
                {},
                403,
                {"Origin": "https://not-allowed.example"},
            )
            guest = await post(
                client, local_server, "/auth/guest", {"username": "Guest"}
            )
            assert guest["isGuest"] and guest["accessToken"]
            renewed = await post(
                client,
                local_server,
                "/auth/guest",
                {"username": "Renamed"},
                headers={"Authorization": "Bearer " + guest["accessToken"]},
            )
            assert renewed["userId"] == guest["userId"]
            await post(
                client,
                local_server,
                "/auth/guest",
                {},
                401,
                {"Authorization": "Bearer forged"},
            )
            for protocols, origin, status in [
                (("bridge.v1",), ORIGIN, 401),
                (("bridge.v1", "bridge.auth.forged"), ORIGIN, 401),
                (
                    ("bridge.v1", "bridge.auth." + guest["accessToken"]),
                    "https://not-allowed.example",
                    403,
                ),
            ]:
                with pytest.raises(aiohttp.WSServerHandshakeError) as error:
                    await client.ws_connect(
                        local_server["ws"],
                        protocols=protocols,
                        headers={"Origin": origin},
                    )
                assert error.value.status == status
            async with client.ws_connect(
                local_server["ws"],
                protocols=("bridge.v1", "bridge.auth." + guest["accessToken"]),
            ) as ws:
                assert ws.protocol == "bridge.v1"
                await ws.send_str("not json")
                assert (await receive(ws, "error"))["statusCode"] == 400
                await send(ws, "$disconnect")
                assert (await receive(ws, "error"))["statusCode"] == 400

    asyncio.run(check())


def test_accounts_two_clients_full_board_reconnect_and_privacy(local_server):
    async def check():
        timeout = aiohttp.ClientTimeout(total=180)
        cookies = aiohttp.CookieJar(
            unsafe=True
        )  # Explicitly accept loopback-IP cookies.
        async with aiohttp.ClientSession(
            headers={"Origin": ORIGIN},
            cookie_jar=cookies,
            timeout=timeout,
        ) as client:
            password = "LocalBridge123!"
            user = await post(
                client,
                local_server,
                "/api/account",
                {
                    "username": "local_north",
                    "email": "north@example.test",
                    "password": password,
                },
                201,
            )
            login = await post(
                client,
                local_server,
                "/api/account/login",
                {
                    "username": "local_north",
                    "password": password,
                },
            )
            assert login["user"]["userId"] == user["user"]["userId"]
            await post(
                client,
                local_server,
                "/account/login",
                {
                    "username": "local_north",
                    "password": "WrongPassword123!",
                },
                401,
            )
            refreshed = await post(client, local_server, "/api/auth/refresh", {})
            assert refreshed["accessToken"]
            # Refresh also reissues the production Secure cookie. The local HTTP
            # transport must adapt it so a second refresh actually works.
            await post(client, local_server, "/auth/refresh", {})
            refresh_token = next(
                cookie.value for cookie in cookies if cookie.key == "refresh_token"
            )
            with pytest.raises(aiohttp.WSServerHandshakeError) as error:
                await client.ws_connect(
                    local_server["ws"],
                    protocols=("bridge.v1", "bridge.auth." + refresh_token),
                )
            assert error.value.status == 401
            await post(
                client,
                local_server,
                "/account",
                {
                    "username": "second_account",
                    "email": "second@example.test",
                    "password": password,
                },
                201,
            )
            second_login = await post(
                client,
                local_server,
                "/account/login",
                {
                    "username": "second_account",
                    "password": password,
                },
            )
            assert second_login["user"]["userId"] != login["user"]["userId"]
            guest = await post(
                client, local_server, "/auth/guest", {"username": "East"}
            )
            north_id, east_id = login["user"]["userId"], guest["userId"]
            north_protocols = ("bridge.v1", "bridge.auth." + login["accessToken"])
            east_protocols = ("bridge.v1", "bridge.auth." + guest["accessToken"])
            async with client.ws_connect(
                local_server["ws"], protocols=north_protocols
            ) as north:
                async with client.ws_connect(
                    local_server["ws"], protocols=east_protocols
                ) as east:
                    await send(
                        north,
                        "createRoom",
                        ownerId=north_id,
                        playerName="North",
                        roomName="Local integration",
                        isPrivate=False,
                    )
                    created = await receive(north, "createRoom")
                    room_id = created["room"]["roomId"]
                    if created["assignedSeat"] != "North":
                        await send(
                            north,
                            "changeSeat",
                            userId=north_id,
                            roomId=room_id,
                            newSeat="North",
                        )
                        await receive(north, "roomUpdated")
                    await send(east, "joinRoom", userId=east_id, roomId=room_id)
                    joined = await receive(east, "roomUpdated")
                    async with client.get(
                        local_server["http"] + "/api/connections",
                        headers={"Authorization": "Bearer " + login["accessToken"]},
                    ) as response:
                        assert response.status == 200
                        assert await response.json() == {
                            "activeUserCount": 2,
                            "activeRoomCount": 1,
                        }
                    if joined["assignedSeat"] != "East":
                        await send(
                            east,
                            "changeSeat",
                            userId=east_id,
                            roomId=room_id,
                            newSeat="East",
                        )
                        await receive(east, "roomUpdated")
                    await send(north, "startRoom", userId=north_id, roomId=room_id)
                    north_state, east_state = await asyncio.gather(
                        snapshot(north, room_id), snapshot(east, room_id)
                    )
                    assert north_state["privateState"]["seat"] == "North"
                    assert east_state["privateState"]["seat"] == "East"
                    assert len(north_state["privateState"]["hand"]) == 13
                    assert len(east_state["privateState"]["hand"]) == 13
                    assert not (
                        set(north_state["privateState"]["hand"])
                        & set(east_state["privateState"]["hand"])
                    )
                    assert "hands" not in north_state["publicState"]
                    assert "hands" not in north_state["room"]
                    assert north_state["publicState"]["dummyHand"] is None
                    first_board_id = north_state["publicState"]["boardId"]
                    await send(north, "getBoardArchive", roomId=room_id, boardId=first_board_id)
                    assert (await receive(north, "error"))["statusCode"] == 409
                    await send(north, "listBoardArchives", roomId=room_id)
                    assert (await receive(north, "boardArchives"))["boards"] == []
                    await send(east, "getAgreementCard", roomId=room_id)
                    agreement = await receive(east, "agreementCard")
                    assert agreement["card"]["version"] == "sayc-supported-1"
                    assert agreement["card"]["unsupported"]
                    assert "initialHands" not in agreement and "hands" not in agreement
                    await send(north, "setPracticePace", roomId=room_id,
                               practiceMode=True, robotCardDelayMs=100, trickHoldMs=1000)
                    assert (await receive(north, "error"))["statusCode"] == 403

                    # Spoofed identity and stale revisions are production errors.
                    await send(
                        east, "makeBid", roomId=room_id, userId=north_id, bid="pass"
                    )
                    assert (await receive(east, "error"))["statusCode"] == 403
                    await send(north, "makeBid", roomId=room_id, bid="7NT", revision=-1)
                    assert (await receive(north, "error"))["statusCode"] == 409
                    await send(
                        north,
                        "makeBid",
                        roomId=room_id,
                        bid="7NT",
                        revision=north_state["publicState"]["revision"],
                    )
                    broadcast = await receive(east, "bidMade")
                    assert broadcast["privateState"]["seat"] == "East"
                    assert (
                        broadcast["privateState"]["hand"]
                        == east_state["privateState"]["hand"]
                    )
                    assert "hands" not in broadcast["publicState"]

                    # A second real socket for the same signed identity recovers
                    # its own hand, without joinRoom or trusting a supplied userId.
                    async with client.ws_connect(
                        local_server["ws"],
                        protocols=north_protocols,
                    ) as reconnected:
                        recovered = await snapshot(reconnected, room_id)
                        assert recovered["privateState"]["seat"] == "North"
                        assert (
                            recovered["privateState"]["hand"]
                            == north_state["privateState"]["hand"]
                        )
                    await north.close()
                    async with client.ws_connect(
                        local_server["ws"],
                        protocols=north_protocols,
                    ) as resumed:
                        human_bids = human_plays = autonomous_moves = collected = 0
                        for _ in range(100):
                            states = await asyncio.gather(
                                snapshot(resumed, room_id), snapshot(east, room_id)
                            )
                            phase = states[0]["publicState"]["currentPhase"]
                            if phase == "completed":
                                completed = states[0]["publicState"]
                                assert len(completed["tricks"]) == 13
                                assert completed["result"] is not None
                                assert sum(completed["handCounts"].values()) == 0
                                assert human_plays > 0
                                assert human_bids > 0
                                assert autonomous_moves > 0
                                assert collected == 13
                                assert completed["completedTrick"] is None
                                break
                            for ws, state in zip((resumed, east), states):
                                private = state["privateState"]
                                if not private["isMyTurn"]:
                                    continue
                                revision = state["publicState"]["revision"]
                                if phase == "bidding":
                                    assert "pass" in private["validBids"]
                                    await send(
                                        ws,
                                        "makeBid",
                                        roomId=room_id,
                                        bid="pass",
                                        revision=revision,
                                    )
                                    human_bids += 1
                                else:
                                    assert phase == "playing"
                                    assert private["legalCards"]
                                    await send(
                                        ws,
                                        "playCard",
                                        roomId=room_id,
                                        card=private["legalCards"][0],
                                        revision=revision,
                                    )
                                    human_plays += 1
                                break
                            else:
                                latest = max(
                                    states, key=lambda state: state["publicState"]["revision"]
                                )["publicState"]
                                pending = latest["pendingAction"]
                                assert pending is not None, states
                                # No requesting client drives this interval: the
                                # local deadline worker must publish autonomously.
                                advanced = await receive_newer(resumed, latest["revision"])
                                assert advanced["publicState"]["serverTimeMs"] >= pending["dueAt"]
                                if pending["kind"] == "clearTrick":
                                    assert latest["completedTrick"] is not None
                                    assert advanced["action"] == "trickCleared"
                                    assert advanced["publicState"]["completedTrick"] is None
                                    collected += 1
                                else:
                                    assert advanced["action"] in ("cardPlayed", "bidMade")
                                    autonomous_moves += 1
                        else:
                            pytest.fail(
                                "Board did not finish within the legal action bound"
                            )
                        await send(resumed, "getBoardArchive", roomId=room_id,
                                   boardId=first_board_id)
                        archived = (await receive(resumed, "boardArchive"))["board"]
                        assert archived["result"] == completed["result"]
                        assert archived["initialHands"]["North"] == north_state["privateState"]["hand"]
                        assert archived["initialHands"]["East"] == east_state["privateState"]["hand"]
                        assert len(archived["tricks"]) == 13
                        assert sum(len(trick["plays"]) for trick in archived["tricks"]) == 52
                        assert archived["auction"] == completed["bids"]
                        await send(east, "getBoardArchive", roomId=room_id,
                                   boardId=first_board_id)
                        assert (await receive(east, "boardArchive"))["board"] == archived
                        await send(resumed, "getMatchScoreboard", roomId=room_id)
                        scoreboard = (await receive(resumed, "matchScoreboard"))["scoreboard"]
                        assert scoreboard["completedBoards"] == 1
                        assert scoreboard["scoreNS"] == completed["result"]["scoreNS"]
                        await send(resumed, "nextBoard", roomId=room_id,
                                   revision=completed["revision"])
                        next_state = await snapshot(resumed, room_id)
                        assert next_state["publicState"]["boardNumber"] == 2
                        assert next_state["publicState"]["boardId"] != first_board_id
                        assert next_state["publicState"]["scoreboard"] == scoreboard
                        await send(resumed, "nextBoard", roomId=room_id,
                                   revision=completed["revision"])
                        assert (await receive(resumed, "error"))["statusCode"] == 409
                        await send(resumed, "getBoardArchive", roomId=room_id,
                                   boardId=first_board_id)
                        assert (await receive(resumed, "boardArchive"))["board"] == archived
            await post(client, local_server, "/api/logout", {})
            await post(client, local_server, "/auth/refresh", {}, 400)

    asyncio.run(check())


def test_non_loopback_binding_is_refused():
    result = subprocess.run(
        [sys.executable, "scripts/local_server.py", "--host", "0.0.0.0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "must be a loopback address" in result.stderr


def test_aws_wire_transport_fails_closed():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from scripts.local_server import LocalRuntime,DEFAULT_ORIGINS; "
                "r=LocalRuntime(DEFAULT_ORIGINS); r.start(); "
                "import boto3; "
                "c=boto3.client('dynamodb',endpoint_url='http://127.0.0.1:9'); "
                "c.list_tables()"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "Real network access through AWS SDK is disabled locally" in result.stderr
