# Outbox Pattern

Guarantees reliable event publishing.

Flow:
- Save business data
- Save event in Outbox
- Commit transaction
- Background worker publishes events
- Mark event as processed
