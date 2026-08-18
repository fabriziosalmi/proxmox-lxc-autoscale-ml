"""Security properties of the API.

Everything here protects a daemon that runs as root on a Proxmox hypervisor and
executes `pct`. Each test names the exposure it closes.
"""

import pytest

REMOTE = {"REMOTE_ADDR": "192.168.1.50"}

MUTATING_ROUTES = [
    ("POST", "/scale/cores", {"lxc_id": 104, "cores": 1}),
    ("POST", "/scale/ram", {"lxc_id": 104, "memory": 64}),
    ("POST", "/scale/storage/increase", {"lxc_id": 104, "disk_size": 1}),
    ("POST", "/snapshot/create", {"lxc_id": 104, "snapshot_name": "x"}),
    ("POST", "/snapshot/rollback", {"lxc_id": 104, "snapshot_name": "x"}),
    ("POST", "/clone/create", {"lxc_id": 104, "new_lxc_id": 105, "new_lxc_name": "c"}),
    ("DELETE", "/clone/delete", {"lxc_id": 105}),
]


class TestCrossSiteRequestForgery:
    """A cross-origin `<form method=post>` is a CORS *simple request*: no
    preflight, no JSON content type. While the parameters could come from the
    query string, any page an operator loaded could resize or destroy
    containers on an API that ships unauthenticated and bound to 0.0.0.0.
    """

    @pytest.mark.parametrize("method,path,params", MUTATING_ROUTES,
                             ids=[r[1] for r in MUTATING_ROUTES])
    def test_query_string_cannot_drive_a_mutating_route(self, client, pct, method, path, params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        response = client.open(f"{path}?{query}", method=method,
                               content_type="application/x-www-form-urlencoded",
                               data="", environ_overrides=REMOTE)
        assert response.status_code == 400, f"{method} {path} accepted query-string parameters"
        assert pct == [], f"{method} {path} executed a command: {pct.commands}"

    @pytest.mark.parametrize("method,path,params", MUTATING_ROUTES,
                             ids=[r[1] for r in MUTATING_ROUTES])
    def test_a_json_body_still_works(self, client, pct, method, path, params):
        response = client.open(path, method=method, json=params)
        assert response.status_code == 200, f"{method} {path} rejected a legitimate JSON body"

    def test_get_routes_still_accept_the_query_string(self, client, pct):
        """Issue #14: the whole point of reading the query string was GETs."""
        for url in ("/resource/lxc/config?lxc_id=104",
                    "/resource/lxc/status?lxc_id=104",
                    "/snapshot/list?lxc_id=104"):
            assert client.get(url).status_code == 200, url


class TestRouteProtection:
    """A table of what every route requires, so that deleting a decorator or
    adding an unprotected route fails CI. Authentication and rate limiting were
    previously exercised on exactly one route between them."""

    # route -> (requires_api_key, rate_limited)
    EXPECTED = {
        "/": (False, False),
        "/health/check": (False, True),
        "/metrics": (False, False),
        "/routes": (True, True),
        "/scale/cores": (True, True),
        "/scale/ram": (True, True),
        "/scale/storage/increase": (True, True),
        "/snapshot/create": (True, True),
        "/snapshot/list": (True, True),
        "/snapshot/rollback": (True, True),
        "/clone/create": (True, True),
        "/clone/delete": (True, True),
        "/resource/lxc/status": (True, True),
        "/resource/vm/status": (True, True),
        "/resource/lxc/config": (True, True),
        "/resource/vm/config": (True, True),
        "/resource/node/status": (True, True),
        "/resource/cluster/status": (True, True),
    }

    def test_every_route_has_a_declared_expectation(self, app):
        actual = {str(r) for r in app.url_map.iter_rules()
                  if not str(r).startswith("/static")}
        assert actual == set(self.EXPECTED), (
            "a route was added or removed without declaring its protection here"
        )

    @pytest.mark.parametrize("route", sorted(r for r, (_, limited) in EXPECTED.items() if limited))
    def test_declared_rate_limiting_is_actually_applied(self, app, client, pct, route):
        """Behavioural, not introspective: @wraps hides the decorator names, and
        what matters is that a remote caller is actually throttled."""
        rule = next(r for r in app.url_map.iter_rules() if str(r) == route)
        method = next(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
        remote = {"REMOTE_ADDR": "10.9.9.9"}
        codes = [client.open(route, method=method, json={}, environ_overrides=remote).status_code
                 for _ in range(5)]
        assert 429 in codes, f"{route} is not rate limited (saw {codes})"

    @pytest.mark.parametrize("route", sorted(r for r, (_, limited) in EXPECTED.items() if not limited))
    def test_unlimited_routes_stay_unlimited(self, app, client, pct, route):
        remote = {"REMOTE_ADDR": "10.9.9.8"}
        codes = [client.get(route, environ_overrides=remote).status_code for _ in range(5)]
        assert 429 not in codes, f"{route} unexpectedly throttled"

    @pytest.mark.parametrize("route", sorted(r for r, (a, _) in EXPECTED.items() if a))
    def test_protected_routes_reject_an_anonymous_caller(self, app, client, pct, route):
        """Behavioural check, independent of how the decorators are spelled."""
        app.config["AUTHENTICATION"] = {"enabled": True, "api_keys": ["s3cret"]}
        rule = next(r for r in app.url_map.iter_rules() if str(r) == route)
        method = next(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
        response = client.open(route, method=method, json={})
        assert response.status_code == 401, f"{route} served an anonymous caller"
        assert pct == []


class TestApiKeyHandling:
    def test_the_key_is_not_accepted_in_the_query_string(self, app, client, pct):
        """It used to be, which wrote the secret into the gunicorn access log,
        shell history and any intermediate proxy log."""
        app.config["AUTHENTICATION"] = {"enabled": True, "api_keys": ["s3cret"]}
        assert client.get("/resource/lxc/status?lxc_id=104&api_key=s3cret").status_code == 401

    def test_the_header_is_accepted(self, app, client, pct):
        app.config["AUTHENTICATION"] = {"enabled": True, "api_keys": ["s3cret"]}
        response = client.get("/resource/lxc/status?lxc_id=104",
                              headers={"X-API-Key": "s3cret"})
        assert response.status_code == 200

    def test_a_non_ascii_key_is_rejected_not_a_500(self, app, client, pct):
        """hmac.compare_digest raises TypeError on a non-ASCII str, so a
        configured key with a curly quote made every request 500."""
        app.config["AUTHENTICATION"] = {"enabled": True, "api_keys": ["s3cret’"]}
        response = client.get("/resource/lxc/status?lxc_id=104",
                              headers={"X-API-Key": "wrong"})
        assert response.status_code == 403

    def test_a_matching_non_ascii_key_still_authenticates(self, app, client, pct):
        app.config["AUTHENTICATION"] = {"enabled": True, "api_keys": ["s3cret’"]}
        response = client.get("/resource/lxc/status?lxc_id=104",
                              headers={"X-API-Key": "s3cret’"})
        assert response.status_code == 200


class TestArgumentInjection:
    @pytest.mark.parametrize("name", ["-f", "--force", "-rf"])
    def test_a_snapshot_name_cannot_start_a_pct_option(self, client, pct, name):
        """`pct delsnapshot 104 -foo` reads the name as an option."""
        response = client.post("/snapshot/create",
                               json={"lxc_id": 104, "snapshot_name": name})
        assert response.status_code == 400
        assert pct == []

    @pytest.mark.parametrize("name", ["backup-1", "b_2", "Snap9"])
    def test_ordinary_names_are_still_accepted(self, client, pct, name):
        assert client.post("/snapshot/create",
                           json={"lxc_id": 104, "snapshot_name": name}).status_code == 200


class TestRateLimiterState:
    def test_idle_clients_are_evicted(self, client, pct, monkeypatch):
        """The window was pruned only for the IP being served, so a scan of
        source addresses grew the table without bound."""
        import rate_limiting

        clock = [1000.0]
        monkeypatch.setattr(rate_limiting.time, "time", lambda: clock[0])
        for i in range(50):
            client.get("/resource/lxc/status?lxc_id=104",
                       environ_overrides={"REMOTE_ADDR": f"10.0.0.{i}"})
        assert len(rate_limiting.rate_limit_data) == 50

        clock[0] += 3600  # every window has expired
        client.get("/resource/lxc/status?lxc_id=104",
                   environ_overrides={"REMOTE_ADDR": "10.0.1.1"})
        assert len(rate_limiting.rate_limit_data) == 1

    def test_the_table_is_capped(self, client, pct, monkeypatch):
        import rate_limiting

        monkeypatch.setattr(rate_limiting, "MAX_TRACKED_CLIENTS", 10)
        for i in range(40):
            client.get("/resource/lxc/status?lxc_id=104",
                       environ_overrides={"REMOTE_ADDR": f"10.1.{i // 256}.{i % 256}"})
        assert len(rate_limiting.rate_limit_data) <= 11

    def test_rate_limit_headers_are_emitted_on_success(self, client, pct):
        """Every rate-limited view returns Flask's (body, status) tuple, which
        has no `.headers`, so the documented headers were unreachable."""
        response = client.get("/resource/lxc/status?lxc_id=104",
                              environ_overrides={"REMOTE_ADDR": "10.2.0.1"})
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "3"
        assert response.headers["X-RateLimit-Remaining"] == "2"
        assert int(response.headers["X-RateLimit-Reset"]) > 0

    def test_remaining_counts_down(self, client, pct):
        remote = {"REMOTE_ADDR": "10.2.0.2"}
        seen = [client.get("/resource/lxc/status?lxc_id=104", environ_overrides=remote)
                .headers["X-RateLimit-Remaining"] for _ in range(3)]
        assert seen == ["2", "1", "0"]


class TestHealthCheckExposure:
    def test_the_probe_is_cached(self, client, monkeypatch):
        """The endpoint is deliberately anonymous, so an unauthenticated caller
        could make the API fork a root `pct list` per request."""
        import health_check

        calls = []
        monkeypatch.setattr(health_check, "_check_pct",
                            lambda: (calls.append(1), (True, "ok"))[1])
        for _ in range(20):
            client.get("/health/check")
        assert len(calls) == 1

    def test_it_is_rate_limited_for_remote_callers(self, client, monkeypatch):
        import health_check

        monkeypatch.setattr(health_check, "_check_pct", lambda: (True, "ok"))
        codes = [client.get("/health/check", environ_overrides={"REMOTE_ADDR": "10.3.0.1"})
                 .status_code for _ in range(5)]
        assert 429 in codes


class TestMetricLabels:
    def test_an_unknown_method_does_not_mint_a_new_series(self, client, pct):
        """An unmatched route never reaches @rate_limit, so the method label
        was attacker-controlled at line rate."""
        metrics = pytest.importorskip("metrics")
        if not metrics.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client is not installed")
        client.open("/no/such/route", method="PROPFIND")
        body = client.get("/metrics").get_data(as_text=True)
        assert "PROPFIND" not in body
        assert 'method="other"' in body


class TestEmptyConfigSections:
    """A section written but left empty parses to None, and
    `.get(key, default)` returns that stored None rather than the default --
    which surfaced as a raw HTML 500 on every request. The gunicorn config, the
    monitor and the model loader all guarded this; the API did not."""

    @pytest.mark.parametrize("section", [
        "lxc", "rate_limiting", "authentication", "server", "logging", "error_handling",
    ])
    def test_an_empty_section_does_not_break_startup(self, section, tmp_path, monkeypatch):
        import config as api_config

        base = {
            "lxc": {"node": "pve", "timeout_seconds": 5},
            "rate_limiting": {"enabled": False},
            "authentication": {"enabled": False},
            "server": {}, "logging": {}, "error_handling": {},
        }
        base[section] = None
        app = api_config.create_app(base)
        assert app.config["TIMEOUT"] in (5, 30)

    def test_a_wholly_empty_file_is_tolerated(self, tmp_path, monkeypatch):
        import config as api_config

        path = tmp_path / "api.yaml"
        path.write_text("# nothing here\n")
        monkeypatch.setenv("LXC_AUTOSCALE_API_CONFIG", str(path))
        assert api_config.load_config() == {}


class TestScalingFailureLabels:
    def test_a_failure_carries_a_reason(self, client, pct):
        """Every failure used to be labelled reason="unknown", so the failure
        counter carried no diagnostic value."""
        metrics = pytest.importorskip("metrics")
        if not metrics.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client is not installed")

        pct.responses = {("pct", "set"): RuntimeError("container is locked")}
        client.post("/scale/cores", json={"lxc_id": 104, "cores": 8})
        body = client.get("/metrics").get_data(as_text=True)
        assert 'reason="command_failed"' in body

    def test_the_reason_label_set_is_finite(self):
        import lxc_autoscale_api as api

        reasons = {api._failure_reason((None, code))
                   for code in (200, 400, 401, 403, 404, 429, 500, 502, 503)}
        assert None in reasons
        assert len(reasons - {None}) <= 6, "the reason label must stay bounded"
