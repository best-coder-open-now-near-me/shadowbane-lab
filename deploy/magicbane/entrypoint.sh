#!/bin/bash
# Fixed-source local server; never invoke the upstream branch-pulling entrypoint.
set -Eeuo pipefail
cd /home/mbbox/magicbane
login_pid=""
world_pid=""
cleanup() {
    local result=$?
    trap - EXIT TERM INT
    for pid in "$login_pid" "$world_pid"; do
        if [[ -n "$pid" ]]; then kill -TERM "$pid" 2>/dev/null || true; fi
    done
    # Let Java persist outstanding state before shutting down its database.
    for ((attempt=0; attempt<40; attempt++)); do
        local running=0
        for pid in "$login_pid" "$world_pid"; do
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then running=1; fi
        done
        [[ "$running" == 0 ]] && break
        sleep 1
    done
    for pid in "$login_pid" "$world_pid"; do
        if [[ -n "$pid" ]]; then
            kill -KILL "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
    sudo mysqladmin shutdown 2>/dev/null || true
    exit "$result"
}
trap cleanup EXIT
trap 'exit 0' TERM INT

password=$(tr -d '\r\n' < /run/secrets/database-password)
[[ "$password" =~ ^[0-9a-f]{64}$ ]] || { echo "Invalid database secret format" >&2; exit 2; }
sudo service mysql start
sudo mysql --batch --skip-column-names <<SQL
CREATE USER IF NOT EXISTS 'shadowbane'@'localhost' IDENTIFIED BY '$password';
ALTER USER 'shadowbane'@'localhost' IDENTIFIED BY '$password';
GRANT ALL PRIVILEGES ON magicbane.* TO 'shadowbane'@'localhost';
SET GLOBAL sql_mode=(SELECT REPLACE(@@sql_mode,'ONLY_FULL_GROUP_BY',''));
SQL
# The named database volume is seeded by Docker from this exact image on first use.
# Later starts reuse it; no import, restore, drop, or wipe runs at startup.
tables=$(sudo mysql --batch --skip-column-names -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='magicbane'")
[[ "$tables" -ge 125 ]] || { echo "Database seed is incomplete" >&2; exit 3; }

set -a
source mb.data/magicbane.conf
set +a
export MB_DATABASE_ADDRESS=localhost MB_DATABASE_PORT=3306
export MB_DATABASE_NAME=magicbane MB_DATABASE_USER=shadowbane MB_DATABASE_PASS="$password"
export MB_EXTERNAL_ADDR="${SERVER_EXTERNAL_ADDRESS:-127.0.0.1}"
export MB_BIND_ADDR="$(hostname -I | awk '{print $1}')"
export MB_WORLD_NAME="${SERVER_WORLD_NAME:-ShadowbaneLocal}"
[[ "$MB_WORLD_NAME" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "World name must contain only letters, digits, underscore or hyphen" >&2; exit 4; }
export MB_LOGIN_PORT=6000 MB_WORLD_PORT=8000 MB_LOGIN_AUTOREG=TRUE
export MB_WORLD_WAREHOUSE_PUSH=false MB_WORLD_MAINTENANCE=false
export CLASSPATH='/usr/share/java/*:build/bin/magicbane.jar'
[[ -n "$MB_BIND_ADDR" ]] || { echo "Container address unavailable" >&2; exit 4; }
[[ -f "mb.data/$MB_WORLD_NAME.pop" ]] || printf '0\n' > "mb.data/$MB_WORLD_NAME.pop"

java -server -Djava.awt.headless=true -cp "$CLASSPATH" engine.server.login.LoginServer &
login_pid=$!
printf '%s\n' "$login_pid" > /tmp/shadowbane-login.pid
java -server -Djava.awt.headless=true -cp "$CLASSPATH" engine.server.world.WorldServer &
world_pid=$!
printf '%s\n' "$world_pid" > /tmp/shadowbane-world.pid

# Any component's unexpected exit ends the container instead of leaving a partial server.
while kill -0 "$login_pid" 2>/dev/null && kill -0 "$world_pid" 2>/dev/null; do
    sudo mysqladmin ping --silent >/dev/null 2>&1 || { echo "Database exited" >&2; exit 5; }
    sleep 2
done
echo "Login or world server exited" >&2
exit 6
