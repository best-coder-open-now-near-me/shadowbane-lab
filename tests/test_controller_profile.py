from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.controller_profile import (
    DEFAULT_CONTROLLER_BINDINGS,
    decode_profile,
    encode_profile,
)
from shadowbane_lab.client_extension.controller_profile import (
    ControllerAction as A,
)
from shadowbane_lab.client_extension.controller_profile import (
    ControllerBinding as B,
)
from shadowbane_lab.client_extension.controller_profile import (
    ControllerControl as C,
)
from shadowbane_lab.client_extension.movement_wire import Settings


def test_default_empty_and_modified_profiles_round_trip():
    for profile in (
        DEFAULT_CONTROLLER_BINDINGS,
        (),
        (B(A.MOVEMENT, C.RIGHT_STICK), B(A.CAMERA, C.LEFT_STICK), B(A.CANCEL_MOVEMENT, C.A, 3)),
    ):
        assert decode_profile(encode_profile(profile)) == profile
        settings = replace(Settings(), controller_bindings=profile)
        assert Settings.decode(settings.encode()).controller_bindings == profile


@pytest.mark.parametrize(
    "profile",
    [
        (B(A.MOVEMENT, C.LEFT_STICK), B(A.CAMERA, C.LEFT_STICK)),
        (B(A.MOVEMENT, C.LEFT_STICK), B(A.MOVEMENT, C.RIGHT_STICK)),
        (B(A.MOVEMENT, C.A),),
        (B(A.CANCEL_MOVEMENT, C.LEFT_STICK),),
        (B(A.CANCEL_MOVEMENT, C.B, 4),),
        (B(A.CANCEL_MOVEMENT, C.LEFT_SHOULDER), B(A.CANCEL_MOVEMENT, C.A, 1)),
        (B(A.CANCEL_MOVEMENT, C.RIGHT_SHOULDER), B(A.CANCEL_MOVEMENT, C.A, 3)),
        (B(A.MOVEMENT, C.LEFT_STICK), B(A.CAMERA, C.RIGHT_STICK), B(A.CAMERA, C.LEFT_STICK, 1)),
    ],
)
def test_conflicting_or_unsupported_profile_rejected(profile):
    with pytest.raises(ValueError):
        encode_profile(profile)


def test_unknown_format_padding_and_action_rejected():
    for index, value in ((0, 2), (1, 25), (25, 1), (2, 0x8000), (2, 63), (2, 0)):
        encoded = list(encode_profile(DEFAULT_CONTROLLER_BINDINGS))
        encoded[index] = value
        with pytest.raises(ValueError):
            decode_profile(tuple(encoded))


def test_exact_modifier_swap_is_valid_without_multiple_writers():
    profile = DEFAULT_CONTROLLER_BINDINGS + (
        B(A.CAMERA, C.LEFT_STICK, 1),
        B(A.MOVEMENT, C.RIGHT_STICK, 1),
    )
    assert decode_profile(encode_profile(profile)) == profile
