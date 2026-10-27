"""Real loopback clients against the in-process Moto adapter; no AWS transport."""
import asyncio

import pytest

aiohttp = pytest.importorskip("aiohttp")
from test_local_server import ORIGIN, local_server, post, receive, send, snapshot


async def open_socket(client, server, guest):
    return await client.ws_connect(
        server["ws"], protocols=("bridge.v1", "bridge.auth." + guest["accessToken"]))


async def update(socket, update_type):
    async with asyncio.timeout(10):
        while True:
            payload = await receive(socket, "roomUpdated")
            if payload.get("updateType") == update_type:
                return payload


async def wait_presence(socket, room_id, seat, status, count=None):
    async with asyncio.timeout(10):
        while True:
            current = await snapshot(socket, room_id)
            item = current["room"]["presence"][seat]
            if item["status"] == status and (count is None or item["connectionCount"] == count):
                return item
            await asyncio.sleep(0.01)


def test_duplicate_guest_tabs_disconnect_grace_and_renewed_reconnect(local_server):
    async def check():
        async with aiohttp.ClientSession(headers={"Origin": ORIGIN}) as client:
            owner = await post(client, local_server, "/auth/guest", {"username": "PresenceOwner"})
            guest = await post(client, local_server, "/auth/guest", {"username": "MultiTab"})
            async with await open_socket(client, local_server, owner) as owner_socket:
                await send(owner_socket, "createRoom", ownerId=owner["userId"],
                           playerName="PresenceOwner", roomName="Presence clients", isPrivate=False)
                created = await receive(owner_socket, "createRoom")
                room_id = created["room"]["roomId"]
                first = await open_socket(client, local_server, guest)
                await send(first, "joinRoom", userId=guest["userId"], roomId=room_id)
                joined = await update(first, "userJoined")
                seat = joined["assignedSeat"]
                second = await open_socket(client, local_server, guest)
                await wait_presence(owner_socket, room_id, seat, "online", 2)
                await first.close()
                await wait_presence(owner_socket, room_id, seat, "online", 1)
                await second.close()
                disconnected = await wait_presence(owner_socket, room_id, seat, "reconnecting", 0)
                assert disconnected["reservedUntil"] > 0
                renewed = await post(
                    client, local_server, "/auth/guest", {"username": "RenewedMultiTab"},
                    headers={"Authorization": "Bearer " + guest["accessToken"]})
                assert renewed["userId"] == guest["userId"]
                async with await open_socket(client, local_server, renewed) as reconnected:
                    await send(reconnected, "joinRoom", userId=guest["userId"], roomId=room_id)
                    rejoined = await update(reconnected, "userReconnected")
                    assert rejoined["assignedSeat"] == seat
                    assert rejoined["room"]["presence"][seat]["status"] == "online"
                    assert "reservedUntil" not in rejoined["room"]["presence"][seat]
                    assert "hands" not in rejoined["publicState"]
                    assert "connections" not in str(rejoined["room"]["presence"])
    asyncio.run(check())


def test_private_invite_revocation_lock_transfer_and_explicit_release(local_server):
    async def check():
        async with aiohttp.ClientSession(headers={"Origin": ORIGIN}) as client:
            owner = await post(client, local_server, "/auth/guest", {"username": "PrivateOwner"})
            guest = await post(client, local_server, "/auth/guest", {"username": "InvitedGuest"})
            async with await open_socket(client, local_server, owner) as host, \
                    await open_socket(client, local_server, guest) as visitor:
                await send(host, "createRoom", ownerId=owner["userId"], playerName="PrivateOwner",
                           roomName="Private clients", isPrivate=True)
                created = await receive(host, "createRoom")
                room_id = created["room"]["roomId"]
                owner_seat = created["assignedSeat"]
                await send(visitor, "joinRoom", roomId=room_id, userId=guest["userId"])
                assert (await receive(visitor, "error"))["statusCode"] == 403
                await send(host, "createInvitation", roomId=room_id, expiresInSeconds=60)
                invitation = await receive(host, "roomInvitation")
                token = invitation["invitationToken"]
                assert token != owner["accessToken"]
                await send(host, "setRoomLock", roomId=room_id, locked=True)
                await update(host, "roomLockChanged")
                await send(visitor, "joinRoom", roomId=room_id, userId=guest["userId"],
                           invitationToken=token)
                assert (await receive(visitor, "error"))["statusCode"] == 403
                await send(host, "setRoomLock", roomId=room_id, locked=False)
                await update(host, "roomLockChanged")
                await send(host, "revokeInvitation", roomId=room_id,
                           invitationId=invitation["invitationId"])
                await update(host, "invitationRevoked")
                await send(visitor, "joinRoom", roomId=room_id, userId=guest["userId"],
                           invitationToken=token)
                assert (await receive(visitor, "error"))["statusCode"] == 403
                await send(host, "createInvitation", roomId=room_id)
                invitation = await receive(host, "roomInvitation")
                await send(visitor, "joinRoom", roomId=room_id, userId=guest["userId"],
                           invitationToken=invitation["invitationToken"])
                joined = await update(visitor, "userJoined")
                assert "invitations" not in joined["room"]
                assert "digest" not in str(joined)
                await send(visitor, "setRoomLock", roomId=room_id, locked=True)
                assert (await receive(visitor, "error"))["statusCode"] == 403
                await send(host, "leaveRoom", roomId=room_id)
                assert (await receive(host, "error"))["statusCode"] == 409
                await send(host, "transferOwnership", roomId=room_id, newOwnerId=guest["userId"])
                transferred = await update(host, "ownershipTransferred")
                assert transferred["room"]["ownerId"] == guest["userId"]
                await send(host, "leaveRoom", roomId=room_id)
                assert (await receive(host, "roomLeft"))["releasedSeat"] == owner_seat
                current = await snapshot(visitor, room_id)
                assert current["room"]["ownerId"] == guest["userId"]
                assert not current["room"]["seats"][owner_seat]
                await send(host, "getGameState", roomId=room_id)
                assert (await receive(host, "error"))["statusCode"] == 403
    asyncio.run(check())
