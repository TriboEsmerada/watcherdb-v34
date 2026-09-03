# WatcherDB V3.3 Standard Edition — Licensing Keys

This folder holds the **public** Ed25519 verification key that the WatcherDB
service uses to validate `license.dat` at startup.

## Files

| File | Purpose | Committed? |
|------|---------|-----------|
| `ed25519_public.pem` | Public key embedded in the distributed build. Used by the service to verify signatures. | Yes |
| `ed25519_private.pem` | **Private signing key.** Must never live in this repo. | No (blocked by `.gitignore`) |

## Where does the private key live?

On the maintainer's workstation only:

```
%USERPROFILE%\.watcherdb-council-secrets\ed25519_private.pem
```

Back it up to an encrypted, offline medium. If this key leaks, every
shipped license becomes forgeable and the product must rotate to a new
key pair — breaking every live `license.dat`.

## Generating the key pair (one-off)

Run from the project root:

```powershell
python deploy/generate_license_keys.py
```

This writes:

- `%USERPROFILE%\.watcherdb-council-secrets\ed25519_private.pem` (PKCS#8, unencrypted — NTFS ACL protects it)
- `deploy/keys/ed25519_public.pem` (SPKI, safe to commit)

The script refuses to overwrite existing keys unless `--force` is passed,
so accidental reruns cannot invalidate a live deployment.

## Signing a customer `license.dat`

Use `python -m watcherdb.licensing.generator` (see module docstring).
Runs on a trusted workstation only, never on a customer machine.
