"""In-memory QR decoding helpers.

Screenshots are captured through Qt and are never written to disk. The decoder
is intentionally separate from Riot approval so arbitrary QR payloads cannot
turn into arbitrary network requests.
"""

from __future__ import annotations

import ctypes
import platform
import re
from collections.abc import Iterable
from typing import cast

import zxingcpp
from PySide6.QtGui import QGuiApplication, QImage


def decode_qr_image(image: QImage) -> str | None:
    if image.isNull():
        return None
    # ZXing accepts QImage directly, which avoids shipping OpenCV and NumPy in
    # the Windows bundle. Decode QR symbols only; the Riot parser performs the
    # final strict payload validation before any network request is possible.
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


def _is_riot_client_window_title(title: str) -> bool:
    normalized = " ".join(title.split()).casefold()
    return bool(
        re.fullmatch(
            r"riot client(?:\s+[—-]\s+(?:sign in|log in|login|authentication))?",
            normalized,
        )
    )


def _riot_client_window_ids(*, platform_name: str | None = None) -> tuple[int, ...]:
    """Return visible Riot Client HWNDs without reading unrelated windows."""

    if (platform_name or platform.system()).casefold() != "windows":
        return ()
    try:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        matches: list[int] = []

        def visit(hwnd: int, _lparam: int) -> bool:
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = int(user32.GetWindowTextLengthW(hwnd))
                if not 0 < length <= 512:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, len(buffer))
                if _is_riot_client_window_title(buffer.value):
                    matches.append(int(hwnd))
            except Exception:
                return True
            return True

        callback = callback_type(visit)
        if not user32.EnumWindows(callback, 0):
            return ()
        return tuple(dict.fromkeys(matches))
    except Exception:
        return ()


def capture_riot_client_windows(
    *,
    window_ids: Iterable[int] | None = None,
    platform_name: str | None = None,
) -> tuple[QImage, ...]:
    """Capture only visible Riot Client windows and detach their buffers.

    The previous prototype captured every display, which unnecessarily exposed
    unrelated applications to Peaks.  Windows HWND capture also matches the
    product promise more closely: the Connect action finds the Riot Client and
    scans only that window.  Captured pixels stay in memory and are consumed by
    :func:`decode_qr_images`.
    """

    instance = QGuiApplication.instance()
    if instance is None:
        return ()
    app = cast(QGuiApplication, instance)
    if window_ids is None:
        window_ids = _riot_client_window_ids(platform_name=platform_name)
    primary = app.primaryScreen()
    if primary is None:
        return ()
    images: list[QImage] = []
    for window_id in window_ids:
        if not isinstance(window_id, int) or window_id <= 0:
            continue
        pixmap = primary.grabWindow(window_id)
        if pixmap.isNull():
            continue
        images.append(pixmap.toImage().copy())
    return tuple(images)


# Compatibility name for early controller builds.  It intentionally no longer
# captures complete displays.
capture_all_screens = capture_riot_client_windows


def decode_qr_images(images: tuple[QImage, ...]) -> str | None:
    payload: str | None = None
    for image in images:
        try:
            if payload is None:
                payload = decode_qr_image(image)
        finally:
            # These images may contain the Riot window.  Wipe our detached
            # buffer as soon as decoding finishes instead of waiting for GC.
            image.fill(0)
    return payload


def decode_clipboard_image() -> str | None:
    instance = QGuiApplication.instance()
    if instance is None:
        return None
    app = cast(QGuiApplication, instance)
    mime = app.clipboard().mimeData()
    if not mime.hasImage():
        return None
    image = app.clipboard().image().copy()
    try:
        return decode_qr_image(image)
    finally:
        image.fill(0)
