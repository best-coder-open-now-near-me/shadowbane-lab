-- Compatibility with official CObjects.cache SHA-256
-- 08c115baeef5da811f7ee2802ccdc1002cfeba29cf1818956c452e3e594efef6.
-- Only five Human bloodline cost attributes change. Character rows are untouched.
-- Run with the mysql batch client WITHOUT --force; an assertion error closes
-- the connection and rolls back. The required tables must use InnoDB.
CREATE TEMPORARY TABLE shadowbane_cost_assert (
    valid TINYINT NOT NULL CHECK (valid = 1)
) ENGINE=InnoDB;
INSERT INTO shadowbane_cost_assert
SELECT IF(COUNT(*) = 2, 1, 0) FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('static_rune_runebase', 'static_rune_runebaseattribute')
  AND engine = 'InnoDB';
START TRANSACTION;
SELECT ID FROM static_rune_runebase
WHERE ID IN (252129,252130,252131,252132,252133) FOR UPDATE;
SELECT ID FROM static_rune_runebaseattribute
WHERE RuneBaseID IN (252129,252130,252131,252132,252133)
  AND attributeID = 0 FOR UPDATE;
-- Match exact identities and reject missing/duplicate cost rows or custom costs.
INSERT INTO shadowbane_cost_assert
SELECT IF(COUNT(*) = 5 AND COUNT(DISTINCT r.ID) = 5
    AND SUM(a.modValue IN (0,10)) = 5
    AND SUM((r.ID = 252129 AND BINARY r.name = 'Born of the Ethyri')
         OR (r.ID = 252130 AND BINARY r.name = 'Born of the Taripontor')
         OR (r.ID = 252131 AND BINARY r.name = 'Born of the Gwendannen')
         OR (r.ID = 252132 AND BINARY r.name = 'Born of the Invorri')
         OR (r.ID = 252133 AND BINARY r.name = 'Born of the Irydnu')) = 5, 1, 0)
FROM static_rune_runebase r
JOIN static_rune_runebaseattribute a ON a.RuneBaseID = r.ID
WHERE r.ID IN (252129,252130,252131,252132,252133) AND a.attributeID = 0;
UPDATE static_rune_runebaseattribute SET modValue = 0
WHERE RuneBaseID IN (252129,252130,252131,252132,252133)
  AND attributeID = 0 AND modValue = 10;
INSERT INTO shadowbane_cost_assert
SELECT IF(COUNT(*) = 5 AND COUNT(DISTINCT RuneBaseID) = 5
    AND SUM(modValue = 0) = 5, 1, 0)
FROM static_rune_runebaseattribute
WHERE RuneBaseID IN (252129,252130,252131,252132,252133) AND attributeID = 0;
COMMIT;
DROP TEMPORARY TABLE shadowbane_cost_assert;
