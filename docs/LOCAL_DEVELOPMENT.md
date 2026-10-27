# Play Bridge locally (no AWS changes)

This **development-only, loopback-only** adapter runs the real HTTP authentication
and WebSocket Lambda handlers. It uses the existing authoritative game rules,
robots, personalized broadcasts, revision checks, and signed socket authentication.
There is no alternative gameplay implementation, deployment, or AWS provisioning.

## Start

From the `BridgeLambdas` checkout, using Python 3.10+:

```bash
# Reuse the existing environment; create one only if this checkout has none:
# python3 -m venv venv
venv/bin/python -m pip install -r requirements-local.txt
venv/bin/python scripts/local_server.py
```

The checked environment already has native DDS; **no solver build is necessary**.
Keep this command in its terminal. Stop with Ctrl-C.

In another terminal:

```bash
curl --fail http://127.0.0.1:3001/health
```

Expected response:

```json
{"status":"ready","mode":"local-development","aws":"in-memory-moto","persistent":false}
```

Start the sibling `BridgeGame` frontend with its development proxy:

```bash
cd ../BridgeGame
VITE_API_BASE_URL=http://127.0.0.1:3001 \
VITE_WS_ENDPOINT=ws://127.0.0.1:3002 \
npm start -- --host 127.0.0.1 --port 4200
```

Alternatively, with the existing frontend dependencies:

```bash
VITE_API_BASE_URL=http://127.0.0.1:3001 \
VITE_WS_ENDPOINT=ws://127.0.0.1:3002 \
npx vite --host 127.0.0.1 --port 4200
```

Open `http://127.0.0.1:4200`. `/api` requests stay same-origin at the browser;
Vite forwards them to port 3001 and strips `/api`. Do not point the frontend at a
deployed API when testing this server. Environment changes require a Vite restart.
Use the **same hostname** consistently so account refresh cookies work.

### Sample multiplayer + computer game

1. Open two independent browser profiles/incognito contexts, not merely two tabs
   sharing account/session state. Choose Guest in both and enter distinct names;
   the normal guest flow obtains server-signed sessions.
2. In the first browser, create a room and copy its room ID. Join that ID in the
   second browser. Change seats before starting if desired.
3. The owner starts the board. Empty seats become computer players automatically.
   For a solo computer game, start without the second player.
4. Bid when your private state says it is your turn, then play legal cards.
   Declarer controls dummy after the opening lead. Robots advance on the server.
   In a fanned hand, click the card's exposed rank corner rather than a center
   covered by the neighboring card.
5. Reload/reconnect during play: the existing signed session and `getGameState`
   recover your seat, private hand, and current revision; do not join again.
6. After 13 tricks the owner can start the next board. Scores and dealer rotate
   through the production rules.

Account creation/login also use their real handlers, password hashing and signed
access tokens. No successful authentication is fabricated. Registered access tokens
expire after 15 minutes; the frontend refreshes via its HttpOnly refresh cookie.
Guest sessions last 24 hours; valid guest renewal retains the same identity.

## HTTP and socket contract

| Browser route (through Vite) | Adapter route | Production handler |
| --- | --- | --- |
| `POST /api/account` | `POST /account` | `account_create` |
| `POST /api/account/login` | `POST /account/login` | `account_login` |
| `POST /api/auth/refresh` | `POST /auth/refresh` | `account_refresh_token` |
| `POST /api/auth/guest` | `POST /auth/guest` | `guest_session` |
| `POST /api/logout` | `POST /logout` | Local refresh-cookie deletion only |
| `GET /api/connections` | `GET /connections` | `connection_count` (account access JWT required) |

Direct `/api/...` aliases are also accepted by the adapter for diagnostics.
`GET /health` is an unauthenticated readiness endpoint. CORS permits only configured
origins and credentials; preflight is supported.
The connection counter preserves the production account-auth requirement. Anonymous
and guest clients may show statistics as unavailable; the adapter never fabricates
zero counts or bypasses that handler's authentication.

Guest request example (omit tokens from logs and shell history):

```bash
curl --fail http://127.0.0.1:3001/auth/guest \
  -H 'Origin: http://127.0.0.1:4200' \
  -H 'Content-Type: application/json' \
  --data '{"username":"Local player"}'
```

The response contains `userId`, `username`, `accessToken`, `expiresIn`, `tokenType`,
and `isGuest`. The browser opens:

```javascript
new WebSocket('ws://127.0.0.1:3002', [
  'bridge.v1',
  'bridge.auth.' + accessToken,
]);
```

