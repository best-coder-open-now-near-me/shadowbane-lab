"""Bounds-checked collision metadata from CObjects, Render, and Mesh caches."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from math import hypot, isfinite

from shadowbane_lab.world_data.cache import CacheArchive, CacheResourceEntry
from shadowbane_lab.world_data.zone_metadata import ZoneResourceKey

_COBJECT_MAGIC = 0x434C4E54
_MAX_COLLECTION_SIZE = 65_536
_MAX_RENDER_GRAPH_NODES = 4_096
_MAX_TEXTURE_DEPTH = 16


class ObjectNavigationFormatError(ValueError):
    """Raised when collision metadata violates its binary cache contract."""


@dataclass(frozen=True, slots=True)
class ObjectNavigationMetadata:
    object_type: int
    name: str
    scale: tuple[float, float, float]
    render_key: ZoneResourceKey
    parsed_size: int


@dataclass(frozen=True, slots=True)
class RenderNavigationMetadata:
    mesh_keys: tuple[ZoneResourceKey, ...]
    child_keys: tuple[ZoneResourceKey, ...]
    scale: tuple[float, float, float]
    location: tuple[float, float, float] | None
    collides: bool
    calculates_bounding_box: bool
    parsed_size: int


@dataclass(frozen=True, slots=True)
class MeshNavigationBounds:
    name: str
    distance: float
    center: tuple[float, float, float]
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    parsed_size: int

    @property
    def horizontal_radius(self) -> float:
        return max(
            hypot(x, z)
            for x in (self.minimum[0], self.maximum[0])
            for z in (self.minimum[2], self.maximum[2])
        )


@dataclass(frozen=True, slots=True)
class ObjectCollisionProfile:
    object_key: ZoneResourceKey
    name: str
    colliding_mesh_keys: tuple[ZoneResourceKey, ...]
    horizontal_radius: float | None

    @property
    def collides(self) -> bool:
        return bool(self.colliding_mesh_keys)


def parse_object_navigation_metadata(payload: bytes) -> ObjectNavigationMetadata:
    """Decode the shared CObject prefix through its primary render reference."""

    reader = _NavigationReader(payload, "CObject")
    magic = reader.u32("magic")
    if magic != _COBJECT_MAGIC:
        raise ObjectNavigationFormatError(
            f"CObject magic is 0x{magic:08x}; expected 0x{_COBJECT_MAGIC:08x}"
        )
    object_type = reader.u32("object type")
    if not 1 <= object_type <= 19:
        raise ObjectNavigationFormatError(f"CObject type {object_type} is unsupported")
    name = reader.string("name")
    reader.boolean("pickable flag")
    reader.f32("gravity")
    reader.f32("cull distance")
    scale = reader.tuple3("scale")
    render_key = reader.resource_key("render template")
    return ObjectNavigationMetadata(
        object_type=object_type,
        name=name,
        scale=scale,
        render_key=render_key,
        parsed_size=reader.offset,
    )


def parse_render_navigation_metadata(payload: bytes) -> RenderNavigationMetadata:
    """Decode one render template through its collision flags."""

    reader = _NavigationReader(payload, "Render")
    reader.boolean("fade flag")
    reader.u32("tracker")
    reader.boolean("illuminated flag")
    reader.f32("bone length")
    reader.u32("clip map")
    reader.u32("two-side lighting")
    reader.u32("cull face")
    reader.resource_key("specular map")
    reader.f32("shininess")
    has_mesh = reader.boolean("mesh flag")
    mesh_keys: tuple[ZoneResourceKey, ...] = ()
    if has_mesh:
        mesh_count = reader.count("meshes")
        meshes = []
        for index in range(mesh_count):
            meshes.append(reader.resource_key(f"mesh {index}"))
            reader.boolean(f"mesh {index} decal flag")
            reader.boolean(f"mesh {index} double-sided flag")
        mesh_keys = tuple(meshes)

    reader.string("target bone")
    scale = reader.tuple3("scale")
    has_location = reader.binary_u32("location flag")
    location = None
    child_keys: tuple[ZoneResourceKey, ...] = ()
    if has_location:
        location = reader.tuple3("location")
        child_count = reader.count("children")
        child_keys = tuple(
            reader.resource_key(f"child {index}") for index in range(child_count)
        )

    if reader.boolean("texture-set flag"):
        texture_count = reader.count("texture sets")
        for _ in range(texture_count):
            _skip_texture_set(reader, depth=0)
    collides = reader.boolean("collision flag")
    calculates_bounding_box = reader.boolean("bounding-box flag")
    return RenderNavigationMetadata(
        mesh_keys=mesh_keys,
        child_keys=child_keys,
        scale=scale,
        location=location,
        collides=collides,
        calculates_bounding_box=calculates_bounding_box,
        parsed_size=reader.offset,
    )


def parse_mesh_navigation_bounds(payload: bytes) -> MeshNavigationBounds:
    """Decode the navigation-relevant prefix of one mesh resource."""

    reader = _NavigationReader(payload, "Mesh")
    name = reader.string("name")
    distance = reader.f32("distance")
    center = reader.tuple3("center")
    minimum = reader.tuple3("minimum bounds")
    maximum = reader.tuple3("maximum bounds")
    if any(high < low for low, high in zip(minimum, maximum, strict=True)):
        raise ObjectNavigationFormatError("Mesh bounds are reversed")
    return MeshNavigationBounds(
        name=name,
        distance=distance,
        center=center,
        minimum=minimum,
        maximum=maximum,
        parsed_size=reader.offset,
    )


class ObjectNavigationResolver:
    """Resolve collision geometry through three already-open cache archives."""

    def __init__(
        self,
        objects: CacheArchive,
        renders: CacheArchive,
        meshes: CacheArchive,
    ) -> None:
        if not all(isinstance(archive, CacheArchive) for archive in (objects, renders, meshes)):
            raise ValueError("object navigation resolver requires CacheArchive values")
        self._objects = objects
        self._renders = renders
        self._meshes = meshes
        self._object_entries = _index_entries(objects, "CObjects")
        self._render_entries = _index_entries(renders, "Render")
        self._mesh_entries = _index_entries(meshes, "Mesh")
        self._render_cache: dict[ZoneResourceKey, RenderNavigationMetadata] = {}
        self._mesh_cache: dict[ZoneResourceKey, MeshNavigationBounds] = {}

    def resolve(self, object_key: ZoneResourceKey) -> ObjectCollisionProfile:
        if not isinstance(object_key, ZoneResourceKey):
            raise ValueError("object_key must be ZoneResourceKey")
        object_entry = _require_entry(self._object_entries, object_key, "CObject")
        metadata = parse_object_navigation_metadata(
            self._objects.read_resource(object_entry)
        )
        if metadata.render_key == ZoneResourceKey(0, 0):
            return ObjectCollisionProfile(object_key, metadata.name, (), None)

        colliding_meshes: list[ZoneResourceKey] = []
        maximum_radius: float | None = None
        active: set[ZoneResourceKey] = set()
        visited_nodes = 0

        def visit(
            render_key: ZoneResourceKey,
            parent_scale: tuple[float, float, float],
            parent_location: tuple[float, float, float],
        ) -> None:
            nonlocal maximum_radius, visited_nodes
            visited_nodes += 1
            if visited_nodes > _MAX_RENDER_GRAPH_NODES:
                raise ObjectNavigationFormatError("Render graph exceeds its node bound")
            if render_key in active:
                raise ObjectNavigationFormatError("Render graph contains a cycle")
            active.add(render_key)
            try:
                render = self._read_render(render_key)
                scale = tuple(
                    parent_scale[index] * render.scale[index] for index in range(3)
                )
                local_location = render.location or (0.0, 0.0, 0.0)
                location = tuple(
                    parent_location[index]
                    + parent_scale[index] * local_location[index]
                    for index in range(3)
                )
                if render.collides:
                    for mesh_key in render.mesh_keys:
                        bounds = self._read_mesh(mesh_key)
                        radius = max(
                            hypot(
                                location[0] + x * scale[0],
                                location[2] + z * scale[2],
                            )
                            for x in (bounds.minimum[0], bounds.maximum[0])
                            for z in (bounds.minimum[2], bounds.maximum[2])
                        )
                        colliding_meshes.append(mesh_key)
                        maximum_radius = (
                            radius
                            if maximum_radius is None
                            else max(maximum_radius, radius)
                        )
                for child_key in render.child_keys:
                    visit(child_key, scale, location)
            finally:
                active.remove(render_key)

        visit(metadata.render_key, metadata.scale, (0.0, 0.0, 0.0))
        return ObjectCollisionProfile(
            object_key=object_key,
            name=metadata.name,
            colliding_mesh_keys=tuple(colliding_meshes),
            horizontal_radius=maximum_radius,
        )

    def _read_render(self, key: ZoneResourceKey) -> RenderNavigationMetadata:
        cached = self._render_cache.get(key)
        if cached is None:
            entry = _require_entry(self._render_entries, key, "Render")
            cached = parse_render_navigation_metadata(self._renders.read_resource(entry))
            self._render_cache[key] = cached
        return cached

    def _read_mesh(self, key: ZoneResourceKey) -> MeshNavigationBounds:
        cached = self._mesh_cache.get(key)
        if cached is None:
            entry = _require_entry(self._mesh_entries, key, "Mesh")
            cached = parse_mesh_navigation_bounds(self._meshes.read_resource(entry))
            self._mesh_cache[key] = cached
        return cached


def _skip_texture_set(reader: _NavigationReader, *, depth: int) -> None:
    if depth >= _MAX_TEXTURE_DEPTH:
        raise ObjectNavigationFormatError("Render texture nesting exceeds its bound")
    texture_type = reader.u32("texture type")
    reader.resource_key("texture resource")
    reader.u32("texture transparency")
    for field_name in (
        "compression flag",
        "normal-map flag",
        "detail-normal-map flag",
        "mipmap flag",
    ):
        reader.boolean(f"texture {field_name}")
    if texture_type in (0, 1):
        reader.string("texture string 0")
        reader.string("texture string 1")
        reader.u32("texture integer 0")
        reader.u32("texture integer 1")
        reader.boolean("texture unknown flag")
        reader.boolean("texture wrap flag")
        return
    if texture_type == 3:
        reader.f32("animated texture frame timer")
        reader.f32("animated texture scalar")
        reader.u32("animated texture frame randomizer")
        nested_count = reader.count("animated texture sets")
        for _ in range(nested_count):
            _skip_texture_set(reader, depth=depth + 1)
        return
    raise ObjectNavigationFormatError(f"Render texture type {texture_type} is unsupported")


def _index_entries(
    archive: CacheArchive,
    archive_name: str,
) -> dict[ZoneResourceKey, CacheResourceEntry]:
    indexed: dict[ZoneResourceKey, CacheResourceEntry] = {}
    for entry in archive.entries:
        key = ZoneResourceKey(entry.group_id, entry.resource_id)
        if key in indexed:
            raise ObjectNavigationFormatError(
                f"{archive_name} contains duplicate resource {key.group_id}:{key.resource_id}"
            )
        indexed[key] = entry
    return indexed


def _require_entry(
    entries: dict[ZoneResourceKey, CacheResourceEntry],
    key: ZoneResourceKey,
    resource_name: str,
) -> CacheResourceEntry:
    try:
        return entries[key]
    except KeyError as exc:
        raise ObjectNavigationFormatError(
            f"{resource_name} resource {key.group_id}:{key.resource_id} is absent"
        ) from exc


class _NavigationReader:
    def __init__(self, payload: bytes, resource_name: str) -> None:
        if not isinstance(payload, bytes):
            raise ValueError(f"{resource_name} payload must be bytes")
        self._payload = payload
        self._resource_name = resource_name
        self.offset = 0

    def u32(self, field_name: str) -> int:
        return struct.unpack("<I", self._take(4, field_name))[0]

    def f32(self, field_name: str) -> float:
        value = struct.unpack("<f", self._take(4, field_name))[0]
        if not isfinite(value):
            raise ObjectNavigationFormatError(
                f"{self._resource_name} {field_name} is not finite"
            )
        return value

    def boolean(self, field_name: str) -> bool:
        value = self._take(1, field_name)[0]
        if value not in (0, 1):
            raise ObjectNavigationFormatError(
                f"{self._resource_name} {field_name} is not a binary flag"
            )
        return bool(value)

    def binary_u32(self, field_name: str) -> bool:
        value = self.u32(field_name)
        if value not in (0, 1):
            raise ObjectNavigationFormatError(
                f"{self._resource_name} {field_name} is not a binary integer"
            )
        return bool(value)

    def tuple3(self, field_name: str) -> tuple[float, float, float]:
        values = struct.unpack("<3f", self._take(12, field_name))
        if not all(isfinite(value) for value in values):
            raise ObjectNavigationFormatError(
                f"{self._resource_name} {field_name} is not finite"
            )
        return values

    def resource_key(self, field_name: str) -> ZoneResourceKey:
        return ZoneResourceKey(*struct.unpack("<II", self._take(8, field_name)))

    def string(self, field_name: str) -> str:
        length = self.count(f"{field_name} characters", maximum=4_096)
        raw = self._take(length * 2, field_name)
        try:
            return raw.decode("utf-16-le", errors="strict")
        except UnicodeDecodeError as exc:
            raise ObjectNavigationFormatError(
                f"{self._resource_name} {field_name} is not valid UTF-16LE"
            ) from exc

    def count(self, field_name: str, *, maximum: int = _MAX_COLLECTION_SIZE) -> int:
        value = self.u32(field_name)
        if value > maximum:
            raise ObjectNavigationFormatError(
                f"{self._resource_name} {field_name} count {value} exceeds {maximum}"
            )
        return value

    def _take(self, size: int, field_name: str) -> bytes:
        end = self.offset + size
        if end > len(self._payload):
            raise ObjectNavigationFormatError(
                f"{self._resource_name} ended while reading {field_name} at {self.offset}"
            )
        value = self._payload[self.offset : end]
        self.offset = end
        return value
