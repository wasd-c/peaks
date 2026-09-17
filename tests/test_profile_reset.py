from __future__ import annotations

from pathlib import Path

from peaks.adapters.persistence import Database, InMemoryPepperProvider, SecretVault
from peaks.adapters.persistence.profile_reset import (
    RESET_MARKER,
    begin_profile_reset,
    clear_profile_files,
    recover_pending_reset,
)
from peaks.domain import Account
from peaks.ui.controller import AppController


def test_profile_reset_deletes_only_exact_peaks_files(tmp_path: Path) -> None:
    profile = tmp_path / "Peaks"
    profile.mkdir()
    for name in (
        "peaks.sqlite3",
        "peaks.sqlite3-wal",
        "peaks.sqlite3-shm",
        "peaks.sqlite3-journal",
        "vault.json",
        ".vault-pepper",
        ".vault-pepper.dpapi",
        ".vault.json.interrupted.tmp",
    ):
        (profile / name).write_bytes(b"fixture")
    unrelated = profile / "keep-me.txt"
    unrelated.write_text("unrelated", encoding="utf-8")

    begin_profile_reset(profile)
    clear_profile_files(profile, keep_marker=False)

    assert unrelated.read_text(encoding="utf-8") == "unrelated"
    assert not (profile / RESET_MARKER).exists()
    assert sorted(path.name for path in profile.iterdir()) == ["keep-me.txt"]


def test_pending_reset_is_recovered_idempotently(tmp_path: Path) -> None:
    profile = tmp_path / "Peaks"
    begin_profile_reset(profile)
    (profile / "vault.json").write_bytes(b"fixture")

    assert recover_pending_reset(profile) is True
    assert recover_pending_reset(profile) is False
    assert not (profile / "vault.json").exists()


def test_controller_reset_returns_to_working_first_launch(qapp, tmp_path: Path) -> None:
    profile = tmp_path / "Peaks"
    database = Database(profile / "peaks.sqlite3")
    vault = SecretVault(
        profile / "vault.json",
        pepper_provider=InMemoryPepperProvider(b"reset-pepper-01234567890123456"),
    )
    vault.setup_pin("1234")
    vault.unlock_or_raise("1234")
    database.add_account(Account("owned", "Owned", "EUW", "euw1"))
    controller = AppController(
        repository=database,
        vault=vault,
        profile_dir=profile,
        vault_factory=lambda path: SecretVault(
            path,
            pepper_provider=InMemoryPepperProvider(b"new-reset-pepper-012345678901"),
        ),
        demo=False,
    )
    controller._lock_timer.stop()
    controller._detection_timer.stop()
    controller.lockNow()

    controller.resetApplication()

    assert controller.hasPasscode is False
    assert controller.pinMode == "create"
    assert controller.accounts == []
    assert (profile / "peaks.sqlite3").is_file()
    assert not (profile / "vault.json").exists()

    controller.submitPin("2468")
    controller.submitPin("2468")
    assert controller.locked is False
    assert controller.hasPasscode is True
    controller.lockNow()
    controller.deleteLater()
