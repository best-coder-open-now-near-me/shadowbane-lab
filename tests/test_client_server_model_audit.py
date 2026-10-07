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
