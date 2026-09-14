import time

import jwt
import pytest

from jwt_shared import Role, create_access_token, decode_access_token

SECRET = "test-secret"


def test_round_trip_preserves_subject_and_role() -> None:
    token = create_access_token(subject="patient-123", role=Role.PATIENT, secret=SECRET)
    payload = decode_access_token(token, secret=SECRET)

    assert payload.sub == "patient-123"
    assert payload.role == Role.PATIENT.value


def test_accepts_plain_string_role() -> None:
    token = create_access_token(subject="user-1", role="admin", secret=SECRET)
    payload = decode_access_token(token, secret=SECRET)

    assert payload.role == "admin"


def test_expired_token_is_rejected() -> None:
    token = create_access_token(
        subject="patient-1", role=Role.PATIENT, secret=SECRET, expires_minutes=-1
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, secret=SECRET)


def test_wrong_secret_is_rejected() -> None:
    token = create_access_token(subject="patient-1", role=Role.PATIENT, secret=SECRET)

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token, secret="wrong-secret")


def test_expiry_reflects_requested_lifetime() -> None:
    token = create_access_token(
        subject="patient-1", role=Role.PATIENT, secret=SECRET, expires_minutes=5
    )
    payload = decode_access_token(token, secret=SECRET)

    assert payload.exp - int(time.time()) <= 5 * 60
    assert payload.exp - int(time.time()) > 4 * 60


def test_each_token_gets_its_own_unique_jti() -> None:
    # Same subject, same role -- jti still differs, because it identifies
    # the TOKEN, not the user, which is the entire point: revoking one
    # compromised token must not require touching any other token issued
    # to the same person.
    first = decode_access_token(
        create_access_token(subject="patient-1", role=Role.PATIENT, secret=SECRET), secret=SECRET
    )
    second = decode_access_token(
        create_access_token(subject="patient-1", role=Role.PATIENT, secret=SECRET), secret=SECRET
    )
    assert first.jti != second.jti


def test_iat_reflects_issuance_time_not_expiry() -> None:
    token = create_access_token(subject="patient-1", role=Role.PATIENT, secret=SECRET)
    payload = decode_access_token(token, secret=SECRET)

    assert abs(payload.iat - int(time.time())) < 5  # minted just now
    assert payload.exp > payload.iat  # exp is strictly later than iat


def test_round_trip_with_an_rsa_keypair() -> None:
    # RS256: a real asymmetric pair, not the HS256 shared-secret path every
    # other test in this file exercises. The private key signs, the public
    # key verifies -- decoding must succeed with the public key alone, and
    # must fail against a token signed by a DIFFERENT private key (the
    # signature simply won't match a different keypair's public half).
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    def _keypair() -> tuple[str, str]:
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
        return private_pem, public_pem

    private_key, public_key = _keypair()
    other_private_key, _ = _keypair()

    token = create_access_token(
        subject="patient-1", role=Role.PATIENT, secret=private_key, algorithm="RS256"
    )
    payload = decode_access_token(token, secret=public_key, algorithm="RS256")
    assert payload.sub == "patient-1"

    other_token = create_access_token(
        subject="patient-1", role=Role.PATIENT, secret=other_private_key, algorithm="RS256"
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(other_token, secret=public_key, algorithm="RS256")
