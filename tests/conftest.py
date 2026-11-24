from __future__ import annotations

import pytest


class _NoStandaloneTft:
    activity_available = False

    def current_session(self) -> None:
        return None

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolate_standalone_tft(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a TFT client running on the test machine out of runtime tests.

    Tests of the reader build StandaloneTftClient directly; runtime tests that
    need a standalone session patch from_discovery themselves.
    """
    from peaks.adapters.riot import tft_client

    monkeypatch.setattr(tft_client.StandaloneTftClient, "from_discovery", classmethod(lambda cls, discovery: _NoStandaloneTft()))
