"""
Build a signed update package for WatcherDB V3.3 Standard Edition.

Inputs:
  * dist/watcherdb/                  - PyInstaller onedir bundle from Sem 2
  * Ed25519 private key (default in %USERPROFILE%\\.watcherdb-council-secrets\\
    ed25519_private.pem, overridable via --private-key or
    WATCHERDB_LICENSE_PRIVATE_KEY env).

Outputs (placed in dist/update/):
  * watcherdb_v3.3_<version>.zip     - bundle archive
  * watcherdb_v3.3_<version>.manifest.json  - Ed25519-signed manifest
                                              (schema: watcherdb.licensing.manifest)

The customer-side updater loads the manifest, verifies the signature via
the same public key the service already trusts (deploy/keys/
ed25519_public.pem), then applies the zip if version > current and
min_version <= current.

Usage:
    python deploy/updater/build_update_package.py \\
        --version 3.3.1.0 \\
        --min-version 3.3.0.0 \\
        [--bundle-dir dist/watcherdb] \\
        [--output-dir dist/update] \\
        [--private-key PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from watcherdb.licensing.manifest import build_manifest, sign_manifest  # noqa: E402

DEFAULT_BUNDLE_DIR = REPO_ROOT / "dist" / "watcherdb"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "dist" / "update"
DEFAULT_PRIVATE_KEY = Path(
    os.environ.get(
        "WATCHERDB_LICENSE_PRIVATE_KEY",
        str(Path(os.environ.get("USERPROFILE", "")) / ".watcherdb-council-secrets" / "ed25519_private.pem"),
    )
)


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    pem = path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit(f"Private key at {path} is not Ed25519.")
    return key


def _sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _zip_bundle(bundle_dir: Path, zip_path: Path) -> list[dict]:
    """Zip every file under bundle_dir. Returns informational file entries."""
    entries: list[dict] = []
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(bundle_dir.rglob("*")):
            if not p.is_file():
                continue
            arcname = str(p.relative_to(bundle_dir))
            zf.write(p, arcname=arcname)
            entries.append({
                "path": arcname,
                "sha256": _sha256(p),
                "size_bytes": p.stat().st_size,
            })
    return entries


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="New version string (e.g. 3.3.1.0)")
    parser.add_argument("--min-version", required=True, help="Oldest compatible installed version")
    parser.add_argument("--bundle-dir", default=str(DEFAULT_BUNDLE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--private-key", default=str(DEFAULT_PRIVATE_KEY))
    args = parser.parse_args(argv)

    bundle_dir = Path(args.bundle_dir)
    if not bundle_dir.is_dir() or not (bundle_dir / "watcherdb.exe").exists():
        print(f"[build_update_package] ERROR: bundle not found or missing watcherdb.exe: {bundle_dir}")
        return 1

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"watcherdb_v3.3_{args.version}"
    zip_path = out_dir / f"{base_name}.zip"
    manifest_path = out_dir / f"{base_name}.manifest.json"

    print(f"[build_update_package] Zipping {bundle_dir} -> {zip_path}")
    file_entries = _zip_bundle(bundle_dir, zip_path)
    print(f"[build_update_package] Wrote {zip_path} ({zip_path.stat().st_size // 1024} KB, {len(file_entries)} files)")

    print(f"[build_update_package] Building manifest for version {args.version} (min {args.min_version})")
    payload = build_manifest(
        version=args.version,
        min_version=args.min_version,
        zip_path=zip_path,
        file_entries=file_entries,
    )

    print(f"[build_update_package] Signing manifest with {args.private_key}")
    priv = _load_private_key(Path(args.private_key))
    signed = sign_manifest(payload, priv)

    manifest_path.write_text(json.dumps(signed, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[build_update_package] Wrote {manifest_path}")
    print()
    print(f"Distribute both files together:")
    print(f"  {zip_path}")
    print(f"  {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
