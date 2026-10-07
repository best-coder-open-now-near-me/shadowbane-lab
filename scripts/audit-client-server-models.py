"""Compare client cache namespaces with explicit pinned server database references."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from shadowbane_lab.equipment.importer import _sql_value

REFERENCES = (
    ("items", "static_itembase", "ID", "CObjects.cache"),
    ("mob_loads", "static_npc_mobbase", "loadID", "CObjects.cache"),
    ("race_definitions", "static_rune_race", "ID", "CObjects.cache"),
    ("placed_buildings", "obj_building", "meshUUID", "CObjects.cache"),
    ("placed_zones", "obj_zone", "LoadNum", "CZone.cache"),
    ("zone_sizes", "static_zone_size", "loadNum", "CZone.cache"),
    ("building_rank0", "static_building_blueprint", "Rank0UUID", "CObjects.cache"),
    ("building_rank1", "static_building_blueprint", "Rank1UUID", "CObjects.cache"),
    ("building_rank3", "static_building_blueprint", "Rank3UUID", "CObjects.cache"),
    ("building_rank7", "static_building_blueprint", "Rank7UUID", "CObjects.cache"),
    ("building_destroyed", "static_building_blueprint", "DestroyedUUID", "CObjects.cache"),
)


def sql_rows(sql, table):
    """Read positional dump inserts, including repeated statements and quoted semicolons."""
    marker = f"INSERT INTO `{table}` VALUES "
    position = 0
    while (position := sql.find(marker, position)) != -1:
        position += len(marker)
        while True:
            while sql[position].isspace():
                position += 1
            if sql[position] != "(":
                raise ValueError(f"Expected row in {table}")
            position += 1
            values = []
            while True:
                value, position = _sql_value(sql, position, table)
                values.append(value)
                if sql[position] == ")":
                    position += 1
                    break
                if sql[position] != ",":
                    raise ValueError(f"Expected field in {table}")
                position += 1
            yield values
            while sql[position].isspace():
                position += 1
            if sql[position] == ";":
                position += 1
                break
            if sql[position] != ",":
                raise ValueError(f"Expected next row in {table}")
            position += 1


def columns(sql, table):
    match = re.search(r"CREATE TABLE `" + re.escape(table) + r"` \((.*?)\) ENGINE=", sql, re.S)
    if not match:
        raise ValueError(f"Missing schema {table}")
    return re.findall(r"^\s+`([^`]+)`", match[1], re.M)


def analyze(catalog, sql):
    index = defaultdict(list)
    classes = Counter()
    untrusted_prefixes = 0
    for row in catalog:
        index[(row["archive"], row["group_id"], row["resource_id"])].append(row)
        prefix = row.get("object_prefix")
        if prefix:
            classes[str(prefix["object_type"])] += 1
            if any(ord(c) < 32 for c in prefix["name"]):
                untrusted_prefixes += 1
    joins = []
    tables = {}
    for category, table, field, archive in REFERENCES:
        try:
            if table not in tables:
                tables[table] = (columns(sql, table), list(sql_rows(sql, table)))
            names, rows = tables[table]
            field_index = names.index(field)
            if any(len(row) != len(names) for row in rows):
                raise ValueError(f"Column count mismatch in {table}")
            values = Counter(row[field_index] for row in rows)
            present, missing, ambiguous = [], [], []
            for value in sorted(v for v in values if isinstance(v, int) and v > 0):
                matches = index.get((archive, 0, value), [])
                if len(matches) == 1:
                    present.append(value)
                elif len(matches) > 1:
                    ambiguous.append(value)
                else:
                    missing.append(value)
            joins.append(
                {
                    "category": category,
                    "table": table,
                    "field": field,
                    "archive": archive,
                    "group_id": 0,
                    "rows": len(rows),
                    "present_unique": len(present),
                    "missing_ids": missing,
                    "ambiguous_ids": ambiguous,
                    "nonpositive_or_noninteger_rows": sum(
                        n for v, n in values.items() if not isinstance(v, int) or v <= 0
                    ),
                    "status": "id_coverage_only",
                }
            )
        except (ValueError, IndexError) as exc:
            joins.append({"category": category, "error": str(exc)})
    return {
        "schema_version": 1,
        "object_prefix_type_counts": dict(classes),
        "object_prefixes_with_control_characters": untrusted_prefixes,
        "joins": joins,
        "limitations": [
            "Resource identity includes archive, group and ID; this audit tests group zero only.",
            "ID presence does not prove field layout, visuals, gameplay or wire compatibility.",
            "CObject prefix parsing is not a complete schema; suspect names remain unclassified.",
            "Dynamic native object keys are not resource IDs and are not joined here.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--sql", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sql_bytes = args.sql.read_bytes()
    with args.catalog.open(encoding="utf-8") as stream:
        report = analyze((json.loads(line) for line in stream), sql_bytes.decode("utf-8"))
    report["database_sha256"] = hashlib.sha256(sql_bytes).hexdigest()
    with args.catalog.open("rb") as stream:
        report["catalog_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
