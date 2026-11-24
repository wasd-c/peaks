"""Launch an allowlisted game through the installed Riot Client."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from time import sleep

from peaks.domain.models import Game

from .client import RiotClientError, RiotClientHTTP
from .discovery import default_paths, discover_riot_client, read_install_manifest

# These are Riot's desktop shortcut product IDs, including TFT's own entry.
_PRODUCTS = {
    Game.VALORANT: "valorant",
    Game.LEAGUE_OF_LEGENDS: "league_of_legends",
    Game.TFT: "teamfighttactics",
}
# Since patch 18.6 TFT is a standalone client with its own installation.
# Riot's own Play action leaves the player session without a product context
# for it (PendingProductContext), so only the games below get one.
_SESSION_PRODUCTS = {"valorant": "valorant", "league_of_legends": "league_of_legends"}


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


def open_riot_client() -> None:
    """Open Riot's own client exactly as its Start menu shortcut does."""
    if platform.system() != "Windows":
        raise RuntimeError("Riot Client connection is available on Windows only.")
    executable = find_riot_executable()
    if executable is None:
        raise RuntimeError("Riot Client was not found. Install it, then try again.")
    try:
        subprocess.Popen(
            [str(executable)], cwd=executable.parent,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        raise RuntimeError("Riot Client could not open. Start it and try again.") from None


def launch_game(game: Game | str, *, expected_puuid: str | None = None) -> None:
    """Launch through Riot's game API; use a shortcut only to start a closed client.

    QR approval precedes the desktop client's next sign-in poll. An automatic
    launch must wait for that selected identity rather than launch for an old
    session or merely leave the product's page open.
    """
    product = _PRODUCTS[Game.parse(game)]
    if platform.system() != "Windows":
        raise RuntimeError("Game launch is available on Windows only.")
    discovered = discover_riot_client()
    if discovered.lockfile is not None:
        try:
            with RiotClientHTTP(discovered.lockfile, timeout=3.0) as client:
                session_product = _SESSION_PRODUCTS.get(product)
                context_prepared = False
                for attempt in range(30):
                    try:
                        authorization = client.get_json("/rso-auth/v1/authorization")
                        subject = authorization.get("subject") if isinstance(authorization, dict) else None
                        identity_ready = isinstance(subject, str) and bool(subject) and (expected_puuid is None or subject == expected_puuid)
                        entitlements = client.get_json("/entitlements/v1/token") if identity_ready else None
                        credentials_ready = (
                            identity_ready
                            and isinstance(entitlements, dict)
                            and entitlements.get("subject") == subject
                            and bool(entitlements.get("accessToken"))
                            and bool(entitlements.get("token"))
                        )
                        if credentials_ready and session_product is not None and not context_prepared:
                            # QR signs in to Riot, but an account switch can
                            # leave its game session PendingProductContext.
                            # Starting League then opens an empty client.
                            response = client.request("PUT", "/player-session-lifecycle/v1/product-context", json_body={
                                "productContext": {"productId": session_product, "patchlineId": "live"},
                            })
                            if not 200 <= response.status_code < 300:
                                raise RuntimeError("Riot Client could not prepare the game session. Open Riot Client and try again.")
                            context_prepared = True
                        session = client.get_json("/player-session-lifecycle/v1/session") if credentials_ready and session_product is not None else None
                        ready = credentials_ready if session_product is None else (
                            isinstance(session, dict)
                            and session.get("loginState") == "Authorized"
                            and session.get("actionRequired") is False
                            and session.get("puuid") == subject
                            and session.get("productContext") == {"productId": session_product, "patchlineId": "live"}
                        )
                        if ready:
                            config_status = client.get_json("/client-config/v1/status/player")
                            ready = isinstance(config_status, dict) and config_status.get("readiness") == "Ready"
                        if ready and session_product == "league_of_legends":
                            # League reads this player configuration only during
                            # startup. A QR account switch can expose an empty
                            # configuration before the new identity's fetch ends.
                            edge_url = client.get_json("/client-config/v2/config/lol.client_settings.league_edge.url")
                            ready = isinstance(edge_url, str) and bool(edge_url)
                        if ready:
                            ready = client.get_json(f"/product-launcher/v1/products/{product}/patchlines/live/eligibility") is True
                    except RiotClientError:
                        ready = False
                    if ready:
                        break
                    if attempt < 29:
                        sleep(0.5)
                else:
                    raise RuntimeError("Riot Client has not finished signing in to the selected account. Try the launch button shortly.")
                # This is the client's Play action, not a product-page command.
                # Riot returns only once the product startup has progressed;
                # the short readiness timeout would falsely report a failure.
                client.timeout = 30.0
                response = client.request("POST", f"/product-launcher/v1/products/{product}/patchlines/live")
                if not 200 <= response.status_code < 300:
                    raise RuntimeError("Riot Client could not start the game. Check its sign-in and update status, then try again.")
            return
        except RiotClientError:
            raise RuntimeError("Riot Client could not start the game. Check its sign-in and update status, then try again.") from None
    if expected_puuid is not None:
        raise RuntimeError("Riot Client is not ready after sign-in. Open it and try the launch button shortly.")
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
