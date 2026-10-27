"""Connection-authenticated SOLO hints and server-owned computer play tiers."""
import copy
import logging

from lambdas.core.game import runtime
from lambdas.core.robot.level_policy import LEVELS, level_policy
from lambdas.core.robot.practice import PracticeDenied, practice_hint, require_solo
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.utils.websocket_utils import broadcast_to_connection

LOG = logging.getLogger(__name__)


class WebSocketPracticeHandler(WebSocketBaseHandler):
    def process_websocket_request(self, event, context):
        try:
            action = event.get("requestContext", {}).get("routeKey")
            if action not in ("getPracticeHint", "setComputerLevel"):
                raise ValueError("Invalid practice route")
            body = self.parse_body(event)
            if not isinstance(body, dict) or ("data" in body and not isinstance(body["data"], dict)):
                raise ValueError("Request and data must be objects")
            data = self.extract_data_from_body(body)
            user_id = runtime.connection_user(db_utils, event, data.get("userId"))
            room_id = data.get("roomId")
            if not isinstance(room_id, str) or not room_id:
                raise ValueError("roomId is required")
            table = db_utils.get_table("ROOM_TABLE")
            found = db_utils.find_room_by_id(room_id, table)
            if not found:
                raise runtime.GameRequestError(404, "Room does not exist")
            room = runtime.normalize_room(copy.deepcopy(found))
            require_solo(room, user_id)
            if runtime.claims.pending(room["gameData"]):
                raise runtime.GameRequestError(409, "Practice actions are frozen during a claim")
            if "revision" in data and (type(data["revision"]) is not int
                                      or data["revision"] != int(room.get("revision", 0))):
                raise runtime.GameRequestError(409, "Stale revision; request getGameState")
            if action == "getPracticeHint":
                if set(data) - {"action", "roomId", "userId", "revision", "suggest", "data"}:
                    raise ValueError("Unknown hint parameter")
                hint = practice_hint(room, user_id, suggest=data.get("suggest", True))
                payload = {"action": "practiceHint", "roomId": room_id,
                           "revision": int(room.get("revision", 0)), "hint": hint}
            else:
                if room.get("ownerId") != user_id:
                    raise PracticeDenied("Only the room owner may change the computer level")
                if set(data) - {"action", "roomId", "userId", "revision", "computerLevel", "data"}:
                    raise ValueError("Unknown computer level parameter")
                policy = level_policy(data.get("computerLevel"))
                room["computerLevel"] = policy.name
                runtime.save_room(table, room)
                runtime.publish(db_utils, broadcast_to_connection, room,
                                "gameState", "Computer play budget updated")
                payload = {"action": "computerLevelChanged", "roomId": room_id,
                           "revision": int(room["revision"]), "computerLevel": policy.public(),
                           "availableLevels": [level.public() for level in LEVELS.values()]}
            payload = self._convert_for_json(payload)
            self._send(event, payload)
            return self.success_response(payload)
        except PracticeDenied as exc:
            status, message = 403, str(exc)
        except runtime.GameRequestError as exc:
            status, message = exc.status, str(exc)
        except (ValueError, TypeError, KeyError) as exc:
            status, message = 400, str(exc)
        payload = {"action": "error", "statusCode": status, "message": message, "error": message}
        self._send(event, payload)
        return self.error_response(status, message)

    def _send(self, event, payload):
        connection_id = self.get_connection_id(event)
        if connection_id:
            try:
                broadcast_to_connection(connection_id, payload)
            except Exception:
                LOG.warning("Practice response delivery failed", exc_info=True)


handler = WebSocketPracticeHandler()


def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context)
