"""Bounds-checked navigation metadata decoded from one ``CZone`` resource."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from math import isfinite


class ZoneMetadataFormatError(ValueError):
    """Raised when a CZone payload violates its binary navigation contract."""


class ZoneSeaLevelType(IntEnum):
    """Coordinate space used by a CZone sea-level value."""

    PARENT = 0
    WORLD = 1
    SELF = 2


@dataclass(frozen=True, slots=True)
class ZoneResourceKey:
    """The two 32-bit cache identifiers stored in an Arc resource reference."""

    group_id: int
    resource_id: int


@dataclass(frozen=True, slots=True)
class ZoneWaterMetadata:
    texture: ZoneResourceKey
    x_wave_length: float
    z_wave_length: float
    x_speed: float
    z_speed: float
    amplitude: float


@dataclass(frozen=True, slots=True)
class ZoneTerrainGeneration:
    terrain_type: int
    maximum_x: float
    maximum_z: float
    minimum_y: float | None = None
    maximum_y: float | None = None
    image: ZoneResourceKey | None = None

    def sample_height(self, sample: int) -> float | None:
        """Map one image-terrain byte to its local height coordinate."""

        if isinstance(sample, bool) or not isinstance(sample, int) or not 0 <= sample <= 255:
            raise ValueError("terrain sample must be an unsigned byte")
        if self.terrain_type != 7 or self.minimum_y is None or self.maximum_y is None:
            return None
        return self.minimum_y + sample / 256.0 * (self.maximum_y - self.minimum_y)


@dataclass(frozen=True, slots=True)
class ZoneTerrainObjectPopulation:
    object_key: ZoneResourceKey
    fractal_h: float
    lacunarity: float
    octaves: int
    offset: float
    gain: float
    minimum_altitude: float
    maximum_altitude: float
    minimum_slope: float
    maximum_slope: float
    maximum_population: int
    fractal_population: bool
    y_offset: float
    population_image: ZoneResourceKey
    image_minimum_y: float
    image_maximum_y: float

    def population_layer_index(
        self,
        terrain: ZoneTerrainGeneration | None,
    ) -> int | None:
        """Resolve a population image to its layer after the terrain height image."""

        if (
            terrain is None
            or terrain.image is None
            or self.population_image == ZoneResourceKey(0, 0)
            or self.population_image.group_id != terrain.image.group_id
        ):
            return None
        layer_index = self.population_image.resource_id - terrain.image.resource_id
        return layer_index if layer_index > 0 else None


@dataclass(frozen=True, slots=True)
class ZoneNavigationMetadata:
    zone_type: int
    name: str
    minor_radius: float
    major_radius: float
    y_offset: float
    global_height: float
    sea_level_index: int
    sea_level: float
    sea_level_type: ZoneSeaLevelType
    gradient: float
    water: ZoneWaterMetadata | None
    terrain_generation: ZoneTerrainGeneration | None
    terrain_object_populations: tuple[ZoneTerrainObjectPopulation, ...]
    parsed_size: int

    @property
    def has_water(self) -> bool:
        return self.water is not None

    def local_water_sample_threshold(self) -> float | None:
        """Return the first underwater image sample when sea level is zone-local."""

        terrain = self.terrain_generation
        if (
            self.water is None
            or self.sea_level_type is not ZoneSeaLevelType.SELF
            or terrain is None
            or terrain.terrain_type != 7
            or terrain.minimum_y is None
            or terrain.maximum_y is None
        ):
            return None
        span = terrain.maximum_y - terrain.minimum_y
        if span <= 0:
            return None
        return (self.sea_level - terrain.minimum_y) / span * 256.0


def parse_zone_navigation_metadata(payload: bytes) -> ZoneNavigationMetadata:
    """Decode CZone navigation fields through its terrain-object populations."""

    if not isinstance(payload, bytes):
        raise ValueError("CZone payload must be bytes")
    reader = _ZoneReader(payload)
    zone_type = reader.u32("zone type")
    name = reader.string("zone name")
    reader.resource_key("custom texture")
    for field_name in (
        "width threshold",
        "material threshold",
        "maximum width index",
        "maximum material index",
    ):
        reader.u32(field_name)
    reader.boolean("custom texture wrap")
    reader.boolean("peace-zone flag")
    reader.boolean("guild-zone flag")
    minor_radius = reader.f32("minor radius")
    major_radius = reader.f32("major radius")
    reader.f32("minimum blend")
    reader.f32("maximum blend")
    reader.f32("influence")
    reader.f32("unknown zone scalar")
    y_offset = reader.f32("Y offset")
    global_height = reader.f32("global height")
    reader.f32("transition height")
    reader.f32("upper transition height")
    reader.u32("tile coordinate type")
    reader.f32("tile pattern probability")
    reader.u32("pattern type")
    sea_level_index = reader.u32("sea-level index")
    sea_level = reader.f32("sea level")
    raw_sea_level_type = reader.u32("sea-level type")
    try:
        sea_level_type = ZoneSeaLevelType(raw_sea_level_type)
    except ValueError as exc:
        raise ZoneMetadataFormatError(
            f"CZone sea-level type {raw_sea_level_type} is unsupported"
        ) from exc
    gradient = reader.f32("gradient")
    reader.resource_key("tile set")
    reader.resource_key("song")
    if reader.boolean("biome flag"):
        reader.skip(12, "biome state")
    weather_count = reader.count("weather events", maximum=65_536)
    reader.skip(weather_count * 33, "weather events")

    water = _parse_water(reader) if reader.boolean("water flag") else None
    terrain = _parse_terrain_generation(reader) if reader.boolean("terrain flag") else None
    pattern_count = reader.count("terrain patterns", maximum=65_536)
    reader.skip(pattern_count * 8, "terrain patterns")
    altitude_count = reader.count("terrain altitudes", maximum=65_536)
    reader.skip(altitude_count * 4, "terrain altitudes")
    population_count = reader.count("terrain-object populations", maximum=65_536)
    terrain_object_populations = tuple(
        _parse_terrain_object_population(reader) for _ in range(population_count)
    )
    return ZoneNavigationMetadata(
        zone_type=zone_type,
        name=name,
        minor_radius=minor_radius,
        major_radius=major_radius,
        y_offset=y_offset,
        global_height=global_height,
        sea_level_index=sea_level_index,
        sea_level=sea_level,
        sea_level_type=sea_level_type,
        gradient=gradient,
        water=water,
        terrain_generation=terrain,
        terrain_object_populations=terrain_object_populations,
        parsed_size=reader.offset,
    )


def _parse_water(reader: _ZoneReader) -> ZoneWaterMetadata:
    texture = reader.resource_key("water texture")
    for index in range(4):
        reader.f32(f"water unknown scalar {index}")
    x_wave_length = reader.f32("water X wavelength")
    z_wave_length = reader.f32("water Z wavelength")
    x_speed = reader.f32("water X speed")
    z_speed = reader.f32("water Z speed")
    reader.f32("water unknown scalar 4")
    amplitude = reader.f32("water amplitude")
    reader.f32("water vertex density")
    reader.f32("water texture density")
    for index in range(4):
        reader.f32(f"water color component {index}")
    reader.f32("water reflectivity")
    reader.f32("water eye factor")
    return ZoneWaterMetadata(
        texture=texture,
        x_wave_length=x_wave_length,
        z_wave_length=z_wave_length,
        x_speed=x_speed,
        z_speed=z_speed,
        amplitude=amplitude,
    )


def _parse_terrain_generation(reader: _ZoneReader) -> ZoneTerrainGeneration:
    terrain_type = reader.u32("terrain type")
    if terrain_type in (1, 2, 3, 5):
        maximum_x = reader.f32("terrain maximum X")
        maximum_z = reader.f32("terrain maximum Z")
        reader.f32("terrain H")
        reader.f32("terrain lacunarity")
        reader.u32("terrain octaves")
        reader.f32("terrain offset")
        reader.f32("terrain gain")
        reader.u32("terrain seed 1")
        reader.u32("terrain seed 2")
        return ZoneTerrainGeneration(terrain_type, maximum_x, maximum_z)
    if terrain_type == 4:
        maximum_x = reader.f32("terrain maximum X")
        maximum_z = reader.f32("terrain maximum Z")
        height = reader.f32("terrain height")
        return ZoneTerrainGeneration(
            terrain_type,
            maximum_x,
            maximum_z,
            minimum_y=height,
            maximum_y=height,
        )
    if terrain_type == 6:
        maximum_x = reader.f32("terrain maximum X")
        maximum_z = reader.f32("terrain maximum Z")
        reader.f32("terrain X size")
        reader.f32("terrain Z size")
        reader.resource_key("terrain mesh")
        return ZoneTerrainGeneration(terrain_type, maximum_x, maximum_z)
    if terrain_type == 7:
        maximum_x = reader.f32("terrain maximum X")
        maximum_z = reader.f32("terrain maximum Z")
        reader.f32("terrain X size")
        reader.f32("terrain Z size")
        minimum_y = reader.f32("terrain minimum Y")
        maximum_y = reader.f32("terrain maximum Y")
        if maximum_y < minimum_y:
            raise ZoneMetadataFormatError("image terrain Y range is reversed")
        image = reader.resource_key("terrain image")
        return ZoneTerrainGeneration(
            terrain_type,
            maximum_x,
            maximum_z,
            minimum_y=minimum_y,
            maximum_y=maximum_y,
            image=image,
        )
    raise ZoneMetadataFormatError(f"CZone terrain type {terrain_type} is unsupported")


def _parse_terrain_object_population(
    reader: _ZoneReader,
) -> ZoneTerrainObjectPopulation:
    object_key = reader.resource_key("terrain-object template")
    fractal_h = reader.f32("terrain-object H")
    lacunarity = reader.f32("terrain-object lacunarity")
    octaves = reader.u32("terrain-object octaves")
    offset = reader.f32("terrain-object offset")
    gain = reader.f32("terrain-object gain")
    minimum_altitude = reader.f32("terrain-object minimum altitude")
    maximum_altitude = reader.f32("terrain-object maximum altitude")
    minimum_slope = reader.f32("terrain-object minimum slope")
    maximum_slope = reader.f32("terrain-object maximum slope")
    maximum_population = reader.u32("terrain-object maximum population")
    fractal_population = reader.boolean("terrain-object fractal-population flag")
    reader.u32("terrain-object unknown integer")
    y_offset = reader.f32("terrain-object Y offset")
    population_image = reader.resource_key("terrain-object population image")
    image_minimum_y = reader.f32("terrain-object image minimum Y")
    image_maximum_y = reader.f32("terrain-object image maximum Y")
    if maximum_altitude < minimum_altitude:
        raise ZoneMetadataFormatError("terrain-object altitude range is reversed")
    if maximum_slope < minimum_slope:
        raise ZoneMetadataFormatError("terrain-object slope range is reversed")
    if image_maximum_y < image_minimum_y:
        raise ZoneMetadataFormatError("terrain-object image range is reversed")
    return ZoneTerrainObjectPopulation(
        object_key=object_key,
        fractal_h=fractal_h,
        lacunarity=lacunarity,
        octaves=octaves,
        offset=offset,
        gain=gain,
        minimum_altitude=minimum_altitude,
        maximum_altitude=maximum_altitude,
        minimum_slope=minimum_slope,
        maximum_slope=maximum_slope,
        maximum_population=maximum_population,
        fractal_population=fractal_population,
        y_offset=y_offset,
        population_image=population_image,
        image_minimum_y=image_minimum_y,
        image_maximum_y=image_maximum_y,
    )


class _ZoneReader:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.offset = 0

    def u32(self, field_name: str) -> int:
        return struct.unpack("<I", self._take(4, field_name))[0]

    def f32(self, field_name: str) -> float:
        value = struct.unpack("<f", self._take(4, field_name))[0]
        if not isfinite(value):
            raise ZoneMetadataFormatError(f"CZone {field_name} is not finite")
        return value

    def boolean(self, field_name: str) -> bool:
        value = self._take(1, field_name)[0]
        if value not in (0, 1):
            raise ZoneMetadataFormatError(f"CZone {field_name} is not a binary flag")
        return bool(value)

    def resource_key(self, field_name: str) -> ZoneResourceKey:
        group_id, resource_id = struct.unpack("<II", self._take(8, field_name))
        return ZoneResourceKey(group_id, resource_id)

    def string(self, field_name: str) -> str:
        length = self.count(f"{field_name} characters", maximum=4_096)
        raw = self._take(length * 2, field_name)
        try:
            return raw.decode("utf-16-le", errors="strict")
        except UnicodeDecodeError as exc:
            raise ZoneMetadataFormatError(f"CZone {field_name} is not valid UTF-16LE") from exc

    def count(self, field_name: str, *, maximum: int) -> int:
        value = self.u32(field_name)
        if value > maximum:
            raise ZoneMetadataFormatError(
                f"CZone {field_name} count {value} exceeds the bound {maximum}"
            )
        return value

    def skip(self, size: int, field_name: str) -> None:
        self._take(size, field_name)

    def _take(self, size: int, field_name: str) -> bytes:
        end = self.offset + size
        if size < 0 or end > len(self._payload):
            raise ZoneMetadataFormatError(
                f"CZone ended while reading {field_name} at byte {self.offset}"
            )
        result = self._payload[self.offset : end]
        self.offset = end
        return result
