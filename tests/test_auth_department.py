from __future__ import annotations

from shared import auth as auth_module


def test_local_user_department_is_loaded_and_serialized(monkeypatch) -> None:
    monkeypatch.setenv("MEMBER_DEPARTMENT", "  finance  ")

    user = auth_module.authenticate_local_user("member@local", "ChangeMe123!")

    assert user is not None
    assert user.department == "finance"
    assert auth_module.serialize_user(user)["department"] == "finance"


def test_access_token_round_trip_preserves_department(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    user = auth_module.AuthUser(
        user_id="u-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
        department="finance",
    )

    restored = auth_module.decode_access_token(auth_module.create_access_token(user))

    assert restored.department == "finance"


def test_legacy_access_token_without_department_defaults_to_empty(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    token = auth_module.jwt.encode(
        {
            "sub": "u-1",
            "email": "member@local",
            "role": "member",
            "iat": 100,
            "exp": 9999999999,
        },
        "test-secret",
        algorithm="HS256",
    )

    user = auth_module.decode_access_token(token)

    assert user.department == ""
