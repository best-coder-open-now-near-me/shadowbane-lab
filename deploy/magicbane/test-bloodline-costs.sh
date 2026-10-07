#!/bin/bash
# Run only in a disposable image test container. No player data is copied.
set -Eeuo pipefail
db=shadowbane_cost_test
migration=/opt/shadowbane/bloodline-costs.sql
sudo mysql -e "CREATE DATABASE $db"
trap 'sudo mysql -e "DROP DATABASE $db"' EXIT
query() { sudo mysql --batch --skip-column-names "$db" -e "$1"; }
migrate() { sudo mysql --batch --skip-column-names "$db" < "$migration" >/dev/null; }
fingerprint() {
    query "SELECT * FROM static_rune_runebase ORDER BY ID; SELECT * FROM static_rune_runebaseattribute ORDER BY ID;" | sha256sum
}
fixture() {
    query "DROP TABLE IF EXISTS static_rune_runebaseattribute,static_rune_runebase;
CREATE TABLE static_rune_runebase LIKE magicbane.static_rune_runebase;
CREATE TABLE static_rune_runebaseattribute LIKE magicbane.static_rune_runebaseattribute;
INSERT INTO static_rune_runebase SELECT * FROM magicbane.static_rune_runebase;
INSERT INTO static_rune_runebaseattribute SELECT * FROM magicbane.static_rune_runebaseattribute;
UPDATE static_rune_runebaseattribute SET modValue=10 WHERE RuneBaseID BETWEEN 252129 AND 252136 AND attributeID=0;"
}
expect_rejection() {
    local before
    before=$(fingerprint)
    if migrate 2>/tmp/shadowbane-cost-test-error; then echo "Unexpected acceptance: $1" >&2; exit 1; fi
    [[ "$(fingerprint)" = "$before" ]] || { echo "Rejected migration changed data: $1" >&2; exit 1; }
    echo "PASS reject $1 without writes"
}
fixture
before_other=$(query "SELECT * FROM static_rune_runebaseattribute WHERE NOT (RuneBaseID BETWEEN 252129 AND 252136 AND attributeID=0) ORDER BY ID;" | sha256sum)
before_bases=$(query "SELECT * FROM static_rune_runebase ORDER BY ID;" | sha256sum)
migrate
[[ "$(query 'SELECT COUNT(*) FROM static_rune_runebaseattribute WHERE RuneBaseID BETWEEN 252129 AND 252136 AND attributeID=0 AND modValue=0;')" = 8 ]]
[[ "$(query "SELECT * FROM static_rune_runebaseattribute WHERE NOT (RuneBaseID BETWEEN 252129 AND 252136 AND attributeID=0) ORDER BY ID;" | sha256sum)" = "$before_other" ]]
[[ "$(query 'SELECT * FROM static_rune_runebase ORDER BY ID;' | sha256sum)" = "$before_bases" ]]
echo "PASS only eight cost rows changed"
first=$(fingerprint)
migrate
[[ "$(fingerprint)" = "$first" ]]
echo "PASS repeat startup is idempotent"
[[ "$(query 'SELECT 55-SUM(modValue) FROM static_rune_runebaseattribute WHERE attributeID=0 AND RuneBaseID IN (252130,250074,250078,250103,250063,250073);')" = 9 ]]
echo "PASS reported build has nine points remaining"
fixture
# Upgrade an existing Human-only correction without changing other static rows.
query "UPDATE static_rune_runebaseattribute SET modValue=0 WHERE RuneBaseID BETWEEN 252129 AND 252133 AND attributeID=0;"
migrate
[[ "$(query 'SELECT COUNT(*) FROM static_rune_runebaseattribute WHERE RuneBaseID BETWEEN 252129 AND 252136 AND attributeID=0 AND modValue=0;')" = 8 ]]
echo "PASS upgrade from Human-only correction"
fixture
query "UPDATE static_rune_runebaseattribute SET modValue=11 WHERE RuneBaseID=252135 AND attributeID=0;"
expect_rejection custom-cost
fixture
query "DELETE FROM static_rune_runebaseattribute WHERE RuneBaseID=252135 AND attributeID=0;"
expect_rejection missing-cost
fixture
query "INSERT INTO static_rune_runebaseattribute (RuneBaseID,attributeID,modValue) VALUES (252135,0,10);"
expect_rejection duplicate-cost
fixture
query "UPDATE static_rune_runebase SET name='Unexpected bloodline' WHERE ID=252135;"
expect_rejection wrong-identity
fixture
# Force a failure during the UPDATE, after valid preconditions, to test rollback.
query "CREATE TRIGGER reject_cost_update BEFORE UPDATE ON static_rune_runebaseattribute FOR EACH ROW SET NEW.modValue = IF(NEW.RuneBaseID=252135,NULL,NEW.modValue);"
expect_rejection update-error
echo "All Human/Elven bloodline cost migration checks passed."
