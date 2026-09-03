"""
One-off Ed25519 key-pair generator for WatcherDB V3.3 Standard Edition licensing.

Writes:
  * private key -> %USERPROFILE%\\.watcherdb-council-secrets\\ed25519_private.pem
  * public  key -> deploy/keys/ed25519_public.pem

Run once per product line. Refuses to overwrite existing keys unless
`--force` is passed — rotating the key pair invalidates every shipped
`license.dat`, so the safety rail is deliberate.

Usage:
    python deploy/generate_license_keys.py            # generate if missing
    python deploy/generate_license_keys.py --force    # rotate (destructive)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_KEY_PATH = PROJECT_ROOT / "deploy" / "keys" / "ed25519_public.pem"
PRIVATE_KEY_PATH = Path(os.environ["USERPROFILE"]) / ".watcherdb-council-secrets" / "ed25519_private.pem"


def generate(force: bool) -> int:
    if PRIVATE_KEY_PATH.exists() and not force:
        print(f"Refusing to overwrite private key: {PRIVATE_KEY_PATH}")
        print("Pass --force to rotate (INVALIDATES ALL SHIPPED LICENSES).")
        return 1
    if PUBLIC_KEY_PATH.exists() and not force:
        print(f"Refusing to overwrite public key: {PUBLIC_KEY_PATH}")
        print("Pass --force to rotate.")
        return 1

    PRIVATE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    PRIVATE_KEY_PATH.write_bytes(priv_pem)
    PUBLIC_KEY_PATH.write_bytes(pub_pem)

    print(f"  private -> {PRIVATE_KEY_PATH}")
    print(f"  public  -> {PUBLIC_KEY_PATH}")
    print()
    print("NEXT STEPS:")
    print("  1. Back up the private key to encrypted offline media.")
    print("  2. Commit deploy/keys/ed25519_public.pem to the repo.")
    print("  3. Restrict NTFS permissions on the private key folder to your user.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="rotate existing keys (destructive)")
    args = parser.parse_args()
    sys.exit(generate(args.force))
