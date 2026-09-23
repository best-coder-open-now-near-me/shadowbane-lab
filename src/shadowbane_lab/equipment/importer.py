"""Build a provenance-aware equipment catalog from reviewed public snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

EQUIPPABLE_TYPES = frozenset({"ARMOR", "JEWELRY", "WEAPON"})
TABLE_FILES = {
    "general": ("TreasureTables/GeneralItemTables.wpak", ".gentable"),
    "item": ("TreasureTables/ItemTables.wpak", ".itemtable"),
    "modifier": ("TreasureTables/ModTables.wpak", ".modtable"),
    "modifier_type": ("TreasureTables/ModTypeTables.wpak", ".modtypetable"),
}


class EquipmentImportError(ValueError):
    """Raised when a source snapshot cannot be normalized without guessing."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_file(manifest: dict[str, Any], source_path: str) -> dict[str, Any]:
    matches = [item for item in manifest["files"] if item.get("path") == source_path]
    if len(matches) != 1:
        raise EquipmentImportError(f"manifest must contain exactly one {source_path}")
    return matches[0]


def _verify_file(path: Path, record: dict[str, Any], source_path: str) -> dict[str, Any]:
    size = path.stat().st_size
    digest = _sha256(path)
    if size != record.get("size") or digest != record.get("sha256"):
        raise EquipmentImportError(f"{source_path} does not match the official manifest")
    return {"path": source_path, "size": size, "sha256": digest}


def _archive_ids(path: Path, extension: str) -> set[int]:
    result: set[int] = set()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            member = PurePosixPath(name)
            if member.name != name or member.suffix != extension:
                raise EquipmentImportError(f"unexpected archive member {name!r} in {path.name}")
            try:
                table_id = int(member.stem)
            except ValueError as exc:
                raise EquipmentImportError(f"non-numeric table member {name!r}") from exc
            if table_id in result:
                raise EquipmentImportError(f"duplicate table id {table_id} in {path.name}")
            result.add(table_id)
    return result


def _extract_insert(sql: str, table: str) -> str:
    marker = f"INSERT INTO `{table}` VALUES "
    start = sql.find(marker)
    if start < 0:
        raise EquipmentImportError(f"missing INSERT for {table}")
    start += len(marker)
    end = sql.find(";", start)
    if end < 0:
        raise EquipmentImportError(f"unterminated INSERT for {table}")
    return sql[start:end]


def _sql_rows(sql: str, table: str) -> list[tuple[Any, ...]]:
    text = _extract_insert(sql, table)
    rows: list[tuple[Any, ...]] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] == ",":
            cursor += 1
        if cursor >= len(text) or text[cursor] != "(":
            raise EquipmentImportError(f"invalid tuple boundary in {table} at {cursor}")
        cursor += 1
        row: list[Any] = []
        while True:
            value, cursor = _sql_value(text, cursor, table)
            row.append(value)
            if cursor >= len(text):
                raise EquipmentImportError(f"unterminated row in {table}")
            if text[cursor] == ",":
                cursor += 1
                continue
            if text[cursor] == ")":
                cursor += 1
                break
            raise EquipmentImportError(f"invalid field boundary in {table} at {cursor}")
        rows.append(tuple(row))
    return rows


def _sql_value(text: str, cursor: int, table: str) -> tuple[Any, int]:
    if text[cursor] == "'":
        cursor += 1
        result: list[str] = []
        escapes = {"0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a"}
        while cursor < len(text):
            character = text[cursor]
            cursor += 1
            if character == "'":
                return "".join(result), cursor
            if character == "\\":
                if cursor >= len(text):
                    raise EquipmentImportError(f"unterminated escape in {table}")
                escaped = text[cursor]
                cursor += 1
                result.append(escapes.get(escaped, escaped))
            else:
                result.append(character)
        raise EquipmentImportError(f"unterminated string in {table}")

    end = cursor
    while end < len(text) and text[end] not in ",)":
        end += 1
    token = text[cursor:end].strip()
    if token == "NULL":
        return None, end
    try:
        if "." in token or "e" in token.lower():
            return float(token), end
        return int(token), end
    except ValueError as exc:
        raise EquipmentImportError(f"invalid scalar {token!r} in {table}") from exc


