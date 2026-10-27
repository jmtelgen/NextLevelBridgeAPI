"""Server-authoritative card-play route, including declarer's dummy control."""
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.core.game import rules
from lambdas.core.game.runtime import process_game_request

SUITS = list(rules.SUITS)
RANKS = list(rules.RANKS)


class WebSocketPlayCardHandler(WebSocketBaseHandler):
    def _determine_trick_winner(self, trick, contract=None):
        return rules.trick_winner(trick, contract)

    def process_websocket_request(self, event, context):
        try:
            self.validate_route_key(event, "playCard")
        except ValueError as exc:
            return self.error_response(400, str(exc))
        return process_game_request(
            self, event, context, "playCard", db_utils, broadcast_to_connection)


handler = WebSocketPlayCardHandler()


def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context)
