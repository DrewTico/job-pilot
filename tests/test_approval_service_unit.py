"""Repository-only unit contract; never contact a service manager or private data."""
import configparser
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "deploy/systemd/job-pilot-approval.service"
PROJECT = "%h/projects/job-pilot"


@pytest.fixture
def unit():
    assert UNIT.is_file()
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(UNIT.read_text())
    return parser


def test_user_service_and_only_approval_command(unit):
    assert unit.sections() == ["Unit", "Service", "Install"]
    assert dict(unit["Install"]) == {"WantedBy": "default.target"}
    service = unit["Service"]
    assert service["Type"] == "exec"
    assert service["WorkingDirectory"] == PROJECT
    assert shlex.split(service["ExecStart"]) == [
        PROJECT + "/.venv/bin/job-agent", "approval-queue", "--access", "tailscale",
        "--data-dir", PROJECT + "/data", "--port", "8643",
    ]
    assert [key for key in service if key.startswith("Exec")] == ["ExecStart"]
    assert "User" not in service and "Group" not in service


def test_no_other_process_installation_network_or_secrets(unit):
    text = UNIT.read_text().lower()
    for forbidden in ("scheduler", "--revisions-only", "revision-process", "sudo",
                      "powershell", "windows", "wsl.exe", "cmd.exe", "0.0.0.0",
                      "funnel", "tailscaled", "network-online", "systemctl",
                      "environment=", "environmentfile=", "api_key", "sk-ant-",
                      "job_agent_approval_tailscale", ".ts.net", "@", "/root",
                      "/etc/systemd", "multi-user.target"):
        assert forbidden not in text
    # The access-mode argument is the only tailscale token, never an executable.
    assert text.count("tailscale") == 1
    assert not re.search(r"https?://|[;&|`$]", unit["Service"]["ExecStart"])
    assert set(unit["Unit"]) == {"Description", "StartLimitIntervalSec", "StartLimitBurst"}
    assert set(unit["Service"]) == {
        "Type", "WorkingDirectory", "ExecStart", "Restart", "RestartSec",
        "KillSignal", "KillMode", "TimeoutStopSec", "UMask", "LimitCORE",
        "StandardOutput", "StandardError",
    }


def test_bounded_restart_graceful_stop_and_private_files(unit):
    service = unit["Service"]
    assert service["Restart"] == "on-failure"
    assert service["RestartSec"] == "10s"
    assert unit["Unit"]["StartLimitIntervalSec"] == "300"
    assert unit["Unit"]["StartLimitBurst"] == "3"
    assert service["KillSignal"] == "SIGTERM"
    assert service["KillMode"] == "control-group"
    assert service["TimeoutStopSec"] == "30s"
    assert service["UMask"] == "0077"
    assert service["LimitCORE"] == "0"
    assert service["StandardOutput"] == service["StandardError"] == "journal"


@pytest.mark.parametrize("cwd_at_project", [True, False])
def test_existing_loader_discovers_dotenv_in_editable_layout(tmp_path, cwd_at_project):
    # Copy unchanged source into a controlled editable layout. The child has an
    # isolated environment and import path; it cannot discover the real .env.
    import job_agent.config as config

    assert Path(config.__file__).resolve() == ROOT / "src/job_agent/config.py"
    project = tmp_path / "projects/job-pilot"
    package = project / "src/job_agent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    for name in ("config.py", "seniority.py"):
        (package / name).write_bytes((ROOT / "src/job_agent" / name).read_bytes())
    (project / ".env").write_text(
        "JOB_AGENT_APPROVAL_TAILSCALE_LOGIN=operator@example.test\n"
        "JOB_AGENT_APPROVAL_TAILSCALE_HOST=pilot.tailtest.ts.net\n"
    )
    launcher = project / "launcher.py"
    launcher.write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent / 'src'))\n"
        "from job_agent.config import load_settings\n"
        "settings = load_settings()\n"
        "assert settings.approval_tailscale_login.get_secret_value() == 'operator@example.test'\n"
        "assert settings.approval_tailscale_host.get_secret_value() == 'pilot.tailtest.ts.net'\n"
        "assert settings.data_dir == Path('data')\n"
    )
    result = subprocess.run([sys.executable, "-I", str(launcher)],
                            cwd=project if cwd_at_project else tmp_path,
                            env={}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
