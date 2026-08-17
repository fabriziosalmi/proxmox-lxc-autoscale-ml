"""Tests for the ML side: data preparation, prediction and the scaling loop."""
import json
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from data_manager import load_data, preprocess_data
from model import DECISION_SCORE_SCALE, predict_anomalies, score_to_confidence, train_anomaly_models


BASE_CONFIG = {
    "api": {"api_url": "http://127.0.0.1:5000"},
    "spike_detection": {"spike_threshold": 2, "rolling_window": 3},
    "model": {"contamination": 0.05, "n_estimators": 20, "max_samples": 8, "random_state": 42},
    "scaling": {
        "min_cpu_cores": 1, "max_cpu_cores": 8,
        "min_ram_mb": 512, "max_ram_mb": 16384,
        "cpu_scale_up_threshold": 75, "cpu_scale_down_threshold": 30,
        "ram_scale_up_threshold": 75, "ram_scale_down_threshold": 30,
        "cpu_scale_step": 1, "ram_scale_step_mb": 512,
    },
}


def make_snapshot(container_ids, index, cycles=8, **overrides):
    """One collection cycle.

    Timestamps are anchored to *now* rather than a fixed date: the model
    refuses to scale on metrics older than `max_metrics_age_seconds`, so a
    fixture pinned to 2026-01-01 exercises the staleness path instead of the
    scaling path.
    """
    stamp = datetime.now() - timedelta(seconds=60 * (cycles - 1 - index))
    snapshot = {}
    for container_id in container_ids:
        metrics = {
            "timestamp": stamp.isoformat(),
            "cpu_usage_percent": 40.0 + index,
            "memory_usage_mb": 900.0 + index * 10,
            "swap_usage_mb": 0,
            "swap_total_mb": 0,
            "process_count": 20 + index,
            "io_stats": {"reads": 100 * index, "writes": 50 * index},
            "network_usage": {"rx_bytes": 1000 * index, "tx_bytes": 500 * index},
            "filesystem_usage_gb": 2.0,
            "filesystem_total_gb": 8.0,
            "filesystem_free_gb": 6.0,
        }
        metrics.update(overrides)
        snapshot[container_id] = metrics
    snapshot["summary"] = {"total_containers": len(container_ids)}
    return snapshot


@pytest.fixture
def metrics_file(tmp_path):
    def _write(container_ids=("104", "105"), cycles=8, **overrides):
        path = tmp_path / "lxc_metrics.json"
        data = [make_snapshot(container_ids, i, cycles=cycles, **overrides)
                for i in range(cycles)]
        path.write_text(json.dumps(data))
        return str(path)
    return _write


