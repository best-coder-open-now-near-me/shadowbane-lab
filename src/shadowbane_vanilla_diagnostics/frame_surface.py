"""Low-overhead visible-window surface fingerprints for frame-change evidence."""

from __future__ import annotations

import ctypes
import hashlib
import os
from ctypes import wintypes


class WindowsSurfaceFrameProbe:
    """Hash a tiny downsample of the visible client surface without retaining pixels."""

    _SAMPLE_WIDTH = 16
    _SAMPLE_HEIGHT = 9
    _SRCCOPY = 0x00CC0020
    _CAPTUREBLT = 0x40000000
    _COLORONCOLOR = 3
    _DIB_RGB_COLORS = 0

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("window surface diagnostics require Windows")

        class BitmapInfoHeader(ctypes.Structure):
            _fields_ = (
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            )

        class BitmapInfo(ctypes.Structure):
            _fields_ = (("bmiHeader", BitmapInfoHeader), ("bmiColors", wintypes.DWORD * 1))

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.GetDC.argtypes = (wintypes.HWND,)
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
        user32.ReleaseDC.restype = ctypes.c_int
        gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
        gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.SetStretchBltMode.argtypes = (wintypes.HDC, ctypes.c_int)
        gdi32.SetStretchBltMode.restype = ctypes.c_int
        gdi32.StretchBlt.argtypes = (
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
        )
        gdi32.StretchBlt.restype = wintypes.BOOL
        gdi32.GetDIBits.argtypes = (
            wintypes.HDC,
            wintypes.HBITMAP,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.LPVOID,
            ctypes.POINTER(BitmapInfo),
            wintypes.UINT,
        )
        gdi32.GetDIBits.restype = ctypes.c_int
        gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.DeleteDC.argtypes = (wintypes.HDC,)
        gdi32.DeleteDC.restype = wintypes.BOOL
        self._user32 = user32
        self._gdi32 = gdi32
        self._bitmap_info_type = BitmapInfo

    def sample(self, window_handle: int) -> dict[str, object]:
        if window_handle <= 0:
            raise ValueError("window_handle must be positive")
        client = wintypes.RECT()
        if not self._user32.GetClientRect(window_handle, ctypes.byref(client)):
            raise OSError(ctypes.get_last_error(), "GetClientRect failed")
        origin = wintypes.POINT(client.left, client.top)
        if not self._user32.ClientToScreen(window_handle, ctypes.byref(origin)):
            raise OSError(ctypes.get_last_error(), "ClientToScreen failed")
        width = client.right - client.left
        height = client.bottom - client.top
        if width <= 0 or height <= 0:
            raise ValueError("target window client surface has no visible area")

        screen_dc = self._user32.GetDC(0)
        if not screen_dc:
            raise OSError(ctypes.get_last_error(), "GetDC failed")
        memory_dc = self._gdi32.CreateCompatibleDC(screen_dc)
        bitmap = None
        previous = None
        try:
            if not memory_dc:
                raise OSError(ctypes.get_last_error(), "CreateCompatibleDC failed")
            bitmap = self._gdi32.CreateCompatibleBitmap(
                screen_dc,
                self._SAMPLE_WIDTH,
                self._SAMPLE_HEIGHT,
            )
            if not bitmap:
                raise OSError(ctypes.get_last_error(), "CreateCompatibleBitmap failed")
            previous = self._gdi32.SelectObject(memory_dc, bitmap)
            if not previous:
                raise OSError(ctypes.get_last_error(), "SelectObject failed")
            self._gdi32.SetStretchBltMode(memory_dc, self._COLORONCOLOR)
            if not self._gdi32.StretchBlt(
                memory_dc,
                0,
                0,
                self._SAMPLE_WIDTH,
                self._SAMPLE_HEIGHT,
                screen_dc,
                origin.x,
                origin.y,
                width,
                height,
                self._SRCCOPY | self._CAPTUREBLT,
            ):
                raise OSError(ctypes.get_last_error(), "StretchBlt failed")
            info = self._bitmap_info_type()
            info.bmiHeader.biSize = ctypes.sizeof(info.bmiHeader)
            info.bmiHeader.biWidth = self._SAMPLE_WIDTH
            info.bmiHeader.biHeight = -self._SAMPLE_HEIGHT
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            buffer = ctypes.create_string_buffer(
                self._SAMPLE_WIDTH * self._SAMPLE_HEIGHT * 4
            )
            scan_lines = self._gdi32.GetDIBits(
                memory_dc,
                bitmap,
                0,
                self._SAMPLE_HEIGHT,
                buffer,
                ctypes.byref(info),
                self._DIB_RGB_COLORS,
            )
            if scan_lines != self._SAMPLE_HEIGHT:
                raise OSError(ctypes.get_last_error(), "GetDIBits did not return every scan line")
            return {
                "scope": "visible client surface fingerprint; no pixels retained",
                "target_window_handle": window_handle,
                "source_client_rect_screen": [
                    origin.x,
                    origin.y,
                    origin.x + width,
                    origin.y + height,
                ],
                "sample_size": [self._SAMPLE_WIDTH, self._SAMPLE_HEIGHT],
                "surface_sha256": hashlib.sha256(buffer.raw).hexdigest(),
                "pixels_retained": False,
            }
        finally:
            if previous and memory_dc:
                self._gdi32.SelectObject(memory_dc, previous)
            if bitmap:
                self._gdi32.DeleteObject(bitmap)
            if memory_dc:
                self._gdi32.DeleteDC(memory_dc)
            self._user32.ReleaseDC(0, screen_dc)


__all__ = ["WindowsSurfaceFrameProbe"]
