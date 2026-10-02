"""Regression: deploy preparation must NEVER overwrite an existing config/brand.yml.

Covers the bug where `deploy.sh` unconditionally copied brand.example.yml over the
owner's real brand configuration on every deployment.
"""
import os
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_prepare(app_dir: str) -> str:
    # bare 'bash' from python may resolve to WSL bash (drops args, no /c mount).
    # Use Git Bash explicitly when present; override via TEST_BASH.
    bash = os.environ.get('TEST_BASH')
    if not bash:
        cand = r'C:' + os.sep + os.path.join('Program Files', 'Git', 'usr', 'bin', 'bash.exe')
        bash = cand if os.path.exists(cand) else 'bash'
    return subprocess.run(
        [bash, 'scripts/deploy.sh', '--prepare-only'],
        env=dict(os.environ, AKH_DIR=app_dir), capture_output=True, text=True,
        timeout=30, cwd=str(REPO),
    ).stdout


@pytest.fixture()
def fake_app_dir(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / ".env").write_text("APP_ENV=test\n", encoding="utf-8")
    src = os.path.join(REPO, "config", "brand.example.yml")
    shutil.copy(src, tmp_path / "app" / "brand.example.yml")
    os.makedirs(tmp_path / "app" / "config")
    shutil.copy(src, tmp_path / "app" / "config" / "brand.example.yml")
    return tmp_path


def test_existing_brand_yml_survives_deploy_prepare(fake_app_dir):
    owner_config = fake_app_dir / "app" / "config" / "brand.yml"
    owner_config.write_text(
        "brand_status: DECIDED\nname_fa: برند-مالک\n", encoding="utf-8"
    )
    out = _run_prepare(str(fake_app_dir))
    assert "preserved existing config/brand.yml" in out
    assert "created config/brand.yml" not in out
    assert owner_config.read_text(encoding="utf-8") == "brand_status: DECIDED\nname_fa: برند-مالک\n"


def test_missing_brand_yml_created_from_example(fake_app_dir):
    out = _run_prepare(str(fake_app_dir))
    assert "created config/brand.yml from example" in out
    created = (fake_app_dir / "app" / "config" / "brand.yml").read_text(encoding="utf-8")
    example = (fake_app_dir / "app" / "config" / "brand.example.yml").read_text(encoding="utf-8")
    assert created == example
    assert "UNDECIDED" in created


def test_repeat_prepare_is_stable(fake_app_dir):
    _run_prepare(str(fake_app_dir))
    first = (fake_app_dir / "app" / "config" / "brand.yml").read_text(encoding="utf-8")
    (fake_app_dir / "app" / "config" / "brand.yml").write_text(
        first.replace("UNDECIDED", "DECIDED"), encoding="utf-8"
    )
    _run_prepare(str(fake_app_dir))
    again = (fake_app_dir / "app" / "config" / "brand.yml").read_text(encoding="utf-8")
    assert "DECIDED" in again  # second run preserved the edited owner config
