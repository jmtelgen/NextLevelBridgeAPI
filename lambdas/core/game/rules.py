"""Pure duplicate-bridge rules. Mutators operate on a caller-owned room copy."""
import random
import time
import copy
import uuid

from lambdas.core.game import agreements, match

SEATS = ("North", "East", "South", "West")
RANKS = "23456789TJQKA"
SUITS = "CDHS"
CONTRACTS = [f"{level}{strain}" for level in range(1, 8)
             for strain in ("C", "D", "H", "S", "NT")]
VULNERABILITIES = ("None", "NS", "EW", "Both", "NS", "EW", "Both", "None",
                   "EW", "Both", "None", "NS", "Both", "None", "NS", "EW")


def next_seat(seat):
    return SEATS[(SEATS.index(seat) + 1) % 4]


def partner(seat):
    return SEATS[(SEATS.index(seat) + 2) % 4]


def side(seat):
    return "NS" if seat in ("North", "South") else "EW"


def auction_contract(bids):
    last = None
    multiplier = 1
    for call in bids:
        if call["bid"] in CONTRACTS:
            last = call
            multiplier = 1
        elif call["bid"] == "double":
            multiplier = 2
        elif call["bid"] == "redouble":
            multiplier = 4
    return last, multiplier


def legal_calls(game, seat=None):
    if game.get("currentPhase") != "bidding":
        return []
    seat = seat or game.get("turn")
    if seat not in SEATS or seat != game.get("turn"):
        return []
    last, multiplier = auction_contract(game.get("bids", []))
    start = CONTRACTS.index(last["bid"]) + 1 if last else 0
    calls = ["pass"] + CONTRACTS[start:]
    if last:
        if multiplier == 1 and side(last["seat"]) != side(seat):
            calls.append("double")
        elif multiplier == 2 and side(last["seat"]) == side(seat):
            calls.append("redouble")
    return calls


def declarer_and_leader(bids):
    last, _ = auction_contract(bids)
    if not last:
        return None, None
    strain = last["bid"][1:]
    declarer = next(call["seat"] for call in bids
                    if call["bid"] in CONTRACTS and call["bid"][1:] == strain
                    and side(call["seat"]) == side(last["seat"]))
    return declarer, next_seat(declarer)


def deal_cards():
    deck = [rank + suit for suit in SUITS for rank in RANKS]
    random.SystemRandom().shuffle(deck)
    return {seat: deck[i * 13:(i + 1) * 13] for i, seat in enumerate(SEATS)}


def new_board(room, hands=None):
    old = room.get("gameData", {})
    number = int(old.get("boardNumber", 0)) + 1
    dealer = SEATS[(number - 1) % 4]
    room["state"] = "bidding"
    dealt = copy.deepcopy(hands if hands is not None else deal_cards())
    room["gameData"] = {
        "boardId": str(uuid.uuid4()), "initialHands": copy.deepcopy(dealt),
        "eventId": room.get("eventId"),
        "agreements": agreements.board_agreements(),
        "scoreboard": copy.deepcopy(old.get("scoreboard") or match.empty()),
        "currentPhase": "bidding", "turn": dealer, "dealer": dealer,
        "boardNumber": number, "vulnerability": VULNERABILITIES[(number - 1) % 16],
        "bids": [], "hands": dealt,
        "tricks": [], "currentTrick": [], "dummyRevealed": False,
        "contractMultiplier": 1, "scores": old.get("scores", {"NS": 0, "EW": 0}),
    }


def apply_call(room, seat, call):
    game = room["gameData"]
    if call not in legal_calls(game, seat):
        raise ValueError("Illegal bid or not your turn")
    game.setdefault("bids", []).append(
        {"seat": seat, "bid": call, "timestamp": int(time.time() * 1000)})
    game["turn"] = next_seat(seat)
    bids = game["bids"]
    last, multiplier = auction_contract(bids)
    passes = 0
    for entry in reversed(bids):
        if entry["bid"] != "pass":
            break
        passes += 1
    if not last and passes == 4:
        finish_board(room, passed_out=True)
    elif last and passes == 3:
        declarer, leader = declarer_and_leader(bids)
        game.update(currentPhase="playing", contract=last["bid"],
                    contractMultiplier=multiplier, declarer=declarer,
                    dummy=partner(declarer), openingLeader=leader,
                    turn=leader, currentTrick=[], dummyRevealed=False)
        room["state"] = "playing"


def legal_cards(game, seat=None):
    seat = seat or game.get("turn")
    if (game.get("currentPhase") != "playing" or seat != game.get("turn")
            or game.get("completedTrick") or game.get("claim", {}).get("status") == "pending"):
        return []
    hand = game.get("hands", {}).get(seat, [])
    trick = game.get("currentTrick") or []
    if trick:
        following = [card for card in hand if card[1] == trick[0]["card"][1]]
        if following:
            return following
    return list(hand)