class TestLoadData:
    def test_container_ids_stay_strings(self, metrics_file):
        """The scaling loop matches on these; a silent int/str mismatch
        matched no rows and raised IndexError on the first container.

        Asserts the contract -- the values are strings and selecting by a
        string id matches rows -- rather than the dtype. pandas 3 gives a
        string column `StringDtype` instead of `object`, which changes the
        dtype without changing any behaviour this code depends on.
        """
        df = load_data(metrics_file())
        assert set(df["container_id"]) == {"104", "105"}
        assert all(isinstance(v, str) for v in df["container_id"])
        assert [str(c) for c in df["container_id"].unique()] == ["104", "105"]
        # The selection the scaling loop performs.
        assert not df[df["container_id"] == "104"].empty

    def test_summary_entry_is_skipped(self, metrics_file):
        df = load_data(metrics_file())
        assert "summary" not in set(df["container_id"])

    def test_missing_file_returns_none(self, tmp_path):
        assert load_data(str(tmp_path / "nope.json")) is None

    def test_malformed_json_returns_none(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json")
        assert load_data(str(path)) is None


class TestPreprocessing:
    def test_produces_the_engineered_features(self, metrics_file):
        df = preprocess_data(load_data(metrics_file()), BASE_CONFIG)
        for column in ["cpu_per_process", "memory_per_process", "cpu_memory_ratio",
                       "rolling_mean_cpu", "cpu_trend", "max_cpu", "time_diff"]:
            assert column in df.columns

    def test_zero_process_count_does_not_produce_inf(self, metrics_file):
        """A failed `pct exec` reports 0 processes; dividing by it used to make
        inf, which StandardScaler turns into NaN and IsolationForest rejects."""
        df = preprocess_data(load_data(metrics_file(process_count=0)), BASE_CONFIG)
        assert np.isfinite(df.select_dtypes(include=[np.number]).to_numpy()).all()

    def test_zero_memory_does_not_produce_inf(self, metrics_file):
        df = preprocess_data(load_data(metrics_file(memory_usage_mb=0.0)), BASE_CONFIG)
        assert np.isfinite(df.select_dtypes(include=[np.number]).to_numpy()).all()

    def test_single_sample_group_does_not_abort_preprocessing(self, metrics_file):
        """np.polyfit raises on one point; that used to return a
        half-transformed frame to the caller."""
        df = preprocess_data(load_data(metrics_file(cycles=1)), BASE_CONFIG)
        assert df is not None
        assert "cpu_trend" in df.columns
        assert (df["cpu_trend"] == 0).all()

    def test_rolling_window_is_read_from_spike_detection(self, metrics_file):
        """The key is nested there in the shipped config; a top-level lookup
        silently fell back to the default."""
        df = load_data(metrics_file(cycles=6))
        wide = preprocess_data(df.copy(), {**BASE_CONFIG, "spike_detection": {"rolling_window": 6}})
        narrow = preprocess_data(df.copy(), {**BASE_CONFIG, "spike_detection": {"rolling_window": 2}})
        assert not wide["rolling_mean_cpu"].equals(narrow["rolling_mean_cpu"])

    def test_no_pandas_chained_assignment_warnings(self, metrics_file, recwarn):
        preprocess_data(load_data(metrics_file()), BASE_CONFIG)
        chained = [w for w in recwarn if "chained assignment" in str(w.message).lower()]
        assert chained == []


class TestConfidence:
    def test_is_bounded_to_a_percentage(self):
        """The old formula was (1 - score) * 100: roughly 50-150%, so it could
        never be compared against a percentage threshold."""
        for score in [-10, -0.5, -0.1, 0, 0.1, 0.5, 10]:
            assert 0.0 <= score_to_confidence(score) <= 100.0

    def test_boundary_scores_are_zero_confidence(self):
        assert score_to_confidence(0.0) == 0.0

    def test_confidence_grows_with_distance_from_the_boundary(self):
        assert score_to_confidence(0.1) < score_to_confidence(0.3) < score_to_confidence(0.5)

    def test_is_symmetric_around_the_boundary(self):
        assert score_to_confidence(-0.2) == score_to_confidence(0.2)

    def test_saturates_at_the_scale(self):
        assert score_to_confidence(DECISION_SCORE_SCALE) == 100.0
        assert score_to_confidence(DECISION_SCORE_SCALE * 5) == 100.0


class TestTrainAndPredict:
    def test_round_trip(self, metrics_file):
        df = preprocess_data(load_data(metrics_file()), BASE_CONFIG)
        model, features = train_anomaly_models(df, BASE_CONFIG)
        assert model is not None

        latest = df[df["container_id"] == "104"].iloc[-1]
        prediction, confidence = predict_anomalies(model, latest, features, BASE_CONFIG)
        assert prediction in (-1, 1)
        assert 0.0 <= confidence <= 100.0


class TestRunCycle:
    """The scaling loop, with the API and the clock stubbed out."""

    @pytest.fixture
    def orchestrator(self, monkeypatch, metrics_file):
        import lxc_autoscale_ml as orch

        applied = []
        monkeypatch.setattr(
            orch, "apply_scaling",
            lambda cid, cores, ram, config: applied.append((cid, cores, ram)))
        monkeypatch.setattr(
            orch, "fetch_container_configs_sync",
            lambda ids, url, **kw: {cid: {"cores": 2, "memory_mb": 1024} for cid in ids})
        orch.applied = applied
        return orch

    def test_a_full_cycle_completes(self, orchestrator, metrics_file, caplog):
        """Regression: the int/str container id mismatch made every cycle die
        on the first container with IndexError."""
        config = {**BASE_CONFIG, "data_file": metrics_file()}
        with caplog.at_level(logging.WARNING):
            assert orchestrator.run_cycle(config) is True
        assert "IndexError" not in caplog.text
        assert "single positional indexer" not in caplog.text
        # Every container must actually resolve to its metrics rows. A silent
        # id-type mismatch shows up here as "No metrics rows" for all of them.
        assert "No metrics rows" not in caplog.text

    def test_every_container_is_evaluated(self, orchestrator, metrics_file, monkeypatch):
        """Each container id must match rows in the frame it came from."""
        evaluated = []
        real_evaluate = orchestrator.evaluate_container

        def record(container_id, **kwargs):
            assert not kwargs["df"][kwargs["df"]["container_id"] == container_id].empty, (
                f"container {container_id!r} matched no rows: the id types have drifted apart"
            )
            evaluated.append(container_id)
            return real_evaluate(container_id=container_id, **kwargs)

        monkeypatch.setattr(orchestrator, "evaluate_container", record)
        config = {**BASE_CONFIG, "data_file": metrics_file()}
        orchestrator.run_cycle(config)
        assert evaluated == ["104", "105"]

    def test_missing_metrics_file_skips_the_cycle_without_raising(self, orchestrator, tmp_path):
        config = {**BASE_CONFIG, "data_file": str(tmp_path / "absent.json")}
        assert orchestrator.run_cycle(config) is False

    def test_dry_run_applies_nothing(self, orchestrator, metrics_file):
        """dry_run shipped in the default config and was never read."""
        config = {
            **BASE_CONFIG,
            "data_file": metrics_file(cpu_usage_percent=99.0),
            "scaling": {**BASE_CONFIG["scaling"], "dry_run": True},
        }
        orchestrator.run_cycle(config)
        assert orchestrator.applied == []

    def test_scaling_is_applied_when_dry_run_is_off(self, orchestrator, metrics_file):
        config = {**BASE_CONFIG, "data_file": metrics_file(cpu_usage_percent=99.0)}
        orchestrator.run_cycle(config)
        assert orchestrator.applied != []

    def test_ignore_lxc_excludes_containers(self, orchestrator, metrics_file):
        """ignore_lxc shipped in the default config and was never read."""
        config = {
            **BASE_CONFIG,
            "data_file": metrics_file(container_ids=("104", "105"), cpu_usage_percent=99.0),
            "ignore_lxc": ["104"],
        }
        orchestrator.run_cycle(config)
        scaled = {cid for cid, _, _ in orchestrator.applied}
        assert "104" not in scaled

    def test_ignore_lxc_accepts_integers(self, orchestrator, metrics_file):
        config = {
            **BASE_CONFIG,
            "data_file": metrics_file(cpu_usage_percent=99.0),
            "ignore_lxc": [104, 105],
        }
        orchestrator.run_cycle(config)
        assert orchestrator.applied == []

    def test_min_confidence_gates_scaling(self, orchestrator, metrics_file):
        config = {
            **BASE_CONFIG,
            "data_file": metrics_file(cpu_usage_percent=99.0),
            "scaling": {**BASE_CONFIG["scaling"], "min_confidence": 101},
        }
        orchestrator.run_cycle(config)
        assert orchestrator.applied == []

    def test_min_confidence_defaults_to_no_gating(self, orchestrator, metrics_file):
        config = {**BASE_CONFIG, "data_file": metrics_file(cpu_usage_percent=99.0)}
        orchestrator.run_cycle(config)
        assert orchestrator.applied != []

    def test_one_failing_container_does_not_abandon_the_rest(
            self, orchestrator, metrics_file, monkeypatch):
        calls = []
        real_evaluate = orchestrator.evaluate_container

        def flaky(container_id, **kwargs):
            calls.append(container_id)
            if container_id == "104":
                raise RuntimeError("boom")
            return real_evaluate(container_id=container_id, **kwargs)

        monkeypatch.setattr(orchestrator, "evaluate_container", flaky)
        config = {**BASE_CONFIG, "data_file": metrics_file(cpu_usage_percent=99.0)}
        assert orchestrator.run_cycle(config) is True
        assert set(calls) == {"104", "105"}


class TestCircuitBreakerConfig:
    def test_reads_the_configured_thresholds(self):
        import lxc_autoscale_ml as orch

        breaker = orch.build_circuit_breaker(
            {"circuit_breaker": {"failure_threshold": 7, "timeout_seconds": 42}})
        assert breaker.failure_threshold == 7
        assert breaker.timeout == 42

    def test_can_be_disabled(self):
        import lxc_autoscale_ml as orch

        assert orch.build_circuit_breaker({"circuit_breaker": {"enabled": False}}) is None

    def test_defaults_when_unconfigured(self):
        import lxc_autoscale_ml as orch

        breaker = orch.build_circuit_breaker({})
        assert breaker.failure_threshold == 3
        assert breaker.timeout == 300


class TestScalingDecisions:
    def test_scale_up_moves_one_step(self):
        from scaling_decisions import determine_scaling_action

        metrics = pd.Series({
            "cpu_usage_percent": 99.0, "memory_usage_mb": 15000.0,
            "current_cores": 4, "current_ram_mb": 8192,
        })
        cpu_action, ram_action, new_cores, new_ram = determine_scaling_action(
            metrics, -1, 90.0, BASE_CONFIG)
        assert (cpu_action, new_cores) == ("Scale Up", 5)
        assert (ram_action, new_ram) == ("Scale Up", 8704)

    def test_scale_down_moves_one_step(self):
        from scaling_decisions import determine_scaling_action

        metrics = pd.Series({
            "cpu_usage_percent": 1.0, "memory_usage_mb": 10.0,
            "current_cores": 4, "current_ram_mb": 8192,
        })
        cpu_action, ram_action, new_cores, new_ram = determine_scaling_action(
            metrics, 1, 90.0, BASE_CONFIG)
        assert (cpu_action, new_cores) == ("Scale Down", 3)
        assert (ram_action, new_ram) == ("Scale Down", 7680)

    def test_scale_up_is_capped_at_the_maximum(self):
        from scaling_decisions import determine_scaling_action

        metrics = pd.Series({
            "cpu_usage_percent": 99.0, "memory_usage_mb": 15000.0,
            "current_cores": 7, "current_ram_mb": 16000,
        })
        cpu_action, ram_action, new_cores, new_ram = determine_scaling_action(
            metrics, -1, 90.0, BASE_CONFIG)
        assert new_cores == BASE_CONFIG["scaling"]["max_cpu_cores"]
        assert new_ram == BASE_CONFIG["scaling"]["max_ram_mb"]

    def test_a_container_already_at_the_ceiling_reports_no_action(self):
        """It used to report "Scale Up" with new_cores == current_cores, so the
        loop issued a no-op root `pct set` every interval and the scaling
        counter stopped meaning anything."""
        from scaling_decisions import determine_scaling_action

        metrics = pd.Series({
            "cpu_usage_percent": 99.0, "memory_usage_mb": 15000.0,
            "current_cores": BASE_CONFIG["scaling"]["max_cpu_cores"],
            "current_ram_mb": BASE_CONFIG["scaling"]["max_ram_mb"],
        })
        cpu_action, ram_action, new_cores, new_ram = determine_scaling_action(
            metrics, -1, 90.0, BASE_CONFIG)
        assert (cpu_action, new_cores) == ("No Scaling", None)
        assert (ram_action, new_ram) == ("No Scaling", None)

    def test_a_container_already_at_the_floor_reports_no_action(self):
        from scaling_decisions import determine_scaling_action

        metrics = pd.Series({
            "cpu_usage_percent": 1.0, "memory_usage_mb": 10.0,
            "current_cores": BASE_CONFIG["scaling"]["min_cpu_cores"],
            "current_ram_mb": BASE_CONFIG["scaling"]["min_ram_mb"],
        })
        cpu_action, ram_action, new_cores, new_ram = determine_scaling_action(
            metrics, 1, 90.0, BASE_CONFIG)
        assert (cpu_action, new_cores) == ("No Scaling", None)
        assert (ram_action, new_ram) == ("No Scaling", None)

    def test_zero_ram_allocation_does_not_divide_by_zero(self):
        from scaling_decisions import determine_scaling_action

        metrics = pd.Series({
            "cpu_usage_percent": 50.0, "memory_usage_mb": 100.0,
            "current_cores": 2, "current_ram_mb": 0,
        })
        cpu_action, ram_action, _, _ = determine_scaling_action(
            metrics, 1, 90.0, BASE_CONFIG)
        assert ram_action in ("Scale Up", "Scale Down", "No Scaling")


class TestScalingDirectionEndToEnd:
    """The regression that two repair rounds walked past.

    `preprocess_data` used to standard-scale `cpu_usage_percent` and
    `memory_usage_mb`, which `determine_scaling_action` then compared against
    percentage thresholds. A z-score never exceeds 75 and is almost always
    below 30, so every container was scaled DOWN on both axes every cycle: a
    container at 99% CPU produced the same decision as one at 3%.

    The existing tests asserted only that *something* was applied. These assert
    the direction and the target value, driving the real pipeline from the
    metrics file all the way to the call `apply_scaling` would make.
    """

    @pytest.fixture
    def cycle(self, monkeypatch, tmp_path):
        import lxc_autoscale_ml as orch

        applied = []
        monkeypatch.setattr(
            orch, "apply_scaling",
            lambda cid, cores, ram, config: applied.append((cid, cores, ram)))
        monkeypatch.setattr(
            orch, "fetch_container_configs_sync",
            lambda ids, url, **kw: {cid: {"cores": 4, "memory_mb": 8192} for cid in ids})

        def _run(cpu_series, mem_series, **config_overrides):
            cycles = len(cpu_series)
            data = []
            for i, (cpu, mem) in enumerate(zip(cpu_series, mem_series, strict=True)):
                snap = make_snapshot(("104",), i, cycles=cycles,
                                     cpu_usage_percent=cpu, memory_usage_mb=mem)
                data.append(snap)
            path = tmp_path / "metrics.json"
            path.write_text(json.dumps(data))
            config = {**BASE_CONFIG, "data_file": str(path), **config_overrides}
            applied.clear()
            orch.run_cycle(config)
            return list(applied)

        return _run

    def test_a_saturated_container_scales_up(self, cycle):
        # 8192 MB allocated, ~7900 MB used -> 96%.
        applied = cycle([92, 95, 97, 99, 93, 96, 98, 99],
                        [7600, 7700, 7800, 7900, 7650, 7750, 7850, 7900])
        assert applied == [("104", 5, 8704)], (
            "a container at 99% CPU and 96% RAM must gain a step of each"
        )

    def test_an_idle_container_scales_down(self, cycle):
        applied = cycle([4, 6, 5, 7, 3, 5, 6, 5],
                        [900, 1000, 950, 1050, 880, 940, 1000, 980])
        assert applied == [("104", 3, 7680)]

    def test_a_steady_container_is_left_alone(self, cycle):
        applied = cycle([48, 52, 50, 49, 51, 50, 52, 50],
                        [4000, 4100, 4050, 4090, 4020, 4060, 4100, 4096])
        assert applied == []

    def test_busy_and_idle_do_not_produce_the_same_decision(self, cycle):
        """The single clearest symptom of the inversion."""
        busy = cycle([92, 95, 97, 99, 93, 96, 98, 99],
                     [7600, 7700, 7800, 7900, 7650, 7750, 7850, 7900])
        idle = cycle([4, 6, 5, 7, 3, 5, 6, 5],
                     [900, 1000, 950, 1050, 880, 940, 1000, 980])
        assert busy != idle, "load has no effect on the scaling decision"

    def test_thresholds_see_real_units(self, metrics_file):
        """Guards the root cause directly rather than its symptom."""
        df = preprocess_data(load_data(metrics_file(cpu_usage_percent=99.0,
                                                    memory_usage_mb=7900.0)),
                             BASE_CONFIG)
        latest = df[df["container_id"] == "104"].iloc[-1]
        assert latest["cpu_usage_percent"] == pytest.approx(99.0), (
            "cpu_usage_percent must reach the thresholds as a percentage, "
            "not as a standardised score"
        )
        assert latest["memory_usage_mb"] == pytest.approx(7900.0)


class TestUnknownAllocationIsNotGuessed:
    """A failed config fetch used to substitute the configured minimum as the
    container's *current* size, then compute an absolute target from that
    fiction. One cycle collapsed the container to the floor, and the write was
    self-masking because the next fetch reported the value just imposed."""

    @pytest.fixture
    def cycle(self, monkeypatch, tmp_path, metrics_file):
        import lxc_autoscale_ml as orch

        applied = []
        monkeypatch.setattr(
            orch, "apply_scaling",
            lambda cid, cores, ram, config: applied.append((cid, cores, ram)))

        def _run(fetch_result):
            monkeypatch.setattr(orch, "fetch_container_configs_sync",
                                lambda ids, url, **kw: {cid: fetch_result for cid in ids})
            config = {**BASE_CONFIG, "data_file": metrics_file(cpu_usage_percent=99.0)}
            applied.clear()
            orch.run_cycle(config)
            return list(applied)

        return _run

    def test_no_response_skips_the_container(self, cycle):
        assert cycle(None) == []

    def test_empty_response_skips_the_container(self, cycle):
        assert cycle({}) == []

    def test_missing_cores_skips_the_container(self, cycle):
        """`cores` is optional in Proxmox; unset means all host cores."""
        assert cycle({"memory_mb": 8192}) == []

    def test_missing_memory_skips_the_container(self, cycle):
        assert cycle({"cores": 4}) == []

    def test_a_complete_response_is_used(self, cycle):
        # CPU is pinned at 99% and memory sits near 970 MB of the 8192 MB
        # allocation (~12%), so the correct answer is up on CPU, down on RAM.
        assert cycle({"cores": 4, "memory_mb": 8192}) == [
            ("104", 5, 7680), ("105", 5, 7680)]


class TestStaleAndDepartedContainers:
    @pytest.fixture
    def orchestrator(self, monkeypatch):
        import lxc_autoscale_ml as orch

        applied = []
        monkeypatch.setattr(
            orch, "apply_scaling",
            lambda cid, cores, ram, config: applied.append((cid, cores, ram)))
        monkeypatch.setattr(
            orch, "fetch_container_configs_sync",
            lambda ids, url, **kw: {cid: {"cores": 4, "memory_mb": 8192} for cid in ids})
        orch.applied = applied
        return orch

    def test_only_containers_in_the_newest_snapshot_are_evaluated(
            self, orchestrator, tmp_path):
        """The monitor records only running containers, but the file keeps
        1000 cycles of history. A container stopped hours ago used to be
        evaluated every cycle -- and with VMID reuse, a new container could be
        scaled on its predecessor's metrics."""
        data = [make_snapshot(("104", "105"), i, cycles=8) for i in range(6)]
        data += [make_snapshot(("104",), i, cycles=8) for i in (6, 7)]  # 105 stopped
        path = tmp_path / "metrics.json"
        path.write_text(json.dumps(data))

        config = {**BASE_CONFIG, "data_file": str(path)}
        seen = []
        real = orchestrator.evaluate_container
        orchestrator.evaluate_container = lambda container_id, **kw: (
            seen.append(container_id), real(container_id=container_id, **kw))[1]
        try:
            orchestrator.run_cycle(config)
        finally:
            orchestrator.evaluate_container = real
        assert seen == ["104"], "a departed container must not be evaluated"

    def test_stale_metrics_stop_the_cycle(self, orchestrator, tmp_path):
        """A wedged monitor used to leave the model scaling on a frozen
        snapshot forever, ratcheting every container toward a limit."""
        old = datetime.now() - timedelta(hours=6)
        data = []
        for i in range(8):
            snap = make_snapshot(("104",), i, cycles=8)
            snap["104"]["timestamp"] = (old + timedelta(seconds=60 * i)).isoformat()
            data.append(snap)
        path = tmp_path / "metrics.json"
        path.write_text(json.dumps(data))

        config = {**BASE_CONFIG, "data_file": str(path)}
        assert orchestrator.run_cycle(config) is False
        assert orchestrator.applied == []

    def test_fresh_metrics_are_accepted(self, orchestrator, tmp_path):
        data = [make_snapshot(("104",), i, cycles=8, cpu_usage_percent=99.0)
                for i in range(8)]
        path = tmp_path / "metrics.json"
        path.write_text(json.dumps(data))
        config = {**BASE_CONFIG, "data_file": str(path)}
        assert orchestrator.run_cycle(config) is True
