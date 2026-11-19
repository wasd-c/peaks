"""Prepare the local Riot Client's own QR challenge for an explicit Connect action.

The challenge stays in the Python service. No renderer-supplied URL, lockfile,
credential injection, UI modification or screen coordinates are involved.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from time import sleep

from .client import RiotClientError, RiotClientHTTP
from .discovery import RiotLockfile, discover_riot_client
from .launcher import open_riot_client
from .qr import QRLoginPayload, QRParseError, parse_qr_text

_AUTHORIZATION = "/rso-auth/v1/authorization"
_AUTHENTICATION = "/rso-authenticator/v1/authentication"
_SESSION = "/player-session-lifecycle/v1/session"
_READY = "/rso-auth/configuration/v3/ready-state"
_LANGUAGES = {"en": "en_US", "fr": "fr_FR", "ko": "ko_KR"}


class LocalQRSessionReplaced(RuntimeError):
    """Riot's newly mounted login form replaced our pending QR challenge."""


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise RuntimeError("Connection cancelled")


def _subject(client: RiotClientHTTP) -> str | None:
    try:
        authorization = client.get_json(_AUTHORIZATION)
    except RiotClientError as error:
        if error.status_code == 404 or (error.status_code == 400 and error.detail_code == "authorization_missing"):
            return None
        raise
    if not isinstance(authorization, dict):
        raise RuntimeError("Riot Client returned an invalid sign-in state. Try again.")
    subject = authorization.get("subject")
    return subject if isinstance(subject, str) and subject else None


def _require_success(status: int, message: str) -> None:
    if not 200 <= status < 300:
        raise RuntimeError(message)


def _wait_for_client(cancelled: Callable[[], bool] | None = None) -> RiotLockfile:
    for attempt in range(40):
        _check_cancelled(cancelled)
        discovered = discover_riot_client()
        if discovered.lockfile is not None:
            return discovered.lockfile
        if attempt < 39:
            sleep(0.5)
    raise RuntimeError("Riot Client is taking too long to open. Try Connect again shortly.")


def _wait_for_authorization_route(client: RiotClientHTTP, cancelled: Callable[[], bool] | None = None) -> str | None:
    # A verified lockfile can appear before Riot initializes its auth routes.
    for attempt in range(40):
        _check_cancelled(cancelled)
        try:
            return _subject(client)
        except RiotClientError as error:
            if error.status_code not in {None, 400, 503}:
                raise
            if attempt < 39:
                sleep(0.5)
    raise RuntimeError("Riot Client is not ready for QR sign-in. Try Connect again shortly.")


def _restart_signed_out_client(
    client: RiotClientHTTP, lockfile: RiotLockfile, cancelled: Callable[[], bool] | None = None,
) -> RiotLockfile:
    # Riot can retain broken League configuration observers after sign-out.
    # The same empty League client occurs with Riot's own Play button. Use
    # Riot's normal quit action, never terminate a process or a running game.
    response = client.request("POST", "/riot-client-lifecycle/v1/quit")
    _require_success(response.status_code, "Riot Client could not restart after sign-out. Close it and try Connect again.")
    for attempt in range(40):
        _check_cancelled(cancelled)
        current = discover_riot_client().lockfile
        if current is None:
            open_riot_client()
            return _wait_for_client(cancelled)
        if current.pid != lockfile.pid:
            return current
        if attempt < 39:
            sleep(0.5)
    raise RuntimeError("Riot Client has not finished closing. Close it and try Connect again.")


