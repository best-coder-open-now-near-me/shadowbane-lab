#!/bin/bash
# Uses only synthetic values; never starts a database or registers an account.
set -Eeuo pipefail
cd /home/mbbox/magicbane
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
classpath='/usr/share/java/*:build/bin/magicbane.jar'
javac -cp "$classpath" -d "$scratch" /opt/shadowbane/CredentialLoggingSmoke.java
if ! java -cp "$classpath:$scratch" CredentialLoggingSmoke >"$scratch/output" 2>&1; then
    echo "Credential initialization smoke failed; output withheld" >&2
    exit 1
fi
if grep -Fq 'ShadowbaneSmokeSecret_' "$scratch/output"; then
    echo "Credential value leaked in smoke output" >&2
    exit 1
fi
grep -Fq 'Credential logging smoke passed' "$scratch/output"
echo "Credential logging smoke passed; values preserved and absent from logs"
