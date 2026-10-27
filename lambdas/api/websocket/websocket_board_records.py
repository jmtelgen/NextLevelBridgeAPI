"""Authenticated archive, agreement, cumulative score and practice-pace routes."""
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.core.game.runtime import READ_FEATURES, process_game_request


class BoardRecordsHandler(WebSocketBaseHandler):
    def process_websocket_request(self, event, context):
        route = event.get("requestContext", {}).get("routeKey")
        if route not in (*READ_FEATURES, "setPracticePace"):
            return self.error_response(400, "Unknown board-record operation")
        return process_game_request(
            self, event, context, route, db_utils, broadcast_to_connection)


handler = BoardRecordsHandler()


def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context)
