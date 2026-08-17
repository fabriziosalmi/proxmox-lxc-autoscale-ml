"""The shipped configuration files must match the code that reads them.

Eleven keys shipped in the default configs and were read by nobody -- `dry_run`
among them, so anyone rehearsing a change with it was scaling for real. These
tests fail if a key is added to a config file without code to honour it, or if
code starts reading a key the shipped file never mentions.
"""
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIGS = {
    "api": ROOT / "lxc_autoscale_ml/api/lxc_autoscale_api.yaml",
    "model": ROOT / "lxc_autoscale_ml/model/lxc_autoscale_ml.yaml",
    "monitor": ROOT / "lxc_autoscale_ml/monitor/lxc_monitor.yaml",
}
SOURCE = "\n".join(
    path.read_text() for path in (ROOT / "lxc_autoscale_ml").rglob("*.py")
)

# Keys whose consumer cannot be found by name because they are read through the
# section dict rather than individually.
READ_INDIRECTLY = {
    "error_handling.notification_recipients",
    "gunicorn.access_log_file",
    "gunicorn.error_log_file",
}


def leaf_keys(node, prefix=""):
    """Yield (dotted_path, leaf_name) for every scalar setting."""
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if isinstance(value, dict):
            yield from leaf_keys(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}", key


def is_read_by_code(leaf):
    return bool(re.search(rf"""['"]{re.escape(leaf)}['"]""", SOURCE))


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_every_shipped_key_is_read_by_code(name):
    config = yaml.safe_load(CONFIGS[name].read_text())
    unread = [
        dotted
        for dotted, leaf in leaf_keys(config)
        if dotted not in READ_INDIRECTLY and not is_read_by_code(leaf)
    ]
    assert not unread, (
        f"{CONFIGS[name].name} ships keys no code reads: {unread}. "
        f"Either honour them or take them out -- a setting that silently does "
        f"nothing is worse than an absent one."
    )


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_configs_parse(name):
    assert isinstance(yaml.safe_load(CONFIGS[name].read_text()), dict)


class TestDocumentedKeysExist:
    """Every key in the configuration reference must exist in a shipped file."""

    REFERENCE = ROOT / "docs/reference/configuration.md"

    def shipped_keys(self):
        keys = set()
        for path in CONFIGS.values():
            config = yaml.safe_load(path.read_text())
            for dotted, _ in leaf_keys(config):
                keys.add(dotted)
                keys.add(dotted.split(".")[-1])
        return keys

    def test_option_tables_reference_real_keys(self):
        text = self.REFERENCE.read_text()
        shipped = self.shipped_keys()
        # Option tables use a leading `| `key`` cell.
        documented = set(re.findall(r"^\|\s*`([a-z_]+(?:\.[a-z_]+)*)`\s*\|", text, re.M))
        # Commented-out optional settings still count as shipped.
        for path in CONFIGS.values():
            for match in re.findall(r"^\s*#\s*([a-z_]+):", path.read_text(), re.M):
                shipped.add(match)
        unknown = sorted(
            key for key in documented
            if key not in shipped and key.split(".")[-1] not in shipped
        )
        assert not unknown, (
            f"configuration.md documents settings that no shipped config has: {unknown}"
        )


class TestDocumentedYamlSnippets:
    """YAML examples anywhere in the docs must use keys that exist.

    The option tables were not enough: `isolation_forest:`, `sleep_interval:`
    and `metrics_file:` lived on in copy-paste-ready snippets long after the
    real keys had become `model:`, `interval_seconds:` and `data_file:`.
    """

    DOCS = sorted(
        p for p in (ROOT / "docs").rglob("*.md")
        if "node_modules" not in str(p) and ".vitepress" not in str(p)
    )
    # Keys belonging to other tools that legitimately appear in examples.
    FOREIGN = {
        "groups", "rules", "alert", "expr", "for", "labels", "annotations",
        "severity", "summary", "description", "scrape_configs", "job_name",
        "static_configs", "targets", "metrics_path", "scrape_interval",
        "global", "evaluation_interval", "route", "receivers", "receiver",
        "name", "url", "send_resolved", "webhook_configs", "repeat_interval",
        "group_wait", "group_interval", "apiVersion", "kind", "metadata",
        "spec", "image", "ports", "services", "volumes", "environment",
        "version", "command", "container_name", "restart", "networks",
        "healthcheck", "test", "interval", "timeout", "retries", "depends_on",
        "build", "context", "dockerfile", "entrypoint", "user", "working_dir",
    }

    def shipped(self):
        keys = set()
        for path in CONFIGS.values():
            text = path.read_text()
            config = yaml.safe_load(text)
            for dotted, leaf in leaf_keys(config):
                keys.add(dotted)
                keys.add(leaf)
            keys.update(config.keys())
            # Settings shipped commented out still count.
            keys.update(re.findall(r"^\s*#\s*([a-z_]+):", text, re.M))
        return keys

    @pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
    def test_yaml_examples_use_real_keys(self, doc):
        shipped = self.shipped() | self.FOREIGN
        unknown = set()
        for block in re.findall(r"```yaml\n(.*?)```", doc.read_text(), re.S):
            for key in re.findall(r"^\s*([a-z_][a-z0-9_]*):", block, re.M):
                if key not in shipped:
                    unknown.add(key)
        assert not unknown, (
            f"{doc.name} shows YAML settings that no shipped config has: "
            f"{sorted(unknown)}"
        )


class TestServiceUnits:
    """The systemd units must point at files the installer actually places."""

    UNITS = sorted((ROOT / "lxc_autoscale_ml").rglob("*.service"))

    def test_units_exist(self):
        assert len(self.UNITS) == 3

    @pytest.mark.parametrize("unit", UNITS, ids=lambda p: p.name)
    def test_exec_start_target_is_installed(self, unit):
        text = unit.read_text()
        exec_start = re.search(r"^ExecStart=(.+)$", text, re.M)
        assert exec_start, f"{unit.name} has no ExecStart"

        install = (ROOT / "install.sh").read_text()
        for token in exec_start.group(1).split():
            if not token.startswith("/"):
                continue
            name = pathlib.Path(token).name
            if name in ("python3", "gunicorn"):
                # Provided by a package; install.sh must ask for it.
                assert name in install, f"{name} is not installed by install.sh"
                continue

            # The file has to exist in the repository...
            sources = list((ROOT / "lxc_autoscale_ml").rglob(name))
            assert sources, f"{unit.name} runs {token}, which is not in this repository"

            # ...and install.sh has to place it, by name or by directory glob.
            source_dir = sources[0].parent.name
            placed = name in install or f"/{source_dir}/\"*.py" in install
            assert placed, (
                f"{unit.name} runs {token}, which install.sh never puts there"
            )
