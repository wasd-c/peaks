from __future__ import annotations

import ctypes
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from peaks.adapters.persistence import secret_vault as vault_module
from peaks.adapters.persistence.secret_vault import (
    InMemoryPepperProvider,
    KeyringPepperProvider,
    SecretVault,
    VaultKeyUnavailableError,
    WindowsDpapiPepperProvider,
)


class MutableKeyring:
    def __init__(self, value: bytes | None = None, *, available: bool = True) -> None:
        self.value = SecretVault._b64(value) if value is not None else None
        self.available = available
        self.writes = 0

    def get_password(self, _service: str, _username: str) -> str | None:
        if not self.available:
            raise RuntimeError("Synthetic credential-store outage")
        return self.value

    def set_password(self, _service: str, _username: str, value: str) -> None:
        assert self.available
        self.writes += 1
        self.value = value


class StoredPepper:
    def __init__(self, value: bytes | None = None) -> None:
        self.value = value
        self.creations = 0

    def get_pepper(self) -> bytes:
        if self.value is None:
            self.value = b"synthetic-fallback-pepper-01234567"
            self.creations += 1
        return self.value

    def read_pepper(self) -> bytes:
        if self.value is None:
            raise FileNotFoundError("Synthetic protected key is absent")
        return self.value


@pytest.fixture
def windows_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    # Change only this module's platform branch, keeping pathlib native on CI.
    monkeypatch.setattr(vault_module, "os", SimpleNamespace(**{**vars(os), "name": "nt"}))


def test_fallback_vault_survives_keyring_recovery_without_creating_a_key(
    tmp_path: Path, windows_storage: None
) -> None:
    backend = MutableKeyring(available=False)
    fallback = StoredPepper()
    path = tmp_path / "vault.json"
    vault = SecretVault(
        path, pepper_provider=KeyringPepperProvider(backend=backend, dpapi_provider=fallback)
    )
    vault.setup_pin("2748")
    vault.unlock_or_raise("2748")
    vault.put("synthetic", {"cookie": "saved-synthetic-session"})
    vault.lock()
    original = path.read_bytes()

    backend.available = True
    reopened = SecretVault(
        path, pepper_provider=KeyringPepperProvider(backend=backend, dpapi_provider=fallback)
    )
    reopened.unlock_or_raise("2748")

    assert reopened.get("synthetic") == {"cookie": "saved-synthetic-session"}
    assert backend.value is None and backend.writes == 0
    assert fallback.creations == 1
    assert path.read_bytes() == original
    reopened.lock()


def test_keyring_outage_does_not_create_an_unrelated_fallback_or_count_a_bad_pin(
    tmp_path: Path, windows_storage: None
) -> None:
    backend = MutableKeyring()
    fallback = StoredPepper()
    vault = SecretVault(
        tmp_path / "vault.json",
        pepper_provider=KeyringPepperProvider(backend=backend, dpapi_provider=fallback),
    )
    vault.setup_pin("2748")
    original = vault.path.read_bytes()
    protected_key = backend.value

    backend.available = False
    with pytest.raises(VaultKeyUnavailableError, match="protected vault key"):
        vault.unlock("2748")

    assert vault.path.read_bytes() == original
    assert vault.failed_attempts == 0
    assert fallback.value is None and fallback.creations == 0
    backend.available = True
    vault.unlock_or_raise("2748")
    assert backend.value == protected_key and backend.writes == 1
    vault.lock()


