from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = REPO_ROOT / "backend" / "requirements-release-lock-windows.txt"
DEFAULT_OUTPUT = REPO_ROOT / "release" / ".build" / "THIRD-PARTY-NOTICES"
_LICENSE_NAMES = ("license", "copying", "notice", "copyright")


def _normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _parse_lock(lock_path: Path) -> dict[str, str]:
    locked: dict[str, str] = {}
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"Release lock entry is not exact: {line}")
        name, version = line.split("==", 1)
        locked[_normalize_name(name.strip())] = version.strip()
    return locked


def _is_notice_file(path: Path) -> bool:
    lower_parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    if any(part in {"license", "licenses", "build_licenses"} for part in lower_parts):
        return True
    return any(name.startswith(prefix) for prefix in _LICENSE_NAMES)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_python_notices(lock_path: Path, output_dir: Path) -> dict[str, object]:
    locked = _parse_lock(lock_path.resolve())
    output_dir = output_dir.resolve()
    python_dir = output_dir / "python"
    if python_dir.exists():
        shutil.rmtree(python_dir)
    python_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    for normalized_name, expected_version in sorted(locked.items()):
        try:
            dist = metadata.distribution(normalized_name)
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Locked release distribution is not installed: {normalized_name}") from exc
        actual_version = dist.version
        if actual_version != expected_version:
            raise RuntimeError(
                f"Locked release distribution version mismatch for {normalized_name}: "
                f"expected {expected_version}, found {actual_version}"
            )

        package_dir = python_dir / normalized_name
        copied: list[dict[str, str]] = []
        seen_hashes: set[str] = set()
        for dist_file in sorted(dist.files or [], key=lambda item: str(item).lower()):
            relative = Path(str(dist_file))
            if not _is_notice_file(relative):
                continue
            source = Path(dist.locate_file(dist_file))
            if not source.is_file():
                continue
            digest = _sha256(source)
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            destination = package_dir / f"{len(copied) + 1:03d}-{source.name}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied.append(
                {
                    "source_entry": str(relative).replace("\\", "/"),
                    "bundled_file": str(destination.relative_to(output_dir)).replace("\\", "/"),
                    "sha256": digest,
                }
            )

        records.append(
            {
                "name": dist.metadata.get("Name") or normalized_name,
                "normalized_name": normalized_name,
                "version": actual_version,
                "license_expression": dist.metadata.get("License-Expression"),
                "legacy_license": dist.metadata.get("License"),
                "notice_files": copied,
            }
        )

    pypdfium = next((item for item in records if item["normalized_name"] == "pypdfium2"), None)
    if pypdfium is None or not pypdfium["notice_files"]:
        raise RuntimeError("pypdfium2/PDFium license files were not found in the installed release wheel.")
    source_entries = "\n".join(item["source_entry"].lower() for item in pypdfium["notice_files"])
    if "build_licenses" not in source_entries and "pdfium" not in source_entries:
        raise RuntimeError(
            "pypdfium2 notice extraction did not expose PDFium/dependency license material from the installed wheel."
        )

    report: dict[str, object] = {
        "schema_version": "1.0.0",
        "source_lock": str(lock_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "distribution_count": len(records),
        "distributions": records,
        "warning": "Collected files are evidence for notice review, not an automatic declaration of license compliance.",
    }
    report_path = output_dir / "python-third-party-notices.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect license/NOTICE files from the exact Stage 11D Python environment.")
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = collect_python_notices(args.lock, args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
