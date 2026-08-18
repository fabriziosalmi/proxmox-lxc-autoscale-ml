"""The installer must install what the deployed code imports.

`python3-aiohttp` was missing from install.sh since the async client was
introduced, so the model service could not start on *any* fresh install -- and
the installer still exited 0 reporting success. `tests/test_config_contract.py`
checks only the ExecStart binaries, so it structurally could not catch this.
"""
import ast
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
INSTALL_SH = ROOT / "install.sh"

# Deployed trees, and where install.sh puts them.
DEPLOYED = [
    ROOT / "lxc_autoscale_ml/api",
    ROOT / "lxc_autoscale_ml/model",
    ROOT / "lxc_autoscale_ml/monitor",
]

# Third-party distribution -> Debian package installed by install.sh.
DEBIAN_PACKAGE = {
    "flask": "python3-flask",
    "requests": "python3-requests",
    "sklearn": "python3-sklearn",
    "pandas": "python3-pandas",
    "numpy": "python3-numpy",
    "aiohttp": "python3-aiohttp",
    "aiofiles": "python3-aiofiles",
    "psutil": "python3-psutil",
    "yaml": "python3-yaml",
    "prometheus_client": "python3-prometheus-client",
    "gunicorn": "gunicorn",
}


def required_packages():
    match = re.search(r"REQUIRED_SYSTEM_PACKAGES=\(([^)]*)\)", INSTALL_SH.read_text(), re.S)
    assert match, "could not find REQUIRED_SYSTEM_PACKAGES in install.sh"
    return {p.strip('"') for p in match.group(1).split() if p.strip('"')}


def top_level_imports(path):
    """Modules imported unconditionally at module scope.

    Imports inside a try/except ImportError are optional by construction --
    metrics.py guards prometheus_client that way -- so they are excluded.
    """
    tree = ast.parse(path.read_text())
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def local_module_names():
    names = set()
    for directory in DEPLOYED:
        names.update(p.stem for p in directory.glob("*.py"))
    return names


ALL_MODULES = sorted(p for d in DEPLOYED for p in d.glob("*.py"))


@pytest.mark.parametrize("module", ALL_MODULES, ids=lambda p: p.name)
def test_every_unconditional_import_is_installed(module):
    packages = required_packages()
    local = local_module_names()
    stdlib = set(getattr(sys, "stdlib_module_names", ()))

    missing = []
    for name in sorted(top_level_imports(module)):
        if name in local or name in stdlib or name.startswith("_"):
            continue
        package = DEBIAN_PACKAGE.get(name)
        assert package, (
            f"{module.name} imports {name!r}, which this test does not know how "
            f"to map to a Debian package. Add it to DEBIAN_PACKAGE."
        )
        if package not in packages:
            missing.append(f"{name} (needs {package})")

    assert not missing, (
        f"{module.name} imports {missing} but install.sh does not install "
        f"{'them' if len(missing) > 1 else 'it'}. A fresh install cannot run this file."
    )


def test_the_installer_covers_the_runtime_requirements():
    """requirements.txt and install.sh are two different dependency lists and
    only one of them is deployed. They must not disagree about what is needed.
    """
    packages = required_packages()
    declared = []
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        declared.append(re.split(r"[=<>!]", line)[0].strip())

    pypi_to_import = {
        "Flask": "flask", "scikit-learn": "sklearn", "PyYAML": "yaml",
        "prometheus-client": "prometheus_client",
    }
    missing = []
    for dist in declared:
        module = pypi_to_import.get(dist, dist.lower().replace("-", "_"))
        package = DEBIAN_PACKAGE.get(module)
        if package and package not in packages:
            missing.append(f"{dist} -> {package}")
    assert not missing, (
        f"requirements.txt declares {missing}, which install.sh never installs"
    )


def test_a_failed_service_start_is_fatal():
    """The installer used to log the error and still print
    "Installation process complete!" and exit 0."""
    text = INSTALL_SH.read_text()
    setup = text[text.index("setup_service()"):]
    setup = setup[:setup.index("\n}")]
    assert "return 1" in setup, "setup_service does not propagate a failure"


def test_the_installer_requires_root():
    assert "EUID" in INSTALL_SH.read_text()


class TestServiceUnitContract:
    UNITS = sorted((ROOT / "lxc_autoscale_ml").rglob("*.service"))

    def _directives(self, unit):
        out = {}
        for line in unit.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "[")):
                continue
            key, sep, value = line.partition("=")
            if sep:
                out.setdefault(key.strip(), []).append(value.strip())
        return out

    @pytest.mark.parametrize("unit", UNITS, ids=lambda p: p.name)
    def test_no_yaml_is_fed_to_systemd_as_an_environment_file(self, unit):
        """The model unit pointed EnvironmentFile at a YAML file. systemd
        expects KEY=value; the configuration is read by Python."""
        for value in self._directives(unit).get("EnvironmentFile", []):
            assert not value.lstrip("-").endswith((".yaml", ".yml")), (
                f"{unit.name} feeds a YAML file to systemd as an EnvironmentFile"
            )

    @pytest.mark.parametrize("unit", UNITS, ids=lambda p: p.name)
    def test_restart_backs_off(self, unit):
        """With the default RestartSec a persistent failure burned the start
        limit in under a second and latched the unit `failed`, with no restart
        attempts visible in the journal."""
        directives = self._directives(unit)
        assert directives.get("Restart") == ["on-failure"]
        assert int(directives["RestartSec"][0]) >= 5, f"{unit.name} restarts too eagerly"

    @pytest.mark.parametrize("unit", UNITS, ids=lambda p: p.name)
    def test_exec_start_paths_match_the_installer(self, unit):
        install = INSTALL_SH.read_text()
        exec_start = self._directives(unit)["ExecStart"][0]
        for token in exec_start.split():
            if not token.startswith("/"):
                continue
            name = pathlib.Path(token).name
            if name in ("python3", "gunicorn"):
                assert name in install
                continue
            sources = list((ROOT / "lxc_autoscale_ml").rglob(name))
            assert sources, f"{unit.name} runs {token}, absent from this repository"
            directory = sources[0].parent.name
            assert name in install or f'/{directory}/"*.py' in install, (
                f"{unit.name} runs {token}, which install.sh never places there"
            )

    def test_the_model_starts_after_what_it_depends_on(self):
        """It reads the monitor's file and calls the API."""
        after = " ".join(self._directives(
            ROOT / "lxc_autoscale_ml/model/lxc_autoscale_ml.service")["After"])
        assert "lxc_monitor.service" in after
        assert "lxc_autoscale_api.service" in after

    def test_the_api_unit_masks_its_secrets(self):
        directives = self._directives(
            ROOT / "lxc_autoscale_ml/api/lxc_autoscale_api.service")
        assert directives.get("UMask") == ["0077"], (
            "the API writes an access log; without a UMask it is world-readable"
        )