def controller(game):
    if game.get("completedTrick") or game.get("claim", {}).get("status") == "pending":
        return None
    turn = game.get("turn")
    if game.get("currentPhase") == "playing" and turn == game.get("dummy"):
        return game.get("declarer")
    return turn


def trick_winner(plays, contract=None):
    if len(plays) != 4:
        return None
    trump = contract[1:] if contract and not contract.endswith("NT") else None
    lead = plays[0]["card"][1]
    return max(plays, key=lambda play: (
        2 if play["card"][1] == trump else 1 if play["card"][1] == lead else 0,
        RANKS.index(play["card"][0])))["seat"]


def apply_card(room, seat, card, *, timestamp=None, hold_trick=False):
    game = room["gameData"]
    if card not in legal_cards(game, seat):
        raise ValueError("Illegal card, must follow suit, or not your turn")
    game["hands"][seat].remove(card)
    game.setdefault("currentTrick", []).append(
        {"seat": seat, "card": card,
         "timestamp": int(time.time() * 1000) if timestamp is None else timestamp})
    game["dummyRevealed"] = True
    game["turn"] = next_seat(seat)
    if len(game["currentTrick"]) == 4:
        plays = game["currentTrick"]
        winner = trick_winner(plays, game.get("contract"))
        trick = {"leader": plays[0]["seat"], "plays": plays, "winner": winner}
        game.setdefault("tricks", []).append(trick)
        game.update(currentTrick=[], previousTrick=trick, trickWinner=winner, turn=winner)
        if hold_trick:
            game["completedTrick"] = trick
        elif len(game["tricks"]) == 13:
            finish_board(room)


def clear_completed_trick(room):
    game = room["gameData"]
    if not game.get("completedTrick"):
        raise ValueError("No completed trick to clear")
    game["completedTrick"] = None
    if len(game["tricks"]) == 13:
        finish_board(room)


def duplicate_score(contract, multiplier, tricks, vulnerable):
    """Return declarer's signed duplicate score (not rubber/Chicago scoring)."""
    level, strain = int(contract[0]), contract[1:]
    difference = tricks - (level + 6)
    if difference < 0:
        down = -difference
        if multiplier == 1:
            return -down * (100 if vulnerable else 50)
        if vulnerable:
            penalty = 200 + max(0, down - 1) * 300
        else:
            penalty = 100 + min(max(down - 1, 0), 2) * 200 + max(down - 3, 0) * 300
        return -penalty * (2 if multiplier == 4 else 1)
    value = 20 if strain in ("C", "D") else 30
    base = (level * value + (10 if strain == "NT" else 0)) * multiplier
    bonus = (500 if vulnerable else 300) if base >= 100 else 50
    if level == 6:
        bonus += 750 if vulnerable else 500
    elif level == 7:
        bonus += 1500 if vulnerable else 1000
    insult = 50 if multiplier == 2 else 100 if multiplier == 4 else 0
    over = difference * (value if multiplier == 1 else (200 if vulnerable else 100)
                         * (2 if multiplier == 4 else 1))
    return base + bonus + insult + over


def finish_board(room, passed_out=False):
    game = room["gameData"]
    if game.get("result") is not None:
        return
    result = {"passedOut": passed_out, "scoreNS": 0, "scoreEW": 0}
    if not passed_out:
        declarer_side = side(game["declarer"])
        tricks = sum(side(trick["winner"]) == declarer_side for trick in game["tricks"])
        tricks += game.get("claimSettlement", {}).get("allocation", {}).get(declarer_side, 0)
        vulnerable = game.get("vulnerability") in ("Both", declarer_side)
        multiplier = game.get("contractMultiplier", 1)
        score = duplicate_score(game["contract"], multiplier, tricks, vulnerable)
        score_ns = score if declarer_side == "NS" else -score
        result.update(contract=game["contract"], multiplier=multiplier,
                      declarerTricks=tricks, target=int(game["contract"][0]) + 6,
                      made=tricks >= int(game["contract"][0]) + 6,
                      scoreNS=score_ns, scoreEW=-score_ns)
        if game.get("claimSettlement"):
            result["settledByClaim"] = True
    scores = game.setdefault("scores", {"NS": 0, "EW": 0})
    scores["NS"] += result["scoreNS"]
    scores["EW"] += result["scoreEW"]
    game.update(currentPhase="completed", turn=None, result=result,
                gameResult="noWinner" if passed_out else "completed")
    game["completedAt"] = int(time.time() * 1000)
    match.complete(game)
    if passed_out:
        game.update(gameEndReason="allPass", winner=None)
    room["state"] = "completed"
