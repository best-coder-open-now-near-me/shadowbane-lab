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

## Installed qualification — October 7, 2026

The app payload is source a2635f09f927. Its portable ZIP SHA-256 is
94e35c31581000e574ebde662283d5d70c79f04bc32e9d4ceeddb431d5fbafaa.
The Inno Setup 6.7.3 installer recipe is committed in 625680a77ea91c4789739e237aaf47905cf33edd.
The privately configured ShadowbaneCompanion-Setup.exe SHA-256 is
356489ed92b28536ef2b1b0cf5bd5d6ab9e26434d06ebae208d40cd1fde2894c.
It installed per-user with exit 0, and its installed executable passed all five
frozen self-tests: dashboard widgets, disabled Windows hooks, native profiles,
dictation helper resource, and sealed evidence. The installer is unsigned;
Windows may show an unknown-publisher or reputation warning on download.

The private receiver is installed in E:\Services\ShadowbaneReports from
769734e3d538 (receiver code unchanged in the later app payload). A synthetic
report uploaded through loopback and its repeat returned the same durable receipt.
Private configuration, reports, SQLite index and client connection capabilities
remain outside Git. The local receipt and installation logs are under the
ignored character-recorder and watcher-layout artifact directories.

Windows denied both private HTTPS route setup and SYSTEM startup-task registration
without administrator rights. At this checkpoint the receiver runs on loopback
and starts at user sign-in; remote delivery is not activated or qualified.
The committed scripts/enable-private-report-delivery.ps1 provides the one-time
PowerShell 7 administrator setup, preserving the existing update route. After
approval, verify HTTPS health and authenticated upload/retry, then qualify access
from the friend's actual Tailscale device. Do not label loopback acceptance as
remote delivery success.

Obsolete dc7b10851237 and 769734e3d538 application packages were removed after the
current installed app passed. Compact qualification receipts and original capture
sessions remain; no deployment rollback package is retained.

## Private activation — October 8, 2026

The user continued this work for personal use; the former tester is no longer
part of the acceptance plan. No installer or capability was sent to that person
by this task. Existing private connection files retain their historical filenames.

Administrator setup succeeded. The private /shadowbane-reports/ HTTPS proxy is
active alongside the unchanged /shadowbane-updates/ file handler. An elevated
readback confirmed the Shadowbane Report Receiver task is Running as SYSTEM with
an AtStartup trigger and the expected installed Python executable. The former
sign-in Run entry was removed. Startup after an actual reboot was not tested.

Using the installed app's connection.json and the production HTTPS delivery
client, a synthetic report passed HTTPS health, authenticated upload, server ZIP
publication, local Sent state, and repeat-send identical-receipt checks. Local
qualification is complete; this does not certify access from another computer.
Private evidence is retained in artifacts/watcher-layout/https-delivery-receipt.json
and E:\Services\ShadowbaneReports/startup-verification.json. No capability or
captured character data is included in source control.

Next: a real personal recording with microphone notes and game-control correlation.
Qualify a second computer only if one is used. Character database import and
authoritative private-game-server instrumentation remain separate unfinished work.
