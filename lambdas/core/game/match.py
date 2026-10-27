"""Compact cumulative duplicate scores. No IMP or matchpoint conversion."""
import copy
import uuid


def empty():
    return {"completedBoards": 0, "scoreNS": 0, "scoreEW": 0, "lastBoardId": None}


def complete(game):
    game.setdefault("boardId", str(uuid.uuid4()))
    scoreboard = copy.deepcopy(game.get("scoreboard") or empty())
    if scoreboard["lastBoardId"] != game["boardId"]:
        result = game["result"]
        scoreboard["completedBoards"] += 1
        scoreboard["scoreNS"] += result["scoreNS"]
        scoreboard["scoreEW"] += result["scoreEW"]
        scoreboard["lastBoardId"] = game["boardId"]
    game["scoreboard"] = scoreboard
    return scoreboard
