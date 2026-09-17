from __future__ import annotations

import base64

import pytest
import zxingcpp

from peaks.application.qr_decode import decode_bgra_capture


def _capture(payload: str) -> dict[str, object]:
    barcode = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode)
    encoded = zxingcpp.write_barcode_to_image(barcode, scale=4)
    grayscale = memoryview(encoded).tobytes()
    bgra = bytearray()
    for value in grayscale:
        bgra.extend((value, value, value, 255))
    return {
        "encoding": "bgra-base64",
        "width": encoded.shape[1],
        "height": encoded.shape[0],
        "pixels": base64.b64encode(bgra).decode("ascii"),
    }


def test_decode_bgra_capture_round_trip() -> None:
    payload = (
        "https://qr.riotgames.com?"
        "suuid=123e4567-e89b-12d3-a456-426614174000&cluster=rcp-be-prod"
    )

    assert decode_bgra_capture(_capture(payload)) == payload


@pytest.mark.parametrize(
    "update",
    [
        {"encoding": "png-base64"},
        {"width": 0},
        {"height": 5_000},
        {"pixels": "not base64"},
    ],
)
def test_decode_bgra_capture_rejects_invalid_input(update: dict[str, object]) -> None:
    capture = _capture("Peaks")
    capture.update(update)

    with pytest.raises(ValueError, match="capture"):
        decode_bgra_capture(capture)
