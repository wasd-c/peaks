from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from peaks.adapters.riot import qr_session
from peaks.adapters.riot.client import RiotClientError
from peaks.adapters.riot.discovery import RiotLockfile
from peaks.adapters.riot.qr import QRLoginPayload


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    lock = RiotLockfile("Riot Client", 42, 12345, "local-test-secret")
    monkeypatch.setattr(qr_session, "open_riot_client", Mock())
    monkeypatch.setattr(qr_session, "sleep", Mock())
    monkeypatch.setattr(qr_session, "discover_riot_client", Mock(return_value=SimpleNamespace(lockfile=lock)))
    transport = Mock()
    transport.get_json.side_effect = lambda path: {
        qr_session._AUTHORIZATION: {}, qr_session._READY: {"ready": True},
        qr_session._AUTHENTICATION: {"type": "auth", "auth": {"auth_method": "riot_identity"}},
    }[path]
    transport.request.return_value = SimpleNamespace(status_code=204)
    transport.json.return_value = {
        "type": "auth", "auth": {"auth_method": "qrcode"}, "suuid": "local-qr-secret", "cluster": "eu",
    }
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=transport)
    factory.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(qr_session, "RiotClientHTTP", factory)
    return transport


def test_closed_client_opens_before_creating_a_native_qr(client: Mock) -> None:
    discovered = qr_session.discover_riot_client.return_value
    qr_session.discover_riot_client.side_effect = [SimpleNamespace(lockfile=None), SimpleNamespace(lockfile=None), discovered]
    qr = qr_session.start_local_qr("selected", language="fr")
    assert qr is not None and qr.as_tuple() == ("local-qr-secret", "eu")
    qr_session.open_riot_client.assert_called_once_with()
    qr_session.sleep.assert_called_once_with(0.5)
    assert client.method_calls == [
        call.get_json(qr_session._AUTHORIZATION), call.get_json(qr_session._READY), call.get_json(qr_session._AUTHENTICATION),
        call.request("DELETE", qr_session._AUTHENTICATION),
        call.json("POST", qr_session._AUTHENTICATION + "/qrcode", json_body={"language": "fr_FR", "productId": "riot-client"}),
    ]


def test_current_selected_identity_needs_no_logout_or_qr(client: Mock) -> None:
    client.get_json.side_effect = None
    client.get_json.return_value = {"subject": "selected"}
    assert qr_session.start_local_qr("selected") is None
    client.request.assert_not_called()
    client.json.assert_not_called()


def test_cold_start_waits_for_authentication_routes(client: Mock) -> None:
    client.get_json.side_effect = [
        RiotClientError("initializing", status_code=400),
        RiotClientError("initializing", status_code=503),
        RiotClientError("No client authorization", status_code=400, detail_code="authorization_missing"),
        {"ready": True}, {"type": "auth"},
    ]
    assert qr_session.start_local_qr("selected", restart_existing_client=False) is not None
    assert qr_session.sleep.call_count == 2


def test_switch_uses_riot_signout_and_waits_for_authorization_to_clear(client: Mock) -> None:
    client.get_json.side_effect = [{"subject": "previous"}, {"subject": "previous"}, {}, {"ready": False}, {"ready": True}, {"type": "auth"}]
    assert qr_session.start_local_qr("selected", restart_existing_client=False) is not None
    assert client.method_calls.index(call.request("DELETE", qr_session._SESSION)) < client.method_calls.index(call.request("DELETE", qr_session._AUTHENTICATION))
    assert qr_session.sleep.call_args_list == [call(0.5), call(0.5)]


def test_rejected_signout_never_force_closes_a_game_or_creates_a_qr(client: Mock) -> None:
    client.get_json.side_effect = None
    client.get_json.return_value = {"subject": "previous"}
    client.request.return_value.status_code = 403
    with pytest.raises(RuntimeError, match="Finish the current game"):
        qr_session.start_local_qr("selected")
    client.request.assert_called_once_with("DELETE", qr_session._SESSION)
    client.json.assert_not_called()


def test_signout_must_finish_before_preparing_qr(client: Mock) -> None:
    client.get_json.side_effect = None
    client.get_json.return_value = {"subject": "previous"}
    with pytest.raises(RuntimeError, match="has not finished signing out"):
        qr_session.start_local_qr("selected")
    client.request.assert_called_once_with("DELETE", qr_session._SESSION)
    client.json.assert_not_called()


def test_client_startup_timeout_is_bounded(client: Mock) -> None:
    qr_session.discover_riot_client.return_value = SimpleNamespace(lockfile=None)
    with pytest.raises(RuntimeError, match="taking too long"):
        qr_session.start_local_qr("selected")
    assert qr_session.discover_riot_client.call_count == 41
    assert qr_session.sleep.call_count == 39
    client.get_json.assert_not_called()


def test_auth_readiness_timeout_does_not_create_qr(client: Mock) -> None:
    client.get_json.side_effect = lambda path: {} if path == qr_session._AUTHORIZATION else {"ready": False}
    with pytest.raises(RuntimeError, match="not ready for QR"):
        qr_session.start_local_qr("selected", restart_existing_client=False)
    client.request.assert_not_called()
    client.json.assert_not_called()


