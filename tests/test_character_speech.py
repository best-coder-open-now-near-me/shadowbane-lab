import math

import pytest

from shadowbane_lab.character_capture.input import WindowsGameInput
from shadowbane_lab.character_capture.speech import validate_speech_event


@pytest.mark.parametrize("confidence", [-1, 1.1, math.nan, True, "high"])
def test_invalid_speech_confidence_is_rejected(confidence):
    with pytest.raises(ValueError):
        validate_speech_event({"kind": "rejected", "text": "words", "confidence": confidence})


def test_valid_transcript_retains_confidence_and_audio_timing():
    value = {
        "kind": "transcript",
        "text": "cast a spell",
        "confidence": 0.8,
        "audio_start_ms": 100,
        "audio_duration_ms": 200,
        "stream_anchor_ns": 300,
        "observed_monotonic_ns": 400,
    }
    assert validate_speech_event(value) == value


def test_input_queue_is_bounded_and_defaults_disabled():
    observer = WindowsGameInput(123, 456)
    assert not observer.enabled.is_set()
    for i in range(8200):
        observer._put({"test": i})
    assert observer.events.qsize() == 8192
    assert observer.dropped == 8
