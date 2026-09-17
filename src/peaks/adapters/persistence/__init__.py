"""Local persistence adapters."""

from .database import Database, MetadataStore, SQLiteStore
from .secret_vault import (
    FilePepperProvider,
    InMemoryPepperProvider,
    InvalidPinError,
    KeyringPepperProvider,
    PepperProvider,
    SecretVault,
    Vault,
    VaultAlreadyInitializedError,
    VaultBackoffError,
    VaultCorruptedError,
    VaultError,
    VaultKeyUnavailableError,
    VaultLockedError,
    VaultNotInitializedError,
)

__all__ = [
    "Database",
    "FilePepperProvider",
    "InMemoryPepperProvider",
    "InvalidPinError",
    "KeyringPepperProvider",
    "MetadataStore",
    "PepperProvider",
    "SQLiteStore",
    "SecretVault",
    "Vault",
    "VaultAlreadyInitializedError",
    "VaultBackoffError",
    "VaultCorruptedError",
    "VaultError",
    "VaultKeyUnavailableError",
    "VaultLockedError",
    "VaultNotInitializedError",
]