def start_local_qr(
    expected_puuid: str, *, language: str = "en", restart_existing_client: bool = True,
    cancelled: Callable[[], bool] | None = None,
) -> QRLoginPayload | None:
    """Return a fresh local challenge, or None if the selected account is signed in.

    Validate reusable credentials first. Riot's normal sign-out and quit actions
    own permission checks. A replaced QR is retried without another restart.
    """
    if not expected_puuid:
        raise ValueError("The selected account identity is incomplete")
    _check_cancelled(cancelled)
    was_running = discover_riot_client().lockfile is not None
    open_riot_client()
    lockfile = _wait_for_client(cancelled)

    try:
        with ExitStack() as resources:
            client = resources.enter_context(RiotClientHTTP(lockfile, timeout=3.0))
            subject = _wait_for_authorization_route(client, cancelled)
            if subject == expected_puuid:
                return None
            if subject is not None:
                response = client.request("DELETE", _SESSION)
                _require_success(response.status_code, "Riot Client could not switch accounts. Finish the current game or sign out in Riot Client, then try again.")
                for attempt in range(10):
                    _check_cancelled(cancelled)
                    if _subject(client) is None:
                        break
                    if attempt < 9:
                        sleep(0.5)
                else:
                    raise RuntimeError("Riot Client has not finished signing out. Try Connect again shortly.")

            if was_running and restart_existing_client:
                lockfile = _restart_signed_out_client(client, lockfile, cancelled)
                client = resources.enter_context(RiotClientHTTP(lockfile, timeout=3.0))
                subject = _wait_for_authorization_route(client, cancelled)
                if subject == expected_puuid:
                    return None
                if subject is not None:
                    raise RuntimeError("Riot Client signed in to a different account. Try Connect again.")

            for attempt in range(20):
                _check_cancelled(cancelled)
                try:
                    ready = client.get_json(_READY)
                    if isinstance(ready, dict) and ready.get("ready") is True:
                        prompt = client.get_json(_AUTHENTICATION)
                        # Riot's initial sign-in form creates its own prompt on
                        # mount. Wait for it before creating QR, otherwise that
                        # late initialization can replace our fresh challenge.
                        if isinstance(prompt, dict) and prompt.get("type") in {"auth", "error"}:
                            break
                except RiotClientError as error:
                    if error.status_code not in {404, 503}:
                        raise
                if attempt < 19:
                    sleep(0.5)
            else:
                raise RuntimeError("Riot Client is not ready for QR sign-in. Try Connect again shortly.")

            # Same sequence as Riot's QR tab: clear a pending prompt, then let
            # Riot create and poll its own challenge. A live account was either
            # already the selected account (returned above), or signed out first.
            response = client.request("DELETE", _AUTHENTICATION)
            _check_cancelled(cancelled)
            _require_success(response.status_code, "Riot Client could not prepare QR sign-in. Try again.")
            challenge = client.json("POST", f"{_AUTHENTICATION}/qrcode", json_body={
                "language": _LANGUAGES.get(language, "en_US"), "productId": "riot-client",
            })
            if not isinstance(challenge, dict) or challenge.get("type") != "auth":
                raise RuntimeError("Riot Client could not create a QR sign-in request. Try again.")
            auth = challenge.get("auth")
            if not isinstance(auth, dict) or auth.get("auth_method") != "qrcode":
                raise RuntimeError("Riot Client did not return a QR sign-in request. Try again.")
            suuid, cluster = challenge.get("suuid"), challenge.get("cluster")
            if not isinstance(suuid, str) or not isinstance(cluster, str):
                raise QRParseError("Missing local challenge fields")
            return parse_qr_text(f"{suuid}:{cluster}")
    except (RiotClientError, QRParseError):
        raise RuntimeError("Riot Client could not prepare QR sign-in. Try again shortly.") from None


def wait_for_local_sign_in(
    expected_puuid: str, qr: QRLoginPayload, *, cancelled: Callable[[], bool] | None = None,
) -> None:
    """Confirm local sign-in, rather than equating remote approval with login.

    A login form can finish mounting after sign-out and replace the QR. Detect
    that case so the caller can prepare and approve one fresh local challenge.
    Never move presentation tokens out of Riot or accept another identity.
    """
    discovered = discover_riot_client()
    if discovered.lockfile is None:
        raise RuntimeError("Riot Client has not finished signing in. Try Connect again shortly.")
    with RiotClientHTTP(discovered.lockfile, timeout=3.0) as client:
        for attempt in range(40):
            _check_cancelled(cancelled)
            try:
                subject = _subject(client)
                if subject == expected_puuid:
                    return
                if subject is not None:
                    raise RuntimeError("Riot Client signed in to a different account. Try Connect again.")
                prompt = client.get_json(_AUTHENTICATION)
                if isinstance(prompt, dict) and prompt.get("type") == "auth":
                    auth = prompt.get("auth")
                    if (
                        isinstance(auth, dict)
                        and auth.get("auth_method") in {"riot_identity", "qrcode"}
                        and prompt.get("suuid")
                        and prompt["suuid"] != qr.suuid
                    ):
                        raise LocalQRSessionReplaced("Riot Client replaced the pending QR session.")
            except RiotClientError as error:
                if error.status_code not in {None, 404, 503}:
                    raise RuntimeError("Riot Client could not finish signing in. Try Connect again shortly.") from None
            if attempt < 39:
                sleep(0.5)
    raise RuntimeError("Riot Client has not finished signing in. Try Connect again shortly.")
