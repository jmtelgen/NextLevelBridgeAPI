"""Signed socket identities and strict browser-origin validation."""
import os
from urllib.parse import urlsplit

import jwt

from lambdas.shared.security.jwt_utils import JWTUtils


class SessionConfigurationError(Exception):
    pass


def allowed_origins():
    configured = os.environ.get("WS_ALLOWED_ORIGINS") or os.environ.get("FRONTEND_URL", "")
    origins = {value.strip().rstrip("/") for value in configured.split(",") if value.strip()}
    if not origins:
        raise SessionConfigurationError("Frontend origins are not configured")
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            _ = parsed.port
        except ValueError as exc:
            raise SessionConfigurationError("Invalid frontend origin") from exc
        if (parsed.scheme not in ("http", "https") or not parsed.netloc
                or parsed.path or parsed.query or parsed.fragment or parsed.username
                or parsed.password or "*" in origin or any(char.isspace() for char in origin)):
            raise SessionConfigurationError("Frontend origins must be explicit HTTP(S) origins")
    return origins


def request_headers(event):
    return {str(key).lower(): value for key, value in (event.get("headers") or {}).items()}


def require_origin(event):
    origin = request_headers(event).get("origin")
    if not isinstance(origin, str) or origin not in allowed_origins():
        raise PermissionError("Origin is not allowed")
    return origin


def signing_key():
    try:
        return JWTUtils().secret_key
    except Exception as exc:
        raise SessionConfigurationError("Session signing is unavailable") from exc


def verify_identity(token, allowed_types=("access", "guest")):
    if not isinstance(token, str) or not token or len(token) > 8192:
        raise jwt.InvalidTokenError("A signed session token is required")
    payload = jwt.decode(
        token, signing_key(), algorithms=["HS256"],
        options={"require": ["exp", "iat", "userId", "type"]})
    user_id = payload["userId"]
    if (payload["type"] not in allowed_types or not isinstance(user_id, str)
            or not user_id or len(user_id) > 128 or user_id.startswith("ROBOT_")):
        raise jwt.InvalidTokenError("Invalid session identity")
    if (not isinstance(payload["exp"], (int, float)) or isinstance(payload["exp"], bool)
            or not isinstance(payload["iat"], (int, float)) or isinstance(payload["iat"], bool)
            or payload["exp"] <= payload["iat"]):
        raise jwt.InvalidTokenError("Invalid session lifetime")
    username = payload.get("username") or "Guest"
    if not isinstance(username, str) or len(username) > 128:
        raise jwt.InvalidTokenError("Invalid session name")
    return {**payload, "username": username}


def socket_identity(event):
    headers = request_headers(event)
    protocols = [part.strip() for part in headers.get("sec-websocket-protocol", "").split(",")
                 if part.strip()]
    tokens = [protocol[len("bridge.auth."):] for protocol in protocols
              if protocol.startswith("bridge.auth.")]
    authorization = headers.get("authorization")
    if authorization:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            raise jwt.InvalidTokenError("Bearer authorization required")
        tokens.append(authorization[7:])
    if len(tokens) != 1:
        raise jwt.InvalidTokenError("Exactly one signed session token is required")
    if protocols and "bridge.v1" not in protocols:
        raise jwt.InvalidTokenError("bridge.v1 protocol required")
    payload = verify_identity(tokens[0])
    query = event.get("queryStringParameters") or {}
    if query.get("userId") is not None and query["userId"] != payload["userId"]:
        raise PermissionError("Identity does not match signed session")
    return payload, bool(protocols)
