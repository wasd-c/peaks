"""Encrypted local credential vault.

The four-digit PIN is a convenience access-control gate, not an encryption
key by itself.  A machine-protected random pepper and a per-vault scrypt salt
make the on-disk AES-GCM key different for every installation and vault.  The
derived key and decrypted entries are kept only while the vault is unlocked;
``lock`` wipes both.

Windows never falls back to a plaintext pepper file.  Its fallback storage is
the current-user Windows DPAPI, which is intentionally kept separate from the
development-only file provider.  On macOS and other Unix-like systems a file
pepper can only be enabled explicitly by a caller that has accepted the
development/test trade-off; the normal application path requires keyring/
Keychain storage.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import secrets
import threading
import time
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from peaks.domain.models import SecretEntry


class PepperProvider(Protocol):
    """Backend-neutral source for a machine-local vault pepper."""

    def get_pepper(self) -> bytes: ...


class InMemoryPepperProvider:
    """Deterministic test provider; never use this as a production default."""

    def __init__(self, pepper: bytes | None = None) -> None:
        self.pepper = bytes(pepper or secrets.token_bytes(32))

    def get_pepper(self) -> bytes:
        return self.pepper

    def read_pepper(self) -> bytes:
        return self.get_pepper()

    def destroy(self) -> None:
        self.pepper = b""


class FilePepperProvider:
    """Plaintext development/test fallback; never use as a Windows default.

    File permissions reduce accidental disclosure on Unix-like systems but do
    not provide the OS-backed protection expected for production credentials.
    Callers must explicitly opt in through ``allow_file_fallback=True`` on
    :class:`KeyringPepperProvider`.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.RLock()

    def get_pepper(self) -> bytes:
        with self._lock:
            try:
                value = self.read_pepper()
            except FileNotFoundError:
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                value = secrets.token_bytes(32)
                _atomic_write_bytes(self.path, value)
            if len(value) < 16:
                raise ValueError("Invalid local pepper")
            with suppress(OSError):
                self.path.chmod(0o600)
            return value

    def read_pepper(self) -> bytes:
        """Read existing material without creating a replacement."""

        with self._lock:
            value = self.path.read_bytes()
            if len(value) < 16:
                raise ValueError("Invalid local pepper")
            return value

    def destroy(self) -> None:
        with self._lock, suppress(FileNotFoundError):
            self.path.unlink()


