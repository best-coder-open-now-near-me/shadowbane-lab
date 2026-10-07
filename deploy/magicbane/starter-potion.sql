-- Created once at startup; verified by install-starter-potion.sh thereafter.
-- Runs inside character_CREATE's transaction, before the character is returned.
DELIMITER //
CREATE TRIGGER shadowbane_starter_potion
AFTER INSERT ON obj_character
FOR EACH ROW
BEGIN
    DECLARE potion_uid BIGINT UNSIGNED;
    IF (SELECT COUNT(*) FROM static_itembase
        WHERE ID = 980066 AND BINARY name = 'Greater Concoction Potion'
          AND type = 'POTION' AND numCharges = 5 AND durability = 0) <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Starter potion template mismatch';
    END IF;
    INSERT INTO object (type, parent) VALUES ('item', NEW.UID);
    SET potion_uid = LAST_INSERT_ID();
    INSERT INTO obj_item
        (UID, item_itembaseID, item_chargesRemaining,
         item_durabilityCurrent, item_durabilityMax, item_numberOfItems,
         item_equipSlot, item_container, item_flags, item_name)
    VALUES (potion_uid, 980066, 5, 0, 0, 1, 0, 'inventory', 1, '');
END
//
DELIMITER ;
