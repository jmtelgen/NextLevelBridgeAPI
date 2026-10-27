"""Eight signed loopback clients finish two tables; never contact real AWS."""
import asyncio
from contextlib import AsyncExitStack

from tests.test_local_server import ORIGIN, aiohttp, local_server, post, receive, send


async def drain(socket):
    while True:
        try:
            await socket.receive_json(timeout=0.005)
        except asyncio.TimeoutError:
            return


async def fresh(socket, room_id):
    await drain(socket)
    await send(socket, "getGameState", roomId=room_id)
    return await receive(socket, "gameState")


def test_real_two_table_event_claim_settlements_embargo_and_fixed_deals(local_server):
    async def check():
        async with aiohttp.ClientSession(headers={"Origin": ORIGIN}) as client, AsyncExitStack() as stack:
            sockets = []
            identities = []
            for number in range(8):
                guest = await post(client, local_server, "/auth/guest", {"username": f"Duplicate{number}"})
                identities.append(guest["userId"])
                sockets.append(await stack.enter_async_context(client.ws_connect(
                    local_server["ws"], protocols=("bridge.v1", "bridge.auth." + guest["accessToken"]))))
            rooms = []
            for table in (0, 1):
                offset = table * 4
                owner = sockets[offset]
                await send(owner, "createRoom", ownerId=identities[offset], playerName=f"Owner{table}",
                           roomName=f"Duplicate table {table + 1}", isPrivate=False)
                created = await receive(owner, "createRoom")
                room_id = created["room"]["roomId"]
                rooms.append(room_id)
                if created["assignedSeat"] != "North":
                    await send(owner, "changeSeat", roomId=room_id, userId=identities[offset], newSeat="North")
                    await receive(owner, "roomUpdated")
                for index in (1, 2, 3):
                    await send(sockets[offset + index], "joinRoom", roomId=room_id,
                               userId=identities[offset + index])
                    joined = await receive(sockets[offset + index], "roomUpdated")
                    assert joined["assignedSeat"] == ("East", "South", "West")[index - 1]
            await send(sockets[0], "createDuplicateEvent", roomId=rooms[0], tableCount=2, boardCount=2)
            created = await receive(sockets[0], "duplicateEventCreated")
            event_id, token = created["eventId"], created["invitationToken"]
            await send(sockets[4], "joinDuplicateEvent", roomId=rooms[1], eventId=event_id,
                       invitationToken=token)
            await receive(sockets[4], "duplicateEventJoined")
            # Organizer cannot move into another table even with event invitation.
            await send(sockets[0], "joinRoom", roomId=rooms[1], userId=identities[0],
                       invitationToken=token)
            assert (await receive(sockets[0], "error"))["statusCode"] == 409
            await send(sockets[0], "startDuplicateEvent", eventId=event_id)
            started = await receive(sockets[0], "duplicateEventStarted")
            assert "hands" not in str(started) and "invitationHash" not in str(started)
            first_snapshots = []
            for index, socket in enumerate(sockets):
                state = await fresh(socket, rooms[index // 4])
                first_snapshots.append(state)
                assert state["publicState"]["dummyHand"] is None
                assert state["publicState"]["eventId"] == event_id
            for index in range(4):
                assert first_snapshots[index]["privateState"]["hand"] == first_snapshots[index + 4]["privateState"]["hand"]
            board_one = first_snapshots[0]["publicState"]["boardId"]

            async def pass_out(table):
                for index in range(4):
                    socket = sockets[table * 4 + index]
                    await send(socket, "makeBid", roomId=rooms[table], bid="pass")
                    await receive(socket, "bidMade")

            await pass_out(0)
            await send(sockets[0], "getBoardArchive", roomId=rooms[0], boardId=board_one)
            assert (await receive(sockets[0], "error"))["statusCode"] == 403
            await send(sockets[0], "listBoardArchives", roomId=rooms[0])
            assert (await receive(sockets[0], "boardArchives"))["boards"] == []
            await send(sockets[0], "getDuplicateEvent", eventId=event_id)
            partial = (await receive(sockets[0], "duplicateEvent"))["event"]
            assert partial["boards"][0]["completedTables"] == 1
            assert partial["boards"][0]["results"] == []
            await send(sockets[0], "nextBoard", roomId=rooms[0], boardId=board_one)
            await receive(sockets[0], "boardStarted")
            await send(sockets[0], "getBoardArchive", roomId=rooms[0], boardId=board_one)
            assert (await receive(sockets[0], "error"))["statusCode"] == 403
            await pass_out(1)
            await send(sockets[0], "getBoardArchive", roomId=rooms[0], boardId=board_one)
            archive_one = (await receive(sockets[0], "boardArchive"))["board"]
            assert archive_one["initialHands"]["North"] == first_snapshots[0]["privateState"]["hand"]
            await send(sockets[0], "getBoardArchive", roomId=rooms[1], boardId=board_one)
            assert (await receive(sockets[0], "error"))["statusCode"] == 403
            await send(sockets[4], "nextBoard", roomId=rooms[1], boardId=board_one)
            await receive(sockets[4], "boardStarted")

            for table in (0, 1):
                offset, room_id = table * 4, rooms[table]
                # Board two dealer East; East declares, South has the opening lead.
                for index, bid in ((1, "1NT"), (2, "pass"), (3, "pass"), (0, "pass")):
                    await send(sockets[offset + index], "makeBid", roomId=room_id, bid=bid)
                    await receive(sockets[offset + index], "bidMade")
                proposer = sockets[offset + 2]
                state = await fresh(proposer, room_id)
                board_id = state["publicState"]["boardId"]
                if table == 0:
                    before_hand = state["privateState"]["hand"]
                    await send(proposer, "proposeClaim", roomId=room_id, boardId=board_id,
                               proposalId="ws-reject", tricks=2,
                               revision=state["publicState"]["revision"])
                    await receive(proposer, "claimUpdated")
                    rejecting = await fresh(sockets[offset], room_id)
                    await send(sockets[offset], "respondClaim", roomId=room_id, boardId=board_id,
                               proposalId="ws-reject", accept=False,
                               revision=rejecting["publicState"]["revision"])
                    await receive(sockets[offset], "claimUpdated")
                    state = await fresh(proposer, room_id)
                    assert state["publicState"]["claim"]["status"] == "rejected"
                    assert state["privateState"]["isMyTurn"]
                    assert state["privateState"]["hand"] == before_hand
                    assert state["publicState"]["currentTrick"] == []
                    assert state["publicState"]["dummyHand"] is None
                await send(proposer, "proposeClaim", roomId=room_id, boardId=board_id,
                           proposalId=f"ws-claim-{table}", tricks=0 if table == 0 else 13,
                           revision=state["publicState"]["revision"])
                proposed = await receive(proposer, "claimUpdated")
                assert proposed["publicState"]["claim"]["status"] == "pending"
                assert not proposed["privateState"]["isMyTurn"]
                assert proposed["publicState"]["dummyHand"] is None
                await send(proposer, "playCard", roomId=room_id, card=state["privateState"]["hand"][0])
                assert (await receive(proposer, "error"))["statusCode"] == 409
                # Membership alone cannot forge another voter's seat.
                await send(proposer, "respondClaim", roomId=room_id, boardId=board_id,
                           proposalId=f"ws-claim-{table}", accept=True,
                           userId=identities[offset], revision=proposed["publicState"]["revision"])
                assert (await receive(proposer, "error"))["statusCode"] == 403
                for index in (0, 1, 3):
                    voter = sockets[offset + index]
                    current = await fresh(voter, room_id)
                    await send(voter, "respondClaim", roomId=room_id, boardId=board_id,
                               proposalId=f"ws-claim-{table}", accept=True,
                               revision=current["publicState"]["revision"])
                    await receive(voter, "claimUpdated")
                completed = await fresh(proposer, room_id)
                assert completed["publicState"]["currentPhase"] == "completed"
                assert completed["publicState"]["result"]["settledByClaim"]
                assert completed["publicState"]["scoreboard"]["completedBoards"] == 2
                if table == 0:
                    await send(proposer, "getBoardArchive", roomId=room_id, boardId=board_id)
                    assert (await receive(proposer, "error"))["statusCode"] == 403
            await send(sockets[0], "getDuplicateEvent", eventId=event_id)
            final = (await receive(sockets[0], "duplicateEvent"))["event"]
            assert final["status"] == "completed" and final["boards"][1]["released"]
            assert [row["pointsNS"] for row in final["boards"][1]["results"]] == [-12, 12]
            board_two = final["boards"][1]["boardId"]
            await send(sockets[0], "getBoardArchive", roomId=rooms[0], boardId=board_two)
            settled = (await receive(sockets[0], "boardArchive"))["board"]
            assert settled["tricks"] == []
            assert settled["claimSettlement"]["allocation"] == {"NS": 0, "EW": 13}
            assert settled["result"]["settledByClaim"]
            await send(sockets[0], "nextBoard", roomId=rooms[0], boardId=board_two)
            assert (await receive(sockets[0], "error"))["statusCode"] == 409
            # Reconnect with the original identity retains the frozen table.
            await send(sockets[0], "joinRoom", roomId=rooms[0], userId=identities[0])
            rejoined = await receive(sockets[0], "roomUpdated")
            assert rejoined["updateType"] == "userReconnected"

    asyncio.run(check())
