"""
Tests that the app exits with code 1 when a required env var is missing.

Uses a subprocess to import config with overridden env so the main test process
never hits import-time exit; no app import at module level.
"""

import os
import subprocess
import sys


def _run_config_import(env_override):
    """Run 'from app import config' in a subprocess with given env; return (returncode, stderr)."""
    env = os.environ.copy()
    env.update(env_override)
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env.setdefault("PYTHONPATH", src_dir)
    result = subprocess.run(
        [sys.executable, "-c", "from app import config"],
        env=env,
        capture_output=True,
        text=True,
        cwd=src_dir,
    )
    return result.returncode, result.stderr


def test_fails_when_PXE_UBUNTU_KERNEL_URL_unset():
    """Process exits with 1 and stderr mentions PXE_UBUNTU_KERNEL_URL when var is unset."""
    code, stderr = _run_config_import({"PXE_UBUNTU_KERNEL_URL": ""})
    assert code == 1
    assert "PXE_UBUNTU_KERNEL_URL" in stderr


def test_fails_when_PXE_UBUNTU_INITRD_URL_unset():
    """Process exits with 1 and stderr mentions PXE_UBUNTU_INITRD_URL when var is unset."""
    code, stderr = _run_config_import({"PXE_UBUNTU_INITRD_URL": ""})
    assert code == 1
    assert "PXE_UBUNTU_INITRD_URL" in stderr


def test_fails_when_PXE_AUTOINSTALL_URL_unset():
    """Process exits with 1 and stderr mentions PXE_AUTOINSTALL_URL when var is unset."""
    code, stderr = _run_config_import({"PXE_AUTOINSTALL_URL": ""})
    assert code == 1
    assert "PXE_AUTOINSTALL_URL" in stderr


def test_fails_when_PXE_BASE_URL_unset():
    """Process exits with 1 and stderr mentions PXE_BASE_URL when var is unset."""
    code, stderr = _run_config_import({"PXE_BASE_URL": ""})
    assert code == 1
    assert "PXE_BASE_URL" in stderr


def test_fails_when_required_var_missing_emits_fatal_message():
    """Stderr contains 'Fatal' or 'required' so operators see a clear message."""
    code, stderr = _run_config_import({"PXE_UBUNTU_KERNEL_URL": ""})
    assert code == 1
    assert "Fatal" in stderr or "required" in stderr.lower()
