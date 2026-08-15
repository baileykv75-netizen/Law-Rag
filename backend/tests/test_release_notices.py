from __future__ import annotations

from pathlib import Path

from app.release_notices_cli import collect_python_notices


def test_pypdfium2_binary_notice_material_is_collected_from_installed_wheel(tmp_path: Path) -> None:
    lock = tmp_path / "release-lock.txt"
    lock.write_text("pypdfium2==5.12.1\n", encoding="utf-8")
    output = tmp_path / "notices"

    report = collect_python_notices(lock, output)

    assert report["distribution_count"] == 1
    record = report["distributions"][0]
    assert record["normalized_name"] == "pypdfium2"
    assert record["version"] == "5.12.1"
    assert record["notice_files"]
    sources = "\n".join(item["source_entry"].lower() for item in record["notice_files"])
    assert "build_licenses" in sources or "pdfium" in sources
    assert (output / "python-third-party-notices.json").is_file()
