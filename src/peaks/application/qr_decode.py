"""Decode an in-memory Electron window capture without a Qt dependency.

Electron captures the Riot Client window in the trusted main process and sends
only its BGRA bitmap to the Python bridge.  This module validates strict size
bounds, decodes QR symbols only, and wipes its mutable pixel copies before
returning.  Riot payload validation and account binding remain the approval
service's responsibility.
"""

from __future__ import annotations

import base64
import binascii
import ctypes
from collections.abc import Mapping
from typing import Any

import zxingcpp

MAX_CAPTURE_DIMENSION = 4_096
MAX_CAPTURE_PIXELS = 16_000_000


def _wipe(buffer: bytearray) -> None:
    if not buffer:
        return
    ctypes.memset(ctypes.addressof(ctypes.c_char.from_buffer(buffer)), 0, len(buffer))


def decode_bgra_capture(capture: Mapping[str, Any]) -> str | None:
    """Return the first QR payload in a bounded Electron BGRA capture."""

    if capture.get("encoding") != "bgra-base64":
        raise ValueError("Riot Client capture encoding is invalid")
    width = capture.get("width")
    height = capture.get("height")
    encoded = capture.get("pixels")
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or not 0 < width <= MAX_CAPTURE_DIMENSION
        or not 0 < height <= MAX_CAPTURE_DIMENSION
        or width * height > MAX_CAPTURE_PIXELS
        or not isinstance(encoded, str)
    ):
        raise ValueError("Riot Client capture dimensions are invalid")

    expected_bytes = width * height * 4
    # Four base64 characters encode at most three bytes.  Reject oversized
    # input before decoding so a forged renderer payload cannot allocate an
    # unbounded temporary buffer.
    if not encoded or len(encoded) > ((expected_bytes + 2) // 3) * 4 + 4:
        raise ValueError("Riot Client capture size is invalid")

    pixels = bytearray()
    grayscale = bytearray()
    try:
        try:
            pixels = bytearray(base64.b64decode(encoded, validate=True))
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Riot Client capture pixels are invalid") from exc
        if len(pixels) != expected_bytes:
            raise ValueError("Riot Client capture size is invalid")

        # Chromium supplies BGRA.  QR symbols are luminance-based, so the
        # green channel is a reliable single-channel view and avoids channel
        # ordering ambiguity in native image libraries.
        grayscale = bytearray(pixels[1::4])
        image = memoryview(grayscale).cast("B", shape=[height, width])
        barcodes = zxingcpp.read_barcodes(
            image,
            formats=zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode),
            try_rotate=True,
            try_downscale=True,
            try_invert=True,
        )
        for barcode in barcodes:
            payload = barcode.text.strip()
            if payload:
                return payload
        return None
    finally:
        _wipe(grayscale)
        _wipe(pixels)
