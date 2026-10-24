"""Report writing, run identifiers and experiment metadata."""

import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports" / "runs"


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def create_run_dir(base=None, label="run", seed=None):
    """Create a fresh run directory; never reuses or overwrites an existing one."""
    base = Path(base) if base else DEFAULT_REPORTS_DIR
    base.mkdir(parents=True, exist_ok=True)
    stem = f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{label}"
    if seed is not None:
        stem += f"-seed{seed}"
    candidate, n = base / stem, 1
    while True:
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            n += 1
            candidate = base / f"{stem}-{n}"


def write_json(path, payload, overwrite=False):
    """Atomically write JSON (UTF-8). Refuses to replace existing files
    unless ``overwrite`` is set."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing report: {path}")
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def git_commit():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def build_metadata(kind, run_id, config, ai_info, started, finished, extra=None):
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "run_id": run_id,
        "started_utc": iso(started),
        "finished_utc": iso(finished),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "config": config,
        "ai": ai_info,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "git_commit": git_commit(),
        },
    }
    if extra:
        metadata.update(extra)
    return metadata


def sub_seed(seed, label):
    """Deterministic, process-independent sub-seed derivation."""
    import hashlib

    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big")
