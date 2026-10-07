#!/bin/bash
set -euo pipefail
kill -0 "$(cat /tmp/shadowbane-login.pid)"
kill -0 "$(cat /tmp/shadowbane-world.pid)"
sudo mysqladmin ping --silent >/dev/null
for port in 6000 8000; do
    [[ -n "$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t)" ]]
done
