# Desktop manager startup

The installed shortcut delegates to the maintained `shadowbane-manager` entrypoint
(or `pythonw -m shadowbane_lab.manager.desktop_launcher`). It supplies the manifest,
`--worker-state-directory`, `--authorization-token-file`, `--pid-file`, and optional
`--port`/`--startup-timeout-seconds`. Installers can call the same packaged
`open_dashboard` API with those paths; they do not generate startup behavior.
The manager child uses the same installation's `python.exe`, including when the
shortcut is launched with `pythonw.exe`. Startup errors are presented by the
package; authorization tokens are never printed or included in process arguments.

The existing record-store lock serializes only startup inspection, durable intent,
spawn and exact process publication. `manager-startup.json` and
`manager-startup.lock` live alongside the worker directory. The lock is released
before waiting for the listener; it is synchronization metadata, not user settings.
The record contains a generation, startup manifest hash and resolved ownership
configuration, redirector PID/creation and actual interpreter PID/creation.
`desktop-start.stdout.log` and `desktop-start.stderr.log` are appended in place.
The existing dashboard token and PID files retain their production roles.

Authenticated `GET /api/v1/startup` returns immutable server-owned listener identity
without calling application status, reconciling clients or taking worker/service
locks. It proves an exact manager listener, not healthy workers, native readiness,
attachment or dispatch authority. Those existing checks remain separate. A busy
HTTP pool or slow startup remains unknown; one monotonic wait deadline never turns
HTTP delay into authority to start another process. Later desktop clicks continue
the recorded attempt. A foreign or unauthenticated listener is never adopted.

The child verifies the startup manifest hash against the bytes it actually parsed.
Later legitimate live configuration changes do not invalidate the already-owned
manager: reuse checks stable resolved ownership plus the durable startup identity.
Only positive retirement of every recorded process lifetime permits a new attempt.
A typed pre-creation failure (opening logs or Windows rejecting process creation)
clears only the same still-unclaimed intent under the lock, allowing a corrected
installation to start on the next click. Generic or post-creation failures never
receive that exception. The Windows failure proof requires the actual CPython
CreateProcess frame before any returned handles/PID were assigned; unsupported
interpreter layouts remain unknown instead of guessing that no child exists.
An interrupted spawn with no published process identity remains explicitly
unverified and refuses another launch; the launcher does not guess that no child
exists. Repair of that ambiguous record requires independent exact process evidence.

Validation uses real authenticated HTTP with status deliberately blocked. The
Windows test `test_real_desktop_entrypoint_reuses_startup_across_timeout` executes
the packaged desktop main, real subprocess/redirector, production manager CLI,
record locks, OS creation identity and listener. Its only child substitute is an
explicit no-game application; it launches no client and performs no gameplay.
It covers delayed startup past an initial deadline, later reuse and concurrent
clicks, with one child/generation and no token in logs. Qualification runs the same
test against the installed wheel, using `tests/fixtures/manager_desktop_child.py`;
the fixture imports the exact package location used by the test. Other focused
cases cover child exit, PID reuse, foreign identity, unknown process inspection,
manifest replacement and visible sanitized pythonw errors.
