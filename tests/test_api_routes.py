"""End-to-end tests for the AutoScaleAPI routes."""

import pytest


class TestGetConfigEndpoint:
    """Regression tests for issue #14: GET /resource/*/config returned 400."""

    def test_get_config_with_query_string(self, client, pct):
        response = client.get("/resource/lxc/config?lxc_id=104")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "success"
        assert payload["data"]["cores"] == 2
        assert payload["data"]["memory_mb"] == 2048
        assert payload["data"]["lxc_id"] == 104

    def test_deprecated_vm_path_and_key_still_work(self, client, pct):
        response = client.get("/resource/vm/config?vm_id=104")
        assert response.status_code == 200
        assert response.get_json()["data"]["cores"] == 2

    @pytest.mark.parametrize(
        "url",
        [
            "/resource/lxc/config?lxc_id=104",
            "/resource/lxc/config?vm_id=104",
            "/resource/vm/config?lxc_id=104",
            "/resource/vm/config?vm_id=104",
        ],
    )
    def test_all_path_and_key_combinations(self, client, pct, url):
        assert client.get(url).status_code == 200

    def test_missing_id_returns_structured_error(self, client, pct):
        response = client.get("/resource/lxc/config")
        assert response.status_code == 400
        payload = response.get_json()
        assert payload["status"] == "error"
        assert any("vm_id" in err for err in payload["errors"])

    @pytest.mark.parametrize("bad_id", ["abc", "99", "1000000", ""])
    def test_invalid_id_rejected(self, client, pct, bad_id):
        response = client.get(f"/resource/lxc/config?lxc_id={bad_id}")
        assert response.status_code == 400


class TestStatusEndpoint:
    def test_status_via_both_paths(self, client, pct):
        for url in ("/resource/lxc/status?lxc_id=104", "/resource/vm/status?vm_id=104"):
            response = client.get(url)
            assert response.status_code == 200, url
        assert pct == [["pct", "status", "104"], ["pct", "status", "104"]]

    def test_status_requires_valid_id(self, client, pct):
        assert client.get("/resource/lxc/status?lxc_id=notanid").status_code == 400

    def test_command_failure_is_reported_as_an_error(self, client, monkeypatch):
        import resource_checking

        def boom(command):
            raise RuntimeError("Configuration file 'nodes/x/lxc/104.conf' does not exist")

        monkeypatch.setattr(resource_checking, "_run", boom)
        response = client.get("/resource/lxc/status?lxc_id=104")
        assert response.status_code == 500
        assert response.get_json()["status"] == "error"


class TestNodeAndClusterEndpoints:
    def test_node_status(self, client, pct):
        assert client.get("/resource/node/status?node_name=proxmox4").status_code == 200

    @pytest.mark.parametrize("bad_name", ["", "-bad", "no spaces allowed", "a/b"])
    def test_node_name_is_validated(self, client, pct, bad_name):
        response = client.get("/resource/node/status", query_string={"node_name": bad_name})
        assert response.status_code == 400

    def test_cluster_status(self, client, pct):
        assert client.get("/resource/cluster/status").status_code == 200


class TestScalingEndpoints:
    def test_set_cores(self, client, pct):
        response = client.post("/scale/cores", json={"lxc_id": 104, "cores": 4})
        assert response.status_code == 200
        pct.assert_ran("pct", "set", 104, "-cores", 4)

    def test_set_cores_with_legacy_key(self, client, pct):
        assert client.post("/scale/cores", json={"vm_id": 104, "cores": 4}).status_code == 200

    def test_set_ram(self, client, pct):
        response = client.post("/scale/ram", json={"lxc_id": 104, "memory": 4096})
        assert response.status_code == 200
        pct.assert_ran("pct", "set", 104, "-memory", 4096)

    @pytest.mark.parametrize(
        "payload",
        [
            {"lxc_id": 104},
            {"cores": 4},
            {"lxc_id": 104, "cores": 0},
            {"lxc_id": 104, "cores": 999},
            {"lxc_id": 104, "cores": "many"},
        ],
    )
    def test_invalid_scaling_payloads_rejected(self, client, pct, payload):
        assert client.post("/scale/cores", json=payload).status_code == 400

    def test_missing_body_does_not_crash(self, client, pct):
        """A bodyless POST must produce a validation error, not a 500."""
        response = client.post("/scale/cores")
        assert response.status_code == 400
        assert response.get_json()["status"] == "error"

    def test_malformed_json_does_not_crash(self, client, pct):
        response = client.post(
            "/scale/cores", data="{not json", content_type="application/json"
        )
        assert response.status_code == 400

    def test_storage_increase_is_validated(self, client, pct):
        assert client.post("/scale/storage/increase", json={"lxc_id": 104, "disk_size": 2}).status_code == 200
        assert client.post("/scale/storage/increase", json={"lxc_id": 104}).status_code == 400