def test_only_missing_authorization_is_treated_as_signed_out(client: Mock) -> None:
    client.get_json.side_effect = [RiotClientError("missing", status_code=404), {"ready": True}, {"type": "auth"}]
    assert qr_session.start_local_qr("selected", restart_existing_client=False) is not None
    client.reset_mock()
    client.get_json.side_effect = RiotClientError("private token path", status_code=500)
    with pytest.raises(RuntimeError, match="could not prepare") as error:
        qr_session.start_local_qr("selected")
    assert "private" not in str(error.value)
    client.request.assert_not_called()


def test_qr_waits_for_the_initial_signin_prompt_to_finish_loading(client: Mock) -> None:
    client.get_json.side_effect = [
        {}, {"ready": True}, RiotClientError("prompt starting", status_code=404),
        {"ready": True}, {"type": "auth", "auth": {"auth_method": "riot_identity"}},
    ]
    assert qr_session.start_local_qr("selected", restart_existing_client=False) is not None
    qr_session.sleep.assert_called_once_with(0.5)
    assert client.method_calls.index(call.request("DELETE", qr_session._AUTHENTICATION)) == 5


@pytest.mark.parametrize("challenge", [
    None, {}, {"type": "error", "error": "private-detail"}, {"type": "auth", "auth": {}},
    {"type": "auth", "auth": {"auth_method": "qrcode"}, "suuid": "bad:id", "cluster": "eu"},
    {"type": "auth", "auth": {"auth_method": "qrcode"}, "suuid": "id", "cluster": None},
])
def test_malformed_or_non_qr_challenges_cannot_be_approved(client: Mock, challenge: object) -> None:
    client.json.return_value = challenge
    with pytest.raises(RuntimeError) as error:
        qr_session.start_local_qr("selected", restart_existing_client=False)
    assert "private-detail" not in str(error.value)


def test_existing_client_restarts_after_logout_before_preparing_qr(client: Mock) -> None:
    old = qr_session.discover_riot_client.return_value
    new_lock = RiotLockfile("Riot Client", 43, 12346, "new-local-test-secret")
    qr_session.discover_riot_client.side_effect = [old, old, old, SimpleNamespace(lockfile=None), SimpleNamespace(lockfile=new_lock)]
    client.get_json.side_effect = [
        {"subject": "previous"}, {}, {}, {"ready": True}, {"type": "auth"},
    ]
    assert qr_session.start_local_qr("selected") is not None
    assert client.request.call_args_list == [
        call("DELETE", qr_session._SESSION),
        call("POST", "/riot-client-lifecycle/v1/quit"),
        call("DELETE", qr_session._AUTHENTICATION),
    ]
    assert qr_session.open_riot_client.call_count == 2
    assert qr_session.RiotClientHTTP.call_args_list[-1] == call(new_lock, timeout=3.0)


def test_rejected_restart_never_forces_exit_or_creates_qr(client: Mock) -> None:
    client.request.return_value.status_code = 403
    with pytest.raises(RuntimeError, match="could not restart"):
        qr_session.start_local_qr("selected")
    client.request.assert_called_once_with("POST", "/riot-client-lifecycle/v1/quit")
    qr_session.open_riot_client.assert_called_once()
    client.json.assert_not_called()


def test_restart_wait_is_bounded_without_force_killing_the_client(client: Mock) -> None:
    with pytest.raises(RuntimeError, match="has not finished closing"):
        qr_session.start_local_qr("selected")
    client.request.assert_called_once_with("POST", "/riot-client-lifecycle/v1/quit")
    assert qr_session.sleep.call_count == 39
    qr_session.open_riot_client.assert_called_once()
    client.json.assert_not_called()


def test_approval_waits_for_local_identity_even_after_qr_succeeds(client: Mock) -> None:
    client.get_json.side_effect = [
        {}, {"type": "auth", "suuid": "approved-qr", "auth": {"auth_method": "qrcode"}},
        {}, {"type": "success"}, {"subject": "selected"},
    ]
    qr_session.wait_for_local_sign_in("selected", QRLoginPayload("approved-qr", "eu"))
    assert qr_session.sleep.call_count == 2
    client.request.assert_not_called()


def test_late_login_form_replacement_is_detected(client: Mock) -> None:
    client.get_json.side_effect = [
        {}, {"type": "auth", "suuid": "new-prompt", "auth": {"auth_method": "riot_identity"}},
    ]
    with pytest.raises(qr_session.LocalQRSessionReplaced):
        qr_session.wait_for_local_sign_in("selected", QRLoginPayload("approved-qr", "eu"))
    client.request.assert_not_called()


def test_another_signed_in_identity_is_never_accepted(client: Mock) -> None:
    client.get_json.side_effect = None
    client.get_json.return_value = {"subject": "another-account"}
    with pytest.raises(RuntimeError, match="different account"):
        qr_session.wait_for_local_sign_in("selected", QRLoginPayload("approved-qr", "eu"))
    client.request.assert_not_called()


def test_local_sign_in_wait_is_bounded_and_hides_errors(client: Mock) -> None:
    client.get_json.side_effect = RiotClientError("private local detail", status_code=503)
    with pytest.raises(RuntimeError, match="has not finished signing in") as error:
        qr_session.wait_for_local_sign_in("selected", QRLoginPayload("approved-qr", "eu"))
    assert qr_session.sleep.call_count == 39
    assert "private" not in str(error.value)
