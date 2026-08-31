import struct
import unittest

from shadowbane_lab.client_extension.performance import (
    PERFORMANCE_FRAME_CAPABILITY,
    PERFORMANCE_STDIO_IO_FLAG,
    PERFORMANCE_SUCCESS_FLAG,
    PERFORMANCE_TELEMETRY_CAPACITY,
    PERFORMANCE_TELEMETRY_HEADER_SIZE,
    PERFORMANCE_TELEMETRY_MAGIC,
    PERFORMANCE_TELEMETRY_SCHEMA_VERSION,
    PERFORMANCE_TELEMETRY_SIZE,
    PERFORMANCE_TELEMETRY_SLOT_SIZE,
    CacheArchive,
    PerformanceRecordKind,
    PerformanceTelemetryError,
    parse_performance_telemetry,
    performance_telemetry_mapping_name,
)


class PerformanceTelemetryContractTests(unittest.TestCase):
    def test_parses_correlated_frame_cache_and_texture_records(self) -> None:
        payload = self._mapping(write_sequence=3, frame_count=100, slow_frames=1)
        self._slot(
            payload,
            1,
            kind=2,
            flags=5,
            archive=1,
            byte_count=65536,
            arg0=4096,
            arg1=65536,
            duration=50,
        )
        self._slot(
            payload,
            2,
            kind=3,
            flags=9,
            archive=1,
            byte_count=16_777_216,
            arg0=(2048 << 32) | 2048,
            arg1=(0x1908 << 32) | 4,
            pipeline=200,
            duration=300,
        )
        self._slot(payload, 3, kind=1, flags=1, interval=500, duration=20)

        snapshot = parse_performance_telemetry(
            payload,
            expected_process_id=42,
            expected_process_creation_filetime_utc=1000,
        )

        self.assertEqual(PerformanceRecordKind.CACHE_READ, snapshot.records[0].kind)
        self.assertEqual(CacheArchive.TEXTURES, snapshot.records[0].archive)
        converted = snapshot.as_dict()
        self.assertEqual(0.05, converted["records"][0]["duration_ms"])
        self.assertEqual(0.5, converted["summary"]["max_frame_interval_ms"])
        self.assertEqual(2048, converted["records"][1]["width"])
        self.assertEqual(0.2, converted["records"][1]["read_to_upload_ms"])

    def test_keeps_only_the_bounded_tail_after_wrap(self) -> None:
        write_sequence = PERFORMANCE_TELEMETRY_CAPACITY + 1
        payload = self._mapping(write_sequence=write_sequence, overwritten=1)
        for sequence in range(2, write_sequence + 1):
            self._slot(
                payload,
                sequence,
                kind=2,
                flags=PERFORMANCE_SUCCESS_FLAG | PERFORMANCE_STDIO_IO_FLAG,
                archive=255,
            )

        snapshot = parse_performance_telemetry(
            payload,
            expected_process_id=42,
            expected_process_creation_filetime_utc=1000,
        )

        self.assertEqual(PERFORMANCE_TELEMETRY_CAPACITY, len(snapshot.records))
        self.assertEqual(2, snapshot.records[0].sequence)
        self.assertEqual(write_sequence, snapshot.records[-1].sequence)

    def test_rejects_incoherent_or_wrong_lifetime_snapshot(self) -> None:
        payload = self._mapping(write_sequence=1)
        with self.assertRaisesRegex(PerformanceTelemetryError, "coherently committed"):
            parse_performance_telemetry(
                payload,
                expected_process_id=42,
                expected_process_creation_filetime_utc=1000,
            )
        with self.assertRaisesRegex(PerformanceTelemetryError, "another process lifetime"):
            parse_performance_telemetry(
                self._mapping(),
                expected_process_id=42,
                expected_process_creation_filetime_utc=1001,
            )

    def test_mapping_name_uses_the_exact_process_identity(self) -> None:
        self.assertEqual(
            "Local\\ShadowbaneLab.Extension.Performance.42.1000",
            performance_telemetry_mapping_name(42, 1000),
        )

    def test_accepts_frame_only_profile_with_one_active_hook(self) -> None:
        payload = self._mapping(capability_flags=PERFORMANCE_FRAME_CAPABILITY, active_hooks=1)

        snapshot = parse_performance_telemetry(
            payload,
            expected_process_id=42,
            expected_process_creation_filetime_utc=1000,
        )

        self.assertEqual("frame", snapshot.as_dict()["header"]["profile"])

    @staticmethod
    def _mapping(
        *,
        write_sequence: int = 0,
        overwritten: int = 0,
        frame_count: int = 0,
        slow_frames: int = 0,
        capability_flags: int = 0x7,
        active_hooks: int = 21,
    ) -> bytearray:
        payload = bytearray(PERFORMANCE_TELEMETRY_SIZE)
        struct.pack_into(
            "<8s6I11Q2I",
            payload,
            0,
            PERFORMANCE_TELEMETRY_MAGIC,
            PERFORMANCE_TELEMETRY_SCHEMA_VERSION,
            PERFORMANCE_TELEMETRY_HEADER_SIZE,
            PERFORMANCE_TELEMETRY_SLOT_SIZE,
            PERFORMANCE_TELEMETRY_CAPACITY,
            42,
            capability_flags,
            1000,
            1_000_000,
            10_000,
            write_sequence,
            overwritten,
            frame_count,
            slow_frames,
            0,
            0,
            0,
            0,
            0,
            active_hooks,
        )
        return payload

    @staticmethod
    def _slot(
        payload: bytearray,
        sequence: int,
        *,
        kind: int,
        flags: int,
        archive: int = 0,
        byte_count: int = 0,
        arg0: int = 0,
        arg1: int = 0,
        duration: int = 0,
        interval: int = 0,
        pipeline: int = 0,
    ) -> None:
        index = (sequence - 1) % PERFORMANCE_TELEMETRY_CAPACITY
        offset = PERFORMANCE_TELEMETRY_HEADER_SIZE + index * PERFORMANCE_TELEMETRY_SLOT_SIZE
        struct.pack_into(
            "<QIIQQII7Q",
            payload,
            offset,
            sequence,
            kind,
            flags,
            11_000 + sequence,
            duration,
            7,
            archive,
            byte_count,
            arg0,
            arg1,
            0,
            interval,
            pipeline,
            0,
        )


if __name__ == "__main__":
    unittest.main()
