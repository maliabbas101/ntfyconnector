# Signed demo command processing

`process_signed_demo_command` verifies the envelope HMAC and expiry **before** touching the command journal or MT5 terminal. It then validates the command schema, requires the signed envelope ID and expiry to match the embedded command, and delegates to the existing fail-closed processor.

Invalid signatures cannot create journal entries. Valid commands are still rejected before broker execution; this module does not send orders. Tests cover tampering, wrong keys, identity mismatch, and duplicate handling.

This is not yet a network transport. Agent enrollment, secret rotation, tenant binding, bounded command age, clock-skew handling, TLS, local exposure checks, and Windows demo terminal tests remain prerequisites to any trade execution.