def _current_items(path: Path) -> dict[int, str]:
    pattern = re.compile(r'^([0-9]+) "((?:[^"\\]|\\.)*)" [MFN] ".*"$')
    result: dict[int, str] = {}
    for line in path.read_text(encoding="cp1252").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        item_id = int(match.group(1))
        name = match.group(2).replace('\\"', '"').replace("\\\\", "\\")
        if item_id in result:
            raise EquipmentImportError(f"duplicate current item id {item_id}")
        result[item_id] = name
    if not result:
        raise EquipmentImportError("official item dictionary contained no records")
    return result


def _current_affixes(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    prefixes: dict[str, str] = {}
    suffixes: dict[str, str] = {}
    for line in path.read_text(encoding="utf-16").splitlines():
        if not line.startswith('"Effect'):
            continue
        fields = shlex.split(line, posix=True)
        if len(fields) < 2:
            continue
        key, display = fields[:2]
        if key.startswith("EffectPrefix:"):
            prefixes[key.removeprefix("EffectPrefix:")] = display
        elif key.startswith("EffectSuffix:"):
            suffixes[key.removeprefix("EffectSuffix:")] = display
    if not prefixes or not suffixes:
        raise EquipmentImportError("official effect dictionary lacks prefix or suffix records")
    return prefixes, suffixes


def _base_items(
    rows: list[tuple[Any, ...]],
    requirement_rows: list[tuple[Any, ...]],
    current_items: dict[int, str],
) -> list[dict[str, Any]]:
    requirements: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for _, item_id, kind, required, token in requirement_rows:
        requirements[item_id].append(
            {"kind": kind, "required": bool(required), "token": token}
        )

    result: list[dict[str, Any]] = []
    for row in rows:
        item_id, historical_name, item_type = row[:3]
        if item_type not in EQUIPPABLE_TYPES or item_id not in current_items:
            continue
        name = current_items[item_id]
        result.append(
            {
                "item_id": item_id,
                "name": name,
                "historical_name": historical_name,
                "item_type": item_type,
                "durability": row[3],
                "equip_flags": row[4],
                "restrict_flags": row[5],
                "value": row[6],
                "weight": row[7],
                "skill_required": row[9],
                "skill_percent_required": row[10],
                "mastery": row[11],
                "slash_resist": row[12],
                "crush_resist": row[13],
                "pierce_resist": row[14],
                "block_modifier": row[15],
                "defense": row[16],
                "dexterity_penalty": row[17],
                "damage_type": row[18],
                "speed": row[19],
                "range": row[20],
                "minimum_damage": row[21],
                "maximum_damage": row[22],
                "two_handed": bool(row[23]),
                "strength_based": bool(row[24]),
                "parry_bonus": row[25],
                "modifier_table_id": row[30],
                "item_hash_id": row[31],
                "current_name_verified": name == historical_name,
                "requirements": sorted(
                    requirements.get(item_id, []), key=lambda item: (item["kind"], item["token"])
                ),
            }
        )
    return sorted(result, key=lambda item: item["item_id"])


def build_catalog(
    *,
    sql_path: Path,
    manifest_path: Path,
    item_english_path: Path,
    effects_english_path: Path,
    general_tables_path: Path,
    item_tables_path: Path,
    modifier_tables_path: Path,
    modifier_type_tables_path: Path,
    retrieved_on: str,
) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    local_files = {
        "Config/ItemENGLISH.txt": item_english_path,
        "Config/EffectsENGLISH.txt": effects_english_path,
        "TreasureTables/GeneralItemTables.wpak": general_tables_path,
        "TreasureTables/ItemTables.wpak": item_tables_path,
        "TreasureTables/ModTables.wpak": modifier_tables_path,
        "TreasureTables/ModTypeTables.wpak": modifier_type_tables_path,
    }
    verified_files = [
        _verify_file(path, _manifest_file(manifest, source_path), source_path)
        for source_path, path in local_files.items()
    ]
    archive_paths = {
        "general": general_tables_path,
        "item": item_tables_path,
        "modifier": modifier_tables_path,
        "modifier_type": modifier_type_tables_path,
    }
    current_table_ids = {
        key: _archive_ids(archive_paths[key], TABLE_FILES[key][1]) for key in TABLE_FILES
    }

    current_items = _current_items(item_english_path)
    current_prefixes, current_suffixes = _current_affixes(effects_english_path)
    sql = sql_path.read_text(encoding="utf-8")
    item_base_rows = _sql_rows(sql, "static_itembase")
    requirement_rows = _sql_rows(sql, "static_item_itemrequirement")
    modifier_rows = _sql_rows(sql, "static_loot_mod")
    pool_rows = _sql_rows(sql, "static_loot_modtype")
    generation_rows = _sql_rows(sql, "static_loot_gen")
    item_table_rows = _sql_rows(sql, "static_loot_item")

    base_items = _base_items(item_base_rows, requirement_rows, current_items)
    base_item_ids = {item["item_id"] for item in base_items}

    modifiers = [
        {
            "table_id": row[0],
            "table_name": row[1],
            "minimum_roll": row[2],
            "maximum_roll": row[3],
            "action_id": row[4],
            "level": row[5],
            "value": row[6],
            "current_prefix_name": current_prefixes.get(row[4]),
            "current_suffix_name": current_suffixes.get(row[4]),
        }
        for row in modifier_rows
        if row[0] in current_table_ids["modifier"]
    ]
    modifiers.sort(key=lambda item: (item["table_id"], item["minimum_roll"], item["action_id"]))
    modifier_table_ids = {item["table_id"] for item in modifiers}

    prefix_pool_ids = {
        row[7] for row in generation_rows if row[7] in current_table_ids["modifier_type"]
    }
    suffix_pool_ids = {
        row[9] for row in generation_rows if row[9] in current_table_ids["modifier_type"]
    }
    grouped_pool_rows: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in pool_rows:
        if row[0] in current_table_ids["modifier_type"] and row[4] in modifier_table_ids:
            grouped_pool_rows[row[0]].append(row)
    pools = []
    for pool_id, rows in sorted(grouped_pool_rows.items()):
        positions = []
        if pool_id in prefix_pool_ids:
            positions.append("prefix")
        if pool_id in suffix_pool_ids:
            positions.append("suffix")
        if not positions:
            continue
        pools.append(
            {
                "pool_id": pool_id,
                "name": rows[0][1],
                "positions": positions,
                "entries": [
                    {
                        "minimum_roll": row[2],
                        "maximum_roll": row[3],
                        "modifier_table_id": row[4],
                        "modifier_table_name": row[5],
                    }
                    for row in sorted(rows, key=lambda item: (item[2], item[4]))
                ],
            }
        )
    pool_ids = {item["pool_id"] for item in pools}

    items_by_table: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in item_table_rows:
        if row[0] in current_table_ids["item"] and row[5] in base_item_ids:
            items_by_table[row[0]].append(row)
    routes = set()
    for row in generation_rows:
        try:
            generation_table_id = int(row[0])
        except ValueError:
            continue
        if generation_table_id not in current_table_ids["general"]:
            continue
        prefix_pool_id = row[7] if row[7] in pool_ids else None
        suffix_pool_id = row[9] if row[9] in pool_ids else None
        for item_row in items_by_table.get(row[4], []):
            routes.add(
                (
                    generation_table_id,
                    row[1],
                    row[4],
                    row[5],
                    item_row[5],
                    prefix_pool_id,
                    suffix_pool_id,
                )
            )
    route_records = [
        {
            "generation_table_id": row[0],
            "generation_table_name": row[1],
            "item_table_id": row[2],
            "item_table_name": row[3],
            "item_id": row[4],
            "prefix_pool_id": row[5],
            "suffix_pool_id": row[6],
        }
        for row in sorted(routes)
    ]

    historical_ids = {
        "general": {int(row[0]) for row in generation_rows if str(row[0]).isdigit()},
        "item": {row[0] for row in item_table_rows},
        "modifier": {row[0] for row in modifier_rows},
        "modifier_type": {row[0] for row in pool_rows},
    }
    alignment = {
        key: {
            "current_count": len(current_table_ids[key]),
            "historical_count": len(historical_ids[key]),
            "missing_historical_ids": sorted(current_table_ids[key] - historical_ids[key]),
            "not_in_current_ids": sorted(historical_ids[key] - current_table_ids[key]),
        }
        for key in TABLE_FILES
    }
    direct_display_matches = sum(
        item["current_prefix_name"] is not None or item["current_suffix_name"] is not None
        for item in modifiers
    )
    name_verified = sum(item["current_name_verified"] for item in base_items)
    sb_record = _manifest_file(manifest, "sb.exe")
    return {
        "schema_version": 1,
        "catalog_id": "wonderbane_equipment_candidate_v1",
        "target_variant": "WonderBane",
        "status": "current_table_identity_historical_values",
        "retrieved_on": retrieved_on,
        "sources": [
            {
                "source_id": "wonderbane_official_manifest_20260518_185052",
                "kind": "current_official_client_manifest_and_dictionaries",
                "uri": "http://87.99.132.84/manifest.json",
                "revision": manifest["version"],
                "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            },
            {
                "source_id": "magicbane_magicbox_20230810",
                "kind": "historical_public_emulator_sql_candidate",
                "uri": "docker.io/magicbane/magicbox:latest",
                "revision": (
                    "sha256:914b44d019597f0e20b9181a6429576948913670a301b7a79114356c69074ed8"
                ),
                "data_layer_sha256": (
                    "7275e5608da5b07188e4ab81a2e66a3947c940378b73dfce1a59c83c9a55225b"
                ),
                "sql_sha256": _sha256(sql_path),
            },
        ],
        "coverage": {
            "base_item_values": "historical_candidate",
            "affix_values": "historical_candidate",
            "base_item_display_identity": "current_official_dictionary_checked",
            "current_affix_name_dictionary": "complete_current_official_dictionary",
            "historical_modifier_to_current_name_join": "partial_direct_key_match_only",
            "table_identity": "current_official_archive_checked",
            "class_and_rune_requirement_tokens": "preserved_opaque",
            "baked_unique_item_effects": "not_in_first_slice",
            "notes": (
                "Numeric rows come from the pinned historical emulator snapshot. Current encrypted "
                "WPAK member IDs and current English identities are verified, but numeric equality "
                "with WonderBane remains pending live decoding."
            ),
            "counts": {
                "base_items": len(base_items),
                "base_item_names_exactly_matched": name_verified,
                "modifiers": len(modifiers),
                "modifiers_with_direct_current_display_key_match": direct_display_matches,
                "current_prefix_names": len(current_prefixes),
                "current_suffix_names": len(current_suffixes),
                "pools": len(pools),
                "routes": len(route_records),
            },
            "table_alignment": alignment,
        },
        "current_client": {
            "manifest_version": manifest["version"],
            "game_version": manifest["gameVersion"],
            "sb_exe_sha256": sb_record["sha256"],
            "verified_files": verified_files,
            "affix_dictionary": {
                "prefixes": [
                    {"key": key, "display_name": value}
                    for key, value in sorted(current_prefixes.items())
                ],
                "suffixes": [
                    {"key": key, "display_name": value}
                    for key, value in sorted(current_suffixes.items())
                ],
            },
        },
        "base_items": base_items,
        "modifiers": modifiers,
        "pools": pools,
        "routes": route_records,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--item-english", type=Path, required=True)
    parser.add_argument("--effects-english", type=Path, required=True)
    parser.add_argument("--general-tables", type=Path, required=True)
    parser.add_argument("--item-tables", type=Path, required=True)
    parser.add_argument("--modifier-tables", type=Path, required=True)
    parser.add_argument("--modifier-type-tables", type=Path, required=True)
    parser.add_argument("--retrieved-on", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    catalog = build_catalog(
        sql_path=arguments.sql,
        manifest_path=arguments.manifest,
        item_english_path=arguments.item_english,
        effects_english_path=arguments.effects_english,
        general_tables_path=arguments.general_tables,
        item_tables_path=arguments.item_tables,
        modifier_tables_path=arguments.modifier_tables,
        modifier_type_tables_path=arguments.modifier_type_tables,
        retrieved_on=arguments.retrieved_on,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(catalog, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(catalog["coverage"]["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
