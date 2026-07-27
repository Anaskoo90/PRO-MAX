# Unit of Work

Coordinates repositories inside one transaction.

Workflow:
1. Start transaction
2. Execute domain operations
3. Commit
4. Rollback on failure
