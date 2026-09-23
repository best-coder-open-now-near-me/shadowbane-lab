import ctypes
import os
import struct
import time
import unittest
from ctypes import wintypes

from shadowbane_lab.client_extension.event_consumer import WindowsExtensionEventTransport
from shadowbane_lab.client_extension.events import (
    EXTENSION_EVENT_CHANNEL_CAPACITY,
    EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
    EXTENSION_EVENT_CHANNEL_HEADER_SIZE,
    EXTENSION_EVENT_CHANNEL_MAGIC,
    EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION,
    EXTENSION_EVENT_CHANNEL_SIZE,
    EXTENSION_EVENT_CHANNEL_SLOT_SIZE,
    extension_event_mapping_name,
    extension_event_signal_name,
)


@unittest.skipUnless(os.name == "nt", "Windows shared-memory transport")
class WindowsExtensionEventTransportTests(unittest.TestCase):
    def test_claims_exact_channel_exclusively_and_releases_for_next_consumer(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileMappingW.argtypes = (
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPCWSTR,
        )
        kernel32.CreateFileMappingW.restype = wintypes.HANDLE
        kernel32.MapViewOfFile.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_size_t,
        )
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.CreateEventW.argtypes = (
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        kernel32.CreateEventW.restype = wintypes.HANDLE
        kernel32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

        process_id = os.getpid()
        creation = 116_444_736_000_000_000 + time.time_ns() // 100
        mapping = kernel32.CreateFileMappingW(
            wintypes.HANDLE(-1),
            None,
            0x04,
            0,
            EXTENSION_EVENT_CHANNEL_SIZE,
            extension_event_mapping_name(process_id, creation),
        )
        self.assertTrue(mapping)
        view = kernel32.MapViewOfFile(
            mapping,
            0x0002 | 0x0004,
            0,
            0,
            EXTENSION_EVENT_CHANNEL_SIZE,
        )
        self.assertTrue(view)
        signal = kernel32.CreateEventW(
            None,
            False,
            False,
            extension_event_signal_name(process_id, creation),
        )
        self.assertTrue(signal)
        payload = bytearray(EXTENSION_EVENT_CHANNEL_SIZE)
        struct.pack_into(
            "<8s6I4QIIQ",
            payload,
            0,
            EXTENSION_EVENT_CHANNEL_MAGIC,
            EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION,
            EXTENSION_EVENT_CHANNEL_HEADER_SIZE,
            EXTENSION_EVENT_CHANNEL_SLOT_SIZE,
            EXTENSION_EVENT_CHANNEL_CAPACITY,
            process_id,
            EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
            creation,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        ctypes.memmove(view, bytes(payload), len(payload))

        first = WindowsExtensionEventTransport(process_id, creation)
        second = WindowsExtensionEventTransport(process_id, creation)
        try:
            self.assertTrue(first.claim())
            self.assertFalse(second.claim())
            self.assertTrue(first.advance(0, 1))
            self.assertEqual(1, struct.unpack_from("<Q", first.read(), 48)[0])

            first.close()
            self.assertTrue(second.claim())
            second.close()
            owner, heartbeat = struct.unpack_from("<IQ", ctypes.string_at(view, 80), 68)
            self.assertEqual((0, 0), (owner, heartbeat))
        finally:
            first.close()
            second.close()
            kernel32.CloseHandle(signal)
            kernel32.UnmapViewOfFile(view)
            kernel32.CloseHandle(mapping)


if __name__ == "__main__":
    unittest.main()
