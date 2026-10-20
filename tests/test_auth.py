from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import EntraVerifier
from app.config import Settings


@pytest.fixture
def identity(monkeypatch):
    tenant, api, spa = [str(uuid4()) for _ in range(3)]
    settings = Settings(
        environment="test",
        auth_mode="entra",
        entra_tenant_id=tenant,
        entra_api_client_id=api,
        entra_spa_client_id=spa,
        entra_allowed_client_ids=spa,
    )
    verifier = EntraVerifier(settings)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        verifier.keys, "get_signing_key_from_jwt", lambda token: SimpleNamespace(key=private.public_key())
    )
    now = datetime.now(UTC)
    claims = dict(
        iss=settings.issuer,
        aud=api,
        tid=tenant,
        azp=spa,
        sub="demo-user",
        iat=now,
        nbf=now,
        exp=now + timedelta(minutes=5),
        scp="Claims.Access",
        roles=["Claims.Reader"],
    )
    return verifier, private, claims


def test_valid_signed_token(identity):
    verifier, key, claims = identity
    user = verifier.verify(jwt.encode(claims, key, algorithm="RS256"))
    assert user.roles == {"Claims.Reader"}


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "other-api"},
        {"iss": "https://wrong.example"},
        {"tid": "wrong-tenant"},
        {"azp": "unapproved-agent"},
        {"scp": "Other.Scope"},
        {"exp": 1},
        {"roles": "Claims.Reader"},
    ],
)
def test_rejects_wrong_token_claims(identity, change):
    verifier, key, claims = identity
    with pytest.raises(jwt.PyJWTError):
        verifier.verify(jwt.encode({**claims, **change}, key, algorithm="RS256"))


def test_rejects_other_signature(identity):
    verifier, _, claims = identity
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(jwt.PyJWTError):
        verifier.verify(jwt.encode(claims, other_key, algorithm="RS256"))


def test_app_only_token(identity):
    verifier, key, claims = identity
    del claims["scp"]
    claims["roles"] = ["Claims.Reader"]
    assert verifier.verify(jwt.encode(claims, key, algorithm="RS256")).roles == {"Claims.Reader"}
