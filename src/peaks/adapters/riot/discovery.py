"""Windows-first discovery of Riot's local client state.

The Riot lockfile and process names are Windows concepts.  Discovery remains a
safe no-op on unsupported platforms so importing Peaks on macOS or Linux never
touches a ``None`` environment variable or imports ``ctypes.windll``.
"""

from __future__ import annotations

import json
import os
import platform as _platform
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast


class LockfileError(ValueError):
    """Raised when a Riot lockfile is malformed."""


@dataclass(frozen=True, slots=True)
class RiotLockfile:
    name: str
    pid: int
    port: int
    password: str = field(repr=False)
    protocol: str = "https"

    @property
    def base_url(self) -> str:
        return f"{self.protocol}://127.0.0.1:{self.port}"


@dataclass(frozen=True, slots=True)
class RiotClientPaths:
    lockfile: tuple[Path, ...]
    valorant_log: tuple[Path, ...]
    league_lockfile: tuple[Path, ...]
    executables: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """A snapshot of local client availability.

    ``lockfile`` is ``None`` when Riot is closed or the platform cannot support
    local-client integration.  No password is included in this representation
    or its ``repr``.
    """

    supported: bool
    process_running: bool
    lockfile: RiotLockfile | None
    executable: Path | None
    reason: str

    @property
    def available(self) -> bool:
        return self.lockfile is not None


def _env_path(env: Mapping[str, str], key: str) -> Path | None:
    value = env.get(key)
    if not value:
        return None
    return Path(value).expanduser()


def default_paths(
    *, platform_name: str | None = None, env: Mapping[str, str] | None = None
) -> RiotClientPaths:
    """Return candidate paths without touching the filesystem.

    Environment variables are read through ``Mapping.get`` and each missing
    value is skipped.  This is important on macOS, where ``LOCALAPPDATA`` is
    normally absent.
    """

    platform_name = platform_name or _platform.system()
    environment = os.environ if env is None else env
    if platform_name.lower() != "windows":
        return RiotClientPaths((), (), (), ())

    local = _env_path(environment, "LOCALAPPDATA")
    app = _env_path(environment, "APPDATA")
    program_files = _env_path(environment, "PROGRAMFILES")
    program_files_x86 = _env_path(environment, "PROGRAMFILES(X86)")
    all_users = _env_path(environment, "ALLUSERSPROFILE")

    roots = tuple(p for p in (local, app) if p is not None)
    lockfiles = tuple(root / "Riot Games" / "Riot Client" / "Config" / "lockfile" for root in roots)
    league_lockfiles = tuple(
        root / "Riot Games" / "League of Legends" / "Config" / "lockfile" for root in roots
    )
    logs = tuple(root / "VALORANT" / "Saved" / "Logs" / "ShooterGame.log" for root in roots)
    executable_roots = tuple(p for p in (program_files, program_files_x86, local) if p is not None)
    executables = tuple(
        root / "Riot Games" / "Riot Client" / "RiotClientServices.exe"
        for root in executable_roots
    )
    if all_users:
        executables += (
            all_users / "Riot Games" / "Riot Client" / "RiotClientServices.exe",
        )
    return RiotClientPaths(lockfiles, logs, league_lockfiles, executables)


def parse_lockfile(contents: str) -> RiotLockfile:
    """Parse Riot's ``name:pid:port:password:protocol`` format."""

    if not isinstance(contents, str):
        raise LockfileError("lockfile must be text")
    raw = contents.strip()
    pieces = raw.split(":")
    if len(pieces) != 5:
        raise LockfileError("lockfile must contain exactly five fields")
    name, pid_text, port_text, password, protocol = pieces
    if not name or not password or protocol.lower() != "https":
        raise LockfileError("lockfile has invalid fields")
    if not re.fullmatch(r"[1-9][0-9]*", pid_text) or not re.fullmatch(r"[0-9]+", port_text):
        raise LockfileError("lockfile has invalid numeric fields")
    pid = int(pid_text)
    port = int(port_text)
    if pid <= 0 or not 1 <= port <= 65535:
        raise LockfileError("lockfile has invalid process or port")
    # Names and protocol are expected to be simple ASCII tokens.  Password is
    # opaque, but a colon would have changed the field count above.
    # Current Riot Client builds use ``Riot Client`` while older fixtures and
    # League lockfiles use compact names such as ``riot-client``.  Accept
    # single, printable ASCII spaces between otherwise conservative tokens,
    # but keep the field bounded and reject leading/trailing/repeated spaces.
    if len(name) > 128 or not re.fullmatch(
        r"[A-Za-z0-9_.-]+(?: [A-Za-z0-9_.-]+)*", name
    ):
        raise LockfileError("lockfile has invalid process name")
    return RiotLockfile(name, pid, port, password, "https")


