"""Authenticate signed demo commands before journal or MT5 access.

This module never submits broker orders.
"""
from app.agent_auth import SignedEnvelope, verify_envelope
from app.agent_journal import CommandJournal
from app.agent_processor import DemoCommand, process_demo_command

class CommandEnvelopeError(ValueError):
    pass

def process_signed_demo_command(envelope: SignedEnvelope, secret: bytes,
                                journal: CommandJournal, mt5) -> dict:
    """Verify MAC/expiry, validate command, and enforce signed identity consistency.

    Invalid signatures do not touch the journal or the terminal.
    """
    payload = verify_envelope(envelope, secret)
    command = DemoCommand.model_validate(payload)
    if command.command_id != envelope.command_id:
        raise CommandEnvelopeError("Signed command ID mismatch")
    if command.expires_at != envelope.expires_at:
        raise CommandEnvelopeError("Signed expiry mismatch")
    return process_demo_command(command, journal, mt5)
