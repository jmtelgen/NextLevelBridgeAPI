# Account authentication contract

## Routes

All routes below are POST handlers under `lambdas/api/auth`. The frontend
uses `/api` as a same-origin proxy prefix; the development adapter accepts
both prefixed and unprefixed requests.

| Route | Handler | Behavior |
|---|---|---|
| `/account` | `account_create.py` | Validate input/policy, hash password, return 201 or an explicit error |
| `/account/login` | `account_login.py` | Verify credentials, return account identity/access JWT and HttpOnly refresh cookie |
| `/auth/refresh` | `account_refresh_token.py` | Validate refresh JWT, return access JWT; never reissue the refresh cookie |
| `/auth/guest` | `guest_session.py` | Issue/renew a signed guest identity, without account fallback |
| `/logout` | `account_logout.py` | Expire the browser refresh cookie with Max-Age=0 and an expired date |

Signup requires string fields, a username of at least three characters, an
email containing `@`, and the existing `PasswordUtils` policy: 8–128 characters,
lowercase, uppercase, digit and a symbol in `!@#$%^&*()_+-=[]{}|;:,.<>?`.
The client mirrors this policy and requires matching confirmation. Missing,
non-object and wrong-type signup payloads return 400, duplicates return 409.
No password, raw auth body/event, token, cookie, malformed Authorization
header or stored password material is logged. Shared auth-event logging
allowlists diagnostic metadata rather than dumping arbitrary request details.

## Deployment wiring (not performed)

`deploy.sh` packages `account-logout`; `deploy-aws.sh` maps it to
`LogoutAPILambda`. This task did not run either deployment script or access AWS.
Before production use:

1. Wire API Gateway **POST /logout** to that handler with Lambda proxy
   integration. Pass `multiValueHeaders.Set-Cookie` to the browser. Enable
   OPTIONS or equivalent gateway preflight if using a cross-origin API.
2. Set `FRONTEND_URL` to the exact HTTPS frontend origin and
   `ENVIRONMENT=production` on login/logout. Cookies share `Path=/`,
   `HttpOnly`, `SameSite=Strict`, and `Secure` in production.
3. Forward cookies through the frontend `/api` proxy; disable auth-response
   caching. Cross-origin credentialed responses need an exact origin and
   `Access-Control-Allow-Credentials: true`, not wildcard CORS.
4. Configure the existing signing secret and exact WebSocket origins as in the
   socket contract. Seat authorization continues to use signed connection
   identities, not request/display names.

The local adapter now invokes the **same logout Lambda handler**, rather
than a separate synthetic logout response. It removes Secure only for its
loopback HTTP transport.

## Logout limits

Logout removes the refresh cookie from the current browser and the frontend
disconnects its socket and drops account/guest/room state. This is **cookie
expiry, not JWT revocation**: copied access tokens remain usable until their
15-minute expiry, copied refresh tokens until their seven-day expiry, and other
devices are not logged out. There is no new revocation database.

Refresh returns no Set-Cookie header: a response already in flight cannot
reinstall the cookie after logout. The client also guards late refresh/guest
responses from restoring a superseded identity. Failed logout requests are
reported visibly and can be retried.

## Offline verification

From this repository:

```sh
PYTHONDONTWRITEBYTECODE=1 AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing venv/bin/python -m pytest tests/test_account_create.py tests/test_auth_flow.py tests/test_local_server.py tests/test_socket_sessions.py -q --tb=short
bash -n deploy.sh deploy-aws.sh
```

The explicit region makes Moto tables deterministic even if the shell defaults
to another region. Tests use mocks or Moto and the local adapter blocks AWS
wire transport. They exercise successful/failed signup and login, password
boundaries, captured credential-safe logs, matching logout expiry, a full
authenticated board/reconnect/privacy flow, and rejected socket identities.
See `BridgeGame/docs/authentication.md` for the real-browser commands and
3101/3102/4201 helper cleanup instructions.
