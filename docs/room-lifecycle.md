# Room presence, reconnect reservations and private controls

## Plan and implemented boundary

1. Keep seat ownership and presence in one revision-conditional room record.
2. Refresh signed connections on upgrade, disconnect and authoritative snapshots.
3. Add explicit owner-authorized replacement and private-room capabilities.
4. Verify fake-clock races and real loopback clients; leave AWS deployment paused.

Implemented locally. Nothing here deploys infrastructure, changes the hosted
site, or claims live AWS validation. Existing game runtime and local adapter
integration are maintained by the core feature owner.

## Presence contract

`room.presence` maps full seat names (`North`, `East`, `South`, `West`) to:

```json
{"status":"reconnecting","userId":"guest_...","connectionCount":0,"reservedUntil":1800000120}
```

Statuses: `empty`, `robot`, `online`, `reconnecting`, `offline`. `userId` exists
only for occupied seats. `reservedUntil` is an **epoch-second** deadline for a
disconnected human, not milliseconds. No public connection identifiers, auth
tokens, invitation hashes, or other seats' private hands are included.

Every unexpired signed `access`/`guest` connection counts, including multiple
tabs, renewed sessions and sockets whose advisory `currentRoomId` differs.
Closing one tab does not disconnect a player while another valid tab remains.
An open socket with expired authentication is not online. Expiration starts
grace at the last valid token expiry, not when the next snapshot is requested.
Normal final-tab disconnect starts grace when its cleanup is processed.
Legacy rooms without presence acquire a conservative fresh reservation.

The seat remains reserved for **120 seconds**. At the exact deadline its status
becomes `offline`, but its occupant still does not change. There is **no automatic
robot replacement, removal, ownership transfer, or background grace takeover**.
The frontend refreshes at the deadline; other snapshot reads derive the same
status. During upgrade, presence is broadcast to existing sockets; a new socket
requests its snapshot after the upgrade completes.

Existing occupants may `joinRoom` again during an active board, in a locked
room, or in a private room without a fresh invitation. Guest renewal uses the
existing signed guest endpoint and retains the same `userId`. A new anonymous
identity is not the previous seat's identity.

Presence changes and ownership changes use the room's optimistic revision.
Reconnect and replacement compete on that revision: if reconnect wins, the
stale replacement returns 409; if replacement wins, late reconnect cannot
restore the removed seat. A 409 requires a fresh snapshot, not blind replay.
Read-only public status rendering never moves or replaces a player.

## Commands and replies

All commands use the existing signed socket identity; optional `userId` must
match it. Payload examples below are the `data` object of the WebSocket message.

| Action | Data | Successful reply |
| --- | --- | --- |
| `joinRoom` | `roomId`, `userId`, optional `invitationToken` | `roomUpdated`, `updateType: userJoined/userReconnected`, `assignedSeat` |
| `changeSeat` | `roomId`, `userId`, `newSeat` | `roomUpdated`, `updateType: seatChanged`, `oldSeat`, `newSeat` |
| `leaveRoom` | `roomId` | `roomLeft`, `roomId`, `releasedSeat` |
| `replacePlayer` | `roomId`, `seat` | `roomUpdated`, `updateType: playerReplaced` |
| `transferOwnership` | `roomId`, `newOwnerId` | `roomUpdated`, `updateType: ownershipTransferred` |
| `setRoomLock` | `roomId`, boolean `locked` | `roomUpdated`, `updateType: roomLockChanged` |
| `createInvitation` | `roomId`, optional `expiresInSeconds` | `roomInvitation`, `roomId`, `invitationId`, `invitationToken`, `expiresAt` |
| `revokeInvitation` | `roomId`, `invitationId` | `roomUpdated`, `updateType: invitationRevoked` |

Room updates include separately seat-filtered `publicState`/`privateState` and
safe room metadata; they do not expose raw `gameData.hands`. Mutation replies
are explicitly sent to the requesting socket, not merely returned from Lambda.
Clients should tolerate duplicate revision-identical delivery.

`replacePlayer` is owner-only, targets an offline human after grace, and cannot
replace the current owner. It records a bounded `playerReplaced` room event and
broadcasts an explicit announcement. The replacement keeps that seat's hand,
turn, bidding history and score. The existing computer coordinator is invoked
after the committed replacement; it uses normal legal robot transitions and
pacing, not an alternate or automatic takeover engine.

### Safe release and owner policy

