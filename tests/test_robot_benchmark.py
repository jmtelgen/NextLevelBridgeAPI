from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from lambdas.core.robot import fair_play as ai
from scripts import benchmark_robots as benchmark


class ZeroContinuation:
    def solve_board(self, **kwargs):
        return [("S2", 0)]


@pytest.mark.parametrize("score,imps", [
    (0, 0), (10, 0), (20, 1), (40, 1), (50, 2), (4000, 24), (-620, -12),
])
def test_standard_imp_boundaries(score, imps):
    assert benchmark.score_to_imps(score) == imps


def test_paired_deals_fixed_contracts_and_replay():
    first = benchmark.run_benchmark(boards=1, seed=19, samples=1, solver_factory=ZeroContinuation)
    second = benchmark.run_benchmark(boards=1, seed=19, samples=1, solver_factory=ZeroContinuation)
    assert first["expert_strength_proven"] is False
    assert first["comparison"] == second["comparison"]
    for leg, replay in zip(first["pairs"][0]["legs"], second["pairs"][0]["legs"]):
        assert leg["actions"] == 52
        assert leg["action_digest"] == replay["action_digest"]
        assert leg["score_ns"] == replay["score_ns"]
    pair = first["pairs"][0]
    assert pair["sampled_score_delta"] == pair["legs"][0]["score_ns"] - pair["legs"][1]["score_ns"]
    for policy in first["policies"].values():
        assert policy["actions"] == 52
        assert policy["legal_action_rate"] == 1
        assert policy["solver_error_rate"] == 0
        assert policy["latency_ms"]["p95"] >= policy["latency_ms"]["p50"]
    assert first["comparison"]["bootstrap_95_percentile_mean_imp_interval"] is None


def test_both_policies_receive_only_lawful_observations(monkeypatch):
    original_observe = ai.observe
    checked = []

    def protected_observe(room, actor):
        game = room["gameData"]
        dummy = ai.partner(game["declarer"])
        controller = game["declarer"] if actor == dummy else actor
        allowed = {controller}
        if game["currentTrick"] or game["tricks"]:
            allowed.add(dummy)
        original_hands = game["hands"]

        class ProtectedHands(dict):
            def get(self, seat, default=None):
                assert seat in allowed, "Benchmark policy read concealed information"
                return super().get(seat, default)

        game["hands"] = ProtectedHands(original_hands)
        try:
            state = original_observe(room, actor)
        finally:
            game["hands"] = original_hands
        assert isinstance(state, ai.Observation)
        checked.append(actor)
        return state

    monkeypatch.setattr(ai, "observe", protected_observe)
    benchmark.run_benchmark(boards=1, seed=3, samples=1, solver_factory=ZeroContinuation)
    assert len(checked) == 104


def test_missing_dds_requires_explicit_degraded_opt_in(caplog):
    unavailable = Mock(side_effect=RuntimeError("DDS missing for test"))
    with pytest.raises(RuntimeError, match="preflight failed"):
        benchmark.run_benchmark(boards=1, solver_factory=unavailable)
    report = benchmark.run_benchmark(
        boards=1, samples=1, solver_factory=unavailable, allow_degraded=True,
    )
    assert report["solver_available"] is False
    assert report["policies"]["sampled_dds"]["solver_error_actions"] > 0
    assert report["policies"]["sampled_dds"]["degraded_solver_rate"] > 0
    assert report["policies"]["heuristic"]["degraded_solver_rate"] == 0
    assert "robot_play_degraded" in caplog.text


def test_uncertainty_uses_paired_board_units_and_seed():
    values = [-8, 0, 2, 10]
    result = benchmark.uncertainty(values, 7)
    assert result == benchmark.uncertainty(values, 7)
    assert result["paired_boards"] == 4
    assert result["bootstrap_resamples"] == 2000
    low, high = result["bootstrap_95_percentile_mean_imp_interval"]
    assert min(values) <= low <= high <= max(values)


def test_board_generation_is_local_reproducible_and_nonmutating():
    first = benchmark.board_room(17, 2)
    assert first == benchmark.board_room(17, 2)
    before = deepcopy(first)
    metrics = {policy: benchmark._new_metrics() for policy in ("sampled_dds", "heuristic")}
    benchmark._play_leg(first, "NS", ai.PlayConfig(samples=1, budget_ms=0),
                        metrics, ZeroContinuation, benchmark.time.perf_counter)
    assert first == before


def test_cli_rejects_unbounded_board_count(capsys):
    with pytest.raises(SystemExit) as exc:
        benchmark.main(["--boards", "65"])
    assert exc.value.code == 2
    assert "boards must be 1..64" in capsys.readouterr().err


@pytest.mark.integration
def test_native_benchmark_cli_smoke(capsys):
    try:
        ai.default_solver()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    assert benchmark.main(["--boards", "1", "--seed", "17", "--samples", "1"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["solver_available"] is True
    assert report["config"]["budget_ms"] == 0
    assert report["policies"]["sampled_dds"]["solver_error_actions"] == 0
    assert report["policies"]["sampled_dds"]["modes"]["sampled_dds"] > 0
    replay = benchmark.run_benchmark(boards=1, seed=17, samples=1)
    assert report["comparison"] == replay["comparison"]
    assert [leg["action_digest"] for leg in report["pairs"][0]["legs"]] == [
        leg["action_digest"] for leg in replay["pairs"][0]["legs"]
    ]


def test_lambda_friendly_defaults(monkeypatch):
    for variable in ("ROBOT_PLAY_SEED", "ROBOT_PLAY_SAMPLES", "ROBOT_PLAY_BUDGET_MS"):
        monkeypatch.delenv(variable, raising=False)
    assert ai.PlayConfig.from_env() == ai.PlayConfig(seed=0, samples=4, budget_ms=50)
