# Private tester report delivery

The Windows app finds logged-in characters and separates recording from report
review/delivery. A tester explicitly presses Send report. Report bundles stay
local if sending fails, and the same SHA-256 is retried without duplicate storage.
A report is marked Sent only after the server returns its matching durable receipt.

## Server ownership

The receiver is a diagnostics sidecar in shadowbane-lab, not a gameplay service
or a database importer. It accepts only the bounded recorder evidence format.
It stores immutable ZIPs plus a SQLite receipt index; it provides no download,
listing, admin or game-database route. Input is never extracted or executed.

Run the committed package with its report-server optional dependency (Waitress).
The service listens on loopback 127.0.0.1:8765 only. Mount it at
/shadowbane-reports/ through the existing private Tailscale HTTPS service,
preserving the separately owned /shadowbane-updates/ handler. Do not enable
Funnel or publish the backend port. Existing Tailscale device-sharing policy must
permit the intended tester's access to this HTTPS service.

Keep server configuration and the client's connection.json outside Git:
- receiver config: reporter_token_sha256 (list of SHA-256 hashes),
  maximum_store_bytes (default 10 GiB), maximum_daily_reports (default 100/token).
- client config: url (HTTPS base ending /shadowbane-reports), token (random
  upload-only capability, 32-128 ASCII characters). Use a separate token per
  distributed tester installer; remove its hash to revoke it.
These are report-upload capabilities, never server/database/admin credentials.

Receiver endpoint POST /v1/reports/{sha256} verifies authentication, bounded ZIP
geometry, manifest and artifact digests. Publication precedes its transactional
receipt index so an interrupted index write can be reconciled by retrying.
Report files/index and client captures/receipts are non-reproducible user data:
preserve them across updates. Failed upload staging is removed for that request.
Do not silently prune old reports to make space.

## App packaging

Build the clean committed portable app with scripts/build-character-recorder.ps1.
Compile deploy/character-recorder/companion.iss using Inno Setup 6, supplying
AppSource, AppExe, OutputPath and private ConnectionFile defines.
The per-user installer creates Start menu/desktop shortcuts and an uninstaller,
requires no admin password, and keeps captures outside the installation directory.
An update replaces the owned runtime without retaining rollback copies.
The distribution contains an upload capability: share it privately with its
intended tester, never in a source repository or public download.

Acceptance requires authenticated send, repeated-send same receipt, failed-send
local preservation, rejected bad auth/checksum/ZIP, and a remote tester upload.
A successful local HTTPS request does not prove the friend's Tailscale access.
