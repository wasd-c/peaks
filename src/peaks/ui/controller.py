"""QML-facing application controller.

The controller exposes metadata to QML, never TOTP seeds, cookies, access
tokens, Riot lockfile passwords, or raw QR payloads. Secrets stay in the vault
and are consumed only by narrowly scoped commands after unlock.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from inspect import signature
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import (
    Property,
    QEvent,
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication

from peaks.application.demo_data import (
    DEMO_PIN,
    DEMO_TOTP_SEED,
    demo_accounts,
    demo_current_match,
    demo_followed,
    demo_search_history,
    search_demo,
)
from peaks.application.qr_capture import (
    capture_riot_client_windows,
    decode_clipboard_image,
    decode_qr_images,
)

_RIOT_ID_RE = re.compile(r"^.{2,24}#[A-Za-z0-9]{2,8}$")


class _SessionImportBindingError(RuntimeError):
    """A safe, user-facing failure while binding an imported session."""


class _WorkerSignals(QObject):
    finished = Signal(object, object)


class _Worker(QRunnable):
    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.finished.emit(self.function(), None)
        except Exception as exc:  # UI receives a redacted message, never response bodies.
            self.signals.finished.emit(None, exc)


class _DemoVault:
    """Small test-only vault facade; it is enabled only by ``PEAKS_DEMO``."""

    def __init__(self) -> None:
        self._unlocked = False
        self._secrets: dict[str, dict[str, str]] = {
            account_id: {"totp": DEMO_TOTP_SEED} for account_id in ("own-aureline", "own-peaks")
        }

    def has_pin(self) -> bool:
        return True

    def unlock(self, pin: str) -> bool:
        self._unlocked = pin == DEMO_PIN
        return self._unlocked

    def lock(self) -> None:
        self._unlocked = False

    def get_secret(self, owner: str, name: str) -> str | None:
        if not self._unlocked:
            raise RuntimeError("Vault is locked")
        return self._secrets.get(owner, {}).get(name)

    def set_secret(self, owner: str, name: str, value: str) -> None:
        if not self._unlocked:
            raise RuntimeError("Vault is locked")
        self._secrets.setdefault(owner, {})[name] = value


class AppController(QObject):
    pageChanged = Signal()
    lockedChanged = Signal()
    hasPasscodeChanged = Signal()
    pinModeChanged = Signal()
    pinErrorChanged = Signal()
    accountsChanged = Signal()
    followedChanged = Signal()
    searchHistoryChanged = Signal()
    searchResultsChanged = Signal()
    searchBusyChanged = Signal()
    accountRefreshBusyChanged = Signal()
    detectionBusyChanged = Signal()
    qrBusyChanged = Signal()
    currentMatchChanged = Signal()
    gameDetectedChanged = Signal()
    viewModeChanged = Signal()
    selectedAccountChanged = Signal()
    settingsChanged = Signal()
    riotClientChanged = Signal()
    toastChanged = Signal()
    pendingQrChanged = Signal()
    qrPromptOpenChanged = Signal()
    resetRequested = Signal()

    def __init__(
        self,
        *,
        repository: Any | None = None,
        vault: Any | None = None,
        provider: Any | None = None,
        game_detector: Any | None = None,
        qr_approver: Any | None = None,
        session_importer_factory: Callable[[], Any] | None = None,
        profile_dir: Path | None = None,
        repository_factory: Callable[[Path], Any] | None = None,
        vault_factory: Callable[[Path], Any] | None = None,
        demo: bool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._demo = bool(int(os.getenv("PEAKS_DEMO", "0"))) if demo is None else demo
        self._repository = repository
        self._vault = _DemoVault() if self._demo else vault
        self._provider = provider
        self._game_detector = game_detector
        self._qr_approver = qr_approver
        self._session_importer_factory = session_importer_factory
        self._profile_dir = profile_dir
        self._repository_factory = repository_factory
        self._vault_factory = vault_factory
        self._thread_pool = QThreadPool.globalInstance()
        self._workers: set[_Worker] = set()

        # Incremented whenever the vault is locked.  Every background result
        # is tagged with the epoch in which it started, so a result produced
        # after a lock can never repopulate the UI after the vault is sealed
        # (or after a later unlock).
        self._lock_epoch = 0

        self._page = "overview"
        self._locked = True
        self._has_passcode = self._vault_has_pin()
        self._pin_mode = "unlock" if self._has_passcode else "create"
        self._pin_error = ""
        self._pending_pin: str | None = None
        self._failed_attempts = 0
        self._retry_after = 0.0

        self._accounts: list[dict[str, Any]] = demo_accounts() if self._demo else []
        self._followed: list[dict[str, Any]] = demo_followed() if self._demo else []
        self._search_history: list[dict[str, Any]] = demo_search_history() if self._demo else []
        self._search_results: list[dict[str, Any]] = []
        self._search_busy = False
        self._account_refresh_busy = False
        self._detection_busy = False
        self._qr_busy = False
        self._current_match: dict[str, Any] = demo_current_match() if self._demo else {}
        self._game_detected = self._demo
        self._view_mode = "grid"
        self._selected_account: dict[str, Any] = {}
        self._settings: dict[str, Any] = {
            "autoLockMinutes": 15,
            "lockOnBlur": True,
            "reduceMotion": False,
            "riotApiConfigured": False,
            "streamerModeRequired": True,
            "clipboardClearSeconds": 15,
        }
        self._riot_client: dict[str, Any] = {
            "detected": False,
            "label": "Riot Client not detected",
            "path": "",
            "game": "",
        }
        self._toast_text = ""
        self._toast_serial = 0
        self._pending_qr: dict[str, Any] = {}
        self._qr_prompt_open = False
        self._pending_qr_private: dict[str, Any] = {}
        # Set only when the primary Connect action bootstraps a Riot session
        # before continuing into QR capture.  A direct import from the menu
        # never starts a QR capture afterwards.
        self._pending_qr_bootstrap: dict[str, Any] = {}
        self._clipboard_totp_code: str | None = None
        self._clipboard_epoch = 0
        self._qr_attempt = 0
        self._resetting = False
        self._last_activity = time.monotonic()

        self._load_persisted_state()
        self._attach_asset_urls()

        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(1_000)
        self._lock_timer.timeout.connect(self._check_auto_lock)
        self._lock_timer.start()

        self._detection_timer = QTimer(self)
        self._detection_timer.setInterval(8_000)
        self._detection_timer.timeout.connect(self.detectCurrentGame)
        self._detection_timer.start()
        QTimer.singleShot(450, self.detectCurrentGame)

    # ---- QML properties -------------------------------------------------
    @Property(str, notify=pageChanged)
    def page(self) -> str:
        return self._page

    @Property(bool, notify=lockedChanged)
    def locked(self) -> bool:
        return self._locked

    @Property(bool, notify=hasPasscodeChanged)
    def hasPasscode(self) -> bool:
        return self._has_passcode

    @Property(str, notify=pinModeChanged)
    def pinMode(self) -> str:
        return self._pin_mode

    @Property(str, notify=pinErrorChanged)
    def pinError(self) -> str:
        return self._pin_error

    @Property(list, notify=accountsChanged)
    def accounts(self) -> list[dict[str, Any]]:
        return deepcopy(self._accounts) if not self._locked else []

    @Property(list, notify=followedChanged)
    def followed(self) -> list[dict[str, Any]]:
        return deepcopy(self._followed) if not self._locked else []

    @Property(list, notify=searchHistoryChanged)
    def searchHistory(self) -> list[dict[str, Any]]:
        return deepcopy(self._search_history) if not self._locked else []

    @Property(list, notify=searchResultsChanged)
    def searchResults(self) -> list[dict[str, Any]]:
        return deepcopy(self._search_results) if not self._locked else []

    @Property(bool, notify=searchBusyChanged)
    def searchBusy(self) -> bool:
        return self._search_busy

    @Property(bool, notify=accountRefreshBusyChanged)
    def accountRefreshBusy(self) -> bool:
        return self._account_refresh_busy

    @Property(bool, notify=detectionBusyChanged)
    def detectionBusy(self) -> bool:
        return self._detection_busy

    @Property(bool, notify=qrBusyChanged)
    def qrBusy(self) -> bool:
        return self._qr_busy

    @Property(dict, notify=currentMatchChanged)
    def currentMatch(self) -> dict[str, Any]:
        return deepcopy(self._current_match) if not self._locked else {}

    @Property(bool, notify=gameDetectedChanged)
    def gameDetected(self) -> bool:
        return self._game_detected and not self._locked

    @Property(str, notify=viewModeChanged)
    def viewMode(self) -> str:
        return self._view_mode

    @Property(dict, notify=selectedAccountChanged)
    def selectedAccount(self) -> dict[str, Any]:
        return deepcopy(self._selected_account) if not self._locked else {}

    @Property(dict, notify=settingsChanged)
    def settings(self) -> dict[str, Any]:
        return deepcopy(self._settings)

    @Property(dict, notify=riotClientChanged)
    def riotClient(self) -> dict[str, Any]:
        return deepcopy(self._riot_client)

    @Property(str, notify=toastChanged)
    def toastText(self) -> str:
        return self._toast_text

    @Property(int, notify=toastChanged)
    def toastSerial(self) -> int:
        return self._toast_serial

    @Property(dict, notify=pendingQrChanged)
    def pendingQr(self) -> dict[str, Any]:
        return deepcopy(self._pending_qr)

    @Property(bool, notify=qrPromptOpenChanged)
    def qrPromptOpen(self) -> bool:
        return self._qr_prompt_open

    # ---- Navigation and lock state -------------------------------------
    @Slot(str)
    def navigate(self, page: str) -> None:
        if self._locked:
            return
        if page == "followed":
            page = "watchlist"
        if page == "current" and not self._game_detected:
            return
        if page not in {"overview", "search", "watchlist", "current", "settings"}:
            return
        if self._page != page:
            self._page = page
            self.pageChanged.emit()
        self._record_activity()

    @Slot(str)
    def submitPin(self, pin: str) -> None:
        if self._resetting:
            return
        if not re.fullmatch(r"[0-9]{4}", pin or ""):
            self._set_pin_error("Enter four digits")
            return
        now = time.monotonic()
        if now < self._retry_after:
            wait = max(1, int(self._retry_after - now) + 1)
            self._set_pin_error(f"Try again in {wait}s")
            return

        if not self._has_passcode:
            self._handle_pin_setup(pin)
            return

        try:
            unlocked = bool(self._vault and self._vault.unlock(pin))
        except Exception:
            unlocked = False
        if unlocked:
            self._failed_attempts = 0
            self._retry_after = 0.0
            self._set_pin_error("")
            self._set_locked(False)
            self._last_activity = time.monotonic()
            self._refresh_owned_secret_flags()
            self._load_sensitive_configuration()
            self._notify("Unlocked")
            return

        # SecretVault persists its own backoff across launches.  Mirror that
        # state in the controller so the UI cannot immediately hammer unlock()
        # again, while retaining the local fallback for injected test vaults.
        vault_retry = 0.0
        with suppress(Exception):
            vault_retry = float(getattr(self._vault, "retry_after", 0.0))
        vault_attempts = 0
        with suppress(Exception):
            vault_attempts = int(getattr(self._vault, "failed_attempts", 0))
        self._failed_attempts += 1
        self._failed_attempts = max(self._failed_attempts, vault_attempts)
        local_delay = (
            min(30, 2 ** max(0, self._failed_attempts - 2))
            if self._failed_attempts >= 3
            else 0
        )
        delay = max(local_delay, vault_retry)
        self._retry_after = time.monotonic() + delay
        suffix = f" · wait {delay}s" if delay else ""
        self._set_pin_error(f"Incorrect passcode{suffix}")

    def _handle_pin_setup(self, pin: str) -> None:
        if self._pin_mode == "create":
            self._pending_pin = pin
            self._pin_mode = "confirm"
            self.pinModeChanged.emit()
            self._set_pin_error("")
            return
        if self._pending_pin != pin:
            self._pending_pin = None
            self._pin_mode = "create"
            self.pinModeChanged.emit()
            self._set_pin_error("Passcodes did not match. Start again.")
            return
        try:
            if self._vault is None:
                raise RuntimeError("Secure vault is unavailable")
            setup = getattr(self._vault, "setup_pin", None) or getattr(
                self._vault, "initialize", None
            )
            if setup is None:
                raise RuntimeError("Secure vault cannot be initialized")
            setup(pin)
            # Vault implementations normally remain unlocked after setup; use
            # unlock as a compatibility step when they do not.
            unlocker = getattr(self._vault, "unlock", None)
            if callable(unlocker):
                unlocked = unlocker(pin)
                if unlocked is False and not bool(getattr(self._vault, "is_unlocked", False)):
                    raise RuntimeError("Secure vault did not unlock after setup")
        except Exception:
            self._set_pin_error("Could not create the local vault")
            return
        finally:
            self._pending_pin = None
        self._has_passcode = True
        self.hasPasscodeChanged.emit()
        self._pin_mode = "unlock"
        self.pinModeChanged.emit()
        self._set_pin_error("")
        self._set_locked(False)
        self._last_activity = time.monotonic()
        self._refresh_owned_secret_flags()
        self._notify("Passcode created")

    @Slot()
    def lockNow(self) -> None:
        qr_approver = self._qr_approver
        self._qr_approver = None
        if qr_approver is not None:
            close = getattr(qr_approver, "close", None)
            if callable(close):
                with suppress(Exception):
                    close()
        if not self._has_passcode:
            return
        self._lock_epoch += 1
        self._qr_attempt += 1
        if self._vault is not None:
            with suppress(Exception):
                self._vault.lock()
        clear_api_key = getattr(self._provider, "clear_api_key", None)
        if callable(clear_api_key):
            with suppress(Exception):
                clear_api_key()

        # Clear all transient sensitive state before notifying QML that the
        # lock screen is active.  The property getters also hide this data,
        # but clearing the backing values prevents late callbacks or a later
        # unlock from seeing stale QR/current-game details.
        self._pending_qr_private.clear()
        self._pending_qr_bootstrap.clear()
        self._pending_qr = {}
        self._set_qr_prompt(False)
        self._clipboard_epoch += 1
        code = self._clipboard_totp_code
        self._clipboard_totp_code = None
        if code:
            with suppress(Exception):
                clipboard = QGuiApplication.clipboard()
                if clipboard is not None and clipboard.text() == code:
                    clipboard.clear()

        had_match = bool(self._current_match) or self._game_detected
        self._current_match = {}
        self._game_detected = False
        if had_match:
            self.currentMatchChanged.emit()
            self.gameDetectedChanged.emit()
        # These are derived UI hints, never persisted account state.  Drop the
        # backing values while locked so an eventual unlock must re-check the
        # encrypted vault instead of inheriting stale flags.
        for account in self._accounts:
            if account.get("owned", True):
                account["connected"] = False
                account["totpAvailable"] = False
        self._set_locked(True)
        if self._search_busy:
            self._search_busy = False
            self.searchBusyChanged.emit()
        if self._account_refresh_busy:
            self._account_refresh_busy = False
            self.accountRefreshBusyChanged.emit()
        self._set_detection_busy(False)
        self._set_qr_busy(False)
        self._selected_account = {}
        self.selectedAccountChanged.emit()
        self._search_results = []
        self.searchResultsChanged.emit()

    @Slot()
    def recordActivity(self) -> None:
        self._record_activity()

    @Slot()
    def resetApplication(self) -> None:
        """Erase Peaks' local profile after the QML double confirmation."""

        if self._resetting or not self._locked or not self._has_passcode:
            return
        self._resetting = True
        self._lock_timer.stop()
        self._detection_timer.stop()
        self._lock_epoch += 1
        self._qr_attempt += 1
        self._set_pin_error("Preparing secure reset…")

        # Remove queued work; running jobs retain bounded network timeouts and
        # are allowed to finish before any credential files are deleted.
        for worker in tuple(self._workers):
            if self._thread_pool.tryTake(worker):
                self._workers.discard(worker)
        self._continue_profile_reset()

    def _continue_profile_reset(self) -> None:
        if self._workers:
            QTimer.singleShot(100, self._continue_profile_reset)
            return
        self._perform_profile_reset()

    def _perform_profile_reset(self) -> None:
        profile_dir = self._profile_dir
        if profile_dir is None:
            repository_path = getattr(self._repository, "path", None)
            vault_path = getattr(self._vault, "path", None)
            candidate = repository_path or vault_path
            if candidate is not None:
                profile_dir = Path(candidate).parent
        if profile_dir is None:
            self._resetting = False
            self._set_pin_error("Reset is unavailable for this profile")
            return

        from peaks.adapters.persistence.database import Database
        from peaks.adapters.persistence.profile_reset import (
            begin_profile_reset,
            clear_profile_files,
        )
        from peaks.adapters.persistence.secret_vault import SecretVault

        marker: Path | None = None
        try:
            marker = begin_profile_reset(profile_dir)
            for service in (self._provider, self._qr_approver, self._game_detector):
                close = getattr(service, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()
            destroy_repository = getattr(self._repository, "destroy", None)
            if callable(destroy_repository):
                destroy_repository()
            else:
                close_repository = getattr(self._repository, "close", None)
                if callable(close_repository):
                    close_repository()
            destroy_vault = getattr(self._vault, "destroy", None)
            if callable(destroy_vault):
                destroy_vault()
            else:
                lock_vault = getattr(self._vault, "lock", None)
                if callable(lock_vault):
                    lock_vault()
            clear_profile_files(profile_dir, keep_marker=True)

            self._repository = (
                self._repository_factory(profile_dir / "peaks.sqlite3")
                if self._repository_factory is not None
                else Database(profile_dir / "peaks.sqlite3")
            )
            self._vault = (
                self._vault_factory(profile_dir / "vault.json")
                if self._vault_factory is not None
                else SecretVault(profile_dir / "vault.json")
            )
            self._reset_controller_state()
            with suppress(FileNotFoundError):
                marker.unlink()
            self._resetting = False
            self._lock_timer.start()
            self._detection_timer.start()
        except Exception:
            # The marker makes deletion idempotent on the next launch. Quit
            # instead of presenting a half-reset profile as successful.
            self._set_pin_error("Reset will finish when Peaks restarts")
            self.resetRequested.emit()

    def _reset_controller_state(self) -> None:
        self._accounts = []
        self._followed = []
        self._search_history = []
        self._search_results = []
        self._selected_account = {}
        self._current_match = {}
        self._game_detected = False
        self._set_detection_busy(False)
        self._set_qr_busy(False)
        self._pending_qr = {}
        self._pending_qr_private = {}
        self._pending_qr_bootstrap = {}
        self._qr_approver = None
        self._view_mode = "grid"
        self._settings = {
            "autoLockMinutes": 15,
            "lockOnBlur": True,
            "reduceMotion": False,
            "riotApiConfigured": False,
            "streamerModeRequired": True,
            "clipboardClearSeconds": 15,
        }
        self._has_passcode = False
        self._pin_mode = "create"
        self._pending_pin = None
        self._failed_attempts = 0
        self._retry_after = 0.0
        self._set_pin_error("")
        self.hasPasscodeChanged.emit()
        self.pinModeChanged.emit()
        self.accountsChanged.emit()
        self.followedChanged.emit()
        self.searchHistoryChanged.emit()
        self.searchResultsChanged.emit()
        self.selectedAccountChanged.emit()
        self.currentMatchChanged.emit()
        self.gameDetectedChanged.emit()
        self.viewModeChanged.emit()
        self.settingsChanged.emit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in {
            QEvent.Type.KeyPress,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
            QEvent.Type.TouchBegin,
        }:
            self._record_activity()
        return super().eventFilter(watched, event)

    # ---- Accounts ------------------------------------------------------
    @Slot(str)
    def setViewMode(self, mode: str) -> None:
        if mode not in {"grid", "list"} or mode == self._view_mode:
            return
        self._view_mode = mode
        self._settings["viewMode"] = mode
        self.viewModeChanged.emit()
        self.settingsChanged.emit()
        self._persist_setting("layout", mode)

    @Slot(str)
    def selectAccount(self, account_id: str) -> None:
        # Search and Followed identities use the same detail surface as owned
        # accounts, but remain read-only remote snapshots.  Keeping the
        # lookup here (rather than copying search results into ``_accounts``)
        # preserves ownership and prevents a searched player from becoming a
        # local Connect target accidentally.
        account = next((item for item in self._accounts if item.get("id") == account_id), None)
        if account is None:
            account = next((item for item in self._followed if item.get("id") == account_id), None)
        if account is None:
            account = next((item for item in self._search_results if item.get("id") == account_id), None)
        if account is None:
            return
        self._selected_account = deepcopy(account)
        self.selectedAccountChanged.emit()
        self._record_activity()

    @Slot()
    def closeAccount(self) -> None:
        self._selected_account = {}
        self.selectedAccountChanged.emit()

    @Slot(str, str, str, str)
    def addAccount(self, game_name: str, tag_line: str, region: str, seed: str) -> None:
        game_name = game_name.strip()
        tag_line = tag_line.strip().lstrip("#")
        riot_id = f"{game_name}#{tag_line}"
        if not _RIOT_ID_RE.fullmatch(riot_id):
            self._notify("Use a Riot ID like Player#TAG")
            return
        account_id = str(uuid.uuid4())
        account = {
            "id": account_id,
            "riotId": riot_id,
            "region": region or "EUW",
            "owned": True,
            "connected": False,
            "initials": (game_name[:2] or "RI").upper(),
            "accent": "#A8CEFF",
            "lastUpdated": "not synced",
            "totpAvailable": bool(seed.strip()),
            "ranks": [
                {"game": "League", "tier": "Unranked", "rating": "—", "peak": "—", "icon": ""},
                {"game": "VALORANT", "tier": "Unranked", "rating": "—", "peak": "—", "icon": ""},
            ],
            "matches": [],
        }
        if seed.strip():
            try:
                from peaks.adapters.riot.totp import extract_seed

                normalized_seed = extract_seed(seed)
                if not normalized_seed:
                    raise ValueError
                self._vault_set(account_id, "totp", normalized_seed)
            except Exception:
                self._notify("That TOTP secret or otpauth link is not valid")
                return
        self._accounts.insert(0, account)
        self._attach_asset_urls()
        self.accountsChanged.emit()
        self._persist_account(account)
        if self._provider and self._settings.get("riotApiConfigured"):
            self.refreshAccounts()
        self._notify("Account added locally")

    @Slot()
    def refreshAccounts(self) -> None:
        if self._locked or self._account_refresh_busy:
            return
        if self._demo:
            for item in self._accounts:
                item["lastUpdated"] = "just now"
            self.accountsChanged.emit()
            self._notify("Account snapshots refreshed")
            return
        overview = getattr(self._provider, "account_overview", None) if self._provider else None
        remote_enabled = bool(self._settings.get("riotApiConfigured")) and callable(overview)
        local_rank = getattr(self._game_detector, "owned_valorant_rank", None)
        local_enabled = callable(local_rank)
        local_rank_callable = cast(Callable[[str], Any], local_rank)
        if not remote_enabled and not local_enabled:
            if self._provider and not self._settings.get("riotApiConfigured"):
                self._notify(
                    "Remote League/TFT refresh is optional; connect a Windows Riot Client for VALORANT rank"
                )
            elif self._provider:
                self._notify("Account refresh is unavailable for this provider")
            else:
                self._notify(
                    "Add a Riot API key for League/TFT, or connect a Windows Riot Client for VALORANT rank"
                )
            return

        # Copy the small metadata records before dispatching work.  The worker
        # never receives the vault, API key, or any other private state.
        accounts = [deepcopy(account) for account in self._accounts if account.get("owned", True)]
        if not accounts:
            self._notify("No owned accounts to refresh")
            return
        self._account_refresh_busy = True
        self.accountRefreshBusyChanged.emit()
        self._notify(
            "Refreshing account snapshots…"
            if remote_enabled
            else "Checking the signed-in Windows Riot Client for VALORANT rank…"
        )

        def work() -> list[tuple[str, Any, Exception | None, bool]]:
            refreshed: list[tuple[str, Any, Exception | None, bool]] = []
            for account in accounts:
                account_id = str(account.get("id", ""))
                value: Any = None
                account_error: Exception | None = None
                local_only = not remote_enabled
                if remote_enabled:
                    try:
                        value = self._call_account_overview(cast(Callable[..., Any], overview), account)
                    except Exception as exc:
                        # Keep one failed account from hiding successful snapshots.
                        account_error = exc

                # A local rank is queried only for an explicitly stored PUUID.
                # The detector performs the second, authoritative equality
                # check against the active Riot entitlement subject.
                if local_enabled:
                    puuid = account.get("puuid")
                    if isinstance(puuid, str) and puuid:
                        try:
                            local_value = local_rank_callable(puuid)
                        except Exception as exc:
                            local_value = None
                            if account_error is None and not remote_enabled:
                                account_error = exc
                        if local_value is not None:
                            value = self._merge_local_valorant_rank(value, local_value)
                            # A local match is useful even when remote
                            # League/TFT refresh failed for this account.
                            account_error = None
                    elif not remote_enabled:
                        account_error = RuntimeError("account PUUID is unavailable")

                refreshed.append((account_id, value, account_error, local_only))
            return refreshed

        self._run_worker(work, self._finish_account_refresh)

    @staticmethod
    def _call_account_overview(overview: Callable[..., Any], account: dict[str, Any]) -> Any:
        """Call provider account_overview with either account or named fields.

        Provider adapters in early builds accepted the complete account view;
        newer adapters generally accept ``account_id``/``puuid``/``region``.
        Signature inspection keeps this compatibility path deterministic and
        avoids catching TypeError raised inside the provider itself.
        """

        with suppress(ValueError, TypeError):
            parameters = list(signature(overview).parameters.values())
            if any(parameter.kind == parameter.VAR_KEYWORD for parameter in parameters):
                return overview(
                    account_id=str(account.get("id", "")),
                    puuid=account.get("puuid"),
                    region=str(account.get("region", "EUW")),
                )
            if len(parameters) == 1:
                name = parameters[0].name.casefold()
                if name in {"account", "account_view", "record"}:
                    return overview(account)
                if name in {"accounts", "owned_accounts", "account_views"}:
                    return overview([account])
                if name in {"account_id", "id", "puuid", "player_id"}:
                    return overview(str(account.get("id", "")))
            if parameters:
                kwargs = {
                    parameter.name: {
                        "account_id": str(account.get("id", "")),
                        "puuid": account.get("puuid"),
                        "region": str(account.get("region", "EUW")),
                        "riot_id": account.get("riotId", ""),
                    }.get(parameter.name, account)
                    for parameter in parameters
                    if parameter.kind
                    in {parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY}
                    and parameter.name in {"account_id", "puuid", "region", "riot_id"}
                }
                if kwargs:
                    return overview(**kwargs)
        return overview(account)

    def _finish_account_refresh(
        self,
        result: list[tuple[str, Any, Exception | None, bool]],
        error: Exception | None,
    ) -> None:
        self._account_refresh_busy = False
        self.accountRefreshBusyChanged.emit()
        if error is not None:
            self._notify(self._safe_error(error, "Account refresh failed"))
            return
        updated = 0
        failures = 0
        local_only_failures = False
        local_only_success = False
        for account_id, value, account_error, local_only in result:
            if account_error is not None or value is None:
                failures += 1
                local_only_failures = local_only_failures or local_only
                continue
            local = next((item for item in self._accounts if item.get("id") == account_id), None)
            if local is None:
                continue
            merged = self._merge_account_snapshot(local, value)
            merged["lastUpdated"] = (
                "Riot Client · just now" if local_only else "just now"
            )
            local_only_success = local_only_success or local_only
            local.clear()
            local.update(merged)
            self._persist_account(local)
            self._persist_matches(account_id, value)
            updated += 1
            if self._selected_account.get("id") == account_id:
                self._selected_account = deepcopy(local)
        self._attach_asset_urls()
        if updated:
            self.accountsChanged.emit()
            if self._selected_account:
                self.selectedAccountChanged.emit()
        if updated and failures:
            self._notify(f"Refreshed {updated} account(s) · {failures} unavailable")
        elif updated:
            self._notify(
                f"Updated local VALORANT rank for {updated} account(s)"
                if local_only_success
                else f"Refreshed {updated} account(s)"
            )
        elif failures:
            self._notify(
                "No matching signed-in Windows Riot Client account found"
                if local_only_failures
                else "Account refresh failed for all accounts"
            )
        else:
            self._notify("No account snapshots changed")

    @staticmethod
    def _merge_local_valorant_rank(value: Any, rank: Any) -> dict[str, Any]:
        """Add one successful local VALORANT rank without dropping cached data."""

        remote = value.to_dict() if hasattr(value, "to_dict") else AppController._plain_dict(value)
        snapshot = remote if isinstance(remote, dict) else {}
        ranks = snapshot.get("ranks")
        rank_views = list(ranks) if isinstance(ranks, (list, tuple)) else []
        rank_data = rank.to_dict() if hasattr(rank, "to_dict") else AppController._plain_dict(rank)
        if not isinstance(rank_data, dict):
            rank_data = {}
        rank_views.append(
            {
                "game": "valorant",
                "tier": rank_data.get("name") or "Unranked",
                "rating": rank_data.get("rr"),
                "peak_tier": rank_data.get("peak_name") or rank_data.get("name") or "Unranked",
            }
        )
        snapshot["ranks"] = rank_views
        return snapshot

    def _merge_account_snapshot(self, local: dict[str, Any], value: Any) -> dict[str, Any]:
        """Merge provider data while preserving local identity and secret flags."""

        if isinstance(value, (list, tuple)):
            value = value[0] if len(value) == 1 else {}
        remote = value.to_dict() if hasattr(value, "to_dict") else self._plain_dict(value)
        if not isinstance(remote, dict):
            return deepcopy(local)
        merged = deepcopy(local)
        # Identity is local-owned.  A provider may refresh the current Riot ID,
        # but it must never replace the stable local key or ownership marker.
        game_name = remote.get("game_name", remote.get("gameName"))
        tag_line = remote.get("tag_line", remote.get("tagLine"))
        if game_name:
            merged["riotId"] = f"{game_name}#{tag_line}" if tag_line else str(game_name)
            merged["initials"] = str(game_name)[:2].upper()
        elif remote.get("riotId"):
            merged["riotId"] = str(remote["riotId"])
        if remote.get("puuid"):
            merged["puuid"] = remote["puuid"]
        ranks = remote.get("ranks") or remote.get("rank")
        if isinstance(ranks, dict):
            ranks = [ranks]
        if ranks:
            merged["ranks"] = self._merge_rank_views(merged.get("ranks", []), ranks)
        matches = remote.get("matches") or remote.get("match_history")
        if matches:
            merged["matches"] = [self._match_view(match) for match in matches]
        if remote.get("last_seen_at") or remote.get("lastUpdated"):
            merged["lastUpdated"] = remote.get("lastUpdated") or self._relative_time(
                remote.get("last_seen_at")
            )
        # These fields are intentionally not assigned from provider output:
        # ``id``, ``owned``, ``connected``, and ``totpAvailable`` are local.
        return merged

    def _persist_matches(self, account_id: str, value: Any) -> None:
        """Persist provider match DTOs when the repository supports matches."""

        if self._repository is None:
            return
        add_match = getattr(self._repository, "add_match", None)
        if not callable(add_match):
            return
        remote = value.to_dict() if hasattr(value, "to_dict") else self._plain_dict(value)
        matches = remote.get("matches") or remote.get("match_history") if isinstance(remote, dict) else None
        if not matches:
            return
        from peaks.domain.models import MatchRecord

        for match in matches:
            try:
                if isinstance(match, MatchRecord):
                    candidate = match
                else:
                    normalized = dict(match)
                    normalized["account_id"] = account_id
                    candidate = MatchRecord.from_dict(normalized)
                if candidate.account_id != account_id:
                    continue
                add_match(candidate)
            except Exception:
                # A partial provider response must not make a rank snapshot
                # appear failed, and exception text may contain private data.
                continue

    @classmethod
    def _merge_rank_views(cls, local_ranks: Any, remote_ranks: Any) -> list[dict[str, Any]]:
        views = [cls._rank_view(rank) for rank in local_ranks or []]
        by_game = {str(rank.get("game", "")).casefold(): index for index, rank in enumerate(views)}
        for rank in remote_ranks:
            view = cls._rank_view(rank)
            key = str(view.get("game", "")).casefold()
            if key in by_game:
                views[by_game[key]] = view
            else:
                by_game[key] = len(views)
                views.append(view)
        # Overview always promises League and VALORANT cards, even if the
        # provider only supplied a TFT snapshot.
        if "league" not in by_game:
            views.insert(0, cls._rank_view({"game": "league_of_legends"}))
        if "valorant" not in {str(rank.get("game", "")).casefold() for rank in views}:
            views.append(cls._rank_view({"game": "valorant"}))
        return views

    # ---- Search and followed ------------------------------------------
    @Slot(str, str, str)
    def runSearch(self, query: str, region: str, game: str) -> None:
        if self._locked or self._search_busy:
            return
        query = query.strip()
        if not _RIOT_ID_RE.fullmatch(query):
            self._notify("Enter a complete Riot ID: Player#TAG")
            return
        self._add_search_history(query, region, game)
        if self._demo:
            self._search_results = search_demo(query, region, game)
            self.searchResultsChanged.emit()
            return
        if self._provider is None:
            self._search_results = []
            self.searchResultsChanged.emit()
            self._notify("Live search needs a Riot Developer API key in Settings")
            return
        self._search_busy = True
        self.searchBusyChanged.emit()

        def work() -> Any:
            search = getattr(self._provider, "search_player", None) or getattr(
                self._provider, "search", None
            )
            if search is None:
                raise RuntimeError("Search provider is unavailable")
            return search(query, region=region, game=game)

        self._run_worker(work, self._finish_search)

    def _finish_search(self, result: Any, error: Exception | None) -> None:
        self._search_busy = False
        self.searchBusyChanged.emit()
        if error is not None:
            self._notify(self._safe_error(error, "Search failed"))
            return
        records = result if isinstance(result, list) else [result]
        self._search_results = [self._plain_dict(item) for item in records if item]
        self.searchResultsChanged.emit()

    @Slot(str)
    def toggleWatchlist(self, result_id: str) -> None:
        existing = next((item for item in self._followed if item.get("id") == result_id), None)
        if existing:
            self._followed = [item for item in self._followed if item.get("id") != result_id]
            for item in self._search_results:
                if item.get("id") == result_id:
                    item["followed"] = False
            self._repository_call(("remove_followed", "unfollow"), result_id)
            self._notify("Removed from Watchlist")
        else:
            source = next(
                (item for item in self._search_results if item.get("id") == result_id), None
            )
            if source is None:
                return
            followed = deepcopy(source)
            followed["followed"] = True
            self._followed.insert(0, followed)
            source["followed"] = True
            self._persist_followed(followed)
            self._notify("Added to Watchlist")
        self.followedChanged.emit()
        self.searchResultsChanged.emit()

    @Slot(str)
    def toggleFollow(self, result_id: str) -> None:
        """Compatibility alias for the previous QML action name."""

        self.toggleWatchlist(result_id)

    @Slot()
    def clearSearchHistory(self) -> None:
        self._search_history.clear()
        self.searchHistoryChanged.emit()
        self._repository_call(("clear_search_history",))
        self._notify("Search history cleared")

    # ---- Settings ------------------------------------------------------
    @Slot(int)
    def setAutoLock(self, minutes: int) -> None:
        if minutes not in {0, 1, 5, 15, 30}:
            return
        self._settings["autoLockMinutes"] = minutes
        self.settingsChanged.emit()
        self._persist_setting("lock_timeout_minutes", minutes)
        self._record_activity()

    @Slot(bool)
    def setLockOnBlur(self, enabled: bool) -> None:
        self._settings["lockOnBlur"] = enabled
        self.settingsChanged.emit()
        self._persist_setting("lock_on_blur", enabled)

    @Slot(bool)
    def setReduceMotion(self, enabled: bool) -> None:
        self._settings["reduceMotion"] = enabled
        self.settingsChanged.emit()
        self._persist_setting("reduce_motion", enabled)

    @Slot(str)
    def setRiotApiKey(self, api_key: str) -> None:
        api_key = api_key.strip()
        if not api_key:
            self._notify("Paste a Riot Developer API key first")
            return
        try:
            self._vault_set("integration", "riot_api_key", api_key)
        except Exception:
            self._notify("Could not store the API key securely")
            return
        self._settings["riotApiConfigured"] = True
        self.settingsChanged.emit()
        if self._provider and hasattr(self._provider, "set_api_key"):
            self._provider.set_api_key(api_key)
        self._notify("API key stored in the encrypted vault")

    # ---- QR and TOTP connect actions ----------------------------------
    @Slot(str)
    def copyTotp(self, account_id: str) -> None:
        if self._locked:
            return
        try:
            seed = self._vault_get(account_id, "totp")
            if not seed:
                raise ValueError("No TOTP configured")
            from peaks.adapters.riot.totp import get_code

            code = get_code(seed)
        except Exception:
            self._notify("No TOTP is available for this account")
            return
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(code)
        clear_after = int(self._settings.get("clipboardClearSeconds", 15))
        self._clipboard_epoch += 1
        clipboard_epoch = self._clipboard_epoch
        self._clipboard_totp_code = code

        def clear_if_unchanged() -> None:
            if clipboard_epoch != self._clipboard_epoch:
                return
            if clipboard.text() == code:
                clipboard.clear()
            self._clipboard_totp_code = None

        QTimer.singleShot(clear_after * 1_000, clear_if_unchanged)
        self._notify(f"TOTP copied · clears in {clear_after}s")

    @Slot(str)
    def importCurrentRiotSession(self, account_id: str) -> None:
        self._begin_session_import(account_id, continue_qr=False)

    def _begin_session_import(self, account_id: str, *, continue_qr: bool) -> None:
        """Import the active Windows Riot Client session for one account.

        The importer and its network session live entirely inside the worker.
        The short-lived access token is used to fetch authoritative identity,
        then discarded; only an allowlisted cookie bundle is persisted in the
        encrypted vault.  This action is deliberately explicit because the
        underlying Riot Client interfaces are private and undocumented.
        """

        if self._locked or self._qr_busy:
            return
        account = next((item for item in self._accounts if item.get("id") == account_id), None)
        if account is None:
            self._notify("Select an owned account before importing a session")
            return
        if not account.get("owned", True):
            self._notify("Only owned accounts can import a Riot Client session")
            return

        account_snapshot = deepcopy(account)
        self._qr_attempt += 1
        attempt = self._qr_attempt
        if continue_qr:
            self._pending_qr_bootstrap = {"accountId": account_id, "attempt": attempt}
        else:
            self._pending_qr_bootstrap.clear()
        self._set_qr_busy(True)
        if continue_qr:
            self._notify(
                "No saved Riot session. Importing your active Riot Client session on Windows…"
            )
        else:
            self._notify("Importing the current Riot Client session…")

        def work() -> tuple[Any, Any]:
            importer = self._new_session_importer()
            try:
                imported = importer.import_current_session()
                fetch_identity = getattr(importer, "fetch_identity", None)
                if not callable(fetch_identity):
                    raise RuntimeError("Riot account identity is unavailable")
                identity = fetch_identity(imported.access_token)
                self._validate_imported_session(account_snapshot, imported, identity)
                return imported, identity
            finally:
                close = getattr(importer, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()

        self._run_worker(
            work,
            lambda result, error: self._finish_session_import(
                account_id, attempt, result, error
            ),
        )

    def _new_session_importer(self) -> Any:
        factory = self._session_importer_factory
        if factory is not None:
            return factory()
        from peaks.adapters.riot.session_import import RiotSessionImporter

        return RiotSessionImporter()

    @staticmethod
    def _validate_imported_session(
        account: Mapping[str, Any], imported: Any, identity: Any
    ) -> None:
        imported_puuid = str(getattr(imported, "puuid", "") or "").strip()
        identity_puuid = str(getattr(identity, "puuid", "") or "").strip()
        if not imported_puuid or not identity_puuid:
            raise _SessionImportBindingError("Riot session identity could not be verified")
        if imported_puuid.casefold() != identity_puuid.casefold():
            raise _SessionImportBindingError("Riot session identity could not be verified")

        stored_puuid = str(account.get("puuid") or "").strip()
        if stored_puuid and stored_puuid.casefold() != identity_puuid.casefold():
            raise _SessionImportBindingError("This Riot session belongs to a different account")

        game_name, tag_line = AppController._split_riot_id(str(account.get("riotId", "")))
        returned_name = getattr(identity, "game_name", None)
        returned_tag = getattr(identity, "tag_line", None)
        if (
            isinstance(returned_name, str)
            and returned_name.strip()
            and returned_name.strip().casefold() != game_name.strip().casefold()
        ):
            raise _SessionImportBindingError("The Riot session does not match this account")
        if isinstance(returned_tag, str) and returned_tag.strip():
            normalized_tag = returned_tag.strip().lstrip("#")
            if normalized_tag.casefold() != tag_line.strip().lstrip("#").casefold():
                raise _SessionImportBindingError("The Riot session does not match this account")

    @staticmethod
    def _serialize_session_cookies(imported: Any) -> str:
        from peaks.adapters.riot.session_import import ALLOWED_COOKIE_NAMES

        cookies = getattr(imported, "cookies", None)
        if not isinstance(cookies, Mapping):
            raise ValueError("Riot session cookies are unavailable")
        sanitized: dict[str, str] = {}
        for name, value in cookies.items():
            if not isinstance(name, str) or name not in ALLOWED_COOKIE_NAMES:
                raise ValueError("Riot session cookies are invalid")
            if not isinstance(value, str) or not value:
                raise ValueError("Riot session cookies are invalid")
            sanitized[name] = value
        if "ssid" not in sanitized:
            raise ValueError("Riot session cookies are incomplete")
        return json.dumps(sanitized, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    def _finish_session_import(
        self,
        account_id: str,
        attempt: int,
        result: Any,
        error: Exception | None,
    ) -> None:
        if self._locked or attempt != self._qr_attempt:
            return
        self._set_qr_busy(False)
        bootstrap_pending = self._pending_qr_bootstrap == {
            "accountId": account_id,
            "attempt": attempt,
        }
        if error is not None:
            if bootstrap_pending:
                self._pending_qr_bootstrap.clear()
            self._notify(self._safe_error(error, "Could not import the Riot Client session"))
            return
        try:
            imported, identity = result
            cookie_json = self._serialize_session_cookies(imported)
            puuid = str(getattr(identity, "puuid", "") or "").strip()
            if not puuid:
                raise _SessionImportBindingError("Riot session identity could not be verified")
            self._vault_set(account_id, "riot_session_cookies", cookie_json)
        except _SessionImportBindingError as exc:
            if bootstrap_pending:
                self._pending_qr_bootstrap.clear()
            self._notify(str(exc))
            return
        except Exception:
            if bootstrap_pending:
                self._pending_qr_bootstrap.clear()
            self._notify("Could not save the Riot Client session securely")
            return

        for account in self._accounts:
            if account.get("id") != account_id:
                continue
            account["puuid"] = puuid
            account["connected"] = True
            self._persist_account(account)
            if self._selected_account.get("id") == account_id:
                self._selected_account = deepcopy(account)
                self.selectedAccountChanged.emit()
            break
        self.accountsChanged.emit()
        if bootstrap_pending:
            self._pending_qr_bootstrap.clear()
            self._notify("Riot session ready. Looking for a QR code to approve…")
            # The import was explicitly initiated by the primary Connect
            # click.  Resume only QR capture; approval still requires the
            # separate, visible confirmation prompt.
            self.scanRiotQr(account_id)
        else:
            self._notify("Riot Client session imported securely")

    def _load_session_cookies(self, account_id: str) -> dict[str, str] | None:
        """Load and structurally validate the encrypted cookie bundle."""

        raw = self._vault_get(account_id, "riot_session_cookies")
        if not raw:
            return None
        try:
            decoded = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("saved Riot session is invalid") from exc
        if not isinstance(decoded, dict):
            raise ValueError("saved Riot session is invalid")
        from peaks.adapters.riot.session_import import ALLOWED_COOKIE_NAMES

        cookies: dict[str, str] = {}
        for name, value in decoded.items():
            if not isinstance(name, str) or name not in ALLOWED_COOKIE_NAMES:
                raise ValueError("saved Riot session is invalid")
            if not isinstance(value, str) or not value:
                raise ValueError("saved Riot session is invalid")
            cookies[name] = value
        if "ssid" not in cookies:
            raise ValueError("saved Riot session is incomplete")
        return cookies

    def _needs_qr_session_bootstrap(
        self, account_id: str, account: Mapping[str, Any]
    ) -> bool:
        """Return whether Connect needs an explicit Windows session import.

        Legacy profiles may still have a stored short-lived token, so keep
        that read-only compatibility path.  New profiles use encrypted
        cookies and refresh a token only when the QR request is inspected.
        """

        if self._demo:
            return False
        if not str(account.get("puuid") or "").strip():
            return True
        try:
            if self._load_session_cookies(account_id) is not None:
                return False
        except Exception:
            # A malformed or unreadable saved session must be replaced by an
            # explicit local import; never fall through to a dead-end QR scan.
            return True
        with suppress(Exception):
            if self._vault_get(account_id, "riot_access_token"):
                return False
        return True

    @Slot(str)
    def scanRiotQr(self, account_id: str) -> None:
        if self._locked or self._qr_busy:
            return
        account = next((item for item in self._accounts if item.get("id") == account_id), None)
        if account is None:
            self._notify("Select an owned account before connecting")
            return
        if not account.get("owned", True):
            self._notify("Only owned accounts can connect a Riot Client")
            return
        if self._needs_qr_session_bootstrap(account_id, account):
            # The primary Connect click is the explicit consent to read the
            # current local Riot Client session.  No QR approval is performed
            # here; after import, only capture resumes and the user still
            # confirms the pending login in the prompt.
            self._begin_session_import(account_id, continue_qr=True)
            return
        self._qr_attempt += 1
        attempt = self._qr_attempt
        self._set_qr_busy(True)
        self._notify("Looking for a QR code in the Riot Client window…")
        # Yield once so the loading state can paint before the potentially
        # expensive Windows window capture starts.  Capture and decode remain
        # in the same bounded worker, keeping the GUI thread responsive.
        QTimer.singleShot(0, lambda: self._start_qr_capture(account_id, attempt))

    def _start_qr_capture(self, account_id: str, attempt: int) -> None:
        if self._locked or attempt != self._qr_attempt:
            self._set_qr_busy(False)
            return

        def capture_and_decode() -> str | None:
            screenshots = capture_riot_client_windows()
            return decode_qr_images(screenshots)

        self._run_worker(
            capture_and_decode,
            lambda payload, error: self._qr_decoded(
                account_id, payload, error, attempt=attempt
            ),
        )

    @Slot(str)
    def pasteQrScreenshot(self, account_id: str) -> None:
        if self._locked or self._qr_busy:
            return
        self._qr_attempt += 1
        attempt = self._qr_attempt
        self._set_qr_busy(True)
        self._qr_decoded(account_id, decode_clipboard_image(), None, attempt=attempt)

    def _qr_decoded(
        self,
        account_id: str,
        payload: Any,
        error: Exception | None,
        *,
        attempt: int | None = None,
    ) -> None:
        if attempt is None:
            self._qr_attempt += 1
            attempt = self._qr_attempt
        if self._locked or attempt != self._qr_attempt:
            return
        if error is not None or not payload:
            self._set_qr_busy(False)
            self._notify("No readable QR code was found")
            return
        try:
            from peaks.adapters.riot.qr import parse_riot_qr

            parsed = parse_riot_qr(str(payload))
        except Exception:
            self._set_qr_busy(False)
            self._notify("The image does not contain a valid Riot sign-in QR")
            return
        account = next((item for item in self._accounts if item.get("id") == account_id), None)
        if account is None:
            self._set_qr_busy(False)
            return
        self._pending_qr_private = {
            "accountId": account_id,
            "parsed": parsed,
            "attempt": attempt,
        }
        if self._demo:
            self._pending_qr = {
                "account": account["riotId"],
                "location": "Paris, France",
                "device": "Riot Client · Windows",
                "requested": "just now",
                "warning": "Approving signs this Riot Client into the selected account.",
            }
            self.pendingQrChanged.emit()
            self._set_qr_prompt(True)
            self._set_qr_busy(False)
            return
        puuid = str(account.get("puuid") or "").strip()
        if not puuid:
            self._pending_qr_private.clear()
            self._set_qr_busy(False)
            self._notify(
                "QR Connect needs a saved Riot session for this account; TOTP can still be copied"
            )
            return

        # New sessions retain only encrypted, allowlisted cookies.  Mint a
        # fresh short-lived token inside the worker and keep it solely in the
        # private pending state so the exact same token can approve the QR
        # request after the user confirms the prompt.  A legacy token remains
        # a read-only fallback for profiles created before cookie storage was
        # introduced; new imports never write it.
        try:
            session_cookies = self._load_session_cookies(account_id)
        except Exception:
            self._pending_qr_private.clear()
            self._set_qr_busy(False)
            self._notify("The saved Riot session is invalid; import it again")
            return
        legacy_access_token = None
        if session_cookies is None:
            with suppress(Exception):
                legacy_access_token = self._vault_get(account_id, "riot_access_token")
        if session_cookies is None and not legacy_access_token:
            self._pending_qr_private.clear()
            self._set_qr_busy(False)
            self._notify(
                "QR Connect needs a saved Riot session for this account; TOTP can still be copied"
            )
            return
        self._pending_qr_private.update({"puuid": puuid})
        # Construct the service on the GUI thread before dispatching work so
        # a lock cannot clear it and have a late worker recreate a fresh
        # session after the vault has been sealed.
        approver = self._qr_approval_service()

        def session_info() -> dict[str, Any]:
            importer: Any | None = None
            try:
                if session_cookies is not None:
                    importer = self._new_session_importer()
                    access_token = importer.mint_access_token(session_cookies)
                else:
                    access_token = legacy_access_token
                details = approver.session_info(
                    parsed,
                    access_token=access_token,
                    selected_account_puuid=puuid,
                )
                return {"details": details, "access_token": access_token}
            finally:
                if importer is not None:
                    close = getattr(importer, "close", None)
                    if callable(close):
                        with suppress(Exception):
                            close()

        self._run_worker(
            session_info,
            lambda details, lookup_error: self._finish_qr_session_info(
                account_id, attempt, details, lookup_error
            ),
        )

    def _finish_qr_session_info(
        self, account_id: str, attempt: int, details: Any, error: Exception | None
    ) -> None:
        if self._locked or attempt != self._qr_attempt:
            return
        account = next((item for item in self._accounts if item.get("id") == account_id), None)
        if (
            account is None
            or self._pending_qr_private.get("accountId") != account_id
            or self._pending_qr_private.get("attempt") != attempt
        ):
            return
        if error is not None:
            self._pending_qr_private.clear()
            self._set_qr_busy(False)
            self._notify(self._safe_error(error, "Could not verify the pending Riot sign-in"))
            return
        if not isinstance(details, Mapping):
            self._pending_qr_private.clear()
            self._set_qr_busy(False)
            self._notify("Could not verify the pending Riot sign-in")
            return
        access_token = details.get("access_token")
        session_details = details.get("details")
        if not isinstance(access_token, str) or not access_token:
            self._pending_qr_private.clear()
            self._set_qr_busy(False)
            self._notify("Could not verify the pending Riot sign-in")
            return
        # Never expose this value through the QML-facing pendingQr property.
        self._pending_qr_private["accessToken"] = access_token
        self._show_qr_prompt(account, session_details)

    def _show_qr_prompt(self, account: dict[str, Any], details: Any | None) -> None:
        detail_map = self._plain_dict(details) if details is not None else {}
        self._pending_qr = {
            "account": account["riotId"],
            "location": detail_map.get("location") or "Not provided by Riot",
            "device": detail_map.get("device") or "Riot Client",
            "requested": detail_map.get("requested") or "just now",
            "warning": "Approval signs this Riot Client into the selected owned account.",
        }
        self.pendingQrChanged.emit()
        self._set_qr_prompt(True)
        self._set_qr_busy(False)

    @Slot(bool)
    def confirmQr(self, approve: bool) -> None:
        if self._locked:
            return
        if not self._qr_prompt_open:
            return
        if not approve:
            self._set_qr_busy(False)
            self._pending_qr_private.clear()
            self._set_qr_prompt(False)
            self._notify("QR sign-in cancelled")
            return
        if self._demo:
            account_id = self._pending_qr_private.get("accountId")
            for account in self._accounts:
                if account.get("id") == account_id:
                    account["connected"] = True
            self.accountsChanged.emit()
            self._pending_qr_private.clear()
            self._set_qr_busy(False)
            self._set_qr_prompt(False)
            self._notify("Riot Client connected")
            return
        pending = dict(self._pending_qr_private)
        self._set_qr_prompt(False)
        try:
            account_id = str(pending["accountId"])
            parsed = pending["parsed"]
            access_token = pending.get("accessToken")
            # Compatibility path for old profiles that predate encrypted
            # cookie storage. New imports never persist this short-lived
            # token; they place the freshly minted value in pending state only.
            if not isinstance(access_token, str) or not access_token:
                access_token = self._vault_get(account_id, "riot_access_token")
            from peaks.application.riot_connect import OwnedAccountCredentials

            credentials = OwnedAccountCredentials(
                puuid=str(pending.get("puuid") or "") or None,
                access_token=access_token,
            )
        except Exception:
            self._pending_qr_private.clear()
            self._set_qr_busy(False)
            self._notify("The selected account no longer has usable QR credentials")
            return
        self._pending_qr_private.clear()
        self._notify("Approving the selected Riot Client sign-in…")
        self._set_qr_busy(True)

        # Capture the already-created service.  lockNow() closes and removes
        # it, so this worker can fail safely without creating a new client.
        approver = self._qr_approval_service()

        def approve_qr() -> Any:
            return approver.approve(parsed, credentials, user_approved=True)

        self._run_worker(
            approve_qr,
            lambda result, approval_error: self._finish_qr_approval(
                account_id, result, approval_error
            ),
        )

    def _finish_qr_approval(
        self, account_id: str, result: Any, error: Exception | None
    ) -> None:
        if self._locked:
            return
        if error is not None:
            self._set_qr_busy(False)
            self._notify(self._safe_error(error, "Riot Client sign-in was not approved"))
            return
        for account in self._accounts:
            if account.get("id") == account_id:
                account["connected"] = True
                break
        self.accountsChanged.emit()
        self._set_qr_busy(False)
        self._notify("Riot Client connected")

    def _qr_approval_service(self) -> Any:
        if self._qr_approver is None:
            from peaks.application.riot_connect import RiotQRApprovalService

            self._qr_approver = RiotQRApprovalService()
        return self._qr_approver

    @Slot()
    def closeQrPrompt(self) -> None:
        self.confirmQr(False)

    # ---- Game detection ------------------------------------------------
    @Slot()
    def detectCurrentGame(self) -> None:
        if self._locked or self._detection_busy:
            return
        if self._demo:
            self._game_detected = True
            self.gameDetectedChanged.emit()
            return
        if self._game_detector is None:
            if self._game_detected:
                self._game_detected = False
                self._current_match = {}
                self.gameDetectedChanged.emit()
                self.currentMatchChanged.emit()
            return

        def work() -> Any:
            detect = getattr(self._game_detector, "detect", None) or self._game_detector
            if not callable(detect):
                raise RuntimeError("Game detector is unavailable")
            return detect()

        self._set_detection_busy(True)
        self._run_worker(work, self._finish_detection)

    def _finish_detection(self, result: Any, error: Exception | None) -> None:
        self._set_detection_busy(False)
        if self._locked:
            return
        status = getattr(self._game_detector, "client_status", None)
        if isinstance(status, dict) and status != self._riot_client:
            self._riot_client = deepcopy(status)
            self.riotClientChanged.emit()
        if error is not None or not result:
            changed = self._game_detected
            self._game_detected = False
            self._current_match = {}
            if changed:
                self.gameDetectedChanged.emit()
                self.currentMatchChanged.emit()
            return
        data = self._plain_dict(result)
        self._current_match = data
        self._game_detected = True
        self._attach_asset_urls()
        self.currentMatchChanged.emit()
        self.gameDetectedChanged.emit()

    # ---- Internal persistence and helpers ------------------------------
    def _load_persisted_state(self) -> None:
        if self._repository is None or self._demo:
            return
        try:
            settings = self._repository_call(("get_settings", "load_settings"))
            if settings:
                if not isinstance(settings, dict):
                    serializer = getattr(settings, "to_dict", None)
                    settings = serializer() if callable(serializer) else self._plain_dict(settings)
                mapping = {
                    "lock_timeout_seconds": "autoLockMinutes",
                    "lock_on_blur": "lockOnBlur",
                    "reduce_motion": "reduceMotion",
                    "layout": "viewMode",
                }
                for source, target in mapping.items():
                    if source in settings:
                        if target == "viewMode":
                            self._view_mode = str(settings[source])
                        elif target == "autoLockMinutes":
                            self._settings[target] = int(settings[source]) // 60
                        else:
                            self._settings[target] = settings[source]
            accounts = self._repository_call(("list_accounts",))
            followed = self._repository_call(("list_followed", "list_followed_players"))
            history = self._repository_call(("list_search_history",))
            if accounts:
                self._accounts = [self._account_view(item) for item in accounts]
            if followed:
                self._followed = [self._followed_view(item) for item in followed]
            if history:
                self._search_history = [self._search_view(item) for item in history]
        except Exception:
            # A corrupt/non-migrated database must not prevent the lock screen
            # from appearing. Diagnostics remain deliberately secret-free.
            pass

    def _attach_asset_urls(self) -> None:
        asset_root = Path(__file__).resolve().parent / "assets" / "riot"
        for account in self._accounts:
            for rank in account.get("ranks", []):
                if rank.get("icon"):
                    continue
                game = str(rank.get("game", "")).lower()
                tier_label = str(rank.get("tier", "unranked")).strip().lower()
                tier = tier_label.split()[0]
                if game == "league":
                    if tier == "unranked":
                        continue
                    path = asset_root / "lol" / "ranks" / f"{tier}.png"
                elif game == "tft":
                    if tier == "unranked":
                        continue
                    path = asset_root / "tft" / "ranks" / f"{tier}.png"
                elif game == "valorant":
                    parts = tier_label.split()
                    if len(parts) == 2:
                        parts[1] = {"i": "1", "ii": "2", "iii": "3"}.get(
                            parts[1], parts[1]
                        )
                    slug = re.sub(r"[^a-z0-9]+", "-", "-".join(parts)).strip("-")
                    path = asset_root / "valorant" / "ranks" / f"{slug or 'unranked'}.png"
                    if not path.is_file():
                        path = asset_root / "valorant" / "ranks" / "unranked.png"
                else:
                    continue
                if path.is_file():
                    rank["icon"] = path.as_uri()
        if self._current_match and not self._current_match.get("artwork"):
            game = str(self._current_match.get("game", "")).lower()
            artwork_name = {
                "valorant": "valorant-ascent.png",
                "league": "lol-summoners-rift.png",
                "tft": "tft-default-arena.png",
            }.get(game)
            if artwork_name:
                artwork = asset_root / "artwork" / artwork_name
                if artwork.is_file():
                    self._current_match["artwork"] = artwork.as_uri()

    def _load_sensitive_configuration(self) -> None:
        try:
            api_key = self._vault_get("integration", "riot_api_key")
        except Exception:
            api_key = None
        configured = bool(api_key)
        if self._settings.get("riotApiConfigured") != configured:
            self._settings["riotApiConfigured"] = configured
            self.settingsChanged.emit()
        if configured and self._provider and hasattr(self._provider, "set_api_key"):
            self._provider.set_api_key(api_key)

    def _refresh_owned_secret_flags(self) -> None:
        """Derive owned-account connection hints from the unlocked vault.

        ``connected`` and ``totpAvailable`` are presentation hints, not
        persisted account facts.  In particular, a PUUID alone is not proof
        that a session is still available.  Read only the encrypted entries
        after a successful unlock and keep malformed session bundles fail
        closed.
        """

        changed = False
        for account in self._accounts:
            if not account.get("owned", True):
                continue
            account_id = str(account.get("id", "")).strip()
            if not account_id:
                continue
            try:
                has_session = self._load_session_cookies(account_id) is not None
            except Exception:
                has_session = False
            if not has_session:
                with suppress(Exception):
                    has_session = bool(
                        (self._vault_get(account_id, "riot_access_token") or "").strip()
                    )
            try:
                has_totp = bool((self._vault_get(account_id, "totp") or "").strip())
            except Exception:
                has_totp = False
            if account.get("connected") != has_session:
                account["connected"] = has_session
                changed = True
            if account.get("totpAvailable") != has_totp:
                account["totpAvailable"] = has_totp
                changed = True

        if changed:
            self.accountsChanged.emit()
            if self._selected_account:
                selected_id = self._selected_account.get("id")
                selected = next(
                    (item for item in self._accounts if item.get("id") == selected_id), None
                )
                if selected is not None:
                    self._selected_account = deepcopy(selected)
                    self.selectedAccountChanged.emit()

    def _vault_has_pin(self) -> bool:
        if self._vault is None:
            return False
        value = getattr(self._vault, "has_pin", False)
        try:
            return bool(value() if callable(value) else value)
        except Exception:
            return False

    def _vault_get(self, owner: str, name: str) -> str | None:
        if self._vault is None:
            return None
        getter = getattr(self._vault, "get_secret", None)
        if getter:
            value = getter(owner, name)
            return value if isinstance(value, str) else None
        getter = getattr(self._vault, "get", None)
        if getter:
            value = getter(f"{owner}:{name}")
            return value if isinstance(value, str) else None
        return None

    def _vault_set(self, owner: str, name: str, value: str) -> None:
        if self._vault is None:
            raise RuntimeError("Vault unavailable")
        setter = getattr(self._vault, "set_secret", None)
        if setter:
            setter(owner, name, value)
            return
        setter = getattr(self._vault, "put", None) or getattr(self._vault, "set", None)
        if setter:
            setter(f"{owner}:{name}", value)
            return
        raise RuntimeError("Vault unavailable")

    def _add_search_history(self, query: str, region: str, game: str) -> None:
        query_key = query.casefold()
        region_key = region.casefold()
        game_key = game.casefold()
        existing = next(
            (
                item
                for item in self._search_history
                if str(item.get("query", "")).casefold() == query_key
                and str(item.get("region", "")).casefold() == region_key
                and str(item.get("game", "")).casefold() == game_key
            ),
            None,
        )
        self._search_history = [
            item
            for item in self._search_history
            if not (
                str(item.get("query", "")).casefold() == query_key
                and str(item.get("region", "")).casefold() == region_key
                and str(item.get("game", "")).casefold() == game_key
            )
        ]
        record = {
            "id": str(existing.get("id")) if existing and existing.get("id") else str(uuid.uuid4()),
            "query": query,
            "region": region,
            "game": game,
            "when": "just now",
            "searchedAt": time.time(),
        }
        self._search_history.insert(0, record)
        del self._search_history[20:]
        self.searchHistoryChanged.emit()
        self._persist_search(record)

    def _persist_account(self, account: dict[str, Any]) -> None:
        if self._repository is None:
            return
        try:
            from peaks.domain.models import Account, Game, RankInfo

            game_name, tag_line = self._split_riot_id(str(account["riotId"]))
            converted_ranks = [self._domain_rank(rank) for rank in account.get("ranks", [])]
            ranks = tuple(rank for rank in converted_ranks if rank is not None)
            created_at = None
            existing_account = getattr(self._repository, "get_account", None)
            if callable(existing_account):
                with suppress(Exception):
                    saved = existing_account(str(account["id"]))
                    created_at = getattr(saved, "created_at", None)
            domain_account = Account(
                account_id=str(account["id"]),
                game_name=game_name,
                tag_line=tag_line,
                region=str(account.get("region", "global")),
                puuid=account.get("puuid"),
                is_owned=bool(account.get("owned", True)),
                created_at=created_at,
                last_seen_at=datetime.now(UTC)
                if account.get("lastUpdated") not in {None, "", "not synced"}
                else None,
                ranks=ranks
                or (
                    RankInfo(game=Game.LEAGUE_OF_LEGENDS),
                    RankInfo(game=Game.VALORANT),
                ),
            )
            self._repository_call(("add_account", "save_account"), domain_account)
        except Exception:
            return

    @staticmethod
    def _domain_rank(value: Any) -> Any | None:
        """Convert a QML rank card or RankInfo into a persistence DTO."""

        from peaks.domain.models import Game, RankInfo

        data = value.to_dict() if hasattr(value, "to_dict") else value
        if not isinstance(data, dict):
            return None
        game_value = str(data.get("game", "")).casefold()
        game = {
            "league": Game.LEAGUE_OF_LEGENDS,
            "league_of_legends": Game.LEAGUE_OF_LEGENDS,
            "valorant": Game.VALORANT,
            "tft": Game.TFT,
        }.get(game_value)
        if game is None:
            return None
        tier_text = str(data.get("tier", "unranked")).strip()
        parts = tier_text.replace("_", " ").split()
        tier = parts[0] if parts else "unranked"
        division = data.get("division") or (parts[1] if len(parts) > 1 else None)
        rating_value = data.get("rating")
        if isinstance(rating_value, str):
            match = re.search(r"-?\d+", rating_value)
            rating_value = int(match.group()) if match else None
        if not isinstance(rating_value, int):
            rating_value = None
        peak_text = str(data.get("peak", data.get("peak_tier", tier))).strip()
        if peak_text in {"", "—", "-"}:
            peak_text = tier
        peak_parts = peak_text.replace("_", " ").split()
        peak_tier = peak_parts[0] if peak_parts else tier
        peak_division = data.get("peak_division") or (
            peak_parts[1] if len(peak_parts) > 1 else None
        )
        return RankInfo(
            game=game,
            tier=tier,
            division=division,
            rating=rating_value,
            peak_tier=peak_tier,
            peak_division=peak_division,
        )

    def _persist_setting(self, key: str, value: Any) -> None:
        self._repository_call(("update_setting", "set_setting"), key, value)

    def _persist_search(self, record: dict[str, Any]) -> None:
        if self._repository is None:
            return
        try:
            from peaks.domain.models import Game, SearchEntry

            game_name, tag_line = self._split_riot_id(str(record["query"]))
            selected_game = {
                "League": Game.LEAGUE_OF_LEGENDS,
                "VALORANT": Game.VALORANT,
                "TFT": Game.TFT,
            }.get(str(record.get("game")), Game.VALORANT)
            entry = SearchEntry(
                entry_id=str(record["id"]),
                game_name=game_name,
                tag_line=tag_line,
                region=str(record.get("region", "global")),
                game=selected_game,
            )
            self._repository_call(("add_search", "save_search"), entry)
        except Exception:
            return

    @staticmethod
    def _followed_game(record: Mapping[str, Any]) -> Any:
        from peaks.domain.models import Game

        raw_game: Any = record.get("game")
        if not raw_game:
            games = record.get("games")
            if isinstance(games, (list, tuple)) and games:
                raw_game = games[0]
        try:
            return Game.parse(str(raw_game or "VALORANT"))
        except ValueError:
            return Game.VALORANT

    @classmethod
    def _followed_rank(
        cls, record: Mapping[str, Any], field: str, game: Any
    ) -> Any | None:
        """Convert a followed/search rank view without inventing a rank.

        Provider-shaped rank dictionaries are preferred.  Human-readable
        labels are accepted only for the small, known tier/division/rating
        grammar used by Peaks; unavailable/status text is deliberately
        treated as no rank.
        """

        from peaks.domain.models import RankInfo

        raw: Any = record.get(field)
        if raw is None and field == "currentRank":
            raw = record.get("rank")
        if raw is None and field == "peakRank":
            raw = record.get("peak_rank")
        if isinstance(raw, Mapping):
            data = dict(raw)
            data.setdefault("game", game.value)
            with suppress(Exception):
                return cls._domain_rank(data)
            return None
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        unavailable = {
            "—",
            "-",
            "unranked",
            "no rank",
            "tracked after watching",
            "requires approved valorant rso",
        }
        if text.casefold() in unavailable:
            return None
        match = re.fullmatch(
            r"(?P<tier>iron|bronze|silver|gold|platinum|emerald|diamond|ascendant|"
            r"immortal|master|grandmaster|challenger|radiant)"
            r"(?:\s+(?P<division>[ivx]+|[1-5]))?"
            r"(?:\s*#(?P<peak_rating>\d+))?"
            r"(?:\s*·\s*(?P<rating>\d+)(?:\s*(?:rr|lp))?)?\s*",
            text,
            re.IGNORECASE,
        )
        if match is None:
            return None
        values = match.groupdict()
        tier = values["tier"].casefold()
        division = values.get("division")
        rating_text = values.get("rating")
        peak_rating_text = values.get("peak_rating")
        try:
            rating = int(rating_text) if rating_text is not None else None
            peak_rating = int(peak_rating_text) if peak_rating_text is not None else None
            return RankInfo(
                game=game,
                tier=tier,
                division=division,
                rating=rating,
                peak_tier=tier,
                peak_division=division,
                peak_rating=peak_rating,
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _view_timestamp(value: Any) -> datetime | None:
        """Parse canonical or tightly-known relative view timestamps only."""

        if isinstance(value, datetime):
            return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)):
                return None
            seconds = float(value)
            if abs(seconds) > 100_000_000_000:
                seconds /= 1_000
            with suppress(OverflowError, OSError, ValueError):
                return datetime.fromtimestamp(seconds, UTC)
            return None
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        with suppress(ValueError):
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        normalized = text.casefold()
        now = datetime.now(UTC)
        if normalized in {"now", "just now"}:
            return now
        if normalized == "yesterday":
            return now - timedelta(days=1)
        relative = re.fullmatch(
            r"(?P<count>\d+)\s*(?P<unit>minutes?|mins?|hours?|hrs?|days?|d|h|m)\s+ago",
            normalized,
        )
        if relative is None:
            return None
        count = int(relative.group("count"))
        unit = relative.group("unit")
        if unit.startswith("m"):
            return now - timedelta(minutes=count)
        if unit.startswith("h"):
            return now - timedelta(hours=count)
        return now - timedelta(days=count)

    @classmethod
    def _record_timestamp(
        cls, record: Mapping[str, Any], *, last_game: bool
    ) -> datetime | None:
        keys = (
            ("last_game_at", "lastGameAt", "lastGameTimestamp", "last_game", "lastGame")
            if last_game
            else ("updated_at", "updatedAt", "updatedTimestamp", "lastUpdatedAt", "lastUpdated")
        )
        for key in keys:
            parsed = cls._view_timestamp(record.get(key))
            if parsed is not None:
                return parsed
        if last_game:
            matches = record.get("matches")
            if isinstance(matches, (list, tuple)) and matches:
                first = matches[0]
                if isinstance(first, Mapping):
                    for key in ("played_at", "playedAtTimestamp", "playedAt"):
                        parsed = cls._view_timestamp(first.get(key))
                        if parsed is not None:
                            return parsed
        return None

    def _persist_followed(self, record: dict[str, Any]) -> None:
        if self._repository is None:
            return
        try:
            from peaks.domain.models import FollowedAccount

            game_name, tag_line = self._split_riot_id(str(record["riotId"]))
            selected_game = self._followed_game(record)
            rank = self._followed_rank(record, "currentRank", selected_game)
            peak_rank = self._followed_rank(record, "peakRank", selected_game)
            updated_at = self._record_timestamp(record, last_game=False)
            followed_at = self._view_timestamp(
                record.get("followed_at", record.get("followedAt"))
            ) or datetime.now(UTC)
            followed = FollowedAccount(
                account_id=str(record["id"]),
                game_name=game_name,
                tag_line=tag_line,
                region=str(record.get("region", "global")),
                game=selected_game,
                rank=rank,
                peak_rank=peak_rank,
                last_game_at=self._record_timestamp(record, last_game=True),
                followed_at=followed_at,
                updated_at=updated_at,
            )
            self._repository_call(("add_followed", "save_followed"), followed)
        except Exception:
            return

    def _repository_call(self, names: tuple[str, ...], *args: Any) -> Any:
        if self._repository is None:
            return None
        for name in names:
            function = getattr(self._repository, name, None)
            if callable(function):
                return function(*args)
        return None

    def _run_worker(
        self,
        function: Callable[[], Any],
        callback: Callable[[Any, Exception | None], None],
    ) -> None:
        worker = _Worker(function)
        self._workers.add(worker)
        worker_epoch = self._lock_epoch

        def completed(result: Any, error: Exception | None) -> None:
            try:
                if self._locked or worker_epoch != self._lock_epoch:
                    return
                callback(result, error)
            finally:
                self._workers.discard(worker)

        worker.signals.finished.connect(completed)
        self._thread_pool.start(worker)

    @staticmethod
    def _plain_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return deepcopy(value)
        if is_dataclass(value) and not isinstance(value, type):
            return asdict(cast(Any, value))
        serializer = getattr(value, "to_dict", None)
        if callable(serializer):
            return dict(serializer())
        if hasattr(value, "__dict__"):
            return {key: val for key, val in vars(value).items() if not key.startswith("_")}
        return {}

    def _account_view(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict) and "riotId" in value:
            return deepcopy(value)
        data = value.to_dict() if hasattr(value, "to_dict") else self._plain_dict(value)
        account_id = str(data.get("account_id", data.get("id", "")))
        game_name = str(data.get("game_name", data.get("gameName", "Riot account")))
        tag_line = str(data.get("tag_line", data.get("tagLine", "")))
        rank_views = [self._rank_view(rank) for rank in data.get("ranks", [])]
        known_games = {rank["game"] for rank in rank_views}
        if "League" not in known_games:
            rank_views.insert(0, self._rank_view({"game": "league_of_legends"}))
        if "VALORANT" not in known_games:
            rank_views.append(self._rank_view({"game": "valorant"}))
        matches: list[Any] = []
        if self._repository is not None:
            list_matches = getattr(self._repository, "list_matches", None)
            if callable(list_matches):
                with suppress(Exception):
                    matches = list_matches(account_id=account_id, limit=20)
        return {
            "id": account_id,
            "riotId": f"{game_name}#{tag_line}" if tag_line else game_name,
            "region": str(data.get("region", "global")).upper(),
            "owned": bool(data.get("is_owned", True)),
            "connected": False,
            "initials": (game_name[:2] or "RI").upper(),
            "accent": "#A8CEFF",
            "lastUpdated": self._relative_time(data.get("last_seen_at")) or "not synced",
            "totpAvailable": False,
            "ranks": rank_views,
            "matches": [self._match_view(match) for match in matches],
            "puuid": data.get("puuid"),
        }

    @staticmethod
    def _rank_view(value: Any) -> dict[str, Any]:
        data = value.to_dict() if hasattr(value, "to_dict") else dict(value)
        game_value = str(data.get("game", "valorant"))
        game = {
            "league_of_legends": "League",
            "league": "League",
            "valorant": "VALORANT",
            "tft": "TFT",
        }.get(game_value.lower(), game_value)
        tier_value = data.get("tier", "Unranked")
        tier = getattr(tier_value, "value", tier_value)
        tier_text = str(tier).replace("_", " ")
        tier_label = (
            tier_text
            if tier_text in {"VALORANT", "Requires approved VALORANT RSO"}
            else tier_text.title()
        )
        division = data.get("division")
        if division:
            tier_label = f"{tier_label} {division}"
        rating = data.get("rating")
        suffix = " RR" if game == "VALORANT" else " LP"
        if rating is None:
            rating_label = "—"
        elif isinstance(rating, str) and (not rating.strip().isdigit() or rating.endswith(suffix)):
            rating_label = rating
        else:
            rating_label = f"{rating}{suffix}"
        peak_value = data.get("peak_tier") or data.get("tier") or "Unranked"
        peak_value = getattr(peak_value, "value", peak_value)
        peak_text = str(peak_value).replace("_", " ")
        peak = (
            peak_text
            if peak_text in {"VALORANT", "Requires approved VALORANT RSO"}
            else peak_text.title()
        )
        if data.get("peak_division"):
            peak = f"{peak} {data['peak_division']}"
        if data.get("peak_rating") is not None:
            peak = f"{peak} #{data['peak_rating']}"
        return {
            "game": game,
            "tier": tier_label,
            "rating": rating_label,
            "peak": peak,
            "icon": "",
        }

    def _followed_view(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict) and "riotId" in value:
            return deepcopy(value)
        data = value.to_dict() if hasattr(value, "to_dict") else self._plain_dict(value)
        rank = data.get("rank") or {}
        peak_rank = data.get("peak_rank") or {}
        game_name = str(data.get("game_name", "Riot account"))
        tag_line = str(data.get("tag_line", ""))
        game_value = str(data.get("game", "valorant"))
        game_label = {
            "league_of_legends": "League",
            "valorant": "VALORANT",
            "tft": "TFT",
        }.get(game_value, game_value)
        current = self._rank_view(rank) if rank else None
        peak = self._rank_view(peak_rank) if peak_rank else current
        current_label = current["tier"] if current else "Unranked"
        if current and current.get("rating") not in {None, "", "—"}:
            current_label = f'{current_label} · {current["rating"]}'
        return {
            "id": str(data.get("account_id", data.get("id", ""))),
            "riotId": f"{game_name}#{tag_line}" if tag_line else game_name,
            "region": str(data.get("region", "global")).upper(),
            "games": [game_label],
            "currentRank": current_label,
            "peakRank": peak["peak"] if peak else "Unranked",
            "lastGame": self._relative_time(data.get("last_game_at")) or "No recent game",
            "lastUpdated": self._relative_time(data.get("updated_at")) or "Cached",
            "followed": True,
            "initials": (game_name[:2] or "RI").upper(),
        }

    def _search_view(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict) and "query" in value:
            return deepcopy(value)
        data = value.to_dict() if hasattr(value, "to_dict") else self._plain_dict(value)
        game_name = str(data.get("game_name", ""))
        tag_line = str(data.get("tag_line", ""))
        game_value = str(data.get("game", "valorant"))
        return {
            "id": str(data.get("entry_id", data.get("id", ""))),
            "query": f"{game_name}#{tag_line}" if tag_line else game_name,
            "region": str(data.get("region", "global")).upper(),
            "game": {
                "league_of_legends": "League",
                "valorant": "VALORANT",
                "tft": "TFT",
            }.get(game_value, game_value),
            "when": self._relative_time(data.get("searched_at")) or "recently",
            "searchedAt": data.get("searched_at"),
        }

    @staticmethod
    def _match_view(value: Any) -> dict[str, Any]:
        data = value.to_dict() if hasattr(value, "to_dict") else dict(value)
        game_value = str(data.get("game", "valorant"))
        result_value = str(data.get("result", "unknown"))
        positive = result_value.lower() in {"win", "victory", "top_4"}
        kills = data.get("kills")
        deaths = data.get("deaths")
        assists = data.get("assists")
        performance = (
            f"{kills} / {deaths} / {assists}"
            if all(item is not None for item in (kills, deaths, assists))
            else "Match details unavailable"
        )
        delta = data.get("rank_delta")
        return {
            "id": str(data.get("match_id", data.get("id", ""))),
            "game": {
                "league_of_legends": "League",
                "valorant": "VALORANT",
                "tft": "TFT",
            }.get(game_value, game_value),
            "result": result_value.replace("_", " ").title(),
            "score": "—",
            "mode": data.get("queue") or "Unknown queue",
            "map": data.get("map_name") or "Unknown map",
            "played": AppController._relative_time(data.get("played_at")) or "recently",
            "delta": f"{delta:+d}" if isinstance(delta, int) else "—",
            "performance": performance,
            "positive": positive,
        }

    @staticmethod
    def _relative_time(value: Any) -> str:
        if not value:
            return ""
        try:
            if isinstance(value, datetime):
                timestamp = value if value.tzinfo else value.replace(tzinfo=UTC)
            elif isinstance(value, (int, float)):
                timestamp = datetime.fromtimestamp(float(value), UTC)
            else:
                timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if not timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=UTC)
            seconds = max(0, int((datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return ""
        if seconds < 60:
            return "just now"
        if seconds < 3_600:
            return f"{seconds // 60} min ago"
        if seconds < 86_400:
            return f"{seconds // 3_600}h ago"
        return f"{seconds // 86_400}d ago"

    @staticmethod
    def _split_riot_id(riot_id: str) -> tuple[str, str]:
        game_name, _, tag_line = riot_id.partition("#")
        return game_name, tag_line

    @staticmethod
    def _safe_error(error: Exception, fallback: str) -> str:
        # Worker exceptions may wrap provider response bodies, URLs, request
        # headers, account identifiers, or credentials.  Never surface raw
        # exception text through QML; typed status handling stays generic.
        if isinstance(error, _SessionImportBindingError):
            return str(error)
        if error.__class__.__name__ == "UnsupportedPlatformError":
            return "Import current Riot session is available on Windows only"
        status = getattr(error, "status_code", None)
        if status in {401, 403}:
            return f"{fallback} · authorization unavailable"
        if status == 429:
            return f"{fallback} · rate limit reached"
        return fallback

    def _notify(self, text: str) -> None:
        self._toast_text = text
        self._toast_serial += 1
        self.toastChanged.emit()

    def _set_pin_error(self, text: str) -> None:
        if self._pin_error == text:
            return
        self._pin_error = text
        self.pinErrorChanged.emit()

    def _set_detection_busy(self, value: bool) -> None:
        if self._detection_busy == value:
            return
        self._detection_busy = value
        self.detectionBusyChanged.emit()

    def _set_qr_busy(self, value: bool) -> None:
        if self._qr_busy == value:
            return
        self._qr_busy = value
        self.qrBusyChanged.emit()

    def _set_locked(self, value: bool) -> None:
        if self._locked == value:
            return
        self._locked = value
        self.lockedChanged.emit()
        self.accountsChanged.emit()
        self.followedChanged.emit()
        self.searchHistoryChanged.emit()
        self.searchResultsChanged.emit()
        self.currentMatchChanged.emit()
        self.gameDetectedChanged.emit()

    def _set_qr_prompt(self, value: bool) -> None:
        if self._qr_prompt_open == value:
            return
        self._qr_prompt_open = value
        self.qrPromptOpenChanged.emit()
        if not value:
            self._pending_qr = {}
            self.pendingQrChanged.emit()

    def _record_activity(self) -> None:
        if not self._locked:
            self._last_activity = time.monotonic()

    def _check_auto_lock(self) -> None:
        if self._locked or not self._has_passcode:
            return
        minutes = int(self._settings.get("autoLockMinutes", 15))
        if minutes and time.monotonic() - self._last_activity >= minutes * 60:
            self.lockNow()
