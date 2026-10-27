"""Server-issued anonymous identities, scoped to bridge socket authentication."""
import json
import time
import uuid

import jwt

from lambdas.shared.security.socket_auth import (
    require_origin, request_headers, verify_identity, signing_key,
    SessionConfigurationError,
)

SESSION_SECONDS = 86400


def lambda_handler(event, context):
    headers = {"Content-Type": "application/json", "Cache-Control": "no-store", "Vary": "Origin"}

    def response(status, body):
        return {"statusCode": status, "headers": headers, "body": json.dumps(body)}

    try:
        origin = require_origin(event)
        headers.update({
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
            "Access-Control-Allow-Credentials": "true",
        })
        method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
        if method == "OPTIONS":
            return response(204, {})
        if method != "POST":
            return response(405, {"error": "POST required"})
        raw = event.get("body") or "{}"
        body = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(body, dict):
            return response(400, {"error": "Request must be an object"})
        authorization = request_headers(event).get("authorization")
        identity = None
        if authorization:
            if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
                raise jwt.InvalidTokenError("Bearer authorization required")
            identity = verify_identity(authorization[7:], allowed_types=("guest",))
        username = body.get("username", identity["username"] if identity else "Guest")
        if (not isinstance(username, str) or not username.strip() or len(username) > 50
                or any(ord(character) < 32 or ord(character) == 127 for character in username)):
            return response(400, {"error": "username must contain 1–50 printable characters"})
        user_id = identity["userId"] if identity else f"guest_{uuid.uuid4()}"
        now = int(time.time())
        token = jwt.encode({
            "userId": user_id, "username": username.strip(), "type": "guest",
            "iat": now, "exp": now + SESSION_SECONDS,
        }, signing_key(), algorithm="HS256")
        return response(200, {
            "userId": user_id, "username": username.strip(), "accessToken": token,
            "expiresIn": SESSION_SECONDS, "tokenType": "Bearer", "isGuest": True,
        })
    except SessionConfigurationError:
        return response(503, {"error": "Session authentication is not configured"})
    except PermissionError:
        return response(403, {"error": "Origin is not allowed"})
    except jwt.InvalidTokenError:
        return response(401, {"error": "A valid unexpired guest session is required"})
    except (ValueError, TypeError):
        return response(400, {"error": "Invalid request"})
