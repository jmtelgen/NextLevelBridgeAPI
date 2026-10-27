"""Connection-authenticated room owner controls and explicit membership operations."""
import copy

from lambdas.core.game import runtime
from lambdas.core.rooms import lifecycle
from lambdas.core.rooms.responses import deliver_reply, publish_update
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.utils.websocket_utils import broadcast_to_connection

UPDATES = {
    "replacePlayer": "playerReplaced", "transferOwnership": "ownershipTransferred",
    "setRoomLock": "roomLockChanged", "revokeInvitation": "invitationRevoked",
}


class RoomControlsHandler(WebSocketBaseHandler):
    def process_websocket_request(self, event, context):
        try:
            action = event.get("requestContext", {}).get("routeKey")
            if action not in (*UPDATES, "leaveRoom", "createInvitation"):
                raise runtime.GameRequestError(400, "Unknown room action")
            body = self.parse_body(event)
            if not isinstance(body, dict) or (
                    "data" in body and body["data"] is not None and not isinstance(body["data"], dict)):
                raise runtime.GameRequestError(400, "Room request data must be an object")
            data = self.extract_data_from_body(body)
            user = runtime.connection_user(db_utils, event, data.get("userId"))
            room_id = data.get("roomId")
            if not isinstance(room_id, str) or not room_id:
                raise runtime.GameRequestError(400, "roomId is required")
            table = db_utils.get_table("ROOM_TABLE")
            room = db_utils.find_room_by_id(room_id, table)
            if not room:
                raise runtime.GameRequestError(404, "Room does not exist")
            room = copy.deepcopy(room)
            if user not in room.get("seats", {}).values():
                raise runtime.GameRequestError(403, "User is not seated in this room")
            if action == "leaveRoom":
                seat = lifecycle.leave_room(table, room, user)
                publish_update(db_utils, broadcast_to_connection, room,
                               f"{seat} seat released", updateType="seatReleased")
                db_utils.update_user_room(user, "not-joined")
                return self.success_response({
                    "action": "roomLeft", "success": True,
                    "roomId": room_id, "releasedSeat": seat})
            if action == "replacePlayer":
                room = lifecycle.replace_player(
                    db_utils, table, room, user, data.get("seat"))
                message = f"{data['seat']} player explicitly replaced with a robot"
            else:
                result = lifecycle.control_room(table, room, user, action, data, db=db_utils)
                if result:
                    # The invitation capability goes only to its creator.
                    return self.success_response(result)
                message = {
                    "transferOwnership": "Room ownership transferred",
                    "setRoomLock": "Room lock changed",
                    "revokeInvitation": "Room invitation revoked",
                }[action]
            publish_update(db_utils, broadcast_to_connection, room, message,
                           updateType=UPDATES[action])
            if action == "replacePlayer" and room.get("state") in ("bidding", "playing"):
                room = runtime.normalize_room(room)
                room = runtime.advance_robots(
                    db_utils, table, broadcast_to_connection, room, context)
            payload = runtime.personalized(room, user, "roomUpdated", message)
            payload.update(success=True, updateType=UPDATES[action])
            return self.success_response(self._convert_for_json(payload))
        except runtime.GameRequestError as exc:
            return self.error_response(exc.status, str(exc))
        except (ValueError, TypeError):
            return self.error_response(400, "Invalid room request")


handler = RoomControlsHandler()


def lambda_handler(event, context):
    return deliver_reply(event, handler.handle_websocket_request(event, context),
                         broadcast_to_connection)
