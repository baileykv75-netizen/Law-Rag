from __future__ import annotations

import json
from pathlib import Path

from app.main import APP_VERSION
from app.release_metadata_cli import build_release_metadata


def test_release_metadata_is_safe_stable_and_contains_required_fingerprints(tmp_path: Path) -> None:
    public_assets = tmp_path / "public-assets-metadata.json"
    public_assets.write_text(
        json.dumps(
            {
                "legal": {"sha256": "1" * 64},
                "retrieval": {
                    "sha256": "2" * 64,
                    "legal_source_fingerprint": "3" * 64,
                    "schema_version": "1.0.0",
                },
            }
        ),
        encoding="utf-8",
    )
    inventory = tmp_path / "dependency-inventory.json"
    inventory.write_text('{"schema_version":"1.0.0"}\n', encoding="utf-8")
    python_lock = tmp_path / "python-lock.txt"
    python_lock.write_text("fastapi==0.141.1\n", encoding="utf-8")
    frontend_lock = tmp_path / "package-lock.json"
    frontend_lock.write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/react": {"version": "19.2.8"},
                    "node_modules/react-dom": {"version": "19.2.8"},
                    "node_modules/typescript": {"version": "5.9.3"},
                    "node_modules/vite": {"version": "8.2.1"},
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "release-metadata.json"

    metadata = build_release_metadata(
        source_commit_sha="A" * 40,
        node_version="v22.23.2",
        npm_version="10.9.8",
        output_path=output,
        public_assets_metadata_path=public_assets,
        dependency_inventory_path=inventory,
        python_lock_path=python_lock,
        frontend_lock_path=frontend_lock,
        pyinstaller_version="6.22.0",
    )

    assert metadata["application_version"] == APP_VERSION
    assert metadata["source_commit_sha"] == "a" * 40
    assert metadata["toolchain"]["node"] == "v22.23.2"
    assert metadata["toolchain"]["pyinstaller"] == "6.22.0"
    assert metadata["frontend"]["versions"] == {
        "react": "19.2.8",
        "react_dom": "19.2.8",
        "typescript": "5.9.3",
        "vite": "8.2.1",
    }
    assert metadata["public_assets"]["legal_source_fingerprint"] == "3" * 64
    assert metadata["wall_clock_build_timestamp"] is None
    persisted = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in persisted
    assert json.loads(persisted) == metadata


def test_release_metadata_rejects_non_full_git_sha(tmp_path: Path) -> None:
    public_assets = tmp_path / "public-assets-metadata.json"
    public_assets.write_text('{"legal":{"sha256":"x"},"retrieval":{"sha256":"y","legal_source_fingerprint":"z","schema_version":"1"}}', encoding="utf-8")
    inventory = tmp_path / "inventory.json"
    inventory.write_text("{}", encoding="utf-8")
    lock = tmp_path / "lock.txt"
    lock.write_text("x", encoding="utf-8")
    frontend = tmp_path / "package-lock.json"
    frontend.write_text('{"packages":{}}', encoding="utf-8")

    try:
        build_release_metadata(
            source_commit_sha="abc123",
            node_version="v22.23.2",
            npm_version="10.9.8",
            output_path=tmp_path / "out.json",
            public_assets_metadata_path=public_assets,
            dependency_inventory_path=inventory,
            python_lock_path=lock,
            frontend_lock_path=frontend,
            pyinstaller_version="6.22.0",
        )
    except ValueError as exc:
        assert "40-character Git SHA-1" in str(exc)
    else:
        raise AssertionError("short Git SHA must be rejected")
