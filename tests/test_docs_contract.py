"""The documentation must describe the software that exists.

Before v1.3.0 the docs described API-key authentication and a /metrics endpoint
that were never wired up, metric names that appear nowhere in the code, eight
monitor settings that no configuration file has, and a `gunicorn` section the
systemd unit ignored. These tests fail when the docs and the code drift apart
again.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = sorted(
    p for p in ROOT.rglob("*.md")
    if "node_modules" not in str(p) and ".vitepress" not in str(p)
)


@pytest.fixture(scope="module")
def flask_app():
    import config as api_config

    original = api_config.load_config
    api_config.load_config = lambda *a, **kw: {
        "lxc": {"node": "proxmox", "timeout_seconds": 10},
        "logging": {},
        "error_handling": {},
    }
    try:
        import lxc_autoscale_api
        yield lxc_autoscale_api.app
    finally:
        api_config.load_config = original


@pytest.fixture(scope="module")
def real_routes(flask_app):
    return {
        str(rule) for rule in flask_app.url_map.iter_rules()
        if not str(rule).startswith("/static")
    }


class TestEndpoints:
    ENDPOINT = re.compile(
        r"/(?:scale|snapshot|clone|resource|health|metrics|routes)(?:/[a-z_]+)*"
    )

    def test_documented_endpoints_exist(self, real_routes):
        documented = set()
        for doc in DOCS:
            if doc.name == "CHANGELOG.md":
                continue  # history may mention paths that have since changed
            text = doc.read_text()
            for match in self.ENDPOINT.finditer(text):
                path = match.group()
                # `/resource/lxc/*` names a family of routes in prose, not a
                # route. Checked here rather than with a lookahead, which the
                # engine satisfies by backtracking off the last character.
                if text[match.end():match.end() + 2] in ("/*", "*"):
                    continue
                # Bare prefixes like `/resource` also appear in prose.
                if path.count("/") >= 2 or path in ("/metrics", "/routes"):
                    documented.add(path)
        unknown = sorted(documented - real_routes)
        assert not unknown, f"documented endpoints that do not exist: {unknown}"

    def test_every_route_is_documented(self, real_routes):
        """Compared as whole strings: with a substring check, `/scale/core`
        would look documented because `/scale/cores` is present."""
        reference = (ROOT / "docs/reference/api-endpoints.md").read_text()
        documented = set(self.ENDPOINT.findall(reference))
        undocumented = sorted(
            route for route in real_routes
            if route != "/" and route not in documented
        )
        assert not undocumented, (
            f"routes missing from the API reference: {undocumented}"
        )


class TestMetricNames:
    def test_documented_metrics_exist(self):
        source = (ROOT / "lxc_autoscale_ml/api/metrics.py").read_text()
        declared = set(re.findall(r"'(lxc_autoscale_[a-z_]+)'", source))
        assert declared, "no metrics found in metrics.py"

        reference = (ROOT / "docs/reference/metrics.md").read_text()
        mentioned = set(re.findall(r"\b(lxc_autoscale_[a-z_]+)\b", reference))

        # Prometheus appends _total/_bucket/_sum/_count to the base names.
        def base(name):
            for suffix in ("_total", "_bucket", "_sum", "_count", "_created"):
                if name.endswith(suffix):
                    return name[: -len(suffix)]
            return name

        unknown = sorted(
            name for name in mentioned
            if base(name) not in declared and name not in declared
        )
        assert not unknown, (
            f"metrics.md documents metrics that metrics.py does not declare: {unknown}"
        )

    def test_no_stale_metric_prefix(self):
        """The old docs used `lxc_` where the code uses `lxc_autoscale_`."""
        for doc in DOCS:
            if doc.name == "CHANGELOG.md":
                continue
            text = doc.read_text()
            stale = re.findall(r"\blxc_(?!autoscale|monitor|metrics)[a-z_]*(?:_total|_state)\b", text)
            assert not stale, f"{doc.name} uses stale metric names: {set(stale)}"


class TestServiceNames:
    UNITS = {"lxc_autoscale_api", "lxc_autoscale_ml", "lxc_monitor"}

    def test_documented_units_exist(self):
        shipped = {p.stem for p in (ROOT / "lxc_autoscale_ml").rglob("*.service")}
        assert shipped == self.UNITS

        mentioned = set()
        for doc in DOCS:
            mentioned |= set(re.findall(r"systemctl \w+ ([a-z_]+)\.service", doc.read_text()))
            mentioned |= set(re.findall(r"journalctl -u ([a-z_]+)", doc.read_text()))
        unknown = sorted(mentioned - self.UNITS)
        assert not unknown, f"docs reference services that do not exist: {unknown}"


class TestPythonVersionIsConsistent:
    """The docs must state whatever range CI actually tests.

    Derived from the matrix rather than pinned to specific versions, so raising
    the floor or the ceiling does not require editing this test -- it requires
    editing the docs, which is the point.
    """

    DOCS_STATING_THE_RANGE = [
        "README.md", "docs/guide/requirements.md", "docs/index.md",
    ]

    def matrix_versions(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        matrix = re.search(r"python-version:\s*\[([^\]]+)\]", ci)
        assert matrix, "could not find the python-version matrix in ci.yml"
        versions = re.findall(r"3\.\d+", matrix.group(1))
        assert versions, "the python-version matrix is empty"
        return versions

    def test_docs_state_the_tested_range(self):
        versions = self.matrix_versions()
        floor, ceiling = versions[0], versions[-1]

        for path in self.DOCS_STATING_THE_RANGE:
            text = (ROOT / path).read_text()
            assert floor in text and ceiling in text, (
                f"CI tests Python {floor} to {ceiling}, but {path} does not "
                f"state that range"
            )
            assert "Python 3.x" not in text, f"{path} still says 'Python 3.x'"

    def test_requirements_agree_with_the_matrix(self):
        """The stated floor has to be installable, not aspirational."""
        stated = (ROOT / "requirements.txt").read_text()
        floor, ceiling = self.matrix_versions()[0], self.matrix_versions()[-1]
        assert f"{floor}-{ceiling}" in stated, (
            f"requirements.txt should record the supported range "
            f"({floor}-{ceiling}) so it is visible where the pins are"
        )


class TestNoMarketingClaims:
    """Unverifiable superlatives and invented benchmarks."""

    BANNED = [
        r"\b10x\b", r"\benterprise[- ]grade\b", r"\bEnterprise Security\b",
        r"\bproduction[- ]ready\b", r"\bblazing\b", r"\bworld[- ]class\b",
        r"\bzero downtime\b", r"\bhigh accuracy\b", r"\bseamless\b",
    ]

    @pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
    def test_doc_is_free_of_claims(self, doc):
        if doc.name == "CHANGELOG.md":
            pytest.skip("historical entries are left as written")
        text = doc.read_text()
        found = [p for p in self.BANNED if re.search(p, text, re.I)]
        assert not found, f"{doc.name} contains unverifiable claims: {found}"


class TestNoEmoji:
    EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-➿⬀-⯿]")

    @pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
    def test_doc_is_free_of_emoji(self, doc):
        found = self.EMOJI.findall(doc.read_text())
        assert not found, f"{doc.name} contains emoji: {sorted(set(found))}"
