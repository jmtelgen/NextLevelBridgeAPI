"""Real loopback practice routes, using the existing isolated local adapter fixture."""
import asyncio

from tests.test_local_server import (
    ORIGIN, aiohttp, local_server, post, receive, send, snapshot,
)


def test_solo_practice_routes_real_socket_and_persisted_setting(local_server):
    async def check():
        async with aiohttp.ClientSession(headers={"Origin": ORIGIN}) as client:
            guest = await post(client, local_server, "/auth/guest", {"username": "Solo"})
            async with client.ws_connect(
                    local_server["ws"],
                    protocols=("bridge.v1", "bridge.auth." + guest["accessToken"])) as socket:
                await send(socket, "createRoom", ownerId=guest["userId"], playerName="Solo",
                           roomName="SOLO practice", isPrivate=False)
                created = await receive(socket, "createRoom")
                room_id = created["room"]["roomId"]
                if created["assignedSeat"] != "North":
                    await send(socket, "changeSeat", userId=guest["userId"],
                               roomId=room_id, newSeat="North")
                    await receive(socket, "roomUpdated")
                await send(socket, "startRoom", userId=guest["userId"], roomId=room_id)
                before = await snapshot(socket, room_id)
                revision = before["publicState"]["revision"]
                await send(socket, "getPracticeHint", roomId=room_id, revision=revision)
                hint = await receive(socket, "practiceHint")
                assert hint["revision"] == revision
                assert hint["hint"]["phase"] == "bidding"
                assert hint["hint"]["actor"] == "North"
                assert hint["hint"]["suggestion"] is None
                assert 0 <= hint["hint"]["handHcp"] <= 37
                assert sum(hint["hint"]["shape"].values()) == 13
                assert "hands" not in hint["hint"]
                unchanged = await snapshot(socket, room_id)
                assert unchanged["publicState"]["revision"] == revision
                await send(socket, "setComputerLevel", roomId=room_id,
                           revision=revision, computerLevel="thoughtful")
                changed = await receive(socket, "computerLevelChanged")
                assert changed["computerLevel"]["samples"] == 8
                assert changed["computerLevel"]["budgetMs"] == 100
                persisted = await snapshot(socket, room_id)
                assert persisted["room"]["computerLevel"] == "thoughtful"
                assert persisted["publicState"]["revision"] == changed["revision"]
                await send(socket, "setComputerLevel", roomId=room_id, computerLevel="expert")
                error = await receive(socket, "error")
                assert error["statusCode"] == 400
                await send(socket, "getPracticeHint", roomId=room_id, userId="forged-user")
                error = await receive(socket, "error")
                assert error["statusCode"] == 403

    asyncio.run(check())
