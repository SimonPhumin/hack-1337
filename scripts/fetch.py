"""Download and unpack the pinned upstream releases into build/cache (verified by sha256)."""
import hashlib
import shutil
import sys
import urllib.request
import zipfile

from config import CACHE, UPSTREAMS


def fetch(name: str, spec: dict) -> None:
    dest = CACHE / name
    archive = CACHE / f"{name}-{spec['version']}.zip"
    marker = dest / ".ok"
    if marker.exists() and marker.read_text() == spec["sha256"]:
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        print(f"downloading {name} {spec['version']}")
        with urllib.request.urlopen(spec["url"]) as r, open(archive, "wb") as f:
            shutil.copyfileobj(r, f)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != spec["sha256"]:
        archive.unlink()
        sys.exit(f"sha256 mismatch for {name}: {digest}")
    shutil.rmtree(dest, ignore_errors=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(dest)
    (dest / ".ok").write_text(spec["sha256"])


if __name__ == "__main__":
    for name, spec in UPSTREAMS.items():
        fetch(name, spec)
