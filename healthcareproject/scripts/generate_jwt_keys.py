"""One-time RSA keypair generator for RS256 JWT signing.

Writes TWO gitignored env files at the repo root, not one — deliberately
separate, so booking's --env-file literally never has the private key
available to it at all, not just "doesn't happen to use it":

  jwt-keys.env          JWT_PRIVATE_KEY + JWT_PUBLIC_KEY + SERVICE_AUTH_SECRET
                         -- profiles only (the sole signer)
  jwt-public-key.env    JWT_PUBLIC_KEY + SERVICE_AUTH_SECRET
                         -- booking, or any other pure-verifier service

Never commit either file. See deploy/docker-manual-commands.md's
"JWT keys (RS256)" section for how they're consumed.

Usage:
    python scripts/generate_jwt_keys.py
"""

import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    service_secret = secrets.token_urlsafe(32)

    # Escaped to a single line (real \n, not literal newlines) so this
    # drops straight into a docker --env-file without the multi-line PEM
    # value breaking the format.
    private_line = f"JWT_PRIVATE_KEY={private_pem.replace(chr(10), '\\n')}"
    public_line = f"JWT_PUBLIC_KEY={public_pem.replace(chr(10), '\\n')}"
    secret_line = f"SERVICE_AUTH_SECRET={service_secret}"

    repo_root = Path(__file__).resolve().parent.parent
    (repo_root / "jwt-keys.env").write_text(f"{private_line}\n{public_line}\n{secret_line}\n")
    (repo_root / "jwt-public-key.env").write_text(f"{public_line}\n{secret_line}\n")
    print(f"wrote {repo_root / 'jwt-keys.env'} (profiles)")
    print(f"wrote {repo_root / 'jwt-public-key.env'} (booking, or any other verifier-only service)")


if __name__ == "__main__":
    main()
