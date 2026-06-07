from pathlib import Path
import tomllib

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_faster_whisper_is_not_a_base_dependency():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]

    assert not any(dep.startswith("faster-whisper") for dep in deps)

    voice_extra = data["project"]["optional-dependencies"]["voice"]
    assert any(dep.startswith("faster-whisper") for dep in voice_extra)


def test_manifest_includes_bundled_skills():
    manifest_path = REPO_ROOT / "MANIFEST.in"
    if not manifest_path.exists():
        pytest.skip("MANIFEST.in not present in minimal build")

    manifest = manifest_path.read_text(encoding="utf-8")
    assert "graft skills" in manifest
    assert "graft optional-skills" in manifest
