"""CLI camp intent reaches the production entrypoints without a hidden radius."""

from unittest.mock import patch

import pytest

from shadowbane_lab.cli import main
from shadowbane_lab.cli_commands.parser import _parser


@pytest.mark.parametrize("radius", [None, 175.0])
@pytest.mark.parametrize("continuous", [False, True])
def test_run_pve_camp_default_and_manual_override(radius, continuous):
    argv = ["client", "run-pve", "--live"]
    if continuous:
        argv += ["--continuous", "--evidence-output", "camp.json"]
    if radius is not None:
        argv += ["--camp-radius", str(radius)]
    with patch("shadowbane_lab.cli._run_pve", return_value=0) as run:
        assert main(argv) == 0
    assert run.call_args.kwargs["camp_radius"] == radius
    assert run.call_args.kwargs["continuous"] is continuous


@pytest.mark.parametrize("radius", [None, 175.0])
@pytest.mark.parametrize("entry", ["listener", "manager"])
def test_background_entrypoints_preserve_named_default_and_manual_override(entry, radius):
    argv = (["client", "listen-go"] if entry == "listener" else [
        "manager", "worker", "manifest.json", "--worker-state-directory", "workers",
        "--client-id", "client", "--instance-id", "instance", "--game-process-id", "42",
        "--game-process-started-at-100ns", "10000", "--game-window-handle", "99",
    ])
    if radius is not None:
        argv += ["--pve-camp-radius", str(radius)]
    args = _parser().parse_args(argv)
    assert args.pve_camp_radius == radius
    handler = "_listen_for_go_commands" if entry == "listener" else "_run_manager_worker"
    with patch(f"shadowbane_lab.cli.{handler}", return_value=0) as run:
        assert main(argv) == 0
    assert run.call_args.kwargs["pve_camp_radius"] == radius
