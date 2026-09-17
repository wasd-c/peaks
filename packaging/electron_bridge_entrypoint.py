"""PyInstaller entry point for Electron's line-delimited JSON service."""

from __future__ import annotations

import os

from peaks.bridge import main


def _browser_smoke() -> int:
    """Launch the staged browser without network access during packaging."""

    from patchright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        # ``--no-shell`` intentionally stages only the headed Chromium used by
        # Riot login. Point the headless smoke at that same executable instead
        # of asking Patchright for its separately distributed headless shell.
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=playwright.chromium.executable_path,
        )
        try:
            page = browser.new_page()
            page.set_content("<title>Peaks browser runtime</title>")
            if page.title() != "Peaks browser runtime":
                raise RuntimeError("staged browser did not execute the smoke page")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    if os.environ.get("PEAKS_PACKAGING_BROWSER_SMOKE") == "1":
        raise SystemExit(_browser_smoke())
    raise SystemExit(main())
