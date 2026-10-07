import importlib.util
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "audit-client-server-models.py"
spec = importlib.util.spec_from_file_location("model_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_dump_reader_preserves_semicolon_inside_string_and_multiple_inserts():
    sql = "INSERT INTO `t` VALUES (1,'a;b'),(2,'it\\'s');\nINSERT INTO `t` VALUES (3,NULL);"
    assert list(audit.sql_rows(sql, "t")) == [[1, "a;b"], [2, "it's"], [3, None]]


def test_namespace_ambiguity_and_absence_are_distinct():
    rows = [
        {"archive": archive, "group_id": group, "resource_id": key}
        for archive, group, key in [
            ("CObjects.cache", 0, 1),
            ("CObjects.cache", 0, 2),
            ("CObjects.cache", 0, 2),
            ("CObjects.cache", 1, 3),
            ("Mesh.cache", 0, 4),
        ]
    ]
    sql = (
        "CREATE TABLE `t` (\n `ID` int\n) ENGINE=InnoDB;\n"
        "INSERT INTO `t` VALUES (0),(1),(2),(3),(4);"
    )
    with patch.object(audit, "REFERENCES", (("test", "t", "ID", "CObjects.cache"),)):
        result = audit.analyze(rows, sql)["joins"][0]
    assert result["present_unique"] == 1
    assert result["ambiguous_ids"] == [2]
    assert result["missing_ids"] == [3, 4]
    assert result["nonpositive_or_noninteger_rows"] == 1
    assert result["status"] == "id_coverage_only"


def test_malformed_schema_is_not_reported_as_compatible():
    with patch.object(audit, "REFERENCES", (("test", "missing", "ID", "CObjects.cache"),)):
        result = audit.analyze([], "")["joins"][0]
    assert "error" in result and "present_unique" not in result


def test_observed_templates_are_joined_without_exporting_private_identities():
    item = {"item_key": [999999, 30], "template_key": [980066, 0],
            "quantity_raw": 5, "class": "ArcItem"}
    changed = dict(item, quantity_raw=4)
    records = [
        {"character": ["private-name", "server", 12345, 53], "kind": "observation_recovered",
         "delta": {"kind": "initial_inventory", "items": [item]}},
        {"kind": "inventory_change", "changed": [{"before": item, "after": changed}]},
        {"kind": "observation_unavailable", "error": "transient"},
    ]
    catalog = [{"archive": "CObjects.cache", "group_id": 0, "resource_id": 980066,
                "object_prefix": {"object_type": 3, "name": "Greater Concoction Potion"}}]
    sql = (
        "CREATE TABLE `static_itembase` (\n `ID` int,\n `name` text,\n `type` text,\n"
        " `numCharges` int,\n `useID` int,\n `useAmount` int\n) ENGINE=InnoDB;\n"
        "INSERT INTO `static_itembase` VALUES (980066,'Greater Concoction Potion','POTION',"
        "5,429021400,35);"
    )
    report = audit.audit_inventory(records, catalog, sql)
    assert report["unique_templates"] == report["distinct_instances"] == 1
    row = report["templates"][0]
    assert row["observed_raw_counts"] == [4, 5]
    assert row["server_definition"]["numCharges"] == 5
    assert row["native_instance_types"] == [30]
    assert "private-name" not in str(report) and "999999" not in str(report)
    assert report["missing_client_templates"] == report["missing_server_items"] == []
    missing = audit.audit_inventory(records, [], sql)
    assert missing["missing_client_templates"] == [980066]
