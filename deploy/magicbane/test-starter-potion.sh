#!/bin/bash
# Requires a disposable image container with no live volumes or published ports.
set -Eeuo pipefail
[[ "${SHADOWBANE_DISPOSABLE_TEST:-}" = 1 ]] || { echo "Disposable-test marker required" >&2; exit 1; }
query() { sudo mysql --batch --skip-column-names magicbane -e "$1"; }
[[ "$(query 'SELECT COUNT(*) FROM obj_account;')" = 0 ]]
[[ "$(query 'SELECT COUNT(*) FROM obj_character;')" = 0 ]]
install_grant() { bash /opt/shadowbane/install-starter-potion.sh; }
account=$(query "INSERT INTO object(type,parent) VALUES ('account',NULL); SET @account=LAST_INSERT_ID(); INSERT INTO obj_account(UID,acct_uname,acct_passwd) VALUES (@account,'StarterPotionTest','synthetic-test-only'); SELECT @account;")
create_character() {
    query "CALL character_CREATE($account,'$1','Test',2011,2500,0,0,0,0,0,1,0,0,0,0,0);"
}
item_count() { query "SELECT COUNT(*) FROM object o JOIN obj_item i USING(UID) WHERE o.parent=$1 AND i.item_itembaseID=980066;"; }
before=$(create_character BeforeGrant)
[[ "$before" =~ ^[0-9]+$ ]]
install_grant
[[ "$(item_count "$before")" = 0 ]]
echo "PASS existing character untouched"
first=$(create_character PotionFirst)
[[ "$first" =~ ^[0-9]+$ ]]
[[ "$(query "SELECT type FROM object WHERE UID=$first;")" = character ]]
[[ "$(query "SELECT COUNT(*) FROM object o JOIN obj_item i USING(UID) WHERE o.parent=$first AND o.type='item' AND i.item_itembaseID=980066 AND i.item_chargesRemaining=5 AND i.item_numberOfItems=1 AND i.item_container='inventory' AND i.item_flags=1;")" = 1 ]]
echo "PASS real character_CREATE returns character and grants one five-charge inventory potion"
first_item=$(query "SELECT o.UID FROM object o JOIN obj_item i USING(UID) WHERE o.parent=$first AND i.item_itembaseID=980066;")
query "UPDATE obj_item SET item_chargesRemaining=4 WHERE UID=$first_item; UPDATE obj_character SET char_isActive=0 WHERE UID=$first; UPDATE obj_character SET char_isActive=1 WHERE UID=$first;"
install_grant
query "CALL character_GETBYUID($first);" >/dev/null
[[ "$(item_count "$first")" = 1 ]]
[[ "$(query "SELECT item_chargesRemaining FROM obj_item WHERE UID=$first_item;")" = 4 ]]
echo "PASS reload and repeat installation neither duplicate nor refill potion"
# Verify actual persisted state across clean database shutdown and start.
sudo mysqladmin shutdown
sudo service mysql start
install_grant
[[ "$(item_count "$first")" = 1 ]]
[[ "$(query "SELECT item_chargesRemaining FROM obj_item WHERE UID=$first_item;")" = 4 ]]
[[ "$(item_count "$before")" = 0 ]]
second=$(create_character PotionSecond)
[[ "$second" =~ ^[0-9]+$ ]]
[[ "$(item_count "$second")" = 1 ]]
echo "PASS restart preserves consumed charge and next character gets its own potion"
fingerprint() {
    query "CHECKSUM TABLE object,obj_account,obj_character,obj_item EXTENDED;"
}
# Fail after the trigger has inserted the item's object row.
query "CREATE TRIGGER reject_test_potion BEFORE INSERT ON obj_item FOR EACH ROW SET NEW.item_chargesRemaining=NULL;"
baseline=$(fingerprint)
failed=$(create_character PotionFailed)
[[ "$failed" = -1* ]]
[[ "$(fingerprint)" = "$baseline" ]]
echo "PASS potion insertion failure rolls back character and orphan item object"
query "DROP TRIGGER reject_test_potion;"
# Missing/corrupt template fails both startup verification and subsequent creation.
query "UPDATE static_itembase SET numCharges=4 WHERE ID=980066;"
if install_grant >/dev/null 2>&1; then echo "Unexpected invalid-template acceptance" >&2; exit 1; fi
baseline=$(fingerprint)
failed=$(create_character PotionBadBase)
[[ "$failed" = -1* ]]
[[ "$(fingerprint)" = "$baseline" ]]
query "UPDATE static_itembase SET numCharges=5 WHERE ID=980066;"
install_grant
echo "PASS template mismatch rejects startup and character creation without partial data"
query "CREATE TRIGGER unexpected_character_hook BEFORE INSERT ON obj_character FOR EACH ROW SET @test_hook=1;"
if install_grant >/dev/null 2>&1; then echo "Unexpected insertion-hook acceptance" >&2; exit 1; fi
query "DROP TRIGGER unexpected_character_hook;"
query "DROP TRIGGER shadowbane_starter_potion; CREATE TRIGGER shadowbane_starter_potion AFTER INSERT ON obj_character FOR EACH ROW SET @test_hook=1;"
if install_grant >/dev/null 2>&1; then echo "Unexpected replaced-trigger acceptance" >&2; exit 1; fi
echo "PASS unknown or modified trigger is rejected without replacement"
echo "All starter potion integration checks passed."
