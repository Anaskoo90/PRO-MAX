import jwt
import pytest

from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.utils import new_uuid7


def test_issued_token_verifies_and_round_trips_claims() -> None:
    service = JwtTokenService(signing_key="test-signing-key")
    user_id = new_uuid7()
    org_id = new_uuid7()

    token = service.issue_access_token(user_id=user_id, org_id=org_id, scopes=["team:create"])
    claims = service.verify(token)

    assert claims.subject_user_id == user_id
    assert claims.org_id == org_id
    assert claims.scopes == ("team:create",)


def test_token_signed_with_a_different_key_fails_verification() -> None:
    issuer = JwtTokenService(signing_key="key-a")
    verifier = JwtTokenService(signing_key="key-b")
    token = issuer.issue_access_token(user_id=new_uuid7(), org_id=new_uuid7(), scopes=[])

    with pytest.raises(jwt.InvalidSignatureError):
        verifier.verify(token)


def test_tampered_payload_fails_verification() -> None:
    service = JwtTokenService(signing_key="test-signing-key")
    token = service.issue_access_token(user_id=new_uuid7(), org_id=new_uuid7(), scopes=[])

    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}A.{signature}"  # corrupt the payload segment

    with pytest.raises(Exception):
        service.verify(tampered)


def test_expired_token_fails_verification() -> None:
    from datetime import timedelta

    service = JwtTokenService(signing_key="test-signing-key")
    token = service.issue_access_token(
        user_id=new_uuid7(), org_id=new_uuid7(), scopes=[], ttl=timedelta(seconds=-1)
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        service.verify(token)