@pytest.mark.parametrize("original_store", ["keyring", "dpapi"])
def test_conflicting_legacy_keys_preserve_the_authenticated_key_during_pin_rotation(
    tmp_path: Path, windows_storage: None, original_store: str
) -> None:
    keyring_value = b"synthetic-keyring-pepper-012345678"
    dpapi_value = b"synthetic-dpapi-pepper-01234567890"
    original_value = keyring_value if original_store == "keyring" else dpapi_value
    original_provider = InMemoryPepperProvider(original_value)
    path = tmp_path / "vault.json"
    legacy = SecretVault(path, pepper_provider=original_provider)
    legacy.setup_pin("2748")
    legacy.unlock_or_raise("2748")
    legacy.put("synthetic", {"cookie": "saved-synthetic-session"})
    legacy.lock()

    backend = MutableKeyring(keyring_value)
    fallback = StoredPepper(dpapi_value)
    vault = SecretVault(
        path,
        pepper_provider=KeyringPepperProvider(backend=backend, dpapi_provider=fallback),
        base_backoff_seconds=0,
    )
    assert vault.unlock("0000") is False
    assert vault.failed_attempts == 1
    vault.unlock_or_raise("2748")
    vault.change_pin("2748", "8361")
    key_buffer, pepper_buffer = vault._key, vault._active_pepper
    vault.lock()

    reopened = SecretVault(path, pepper_provider=original_provider, base_backoff_seconds=0)
    assert reopened.unlock("2748") is False
    reopened.unlock_or_raise("8361")
    assert reopened.get("synthetic") == {"cookie": "saved-synthetic-session"}
    assert backend.value == SecretVault._b64(keyring_value) and backend.writes == 0
    assert fallback.value == dpapi_value and fallback.creations == 0
    assert key_buffer is not None and not any(key_buffer)
    assert pepper_buffer is not None and not any(pepper_buffer)
    reopened.lock()


def test_missing_protected_keys_leave_existing_vault_and_stores_untouched(
    tmp_path: Path, windows_storage: None
) -> None:
    path = tmp_path / "vault.json"
    SecretVault(path, pepper_provider=InMemoryPepperProvider()).setup_pin("2748")
    original = path.read_bytes()
    backend = MutableKeyring()
    fallback = StoredPepper()
    vault = SecretVault(
        path, pepper_provider=KeyringPepperProvider(backend=backend, dpapi_provider=fallback)
    )

    with pytest.raises(VaultKeyUnavailableError):
        vault.unlock("2748")

    assert path.read_bytes() == original
    assert backend.writes == 0 and backend.value is None
    assert fallback.creations == 0 and fallback.value is None


@pytest.mark.skipif(os.name != "nt", reason="Requires native Windows DPAPI")
def test_native_dpapi_reads_existing_keys_without_replacing_missing_or_corrupt_files(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".vault-pepper.dpapi"
    provider = WindowsDpapiPepperProvider(path)
    with pytest.raises(FileNotFoundError):
        provider.read_pepper()
    assert not path.exists()

    value = provider.get_pepper()
    assert len(value) == 32
    assert value not in path.read_bytes()
    assert WindowsDpapiPepperProvider(path).read_pepper() == value
    corrupt = b"synthetic-invalid-protected-blob"
    path.write_bytes(corrupt)
    with pytest.raises(OSError):
        provider.read_pepper()
    assert path.read_bytes() == corrupt


def test_dpapi_unprotect_uses_optional_output_pointer_and_clears_native_buffers(
    monkeypatch: pytest.MonkeyPatch,
    windows_storage: None,
) -> None:
    plaintext = b"synthetic-native-pepper-012345678"
    allocated = ctypes.create_string_buffer(plaintext)
    observed: dict[str, Any] = {}

    class NativeFunction:
        argtypes: list[Any]
        restype: Any

        def __init__(self, operation: Any) -> None:
            self.operation = operation

        def __call__(self, *args: Any) -> Any:
            return self.operation(*args)

    def unprotect(
        source: Any,
        description: Any,
        _entropy: Any,
        _reserved: Any,
        _prompt: Any,
        flags: int,
        output: Any,
    ) -> int:
        assert description is None
        assert decrypt.argtypes[1] == ctypes.POINTER(ctypes.c_wchar_p)
        assert flags == 1
        observed["source"] = source._obj
        output._obj.cbData = len(plaintext)
        output._obj.pbData = ctypes.cast(allocated, ctypes.POINTER(ctypes.c_ubyte))
        return 1

    def free(pointer: Any) -> None:
        assert ctypes.string_at(pointer, len(plaintext)) == bytes(len(plaintext))
        source = observed["source"]
        assert ctypes.string_at(source.pbData, source.cbData) == bytes(source.cbData)
        observed["freed"] = True

    decrypt = NativeFunction(unprotect)
    libraries = {
        "crypt32": SimpleNamespace(CryptUnprotectData=decrypt),
        "kernel32": SimpleNamespace(LocalFree=NativeFunction(free)),
    }
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **_kwargs: libraries[name], raising=False)

    assert (
        WindowsDpapiPepperProvider._transform(b"synthetic-protected-data", protect=False)
        == plaintext
    )
    assert observed["freed"] is True
