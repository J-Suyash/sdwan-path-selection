"""Guard the standalone CLI import bootstrap in scripts/ (direct entrypoints).

Runs each script with only ``--help`` from an unrelated cwd with PYTHONPATH
removed; no data generated, no credentials imported.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ("audit_offline_dataset.py", "generate_datasets.py")


@pytest.mark.parametrize("script", SCRIPTS)
def test_cli_help_from_foreign_cwd(script: str, tmp_path: Path) -> None:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    script_path = REPO_ROOT / "scripts" / script
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout, result.stderr
    assert script_path.name in result.stdout, result.stderr
