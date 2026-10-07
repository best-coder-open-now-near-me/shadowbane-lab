#!/bin/bash
# Install once; never regrant inventory, replace an unknown trigger or backfill PCs.
set -Eeuo pipefail
query() { sudo mysql --batch --skip-column-names magicbane -e "$1"; }
sql=/opt/shadowbane/starter-potion.sql
[[ "$(query "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='magicbane' AND table_name IN ('object','obj_character','obj_item') AND engine='InnoDB';")" = 3 ]] || {
    echo "Starter potion requires transactional character/item tables" >&2; exit 1;
}
[[ "$(query "SELECT COUNT(*) FROM static_itembase WHERE ID=980066 AND BINARY name='Greater Concoction Potion' AND type='POTION' AND numCharges=5 AND durability=0;")" = 1 ]] || {
    echo "Starter potion template mismatch" >&2; exit 1;
}
# Avoid silently combining this grant with an unknown character-insertion hook.
[[ "$(query "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema='magicbane' AND event_object_table='obj_character' AND event_manipulation='INSERT' AND trigger_name<>'shadowbane_starter_potion';")" = 0 ]] || {
    echo "Unexpected character insertion trigger; review before enabling starter potion" >&2; exit 1;
}
existing=$(query "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema='magicbane' AND trigger_name='shadowbane_starter_potion';")
if [[ "$existing" = 0 ]]; then
    sudo mysql --batch magicbane < "$sql"
fi
body=$(sed -n '/^BEGIN$/,/^END$/p' "$sql")
expected=$(printf '%s' "$body" | sha256sum | cut -d' ' -f1)
actual=$(query "SELECT SHA2(TRIM(action_statement),256) FROM information_schema.triggers WHERE trigger_schema='magicbane' AND trigger_name='shadowbane_starter_potion' AND event_object_table='obj_character' AND event_manipulation='INSERT' AND action_timing='AFTER' AND action_orientation='ROW' AND definer='root@localhost';")
[[ "$actual" = "$expected" ]] || { echo "Starter potion trigger definition mismatch" >&2; exit 1; }
echo "Starter potion creation grant verified"
