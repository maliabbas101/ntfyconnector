from uuid import uuid4

from app.command_queue import CommandQueue
from app.provision_agent import main


def test_agent_enrollment_cli_is_idempotent(tmp_path, capsys):
    tenant, agent = str(uuid4()), str(uuid4())
    path = str(tmp_path / "queue.sqlite")
    args = ["--tenant-id", tenant, "--agent-id", agent,
            "--queue-path", path]
    assert main(args) == 0
    assert main(args) == 0
    output = capsys.readouterr().out
    assert agent in output
    with CommandQueue(path) as queue:
        assert queue.tenant_overview(tenant)["agents_enrolled"] == 1
