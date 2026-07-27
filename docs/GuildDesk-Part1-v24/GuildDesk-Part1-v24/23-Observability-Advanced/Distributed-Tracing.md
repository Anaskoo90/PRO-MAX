# Distributed Tracing

Every request carries:
- Trace ID
- Span ID

Trace flow:
Gateway -> Service -> Database -> Queue -> External API
