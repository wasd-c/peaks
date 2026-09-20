"""Launch an allowlisted game through the installed Riot Client."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from peaks.domain.models import Game

from .discovery import default_paths, discover_riot_client, read_install_manifest

# These are Riot's desktop shortcut product IDs, including TFT's own entry.
_PRODUCTS = {
    Game.VALORANT: "valorant",
    Game.LEAGUE_OF_LEGENDS: "league_of_legends",
    Game.TFT: "teamfighttactics",
}


def find_riot_executable() -> Path | None:
    """Prefer the verified running client, then Riot's installation manifest."""
    discovered = discover_riot_client().executable
    candidates = [discovered] if discovered is not None else []
    for key in ("PROGRAMDATA", "ALLUSERSPROFILE"):
        root = os.environ.get(key)
        if root:
            candidates.extend(read_install_manifest(Path(root) / "Riot Games" / "RiotClientInstalls.json"))
    candidates.extend(default_paths().executables)
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            if (
                resolved.is_absolute()
                and resolved.is_file()
                and resolved.name.casefold() == "riotclientservices.exe"
                and resolved.parent.name.casefold() == "riot client"
            ):
                return resolved
        except OSError:
            continue
    return None


def launch_game(game: Game | str) -> None:
    """Submit a launch request; Riot owns sign-in, updates and game readiness."""
    product = _PRODUCTS[Game.parse(game)]
    if platform.system() != "Windows":
        raise RuntimeError("Game launch is available on Windows only.")
    executable = find_riot_executable()
    if executable is None:
        raise RuntimeError("Riot Client was not found. Install or open it, then try again.")
    try:
        subprocess.Popen(
            [str(executable), f"--launch-product={product}", "--launch-patchline=live"],
            cwd=executable.parent,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        raise RuntimeError("Riot Client could not start the game. Open it and try again.") from None