class KeyringPepperProvider:
    """Read a persistent pepper from OS-protected storage.

    ``backend`` is injectable so tests can provide a tiny fake implementing
    ``get_password`` and ``set_password``.  The real ``keyring`` package is
    imported lazily and therefore does not make domain imports platform-bound.
    On Windows, a keyring failure is retried through current-user DPAPI and
    never through the plaintext file provider.  A file fallback is available
    only when ``allow_file_fallback`` is explicitly true (for development or
    tests on Unix-like systems).
    """

    def __init__(
        self,
        service: str = "Peaks",
        username: str = "vault-pepper",
        backend: Any | None = None,
        fallback: PepperProvider | None = None,
        allow_file_fallback: bool = False,
        dpapi_provider: PepperProvider | None = None,
    ) -> None:
        self.service = service
        self.username = username
        self._backend = backend
        self._fallback = fallback
        self._allow_file_fallback = bool(allow_file_fallback)
        self._dpapi = dpapi_provider
        self._lock = threading.RLock()

    def _backend_or_none(self) -> Any | None:
        if self._backend is not None:
            return self._backend
        try:
            import keyring

            return keyring
        except Exception:
            return None

    @staticmethod
    def _decode(value: str) -> bytes:
        try:
            decoded = base64.urlsafe_b64decode(value.encode("ascii"))
            if len(decoded) >= 16:
                return decoded
        except (ValueError, UnicodeEncodeError, binascii.Error):
            pass
        # Accommodate an existing keyring entry from a user-managed backend.
        raw = value.encode("utf-8")
        if len(raw) < 16:
            raise ValueError("Invalid keyring pepper")
        return raw

    def get_pepper(self) -> bytes:
        """Obtain or create material for a new vault, never for unlocking."""

        with self._lock:
            backend = self._backend_or_none()
            backend_error: Exception | None = None
            if backend is not None:
                try:
                    encoded = backend.get_password(self.service, self.username)
                    if encoded:
                        return self._decode(encoded)
                    pepper = secrets.token_bytes(32)
                    backend.set_password(
                        self.service,
                        self.username,
                        base64.urlsafe_b64encode(pepper).decode("ascii"),
                    )
                    return pepper
                except Exception as exc:
                    backend_error = exc

            # A Windows file pepper would be plaintext machine secret
            # material.  Prefer the native current-user DPAPI blob instead,
            # and fail closed if it is unavailable.
            if os.name == "nt":
                if self._dpapi is None:
                    raise RuntimeError(
                        "Windows protected pepper storage is unavailable"
                    ) from backend_error
                try:
                    return self._dpapi.get_pepper()
                except Exception as exc:
                    raise RuntimeError("Windows protected pepper storage is unavailable") from exc

            if self._allow_file_fallback and self._fallback is not None:
                return self._fallback.get_pepper()
            raise RuntimeError(
                "No usable OS keyring backend or explicitly enabled development fallback"
            ) from (backend_error)

    def get_existing_peppers(self) -> tuple[bytes, ...]:
        """Read existing candidates; the vault's authentication tag selects one.

        Older versions could create an unrelated fallback during a keyring
        outage. Trying existing protected values preserves either legacy vault
        without replacing a key or requiring a storage-format migration.
        """

        with self._lock:
            candidates: list[bytes] = []
            backend_error: Exception | None = None
            backend = self._backend_or_none()
            if backend is not None:
                try:
                    encoded = backend.get_password(self.service, self.username)
                    if encoded:
                        candidates.append(self._decode(encoded))
                except Exception as exc:
                    backend_error = exc

            protected = (
                self._dpapi
                if os.name == "nt"
                else (self._fallback if self._allow_file_fallback else None)
            )
            if protected is not None:
                try:
                    # Default file/DPAPI providers expose a non-creating read.
                    # Never call get_pepper here: a missing key is not a new vault.
                    reader = getattr(protected, "read_pepper", None)
                    if not callable(reader):
                        raise RuntimeError("Protected key storage cannot be read safely")
                    value = reader()
                    if not isinstance(value, bytes) or len(value) < 16:
                        raise ValueError("Invalid protected pepper")
                    if value not in candidates:
                        candidates.append(value)
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    backend_error = exc
            if not candidates:
                raise VaultKeyUnavailableError(
                    "The protected vault key is unavailable. Restore access to your "
                    "OS credential store or original protected key before retrying."
                ) from backend_error
            return tuple(candidates)

    def destroy(self) -> None:
        """Remove Peaks' exact pepper entry and any configured fallback blob.

        The random pepper is not account data on its own once the encrypted
        vault is gone.  Keyring deletion is therefore best-effort so an
        unavailable OS credential service cannot make a confirmed profile
        reset impossible.
        """

        with self._lock:
            backend = self._backend_or_none()
            if backend is not None:
                with suppress(Exception):
                    existing = backend.get_password(self.service, self.username)
                    delete = getattr(backend, "delete_password", None)
                    if existing and callable(delete):
                        delete(self.service, self.username)
            for provider in (self._dpapi, self._fallback if self._allow_file_fallback else None):
                destroy = getattr(provider, "destroy", None)
                if callable(destroy):
                    with suppress(Exception):
                        destroy()