def read_lockfile(path: Path | str) -> RiotLockfile | None:
    """Read a lockfile, returning ``None`` for absence or malformed state."""

    try:
        contents = Path(path).read_text(encoding="utf-8")
        return parse_lockfile(contents)
    except (OSError, UnicodeError, LockfileError):
        return None


def _default_process_names() -> tuple[str, ...]:
    return (
        "RiotClientServices.exe",
        "RiotClientUx.exe",
        "RiotClientUxRender.exe",
        "VALORANT-Win64-Shipping.exe",
        "LeagueClient.exe",
        "LeagueClientUx.exe",
        "League of Legends.exe",
    )


def running_process_names(
    *,
    platform_name: str | None = None,
    process_iter: Callable[[], Iterable[object]] | None = None,
) -> frozenset[str]:
    """Return known Riot process names, or an empty set when unsupported.

    ``process_iter`` is injectable for tests and for hosts that already expose
    process data.  psutil is imported lazily because it is not required by the
    UI and Windows-only integration must not break import on macOS.
    """

    if (platform_name or _platform.system()).lower() != "windows":
        return frozenset()
    if process_iter is None:
        try:
            import psutil  # type: ignore[import-untyped]

            def _psutil_process_iter() -> Iterable[object]:
                return cast(Iterable[object], psutil.process_iter(["name"]))

            process_iter = _psutil_process_iter
        except ImportError:
            return frozenset()
    names: set[str] = set()
    for process in process_iter():
        try:
            if hasattr(process, "info") and isinstance(process.info, dict):
                name = process.info.get("name")
            elif hasattr(process, "name") and callable(process.name):
                name = process.name()
            else:
                name = str(process)
        except Exception:
            continue
        if isinstance(name, str) and name:
            names.add(name.casefold())
    return frozenset(names)


def is_riot_process_running(names: Iterable[str]) -> bool:
    known = {name.casefold() for name in _default_process_names()}
    return any(name.casefold() in known for name in names)


def find_client_executable(paths: RiotClientPaths) -> Path | None:
    for path in paths.executables:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def _default_process_identity(pid: int) -> tuple[str, Path] | None:
    """Return a process name/executable pair without importing psutil on macOS.

    A lockfile password is useful only when it belongs to the process identified
    by the same lockfile. Looking up the PID immediately before use prevents a
    stale lockfile (or an unrelated local HTTPS listener) from being trusted.
    """

    try:
        import psutil

        process = psutil.Process(pid)
        name = process.name()
        executable = process.exe()
    except Exception:
        return None
    if not isinstance(name, str) or not name or not isinstance(executable, str) or not executable:
        return None
    try:
        return name, Path(executable).resolve(strict=True)
    except OSError:
        return None


def _looks_like_riot_client_executable(path: Path) -> bool:
    """Conservatively recognize Riot Client Services at a resolved path.

    Riot supports custom installation drives, so an exact Program Files path is
    too restrictive. The executable name and the two parent directories are
    fixed, however. Resolving the path first also avoids trusting a symlink or
    junction spelling supplied by the lockfile environment.

    This check cannot defend against malware already running as the same user;
    it is a local-integrity boundary, not a code-signing substitute.
    """

    parts = tuple(part.casefold() for part in path.parts)
    return (
        path.name.casefold() == "riotclientservices.exe"
        and len(parts) >= 3
        and parts[-2:] == ("riot client", "riotclientservices.exe")
        and "riot games" in parts[:-2]
    )


