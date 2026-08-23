"""Frozen-entry regression tests (run the real entry script)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "installer" / "entry.py"


def _run(args: list[str], env_extra: dict[str, str] | None = None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ENTRY), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=120,
    )


def test_entry_version_flag_prints_app_and_version():
    from lfms.core.version import APP_NAME, VERSION

    result = _run(["--version"])
    assert result.returncode == 0
    assert f"{APP_NAME} {VERSION}" in result.stdout


def test_entry_self_check_imports_every_package():
    pytest.importorskip("PySide6")  # self-check imports the GUI stack
    result = _run([], env_extra={"LFMS_SELF_CHECK": "1"})
    assert result.returncode == 0, result.stderr[-400:]


def test_runtime_hook_stubs_are_safe_when_real_modules_exist():
    """With full scipy present the stubs must be no-ops."""
    code = (
        "import sys; sys.path.insert(0, 'installer'); "
        "import rthook_scipy_ellip; "  # noqa: F401 runs installers
        "import scipy.special._ellip_harm_2 as m; "
        "assert callable(m._ellipsoid); "
        "from scipy.stats import scoreatpercentile; "
        "assert abs(scoreatpercentile([1,2,3], 50) - 2.0) < 1e-9"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-400:]
