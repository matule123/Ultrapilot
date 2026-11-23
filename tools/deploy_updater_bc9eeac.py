"""Install only the two runtime files from the updater fix, with rollback."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile

from deploy_oct29_diagnostic26 import stopped

ROOT = Path(__file__).resolve().parents[1]
APP = Path(r"C:\Users\PC\AppData\Local\Programs\UltraPilot")
COMMIT = "bc9eeac7ff49bab57a519160693dd8d4dbdab8c6"
PATHS = ("core/update_check.py", "core/i18n.py")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)


def replace(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        staged = Path(stream.name)
        stream.write(data)
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def main():
    stopped()
    before = {p: (APP / p).read_bytes() for p in PATHS}
    after = {p: blob(COMMIT, p) for p in PATHS}
    for p in PATHS:
        assert (APP / p).resolve().is_relative_to(APP.resolve())
        assert before[p] == blob(COMMIT + "^", p), f"Installed base differs: {p}"
        compile(after[p], p, "exec")
    receipt = APP / "manual-deployment.json"
    original_receipt = receipt.read_bytes()
    assert not any(Path(row["target"]).resolve() in {(APP / p).resolve() for p in PATHS}
                   for row in json.loads(original_receipt)["files"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = ROOT / "build" / "updater-deployment" / stamp
    backup.mkdir(parents=True)
    for p, data in before.items():
        out = backup / p
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(data)
        assert out.read_bytes() == data
    stopped()
    assert all((APP / p).read_bytes() == before[p] for p in PATHS)
    try:
        for p in PATHS:
            replace(APP / p, after[p])
        assert all((APP / p).read_bytes() == after[p] for p in PATHS)
        assert receipt.read_bytes() == original_receipt
        result = dict(commit=COMMIT, backup=str(backup),
                      files={p: dict(previous_sha256=sha(before[p]), sha256=sha(after[p]))
                             for p in PATHS})
        (backup / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    except BaseException:
        for p in PATHS:
            if (APP / p).read_bytes() != before[p]:
                replace(APP / p, before[p])
        assert all((APP / p).read_bytes() == before[p] for p in PATHS)
        raise
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
