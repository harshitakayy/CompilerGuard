import json

import pytest

from harness.reporting import (
    PROJECT_ROOT,
    build_metadata,
    create_run_dir,
    sub_seed,
    utc_now,
    write_json,
)


def test_write_json_refuses_to_overwrite(tmp_path):
    path = tmp_path / "nested" / "r.json"
    write_json(path, {"a": 1})
    with pytest.raises(FileExistsError):
        write_json(path, {"a": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    write_json(path, {"a": 3}, overwrite=True)
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 3}


def test_write_json_handles_unicode_and_leaves_no_temp_files(tmp_path):
    write_json(tmp_path / "u.json", {"code": "x = é;"})
    assert "é" in (tmp_path / "u.json").read_text(encoding="utf-8")
    assert [p.name for p in tmp_path.iterdir()] == ["u.json"]


def test_run_directories_are_unique_and_created_automatically(tmp_path):
    base = tmp_path / "does" / "not" / "exist"
    dirs = {create_run_dir(base, "x", 1) for _ in range(3)}
    assert len(dirs) == 3 and all(d.is_dir() for d in dirs)


def test_sub_seed_is_deterministic_and_label_sensitive():
    assert sub_seed(42, "valid") == sub_seed(42, "valid")
    assert sub_seed(42, "valid") != sub_seed(42, "mutation")
    assert sub_seed(42, "valid") != sub_seed(43, "valid")


def test_metadata_fields():
    now = utc_now()
    meta = build_metadata("pipeline", "rid", {"seed": 1}, {"status": "SKIPPED"}, now, now)
    assert meta["run_id"] == "rid" and meta["config"] == {"seed": 1} and meta["schema_version"]
    assert PROJECT_ROOT.is_absolute()