Seat movement, `leaveRoom` and ownership transfer are **waiting/setup-only**;
active and completed boards return 409. This intentionally avoids silently
changing a board's occupants. A waiting-room non-owner may explicitly release
their own seat. An owner must explicitly transfer ownership to another seated
human first; a lone owner cannot currently abandon a room. Owner disconnect
does not orphan the room or transfer control.

Duplicate-event enrollment additionally freezes membership/ownership even
while waiting: no new joins, moves, leaves, replacements or transfers. Existing
members may still reconnect before or after start. Room/event invitations do
not bypass that freeze. See [claims and duplicate events](claims-duplicate.md).

`ownerId` is a DynamoDB room sort key. Transfer uses an atomic transaction:
revision-guarded delete of the old composite key and conditional creation of
the new owner key. It never creates two independent live rooms. No active-board
transfer or active-board seat-release policy is implied by this first wave.

### Private-room controls

New membership in a public legacy room still works without an invitation.
New membership in a private room requires a live invitation. A locked room
denies **all new membership**, including invited membership; existing members
may reconnect. Controls require the current owner and use conditional writes.
Invitation validation and join share the same room revision, so concurrent
revocation/locking cannot silently bypass authorization.

Invitations use a random identifier plus a cryptographically random 256-bit
secret. Only a SHA-256 digest, expiry and revocation flag are stored. Lifetime
defaults to 3,600 seconds and must be an integer from 1 to 86,400; at most 32
live invitations exist per room. Expired/revoked entries are pruned when new
invitations are created. Invitation expiry is **epoch seconds**. Plaintext
capabilities are returned only to the creator, never in snapshots or broadcasts.

An invitation link may carry `#roomId=...&invitationToken=...`. It must **never**
contain an access token, refresh token, guest JWT, `bridge.auth` protocol value
or other real signed authentication material. The invitation is a separate
room-join capability, not an authentication credential. The recipient still
requires their own signed socket session. Revocation prevents later new joins;
it does not eject already seated members.

## Implementation APIs and validation

- `lambdas/core/rooms/lifecycle.py`: `refresh_presence`, `public_presence`,
  `sync_user_presence`, `join_room`, `change_seat`, `leave_room`,
  `replace_player`, `control_room`.
- `lambdas/core/rooms/responses.py`: personalized broadcasts and explicit replies.
- `lambdas/shared/database/db_utils.py`: paginated consistent connection and room
  membership reads; atomic composite-key owner transfer.
- Socket wrappers: existing connect/disconnect/create/join/change handlers plus
  `websocket_leave_room.py`, `websocket_replace_player.py`,
  `websocket_room_controls.py`.
- Core integration: safe `room_metadata`, snapshot refresh and local route
  registration. Presence persistence resolves `runtime.save_room` dynamically
  so revision-bound local robot timers are rescheduled rather than invalidated.

Verified command (214 tests):

```sh
PYTHONDONTWRITEBYTECODE=1 AWS_EC2_METADATA_DISABLED=true \
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
AWS_DEFAULT_REGION=us-east-1 venv/bin/python -m pytest -q \
  tests/test_room_lifecycle.py tests/test_room_lifecycle_local.py \
  tests/test_socket_sessions.py tests/test_websocket_make_bid.py \
  tests/test_bridge_lifecycle.py tests/test_game_pacing.py tests/test_game_tick.py \
  tests/test_local_server.py
```

Dedicated tests cover fake-clock boundaries, duplicate tabs, token expiry and
same-ID renewal, both reconnect/replacement race orderings, simultaneous seat
claims, active-board invariants, filtered replies, computer-coordinator
integration, invitation expiry/revocation, locks/owner checks, composite-key
transfer, and real loopback invitation/reconnect/release flows. All SDK calls
in loopback/Moto tests are in-process mocks with real AWS transport disabled.

## Readiness and future tasks

- Local implementation and targeted regressions pass; deployment remains paused.
- Staging needs route registration, `ROOM_TABLE`/connection-table configuration,
  consistent-read/scan/write permissions and scoped `TransactWriteItems` for
  ownership transfer. This change does not modify deployment packages or IAM.
- Before AWS rollout, verify real concurrent Lambda invocations, paginated
  membership scans, disconnect delivery failures and revision-bound worker
  rescheduling. Production needs indexed membership/session lookups instead of
  table scans for scale.
- A missing disconnect callback cannot be distinguished from a live transport
  until token expiry. Add authenticated heartbeats/transport leases if faster
  detection is required; do not silently infer disconnection or bypass grace.
- Room abandonment, owner recovery, between-board release/transfer and active
  voluntary-leave policy need explicit future decisions. No automatic takeover
  or hidden ownership reassignment should be introduced as a shortcut.
