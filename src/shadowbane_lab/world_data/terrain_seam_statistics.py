"""Statistical and geometric records for TerrainAlpha seams."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from shadowbane_lab.world_data.terrain_seam_support import (
    TerrainSeamAuditError,
    _metric,
    _nearest_rank,
)


@dataclass(frozen=True, slots=True)
class DifferenceStatistics:
    """Compact signed and absolute statistics for one difference series."""

    sample_count: int
    nonzero_count: int
    minimum: int
    maximum: int
    mean: float
    absolute_maximum: int
    absolute_mean: float
    absolute_rms: float
    absolute_p50: int
    absolute_p95: int

    @classmethod
    def from_values(cls, values: Sequence[int]) -> DifferenceStatistics:
        if not values:
            raise TerrainSeamAuditError("difference statistics require at least one sample")
        absolute = sorted(abs(value) for value in values)
        count = len(values)
        return cls(
            sample_count=count,
            nonzero_count=sum(value != 0 for value in values),
            minimum=min(values),
            maximum=max(values),
            mean=_metric(sum(values) / count),
            absolute_maximum=absolute[-1],
            absolute_mean=_metric(sum(absolute) / count),
            absolute_rms=_metric(math.sqrt(sum(value * value for value in absolute) / count)),
            absolute_p50=_nearest_rank(absolute, 0.50),
            absolute_p95=_nearest_rank(absolute, 0.95),
        )

    def as_dict(self) -> dict[str, int | float]:
        return {
            "sample_count": self.sample_count,
            "nonzero_count": self.nonzero_count,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "mean": self.mean,
            "absolute_maximum": self.absolute_maximum,
            "absolute_mean": self.absolute_mean,
            "absolute_rms": self.absolute_rms,
            "absolute_p50": self.absolute_p50,
            "absolute_p95": self.absolute_p95,
        }


@dataclass(frozen=True, slots=True)
class GradientSideStatistics:
    """Reduced statistics for a tile's interior-to-boundary gradient."""

    minimum: int
    maximum: int
    mean: float
    absolute_maximum: int
    absolute_p95: int

    @classmethod
    def from_values(cls, values: Sequence[int]) -> GradientSideStatistics:
        if not values:
            raise TerrainSeamAuditError("gradient statistics require at least one sample")
        absolute = sorted(abs(value) for value in values)
        return cls(
            minimum=min(values),
            maximum=max(values),
            mean=_metric(sum(values) / len(values)),
            absolute_maximum=absolute[-1],
            absolute_p95=_nearest_rank(absolute, 0.95),
        )

    def as_dict(self) -> dict[str, int | float]:
        return {
            "minimum": self.minimum,
            "maximum": self.maximum,
            "mean": self.mean,
            "absolute_maximum": self.absolute_maximum,
            "absolute_p95": self.absolute_p95,
        }



@dataclass(frozen=True, slots=True)
class TerrainSeamRecord:
    """One boundary between two adjacent tiles in stored map coordinates."""

    axis: str
    first_tile: tuple[int, int]
    second_tile: tuple[int, int]
    border_delta: DifferenceStatistics
    first_inward_gradient: GradientSideStatistics
    second_inward_gradient: GradientSideStatistics
    gradient_discontinuity: DifferenceStatistics

    @property
    def diagnostic_score(self) -> int:
        return max(
            self.border_delta.absolute_p95,
            self.gradient_discontinuity.absolute_p95,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "axis": self.axis,
            "first_tile": list(self.first_tile),
            "second_tile": list(self.second_tile),
            "border_delta": self.border_delta.as_dict(),
            "first_inward_gradient": self.first_inward_gradient.as_dict(),
            "second_inward_gradient": self.second_inward_gradient.as_dict(),
            "gradient_discontinuity": self.gradient_discontinuity.as_dict(),
            "diagnostic_score": self.diagnostic_score,
        }


@dataclass(frozen=True, slots=True)
class TerrainCornerRecord:
    """Four touching corner samples at one interior tile-grid junction."""

    junction_x: int
    junction_y: int
    lower_left_tile: tuple[int, int]
    lower_right_tile: tuple[int, int]
    upper_left_tile: tuple[int, int]
    upper_right_tile: tuple[int, int]
    lower_left_value: int
    lower_right_value: int
    upper_left_value: int
    upper_right_value: int

    @property
    def spread(self) -> int:
        values = self.values
        return max(values) - min(values)

    @property
    def values(self) -> tuple[int, int, int, int]:
        return (
            self.lower_left_value,
            self.lower_right_value,
            self.upper_left_value,
            self.upper_right_value,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "junction": [self.junction_x, self.junction_y],
            "tiles": {
                "lower_left": list(self.lower_left_tile),
                "lower_right": list(self.lower_right_tile),
                "upper_left": list(self.upper_left_tile),
                "upper_right": list(self.upper_right_tile),
            },
            "values": {
                "lower_left": self.lower_left_value,
                "lower_right": self.lower_right_value,
                "upper_left": self.upper_left_value,
                "upper_right": self.upper_right_value,
            },
            "spread": self.spread,
            "mean": _metric(sum(self.values) / 4.0),
            "edge_deltas": {
                "lower_x": self.lower_right_value - self.lower_left_value,
                "upper_x": self.upper_right_value - self.upper_left_value,
                "left_y": self.upper_left_value - self.lower_left_value,
                "right_y": self.upper_right_value - self.lower_right_value,
            },
        }




__all__ = [
    "DifferenceStatistics",
    "GradientSideStatistics",
    "TerrainCornerRecord",
    "TerrainSeamRecord",
]