class TestSnapshotEndpoints:
    def test_create_snapshot(self, client, pct):
        response = client.post(
            "/snapshot/create", json={"lxc_id": 104, "snapshot_name": "backup-1"}
        )
        assert response.status_code == 200
        pct.assert_ran("pct", "snapshot", 104, "backup-1")

    def test_snapshot_name_is_validated(self, client, pct):
        response = client.post(
            "/snapshot/create", json={"lxc_id": 104, "snapshot_name": "bad name; rm -rf /"}
        )
        assert response.status_code == 400

    def test_list_snapshots(self, client, pct):
        assert client.get("/snapshot/list?lxc_id=104").status_code == 200

    def test_list_snapshots_requires_id(self, client, pct):
        assert client.get("/snapshot/list").status_code == 400

    def test_rollback(self, client, pct):
        response = client.post(
            "/snapshot/rollback", json={"lxc_id": 104, "snapshot_name": "backup-1"}
        )
        assert response.status_code == 200
        pct.assert_ran("pct", "rollback", 104, "backup-1")


class TestCloneEndpoints:
    def test_create_clone(self, client, pct):
        response = client.post(
            "/clone/create",
            json={"lxc_id": 104, "new_lxc_id": 105, "new_lxc_name": "cloned_container"},
        )
        assert response.status_code == 200
        # Underscores are normalised because pct rejects them in hostnames.
        assert any(argv[:2] == ["pct", "clone"] and "cloned-container" in argv for argv in pct)
        # The temporary snapshot must be cleaned up.
        pct.assert_ran("pct", "delsnapshot", 104, "snapshot-105")

    def test_temporary_snapshot_removed_when_cloning_fails(self, client, pct):
        pct.responses = {("pct", "clone"): RuntimeError("storage full")}
        response = client.post(
            "/clone/create",
            json={"lxc_id": 104, "new_lxc_id": 105, "new_lxc_name": "clone1"},
        )
        assert response.status_code == 500
        pct.assert_ran("pct", "delsnapshot", 104, "snapshot-105")

    def test_failed_cleanup_does_not_mask_the_clone_error(self, client, pct):
        pct.responses = {
            ("pct", "clone"): RuntimeError("storage full"),
            ("pct", "delsnapshot"): RuntimeError("snapshot is locked"),
        }
        response = client.post(
            "/clone/create",
            json={"lxc_id": 104, "new_lxc_id": 105, "new_lxc_name": "clone1"},
        )
        assert response.status_code == 500
        # show_stack_traces is on in the test config, so the reported cause must
        # be the clone failure, not the cleanup failure that happened after it.
        assert "storage full" in response.get_json()["message"]

    def test_cleanup_failure_after_a_successful_clone_is_reported(self, client, pct):
        pct.responses = {("pct", "delsnapshot"): RuntimeError("snapshot is locked")}
        response = client.post(
            "/clone/create",
            json={"lxc_id": 104, "new_lxc_id": 105, "new_lxc_name": "clone1"},
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert "snapshot is locked" in payload["message"]
        assert "could not be removed" in payload["data"]

    def test_delete_clone(self, client, pct):
        """Previously raised NameError on an undefined variable."""
        response = client.delete("/clone/delete", json={"lxc_id": 105})
        assert response.status_code == 200
        assert response.get_json()["status"] == "success"


class TestOperationalEndpoints:
    def test_home_page_has_no_external_assets(self, client):
        body = client.get("/").get_data(as_text=True)
        assert client.get("/").status_code == 200
        assert "http://" not in body.split("<style>")[0] or "cdn" not in body.lower()
        assert "bootstrapcdn" not in body
        assert "jquery" not in body

    def test_health_check_reports_healthy_when_pct_works(self, client, monkeypatch):
        import health_check

        monkeypatch.setattr(health_check, "_check_pct", lambda: (True, "ok"))
        response = client.get("/health/check")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "healthy"
        assert payload["checks"]["lxc_commands"]["ok"] is True

    def test_health_check_reports_unhealthy_when_pct_is_missing(self, client, monkeypatch):
        """A health check that cannot fail is worse than none."""
        import health_check

        monkeypatch.setattr(health_check, "_check_pct", lambda: (False, "pct not found in PATH"))
        response = client.get("/health/check")
        assert response.status_code == 503
        payload = response.get_json()
        assert payload["status"] == "unhealthy"
        assert payload["checks"]["lxc_commands"]["detail"] == "pct not found in PATH"

    def test_health_check_flags_an_unconfigured_node(self, app, client, monkeypatch):
        import health_check

        monkeypatch.setattr(health_check, "_check_pct", lambda: (True, "ok"))
        monkeypatch.setitem(app.config, "LXC_NODE", None)
        response = client.get("/health/check")
        assert response.status_code == 503
        assert response.get_json()["checks"]["configuration"]["ok"] is False

    def test_metrics_endpoint_is_registered(self, client):
        response = client.get("/metrics")
        # 200 with prometheus_client installed, 501 without; never 404.
        assert response.status_code in (200, 501)

    def test_requests_are_recorded_as_metrics(self, client, pct):
        metrics = pytest.importorskip("metrics")
        if not metrics.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client is not installed")

        client.get("/resource/lxc/status?lxc_id=104")
        body = client.get("/metrics").get_data(as_text=True)
        assert "lxc_autoscale_api_requests_total" in body
        # The matched rule is used as the label, not the raw path, so the
        # container id cannot blow up metric cardinality.
        assert 'endpoint="/resource/lxc/status"' in body
        assert "104" not in body.split("lxc_autoscale_api_requests_total")[1][:400]

    def test_scaling_actions_are_recorded_as_metrics(self, client, pct):
        metrics = pytest.importorskip("metrics")
        if not metrics.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client is not installed")

        client.post("/scale/cores", json={"lxc_id": 104, "cores": 4})
        body = client.get("/metrics").get_data(as_text=True)
        assert "lxc_autoscale_scaling_actions_total" in body

    def test_routes_listing(self, client):
        response = client.get("/routes")
        assert response.status_code == 200
        urls = {entry["url"] for entry in response.get_json()}
        assert "/resource/lxc/config" in urls
        assert "/resource/vm/config" in urls
        assert "/metrics" in urls


class TestAuthentication:
    def test_disabled_by_default(self, client, pct):
        assert client.get("/resource/lxc/status?lxc_id=104").status_code == 200

    def test_rejects_missing_key_when_enabled(self, app, client, pct):
        app.config["AUTHENTICATION"] = {"enabled": True, "api_keys": ["s3cret"]}
        assert client.get("/resource/lxc/status?lxc_id=104").status_code == 401

    def test_rejects_wrong_key(self, app, client, pct):
        app.config["AUTHENTICATION"] = {"enabled": True, "api_keys": ["s3cret"]}
        response = client.get(
            "/resource/lxc/status?lxc_id=104", headers={"X-API-Key": "nope"}
        )
        assert response.status_code == 403

    def test_accepts_valid_key(self, app, client, pct):
        app.config["AUTHENTICATION"] = {"enabled": True, "api_keys": ["s3cret"]}
        response = client.get(
            "/resource/lxc/status?lxc_id=104", headers={"X-API-Key": "s3cret"}
        )
        assert response.status_code == 200


class TestRateLimiting:
    def test_localhost_is_exempt(self, client, pct):
        for _ in range(10):
            assert client.get("/resource/lxc/status?lxc_id=104").status_code == 200

    def test_remote_clients_are_limited(self, client, pct):
        remote = {"REMOTE_ADDR": "10.0.0.9"}
        statuses = [
            client.get("/resource/lxc/status?lxc_id=104", environ_base=remote).status_code
            for _ in range(5)
        ]
        assert statuses[:3] == [200, 200, 200]
        assert statuses[3:] == [429, 429]

    def test_rate_limited_response_carries_retry_after(self, client, pct):
        remote = {"REMOTE_ADDR": "10.0.0.10"}
        for _ in range(3):
            client.get("/resource/lxc/status?lxc_id=104", environ_base=remote)
        response = client.get("/resource/lxc/status?lxc_id=104", environ_base=remote)
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0
