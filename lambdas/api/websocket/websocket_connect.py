"""Authenticate the WebSocket upgrade; never trust a caller-selected identity."""
import jwt

from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.security.socket_auth import (
    require_origin, socket_identity, SessionConfigurationError,
)
from lambdas.core.rooms.lifecycle import sync_user_presence
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.core.game.runtime import GameRequestError


class WebSocketConnectHandler(WebSocketBaseHandler):
    def process_websocket_request(self, event, context):
        try:
            self.validate_route_key(event, "$connect")
            connection_id = self.get_connection_id(event)
            if not connection_id:
                return self.error_response(400, "Missing connection ID")
            require_origin(event)
            identity, uses_protocol = socket_identity(event)
            success = db_utils.create_connection_record(
                connection_id=connection_id,
                user_id=identity["userId"],
                user_name=identity["username"],
                request_time=event.get("requestContext", {}).get("requestTimeEpoch"),
                auth_expires_at=int(identity["exp"]),
                auth_type=identity["type"],
            )
            if not success:
                return self.error_response(503, "Unable to establish session")
            try:
                sync_user_presence(db_utils, identity["userId"], broadcast_to_connection)
            except GameRequestError as exc:
                db_utils.delete_connection_record(connection_id)
                return self.error_response(exc.status, str(exc))
            except Exception:
                db_utils.delete_connection_record(connection_id)
                return self.error_response(503, "Unable to synchronize room presence")
            response = {"statusCode": 200}
            if uses_protocol:
                response["headers"] = {"Sec-WebSocket-Protocol": "bridge.v1"}
            return response
        except SessionConfigurationError:
            return self.error_response(503, "Session authentication is not configured")
        except PermissionError as exc:
            return self.error_response(403, str(exc))
        except jwt.InvalidTokenError:
            return self.error_response(401, "A valid unexpired signed session is required")
        except ValueError as exc:
            return self.error_response(400, str(exc))


handler = WebSocketConnectHandler()


def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context)
