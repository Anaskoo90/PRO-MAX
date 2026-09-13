import jwt
import pytest
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.utils import new_uuid7


def test_issued_token_verifies_and_round_trips_claims() -> None:
    service = JwtTokenService(signing_key="a" * 32)
    user_id = new_uuid7()
    org_id = new_uuid7()

    token = service.issue_access_token(user_id=user_id, org_id=org_id, scopes=["team:create"])
    claims = service.verify(token)

    assert claims.subject_user_id == user_id
    assert claims.org_id == org_id
    assert claims.scopes == ("team:create",)


def test_access_token_round_trips_its_session_identifier() -> None:
    service = JwtTokenService(signing_key="a" * 32)
    session_id = new_uuid7()

    token = service.issue_access_token(
        user_id=new_uuid7(), org_id=new_uuid7(), scopes=[], session_id=session_id,
    )

    assert service.verify(token).session_id == session_id


def test_access_token_without_a_session_identifier_remains_valid() -> None:
    service = JwtTokenService(signing_key="a" * 32)

    token = service.issue_access_token(
        user_id=new_uuid7(), org_id=new_uuid7(), scopes=[],
    )

    assert service.verify(token).session_id is None


def test_token_signed_with_a_different_key_fails_verification() -> None:
    issuer = JwtTokenService(signing_key="a" * 32)
    verifier = JwtTokenService(signing_key="b" * 32)
    token = issuer.issue_access_token(user_id=new_uuid7(), org_id=new_uuid7(), scopes=[])

    with pytest.raises(jwt.InvalidSignatureError):
        verifier.verify(token)


def test_tampered_payload_fails_verification() -> None:
    service = JwtTokenService(signing_key="a" * 32)
    token = service.issue_access_token(user_id=new_uuid7(), org_id=new_uuid7(), scopes=[])

    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}A.{signature}"  # corrupt the payload segment

    with pytest.raises(Exception):
        service.verify(tampered)


def test_expired_token_fails_verification() -> None:
    from datetime import timedelta

    service = JwtTokenService(signing_key="a" * 32)
    token = service.issue_access_token(
        user_id=new_uuid7(), org_id=new_uuid7(), scopes=[], ttl=timedelta(seconds=-1)
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        service.verify(token)


def test_mfa_challenge_token_round_trips_and_cannot_be_used_as_access_token() -> None:
    service = JwtTokenService(signing_key="a" * 32)
    user_id = new_uuid7()
    org_id = new_uuid7()
    token = service.issue_mfa_challenge_token(user_id=user_id, org_id=org_id)

    challenge = service.verify_mfa_challenge_token(token)

    assert challenge.subject_user_id == user_id
    assert challenge.org_id == org_id
    with pytest.raises(jwt.InvalidTokenError):
        service.verify(token)


def test_access_token_cannot_be_used_as_an_mfa_challenge() -> None:
    service = JwtTokenService(signing_key="a" * 32)
    token = service.issue_access_token(user_id=new_uuid7(), org_id=new_uuid7(), scopes=[])

    with pytest.raises(jwt.InvalidTokenError):
        service.verify_mfa_challenge_token(token)


def test_oauth_state_is_bound_to_org_and_provider_and_not_an_access_token() -> None:
    service = JwtTokenService(signing_key="a" * 32)
    org_id = new_uuid7()
    state = service.issue_oauth_state_token(org_id=org_id, provider_key="discord")

    claims = service.verify_oauth_state_token(state)

    assert claims.org_id == org_id
    assert claims.provider_key == "discord"
    with pytest.raises(jwt.InvalidTokenError):
        service.verify(state)
