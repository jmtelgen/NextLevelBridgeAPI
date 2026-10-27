"""Server-authoritative auction route."""
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.core.game import rules
from lambdas.core.game.runtime import process_game_request

VALID_BIDS = ["pass"] + rules.CONTRACTS + ["double", "redouble"]


class WebSocketMakeBidHandler(WebSocketBaseHandler):
    def _determine_declarer_and_leader(self, bids):
        return rules.declarer_and_leader(bids)

    def _are_partners(self, seat1, seat2):
        return rules.side(seat1) == rules.side(seat2)

    def process_websocket_request(self, event, context):
        try:
            self.validate_route_key(event, "makeBid")
        except ValueError as exc:
            return self.error_response(400, str(exc))
        return process_game_request(
            self, event, context, "makeBid", db_utils, broadcast_to_connection)


handler = WebSocketMakeBidHandler()


def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context)