The adapter forwards the real browser Origin and subprotocol headers to `$connect`
**before** accepting the upgrade. The server negotiates only `bridge.v1`.
Unsigned identities, forged/expired tokens, refresh tokens, and denied origins
are rejected. Tokens must not appear in the URL. There is no local authentication
bypass, production auth flag change, or client-selected identity fallback.

Messages use the existing `{action, data}` contract. Supported actions:
`createRoom`, `joinRoom`, `changeSeat`, `startRoom`, `makeBid`, `playCard`,
`getGameState`, and `nextBoard`. See [WEBSOCKET_CONTRACT.md](WEBSOCKET_CONTRACT.md)
for complete fields and privacy behavior.

For example, once connected using a real session:

```javascript
socket.send(JSON.stringify({
  action: 'createRoom',
  data: {
    ownerId: userId, playerName: username, roomName: 'Local bridge', isPrivate: false,
  },
}));
// Use room.roomId from the createRoom response:
socket.send(JSON.stringify({action: 'startRoom', data: {roomId}}));
socket.send(JSON.stringify({action: 'getGameState', data: {roomId}}));
// Only when privateState.isMyTurn; use an actually legal bid/card and current revision:
socket.send(JSON.stringify({
  action: 'makeBid', data: {roomId, bid: 'pass', revision: publicState.revision},
}));
socket.send(JSON.stringify({
  action: 'playCard',
  data: {roomId, card: privateState.legalCards[0], revision: publicState.revision},
}));
```

Do not send bid and play examples blindly: choose the action matching the current
phase. After a stale-revision error, request a fresh snapshot before retrying.

## Configuration and isolation

```bash
venv/bin/python scripts/local_server.py \
  --host 127.0.0.1 --http-port 3001 --ws-port 3002 \
  --origin http://127.0.0.1:4200 --origin http://localhost:4200
```

Without `--origin`, the exact allowed origins are `http://localhost:4200`,
`http://127.0.0.1:4200`, `http://localhost:4201`, and `http://127.0.0.1:4201`.
Supplying any `--origin` replaces that list. Non-loopback binds such as `0.0.0.0`
are refused. This is not a LAN server or a production replacement.

The child process discards ambient `AWS_*` settings, supplies dummy development
credentials, and starts Moto **before importing application handlers/SDK clients**.
Moto creates isolated `local-users` (`userId`), `local-rooms` (`roomId`, `ownerId`),
and `local-connections` (`connectionId`, `currentRoomId`) DynamoDB tables plus a
random HS256 signing secret in its in-memory Secrets Manager (`Bridge/JWT`).
Standard SDK service URLs are intercepted inside Moto; botocore's actual network
transport is also blocked, so an unmocked request fails closed rather than reaching
AWS. The API Gateway management endpoint is a local shim, never a deployed URL.
The shim maps connection IDs to real sockets and sends each production-generated
personalized payload to its intended client.

Synchronous Lambda handlers run on a dedicated worker thread, serially, keeping
the async HTTP/WebSocket event loop responsive for independent clients, socket
delivery, and health probes. This intentionally favors deterministic local play
over production throughput. Existing handlers' credential-bearing debug output is
discarded; access/event logging is disabled.

**State resets on restart.** Accounts, rooms, scores, connections, and the generated
signing key are in memory only. After restarting, clear saved guest/account state
or log out and obtain a fresh session. Old JWTs cannot authenticate against the
new key. An in-progress room cannot survive a server restart.

Only this local HTTP transport removes `Secure` from refresh cookies because it
serves plain loopback HTTP; HttpOnly, SameSite and real JWT checks remain intact.
No production cookie or handler code is changed. There is no production logout
handler: local `/logout` deletes the refresh cookie but **does not revoke already
issued JWTs**. The normal client discards its access token; server enforcement
still expires existing access/socket sessions at their signed expiry.

## Verify

```bash
venv/bin/python -m pytest -q tests/test_local_server.py
```

Tests launch and stop their own adapter subprocess on ephemeral loopback ports;
no external server, AWS account, credentials, Docker, solver build, or detached
helper is required. Coverage includes real account creation/login/refresh/logout,
multiple accounts, signed guest issuance/renewal, rejected Origin/forged/refresh
tokens, authenticated connection counts, two independent real WebSocket clients,
create/join/start, private hands
and broadcasts, spoof/stale-revision rejection, reconnect snapshots, legal bidding
and all 52 card plays with two robots, scoring and the next board. Separate checks
verify public binding is refused and an unmocked SDK endpoint cannot reach the wire.

If a port is occupied, choose distinct `--http-port` and `--ws-port` values and
update both frontend environment variables. A 403 on connect usually means the
browser's exact origin (scheme, host and port) is not configured. A 401 after
restart usually means the browser retained a token signed by the previous run.
