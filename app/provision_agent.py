"""Trusted local administrative enrollment for a single development agent."""
import argparse
from uuid import UUID

from app.command_queue import CommandQueue


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Enroll a demo agent in a tenant")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--queue-path", required=True)
    args = parser.parse_args(argv)
    tenant = str(UUID(args.tenant_id))
    agent = str(UUID(args.agent_id))
    if args.queue_path == ":memory:":
        parser.error("A durable queue path is required")
    with CommandQueue(args.queue_path) as queue:
        queue.enroll_agent(agent, tenant)
    print("Enrolled demo agent:", agent)
    print("Tenant:", tenant)
    print("No credentials or command-signing material were generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
