from dataclasses import dataclass

from shadowbane_lab.diagnostics.retention import ByteRetentionBuffer


@dataclass(frozen=True)
class _Payload:
    monotonic_ns: int
    payload: bytes


def _buffer(maximum_bytes: int) -> ByteRetentionBuffer[_Payload]:
    return ByteRetentionBuffer(
        maximum_bytes,
        monotonic_ns=lambda item: item.monotonic_ns,
        size_bytes=lambda item: len(item.payload),
    )


def test_payload_exactly_at_cap_is_accepted() -> None:
    buffer = _buffer(4)

    assert buffer.append(_Payload(1, b"1234"))
    assert buffer.retained_bytes == 4
    assert buffer.peak_retained_bytes == 4


def test_payload_one_byte_over_cap_is_rejected_before_mutation() -> None:
    buffer = _buffer(4)
    accepted = _Payload(1, b"1234")

    assert buffer.append(accepted)
    assert not buffer.append(_Payload(2, b"5"))
    assert tuple(buffer) == (accepted,)
    assert buffer.retained_bytes == 4


def test_single_payload_larger_than_cap_is_rejected() -> None:
    buffer = _buffer(4)

    assert not buffer.append(_Payload(1, b"12345"))
    assert tuple(buffer) == ()
    assert buffer.retained_bytes == 0


def test_discard_before_releases_exact_accounted_bytes() -> None:
    buffer = _buffer(8)
    first = _Payload(10, b"12")
    second = _Payload(20, b"345")
    assert buffer.append(first)
    assert buffer.append(second)

    assert buffer.discard_before(20) == (first,)
    assert tuple(buffer) == (second,)
    assert buffer.retained_bytes == 3
