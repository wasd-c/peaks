from __future__ import annotations

import ctypes

import pytest
import zxingcpp
from PySide6.QtGui import QImage

from peaks.application.qr_capture import (
    _is_riot_client_window_title,
    _riot_client_window_ids,
    decode_qr_image,
    decode_qr_images,
)


def _qr_image(payload: str) -> QImage:
    barcode = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode)
    encoded = zxingcpp.write_barcode_to_image(barcode, scale=4)
    buffer = memoryview(encoded)
    return QImage(
        buffer.tobytes(),
        buffer.shape[1],
        buffer.shape[0],
        buffer.strides[0],
        QImage.Format.Format_Grayscale8,
    ).copy()


def test_decode_qr_image_round_trip() -> None:
    payload = (
        "https://qr.riotgames.com?"
        "suuid=123e4567-e89b-12d3-a456-426614174000&cluster=rcp-be-prod"
    )

    assert decode_qr_image(_qr_image(payload)) == payload


def test_decode_qr_images_skips_empty_images() -> None:
    encoded = _qr_image("Peaks")
    assert decode_qr_images((QImage(), encoded)) == "Peaks"
    assert encoded.pixelColor(0, 0).value() == 0
    assert decode_qr_image(QImage()) is None


def test_window_scan_targets_only_riot_client_and_is_windows_only() -> None:
    assert _is_riot_client_window_title("Riot Client")
    assert _is_riot_client_window_title(" Riot   Client — Sign in ")
    assert not _is_riot_client_window_title("League of Legends")
    assert not _is_riot_client_window_title("Riot Client help - Browser")
    assert _riot_client_window_ids(platform_name="Darwin") == ()


def test_window_scan_without_windows_libraries_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(ctypes, "windll", raising=False)

    assert _riot_client_window_ids(platform_name="Windows") == ()