def validate_lockfile_process(
    lockfile: RiotLockfile,
    *,
    process_lookup: Callable[[int], tuple[str, Path] | None] | None = None,
) -> Path | None:
    """Return the verified Riot executable for ``lockfile`` or ``None``.

    Validation binds the lockfile PID to a live RiotClientServices process and
    a resolved executable below ``Riot Games/Riot Client``. Callers must fail
    closed when validation fails.
    """

    identity = (process_lookup or _default_process_identity)(lockfile.pid)
    if identity is None:
        return None
    name, executable = identity
    if name.casefold() != "riotclientservices.exe":
        return None
    try:
        resolved = executable.resolve(strict=True)
    except OSError:
        return None
    return resolved if _looks_like_riot_client_executable(resolved) else None


def _looks_like_league_client_executable(path: Path) -> bool:
    """Conservatively recognize the LCU process that owns League's lockfile."""

    parts = tuple(part.casefold() for part in path.parts)
    return (
        path.name.casefold() in {"leagueclient.exe", "leagueclientux.exe"}
        and len(parts) >= 3
        and parts[-2] == "league of legends"
        and "riot games" in parts[:-2]
    )


def validate_league_lockfile_process(
    lockfile: RiotLockfile,
    *,
    process_lookup: Callable[[int], tuple[str, Path] | None] | None = None,
) -> Path | None:
    """Bind a League lockfile to its live League client owner process.

    League's local API exposes the signed-in summoner and platform region. A
    stale lockfile must not be treated as an authoritative account source, so
    privacy-sensitive callers use this stricter validator instead of the
    compatibility discovery used by live-game detection.
    """

    identity = (process_lookup or _default_process_identity)(lockfile.pid)
    if identity is None:
        return None
    name, executable = identity
    if name.casefold() not in {"leagueclient.exe", "leagueclientux.exe"}:
        return None
    try:
        resolved = executable.resolve(strict=True)
    except OSError:
        return None
    return resolved if (
        resolved.name.casefold() == name.casefold()
        and _looks_like_league_client_executable(resolved)
    ) else None


def discover_riot_client(
    *,
    platform_name: str | None = None,
    env: Mapping[str, str] | None = None,
    paths: RiotClientPaths | None = None,
    process_names: Iterable[str] | None = None,
    process_lookup: Callable[[int], tuple[str, Path] | None] | None = None,
) -> DiscoveryResult:
    """Discover Riot locally without ever launching or authenticating it."""

    platform_name = platform_name or _platform.system()
    supported = platform_name.lower() == "windows"
    if not supported:
        return DiscoveryResult(False, False, None, None, "Riot local integration is Windows-only")
    candidates = paths or default_paths(platform_name=platform_name, env=env)
    names = (
        frozenset(name.casefold() for name in process_names)
        if process_names is not None
        else running_process_names(platform_name=platform_name)
    )
    process_running = is_riot_process_running(names)
    def existing_lock(path: Path) -> RiotLockfile | None:
        try:
            return read_lockfile(path) if path.is_file() else None
        except OSError:
            return None

    lock = next((lock for path in candidates.lockfile if (lock := existing_lock(path)) is not None), None)
    executable = find_client_executable(candidates)
    if lock is not None:
        # ``process_names`` is an explicit test/integration override. Normal
        # runtime discovery always binds the lockfile PID to the executable.
        verified_executable = (
            executable
            if process_names is not None and process_running
            else validate_lockfile_process(lock, process_lookup=process_lookup)
        )
        if verified_executable is not None or (process_names is not None and process_running):
            return DiscoveryResult(
                True,
                True,
                lock,
                verified_executable or executable,
                "Verified Riot lockfile found",
            )
        return DiscoveryResult(
            True,
            process_running,
            None,
            executable,
            "Riot lockfile process identity could not be verified",
        )
    if process_running:
        return DiscoveryResult(True, True, None, executable, "Riot process is running; lockfile unavailable")
    return DiscoveryResult(True, False, None, executable, "Riot client is not running")


