"""Versioned descriptions of the implemented agreements, not a full SAYC card."""
import copy

CURRENT_VERSION = "sayc-supported-1"
_CARDS = {
    CURRENT_VERSION: {
        "system": "SAYC", "version": CURRENT_VERSION,
        "title": "Supported SAYC-style agreements (limited implementation)",
        "source": "docs/robot-engine-contract.md",
        "supported": [
            {"topic": "Balanced openings",
             "description": "1NT: 15–17 HCP; 2NT: 20–21 HCP; 3NT: 25–27 HCP. "
                            "Balanced shapes: 4333, 4432, 5332."},
            {"topic": "Natural responses to 1NT",
             "description": "Balanced, no four-card major or five-card minor: "
                            "0–7 pass, 8–9 2NT, 10–15 3NT, 16–17 quantitative 4NT."},
            {"topic": "Natural responses to 2NT",
             "description": "Balanced, no four-card major or five-card minor: "
                            "0–3 pass, 4–10 3NT, 11–12 quantitative 4NT."},
            {"topic": "Live auction legality",
             "description": "Every robot proposal is checked against legal calls; "
                            "illegal proposals degrade to pass."},
        ],
        "deviations": [
            "1NT and 2NT deny a five-card major; 3NT permits one.",
            "The simplified strong 2C fallback includes unbalanced 20–21 HCP "
            "without estimating playing tricks.",
        ],
        "unsupported": [
            "This is not full SAYC certification or an expert bidding system.",
            "Stayman, transfers, long-minor and ace-asking routing exist but "
            "their complete strength requirements and continuations are not certified.",
            "Quantitative invitation continuations and later-round slam decisions "
            "are incomplete.",
            "No selectable alternative system or custom partnership conventions.",
            "No promise of complete competitive, rebid, lead or signaling agreements.",
        ],
    }
}


def card(version=None):
    version = CURRENT_VERSION if version is None else version
    if not isinstance(version, str) or version not in _CARDS:
        raise ValueError("Unsupported agreement version")
    return copy.deepcopy(_CARDS[version])


def board_agreements():
    return {side: {"system": "SAYC", "version": CURRENT_VERSION}
            for side in ("NS", "EW")}


def validate(agreements):
    for side in ("NS", "EW"):
        reference = agreements[side]
        if reference.get("system") != "SAYC":
            raise ValueError("Unsupported agreement system")
        card(reference["version"])
    return copy.deepcopy(agreements)
