"""Exercise inspection errors without a game process or any visible window."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

launcher = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="sb-launcher-cli-") as temporary:
    root = Path(temporary)
    client = root / "client"
    client.mkdir()
    (client / "sb.exe").write_bytes(b"invalid-image")
    cases = [
        ["--inspect", "--client-root", str(root / "absent")],
        ["--inspect", "--client-root", str(client)],
        ["--inspect", "--client-root", str(client), "--unknown"],
        ["--inspect", "--inspect"],
        ["--inspect", "--monitor"],
    ]
    for args in cases:
        result = subprocess.run(
            [str(launcher), *args], capture_output=True, timeout=10, check=False,
        )
        assert result.returncode == 1, (args, result.returncode, result.stdout, result.stderr)
        report = json.loads(result.stdout)
        assert report["status"] == "failed" and report["process_id"] == 0
        assert not report["markers_verified"]
    assert (client / "sb.exe").read_bytes() == b"invalid-image"
    assert list(client.iterdir()) == [client / "sb.exe"]
    assert not (root / "absent").exists()
print("Inspection failure paths passed; no game launched or preferences changed.")