class WindowsDpapiPepperProvider:
    """Persist a pepper encrypted with the current user's Windows DPAPI.

    DPAPI binds the blob to the Windows user profile, so copying the stored
    file to another account or machine does not disclose the pepper.  This
    provider deliberately refuses to run off Windows rather than silently
    degrading to a plaintext file.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.RLock()

    @staticmethod
    def _transform(payload: bytes, *, protect: bool) -> bytes:
        if os.name != "nt":
            raise RuntimeError("Windows DPAPI is available only on Windows")

        import ctypes

        ctypes_api: Any = ctypes

        class DataBlob(ctypes.Structure):
            _fields_ = [
                ("cbData", ctypes.c_uint32),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
            ]

        crypt32 = ctypes_api.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes_api.WinDLL("kernel32", use_last_error=True)
        transform = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        transform.argtypes = [
            ctypes.POINTER(DataBlob),
            ctypes.c_wchar_p if protect else ctypes.POINTER(ctypes.c_wchar_p),
            ctypes.POINTER(DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(DataBlob),
        ]
        transform.restype = ctypes.c_int
        local_free = kernel32.LocalFree
        local_free.argtypes = [ctypes.c_void_p]
        local_free.restype = ctypes.c_void_p

        source = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
        source_blob = DataBlob(len(payload), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
        result_blob = DataBlob()
        # CRYPTPROTECT_UI_FORBIDDEN prevents a credential prompt in a desktop
        # process when the profile is not ready; callers get a clear failure.
        flags = 0x1
        try:
            ok = transform(
                ctypes.byref(source_blob),
                # CryptUnprotectData takes an optional output pointer, not an
                # input description. NULL avoids an unused native allocation.
                "Peaks vault pepper" if protect else None,
                None,
                None,
                None,
                flags,
                ctypes.byref(result_blob),
            )
            if not ok or not result_blob.pbData or result_blob.cbData < 16:
                error = ctypes_api.get_last_error()
                raise OSError(error, "Windows DPAPI operation failed")
            return ctypes.string_at(result_blob.pbData, result_blob.cbData)
        finally:
            ctypes.memset(source, 0, ctypes.sizeof(source))
            if result_blob.pbData:
                ctypes.memset(result_blob.pbData, 0, result_blob.cbData)
                local_free(ctypes.cast(result_blob.pbData, ctypes.c_void_p))

    def get_pepper(self) -> bytes:
        with self._lock:
            if os.name != "nt":
                raise RuntimeError("Windows DPAPI is available only on Windows")
            try:
                return self.read_pepper()
            except FileNotFoundError:
                pepper = secrets.token_bytes(32)
                _atomic_write_bytes(self.path, self._transform(pepper, protect=True))
                return pepper

    def read_pepper(self) -> bytes:
        """Read existing protected material without creating a replacement."""

        with self._lock:
            if os.name != "nt":
                raise RuntimeError("Windows DPAPI is available only on Windows")
            pepper = self._transform(self.path.read_bytes(), protect=False)
            if len(pepper) < 16:
                raise ValueError("Invalid Windows DPAPI pepper")
            return pepper

    def destroy(self) -> None:
        with self._lock, suppress(FileNotFoundError):
            self.path.unlink()


class VaultError(RuntimeError):
    """Base class for vault lifecycle errors."""


class VaultNotInitializedError(VaultError):
    pass


class VaultAlreadyInitializedError(VaultError):
    pass


class VaultLockedError(VaultError):
    pass


class InvalidPinError(VaultError):
    pass


class VaultBackoffError(VaultError):
    def __init__(self, retry_after: float) -> None:
        self.retry_after = max(0.0, retry_after)
        super().__init__(f"Try again in {self.retry_after:.1f} seconds")


class VaultCorruptedError(VaultError):
    pass


class VaultKeyUnavailableError(VaultError):
    pass


def _default_vault_path() -> Path:
    try:
        from platformdirs import user_data_dir

        return Path(user_data_dir("Peaks", "Peaks")) / "vault.json"
    except Exception:  # pragma: no cover - fallback for minimal test envs
        return Path.home() / ".peaks" / "vault.json"


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Write and replace a file without exposing an incomplete vault."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            # fdopen closes fd on all normal failure paths.
            raise
        os.replace(temporary, path)
        with suppress(OSError):
            path.chmod(0o600)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # Directory fsync is unavailable on some Windows filesystems; the
            # fsynced temporary file and atomic replace still provide safety.
            pass
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


class SecretVault:
    """AES-GCM encrypted JSON vault with a four-digit PIN unlock gate."""

    FORMAT_VERSION = 1
    SCRYPT_N = 2**14
    SCRYPT_R = 8
    SCRYPT_P = 1
    KEY_LENGTH = 32
    SALT_LENGTH = 16
    NONCE_LENGTH = 12
    AAD = b"peaks-secret-vault-v1"

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        pepper_provider: PepperProvider | None = None,
        keyring_backend: Any | None = None,
        clock: Any | None = None,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 300.0,
        allow_file_pepper_fallback: bool = False,
    ) -> None:
        self.path = Path(path).expanduser() if path is not None else _default_vault_path()
        fallback = FilePepperProvider(self.path.with_name(".vault-pepper"))
        dpapi = WindowsDpapiPepperProvider(self.path.with_name(".vault-pepper.dpapi"))
        if pepper_provider is not None and keyring_backend is not None:
            raise ValueError("Specify pepper_provider or keyring_backend, not both")
        self._pepper: PepperProvider = pepper_provider or KeyringPepperProvider(
            backend=keyring_backend,
            fallback=fallback,
            allow_file_fallback=allow_file_pepper_fallback,
            dpapi_provider=dpapi,
        )
        self._clock = clock or time.time
        self.base_backoff_seconds = max(0.0, float(base_backoff_seconds))
        self.max_backoff_seconds = max(self.base_backoff_seconds, float(max_backoff_seconds))
        self._lock = threading.RLock()
        self._key: bytearray | None = None
        self._active_pepper: bytearray | None = None
        self._entries: dict[str, Any] | None = None
        self._last_error: str | None = None

    @staticmethod
    def _validate_pin(pin: str) -> None:
        if not isinstance(pin, str) or len(pin) != 4 or not pin.isascii() or not pin.isdecimal():
            raise ValueError("PIN must contain exactly four ASCII digits")

    @property
    def has_pin(self) -> bool:
        return self.path.exists()

    @property
    def is_initialized(self) -> bool:
        return self.has_pin

    @property
    def is_unlocked(self) -> bool:
        return self._key is not None and self._entries is not None

    @property
    def failed_attempts(self) -> int:
        if not self.has_pin:
            return 0
        try:
            return int(self._read_header().get("failed_attempts", 0))
        except VaultError:
            return 0

    @property
    def next_attempt_at(self) -> float:
        if not self.has_pin:
            return 0.0
        try:
            return float(self._read_header().get("next_attempt_at", 0.0))
        except VaultError:
            return 0.0

    @property
    def retry_after(self) -> float:
        return max(0.0, self.next_attempt_at - float(self._clock()))

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def setup_pin(self, pin: str) -> None:
        """Create a new vault and leave it locked.

        Existing vaults are never overwritten; callers must use ``change_pin``
        after unlocking instead.
        """

        self._validate_pin(pin)
        with self._lock:
            if self.path.exists():
                raise VaultAlreadyInitializedError("A vault already exists")
            salt = secrets.token_bytes(self.SALT_LENGTH)
            key = bytearray(self._derive_key(pin, salt))
            try:
                header = self._make_header(key, salt, {})
                _atomic_write_bytes(self.path, self._header_bytes(header))
            finally:
                self._wipe(key)

    initialize = setup_pin

    def _derive_key(
        self, pin: str, salt: bytes, *, pepper: bytes | bytearray | None = None
    ) -> bytes:
        self._validate_pin(pin)
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

        if pepper is None:
            pepper = self._pepper.get_pepper()
        if len(pepper) < 16:
            raise ValueError("Pepper must be at least 128 bits")
        # Concatenating a machine-local random pepper with the low-entropy PIN
        # ensures an offline attacker cannot precompute the 10,000 PINs.
        password = pin.encode("ascii") + b"\x00" + bytes(pepper)
        return Scrypt(
            salt=salt,
            length=self.KEY_LENGTH,
            n=self.SCRYPT_N,
            r=self.SCRYPT_R,
            p=self.SCRYPT_P,
        ).derive(password)

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii")

    @staticmethod
    def _unb64(value: Any, expected: int | None = None) -> bytes:
        if not isinstance(value, str):
            raise VaultCorruptedError("Vault contains invalid binary fields")
        try:
            result = base64.urlsafe_b64decode(value.encode("ascii"))
        except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
            raise VaultCorruptedError("Vault contains invalid binary fields") from exc
        if expected is not None and len(result) != expected:
            raise VaultCorruptedError("Vault contains invalid binary fields")
        return result

    def _make_header(
        self, key: bytes | bytearray, salt: bytes, entries: Mapping[str, Any]
    ) -> dict[str, Any]:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = secrets.token_bytes(self.NONCE_LENGTH)
        plaintext = json.dumps(
            {"version": self.FORMAT_VERSION, "entries": dict(entries)},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        ciphertext = AESGCM(bytes(key)).encrypt(nonce, plaintext, self.AAD)
        return {
            "version": self.FORMAT_VERSION,
            "salt": self._b64(salt),
            "nonce": self._b64(nonce),
            "ciphertext": self._b64(ciphertext),
            "failed_attempts": 0,
            "next_attempt_at": 0.0,
        }

    @staticmethod
    def _header_bytes(header: Mapping[str, Any]) -> bytes:
        return (
            json.dumps(header, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")

    def _read_header(self) -> dict[str, Any]:
        try:
            raw = self.path.read_text(encoding="utf-8")
            header = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VaultCorruptedError("Unable to read vault") from exc
        if not isinstance(header, dict) or header.get("version") != self.FORMAT_VERSION:
            raise VaultCorruptedError("Unsupported vault format")
        self._unb64(header.get("salt"), self.SALT_LENGTH)
        self._unb64(header.get("nonce"), self.NONCE_LENGTH)
        ciphertext = self._unb64(header.get("ciphertext"))
        if len(ciphertext) < 16:
            raise VaultCorruptedError("Vault ciphertext is invalid")
        attempts = header.get("failed_attempts", 0)
        next_attempt = header.get("next_attempt_at", 0.0)
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
            raise VaultCorruptedError("Vault backoff metadata is invalid")
        if isinstance(next_attempt, bool) or not isinstance(next_attempt, (int, float)):
            raise VaultCorruptedError("Vault backoff metadata is invalid")
        return header

    def unlock(self, pin: str) -> bool:
        """Try to unlock and return ``True`` on success.

        Invalid PINs return ``False`` so the login UI can remain simple.  Use
        ``unlock_or_raise`` when callers need typed failure distinctions.
        """

        self._validate_pin(pin)
        with self._lock:
            if not self.path.exists():
                raise VaultNotInitializedError("Set up a PIN before unlocking")
            header = self._read_header()
            now = float(self._clock())
            retry_at = float(header.get("next_attempt_at", 0.0))
            if now < retry_at:
                self._last_error = "backoff"
                return False
            salt = self._unb64(header["salt"], self.SALT_LENGTH)
            candidates = (
                self._pepper.get_existing_peppers()
                if isinstance(self._pepper, KeyringPepperProvider)
                else (self._pepper.get_pepper(),)
            )
            from cryptography.exceptions import InvalidTag
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            for pepper in candidates:
                key = bytearray(self._derive_key(pin, salt, pepper=pepper))
                accepted = False
                try:
                    plaintext = AESGCM(bytes(key)).decrypt(
                        self._unb64(header["nonce"], self.NONCE_LENGTH),
                        self._unb64(header["ciphertext"]),
                        self.AAD,
                    )
                    payload = json.loads(plaintext.decode("utf-8"))
                    if (
                        not isinstance(payload, dict)
                        or payload.get("version") != self.FORMAT_VERSION
                        or not isinstance(payload.get("entries"), dict)
                    ):
                        raise VaultCorruptedError("Vault payload is invalid")
                    if header.get("failed_attempts", 0) or header.get("next_attempt_at", 0.0):
                        header["failed_attempts"] = 0
                        header["next_attempt_at"] = 0.0
                        _atomic_write_bytes(self.path, self._header_bytes(header))
                    self.lock()
                    self._key = key
                    # PIN rotation must reuse the value that authenticated this
                    # vault, even when a different protected candidate exists.
                    self._active_pepper = bytearray(pepper)
                    self._entries = cast(dict[str, Any], payload["entries"])
                    self._last_error = None
                    accepted = True
                    return True
                except InvalidTag:
                    continue
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise VaultCorruptedError("Vault payload is invalid") from exc
                finally:
                    if not accepted:
                        self._wipe(key)
            # Count a PIN attempt once, regardless of the number of legacy keys.
            self._record_failure(header, now)
            self._last_error = "invalid_pin"
            return False

    def unlock_or_raise(self, pin: str) -> None:
        if self.unlock(pin):
            return
        retry = self.retry_after
        if retry > 0:
            raise VaultBackoffError(retry)
        raise InvalidPinError("Invalid PIN")

    def _record_failure(self, header: dict[str, Any], now: float) -> None:
        attempts = int(header.get("failed_attempts", 0)) + 1
        delay = min(
            self.max_backoff_seconds,
            self.base_backoff_seconds * (2 ** max(0, attempts - 1)),
        )
        header["failed_attempts"] = attempts
        header["next_attempt_at"] = now + delay
        _atomic_write_bytes(self.path, self._header_bytes(header))

    def lock(self) -> None:
        with self._lock:
            if self._entries is not None:
                self._entries.clear()
            self._entries = None
            if self._key is not None:
                self._wipe(self._key)
            self._key = None
            if self._active_pepper is not None:
                self._wipe(self._active_pepper)
            self._active_pepper = None

    def destroy(self) -> None:
        """Wipe memory and delete only this vault's persistent files."""

        with self._lock:
            self.lock()
            destroy_pepper = getattr(self._pepper, "destroy", None)
            if callable(destroy_pepper):
                destroy_pepper()
            candidates = (
                self.path,
                self.path.with_name(".vault-pepper"),
                self.path.with_name(".vault-pepper.dpapi"),
            )
            for candidate in candidates:
                with suppress(FileNotFoundError):
                    candidate.unlink()
            # Interrupted atomic vault writes use this exact, bounded name
            # pattern beside the configured vault.
            for temporary in self.path.parent.glob(f".{self.path.name}.*.tmp"):
                with suppress(FileNotFoundError):
                    temporary.unlink()

    @staticmethod
    def _wipe(value: bytearray) -> None:
        for index in range(len(value)):
            value[index] = 0

    def _require_unlocked(self) -> tuple[bytearray, dict[str, Any]]:
        if self._key is None or self._entries is None:
            raise VaultLockedError("Unlock the vault first")
        return self._key, self._entries

    def _persist_entries(self, entries: Mapping[str, Any]) -> None:
        key, _ = self._require_unlocked()
        header = self._read_header()
        salt = self._unb64(header["salt"], self.SALT_LENGTH)
        # Keep the existing salt but issue a fresh nonce on every write.
        replacement = self._make_header(key, salt, entries)
        replacement["failed_attempts"] = 0
        replacement["next_attempt_at"] = 0.0
        _atomic_write_bytes(self.path, self._header_bytes(replacement))

    @staticmethod
    def _copy_json(value: Any) -> Any:
        try:
            return json.loads(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        except (TypeError, ValueError) as exc:
            raise TypeError("Vault values must be JSON serializable") from exc

    def put(self, key: str, value: Any) -> None:
        """Store a JSON-compatible secret under ``key``."""

        if not isinstance(key, str) or not key.strip():
            raise ValueError("Vault key cannot be empty")
        with self._lock:
            _, entries = self._require_unlocked()
            candidate = dict(entries)
            candidate[key] = self._copy_json(
                value.to_dict() if isinstance(value, SecretEntry) else value
            )
            self._persist_entries(candidate)
            entries.clear()
            entries.update(candidate)

    def put_entry(self, entry: SecretEntry) -> None:
        self.put(entry.account_id, entry)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            _, entries = self._require_unlocked()
            if key not in entries:
                return default
            return self._copy_json(entries[key])

    def get_entry(self, account_id: str) -> SecretEntry | None:
        value = self.get(account_id)
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise VaultCorruptedError("Secret entry is not an object")
        return SecretEntry.from_dict(value)

    def delete(self, key: str) -> bool:
        with self._lock:
            _, entries = self._require_unlocked()
            if key not in entries:
                return False
            candidate = dict(entries)
            del candidate[key]
            self._persist_entries(candidate)
            entries.clear()
            entries.update(candidate)
            return True

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            _, entries = self._require_unlocked()
            return tuple(sorted(entries))

    def clear(self) -> None:
        with self._lock:
            self._require_unlocked()
            self._persist_entries({})
            assert self._entries is not None
            self._entries.clear()

    def change_pin(self, old_pin: str, new_pin: str) -> None:
        self._validate_pin(new_pin)
        with self._lock:
            if not self.unlock(old_pin):
                raise InvalidPinError("Invalid PIN")
            _, entries = self._require_unlocked()
            new_salt = secrets.token_bytes(self.SALT_LENGTH)
            assert self._active_pepper is not None
            new_key = bytearray(self._derive_key(new_pin, new_salt, pepper=self._active_pepper))
            written = False
            try:
                header = self._make_header(new_key, new_salt, entries)
                _atomic_write_bytes(self.path, self._header_bytes(header))
                written = True
            finally:
                self._wipe(new_key)
                # The old key must not remain usable after a PIN rotation.
                self.lock()
            if written:
                self.unlock(new_pin)


Vault = SecretVault

__all__ = [
    "FilePepperProvider",
    "InMemoryPepperProvider",
    "InvalidPinError",
    "KeyringPepperProvider",
    "PepperProvider",
    "SecretVault",
    "Vault",
    "VaultAlreadyInitializedError",
    "VaultBackoffError",
    "VaultCorruptedError",
    "VaultError",
    "VaultKeyUnavailableError",
    "VaultLockedError",
    "VaultNotInitializedError",
    "WindowsDpapiPepperProvider",
]
