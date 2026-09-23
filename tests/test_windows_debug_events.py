from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from shadowbane_lab.client_observation import native_vendor_dialog as native


class WindowsDebugEventRoutingTests(unittest.TestCase):
    def backend_for_exception(self, code: int, hit: object | None = None):
        event = native._DebugEvent()
        event.dwDebugEventCode = 1
        event.dwProcessId = 77
        event.dwThreadId = 88
        event.Exception.ExceptionRecord.ExceptionCode = code
        event.Exception.dwFirstChance = 1

        def wait(destination, timeout):
            ctypes.memmove(destination, ctypes.byref(event), ctypes.sizeof(event))
            return True

        backend = object.__new__(native.WindowsVendorDialogDebugBackend)
        backend._attached = True
        backend._pending = None
        backend._api = SimpleNamespace(kernel32=SimpleNamespace(WaitForDebugEvent=wait))
        backend._hardware_hit = Mock(return_value=hit)
        backend._continue_event = Mock()
        return backend

    def test_native_and_wow64_hardware_events_remain_pending_until_consumer_resumes(self):
        for code in (0x80000004, 0x4000001E):
            with self.subTest(code=hex(code)):
                hit = object()
                backend = self.backend_for_exception(code, hit)
                self.assertIs(backend.wait_for_hit(0), hit)
                backend._hardware_hit.assert_called_once()
                backend._continue_event.assert_not_called()

    def test_unowned_single_step_is_delivered_to_debuggee(self):
        for code in (0x80000004, 0x4000001E):
            with self.subTest(code=hex(code)):
                backend = self.backend_for_exception(code)
                self.assertIsNone(backend.wait_for_hit(0))
                backend._hardware_hit.assert_called_once()
                self.assertEqual(backend._continue_event.call_args.args[1], 0x80010001)

    def test_native_and_wow64_attach_breakpoints_are_consumed(self):
        for code in (0x80000003, 0x4000001F):
            with self.subTest(code=hex(code)):
                backend = self.backend_for_exception(code)
                self.assertIsNone(backend.wait_for_hit(0))
                backend._hardware_hit.assert_not_called()
                self.assertEqual(backend._continue_event.call_args.args[1], 0x00010002)

    def test_unrelated_application_exception_is_not_swallowed(self):
        backend = self.backend_for_exception(0xC0000005)
        self.assertIsNone(backend.wait_for_hit(0))
        backend._hardware_hit.assert_not_called()
        self.assertEqual(backend._continue_event.call_args.args[1], 0x80010001)


if __name__ == "__main__":
    unittest.main()
