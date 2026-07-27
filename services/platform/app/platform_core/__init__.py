"""
Platform Core: the reusable, business-agnostic foundation every bounded
context in services/platform depends on.

Nothing under app/platform_core may import from a bounded-context package
(app/identity, app/crm, app/engineering_workspace, ...). Dependencies flow
one way, enforced by the boundary linter (tools/boundary-linter, tracked
separately) — this docstring states the rule; the linter enforces it.
"""
