"""Resolve world destinations through the exact live minimap projection."""

from math import sqrt

from shadowbane_lab.client_input.compiler import InputCompilationError
from shadowbane_lab.client_input.model import NormalizedPoint
from shadowbane_lab.protocol import TargetKind


class MinimapDestinationResolver:
    def __init__(self, profile, minimap_reader, position_reader):
        if minimap_reader.process_id != position_reader.process_id:
            raise ValueError("minimap and position readers must own the same client")
        self.profile = profile
        self.minimap_reader = minimap_reader
        self.position_reader = position_reader

    def resolve(self, decision):
        if decision.binding.target_kind is not TargetKind.POSITION:
            return None
        target = decision.binding.position
        projection = self.minimap_reader.observe()
        width, height = self.profile.target.reference_width, self.profile.target.reference_height
        if not (
            0 <= projection.left < projection.right <= width
            and 0 <= projection.top < projection.bottom <= height
        ):
            raise InputCompilationError("live minimap leaves the calibrated client window")
        if sqrt(2) / (2 * projection.pixels_per_world_unit) > 5:
            raise InputCompilationError("minimap zoom is too coarse for a five-unit arrival radius")
        position = self.position_reader.observe()
        if projection != self.minimap_reader.observe():
            raise InputCompilationError("minimap projection changed before the click")
        x, y = projection.destination_pixel(
            lt=target.x,
            lg=target.y,
            player_lt=position.lt,
            player_lg=position.lg,
            radius_x=self.profile.movement.horizontal_radius * (width - 1),
            radius_y=self.profile.movement.vertical_radius * (height - 1),
        )
        return NormalizedPoint(x / (width - 1), y / (height - 1))
