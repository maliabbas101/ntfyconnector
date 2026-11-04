# Agent identity pinning

The new `AgentIdentity` and `verify_bound_command` helpers enforce signed agent UUID, tenant UUID, and MT5 login/server against local immutable configuration. Authentication and identity checks happen before journal or terminal access. A command targeting a different account, tenant, or agent fails closed.

**Integration pending:** the existing `poll_once` transport still uses the legacy signed-command processor and does not yet enforce these pins. This module provides a tested building block for a future versioned command protocol. Enrollment, secret rotation, multi-tenant cloud authorization, and live MT5 validation remain outstanding. Trading stays disabled.