def discover_league_lockfile(
    *, platform_name: str | None = None, env: Mapping[str, str] | None = None
) -> RiotLockfile | None:
    """Read League's local lockfile without assuming environment variables."""

    paths = default_paths(platform_name=platform_name, env=env)
    for path in paths.league_lockfile:
        lock = read_lockfile(path)
        if lock is not None:
            return lock
    return None


def discover_verified_league_lockfile(
    *,
    platform_name: str | None = None,
    env: Mapping[str, str] | None = None,
    paths: RiotClientPaths | None = None,
    process_lookup: Callable[[int], tuple[str, Path] | None] | None = None,
    process_identities: Iterable[tuple[int, str, Path]] | None = None,
) -> RiotLockfile | None:
    """Return League's lockfile only when its PID and executable are verified.

    League normally writes ``lockfile`` beside ``LeagueClientUx.exe`` in the
    selected installation directory. Older builds and test fixtures may use
    an app-data candidate, so both sources are checked and held to the same
    PID/executable validation.
    """

    platform_name = platform_name or _platform.system()
    if platform_name.casefold() != "windows":
        return None
    candidates = paths or default_paths(platform_name=platform_name, env=env)
    for path in candidates.league_lockfile:
        lock = read_lockfile(path)
        if lock is not None and validate_league_lockfile_process(
            lock, process_lookup=process_lookup
        ) is not None:
            return lock

    identities = process_identities
    if identities is None:
        try:
            import psutil

            discovered: list[tuple[int, str, Path]] = []
            for process in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    info = process.info
                    pid = info.get("pid")
                    name = info.get("name")
                    executable = info.get("exe")
                except Exception:
                    continue
                if (
                    isinstance(pid, int)
                    and isinstance(name, str)
                    and isinstance(executable, str)
                    and executable
                ):
                    discovered.append((pid, name, Path(executable)))
            identities = discovered
        except ImportError:
            identities = ()
    for pid, name, executable in identities:
        if name.casefold() not in {"leagueclient.exe", "leagueclientux.exe"}:
            continue
        try:
            resolved = executable.resolve(strict=True)
        except OSError:
            continue
        if not _looks_like_league_client_executable(resolved):
            continue
        for path in (resolved.parent / "lockfile", resolved.parent / "Config" / "lockfile"):
            lock = read_lockfile(path)
            if lock is None or lock.pid != pid:
                continue

            def discovered_process_lookup(
                candidate_pid: int,
                *,
                expected_pid: int = pid,
                expected_name: str = name,
                expected_path: Path = resolved,
            ) -> tuple[str, Path] | None:
                return (
                    (expected_name, expected_path)
                    if candidate_pid == expected_pid
                    else None
                )

            identity_lookup = process_lookup or discovered_process_lookup
            if validate_league_lockfile_process(
                lock, process_lookup=identity_lookup
            ) is not None:
                return lock
    return None


# Compatibility names used by the reference projects and convenient for UI
# composition.  All of them remain read-only.
find_lockfile = read_lockfile
get_lockfile = read_lockfile


def valorant_log_path(
    *, platform_name: str | None = None, env: Mapping[str, str] | None = None
) -> Path | None:
    paths = default_paths(platform_name=platform_name, env=env)
    return paths.valorant_log[0] if paths.valorant_log else None


get_valorant_log_path = valorant_log_path


def read_install_manifest(path: Path | str) -> tuple[Path, ...]:
    """Read Riot's optional ``RiotClientInstalls.json`` executable manifest.

    The manifest has changed shape across client versions, so this helper
    extracts only absolute-looking paths from known keys and ignores malformed
    content.  It never returns secrets or starts a process.
    """

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return ()
    values: list[Path] = []

    def visit(value: object, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str) and ("path" in key.lower() or value.lower().endswith(".exe")):
            candidate = Path(value)
            if candidate.is_absolute() and candidate.suffix.lower() == ".exe":
                values.append(candidate)

    visit(data)
    return tuple(dict.fromkeys(values))
