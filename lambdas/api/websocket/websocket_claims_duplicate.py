"""Local claim and duplicate-event socket routes; no deployment registration."""
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.core.game import claims, duplicate
from lambdas.core.game.runtime import process_game_request


class ClaimsDuplicateHandler(WebSocketBaseHandler):
    def process_websocket_request(self, event, context):
        operation = event.get("requestContext", {}).get("routeKey")
        if operation not in (*claims.OPERATIONS, *duplicate.OPERATIONS):
            return self.error_response(400, "Unknown claim or duplicate operation")
        return process_game_request(self, event, context, operation,
                                    db_utils, broadcast_to_connection)


handler = ClaimsDuplicateHandler()


def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context)
