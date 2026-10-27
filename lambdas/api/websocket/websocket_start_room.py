"""Board start, personalized reconnect snapshot, and next-board routes."""
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.core.game import rules
from lambdas.core.game.runtime import process_game_request

SEATS = list(rules.SEATS)


class WebSocketStartRoomHandler(WebSocketBaseHandler):
    def process_websocket_request(self, event, context):
        route = event.get("requestContext", {}).get("routeKey")
        if route not in ("startRoom", "getGameState", "nextBoard"):
            return self.error_response(400, f"Invalid route key: {route}")
        return process_game_request(
            self, event, context, route, db_utils, broadcast_to_connection,
            hands_factory=self._deal_cards)

    def _deal_cards(self):
        return rules.deal_cards()


handler = WebSocketStartRoomHandler()


def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context)
