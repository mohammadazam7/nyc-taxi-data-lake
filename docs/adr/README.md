# Architecture decision records

Each record states a decision, the context it was made in, and its consequences, in the
format described by Michael Nygard. Records are not edited after they are accepted; a
later record supersedes an earlier one.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-one-codebase-for-local-and-aws.md) | One codebase and CLI for local runs and AWS Glue | Accepted |
| [0002](0002-hash-surrogate-keys.md) | Deterministic hash surrogate keys | Accepted |
| [0003](0003-quarantine-instead-of-drop.md) | Quarantine rejected rows with a reason code | Accepted |
| [0004](0004-step-functions-for-orchestration.md) | Step Functions rather than Glue workflows or Airflow | Accepted |
| [0005](0005-portable-analytics-sql-and-static-dashboard.md) | Portable analytics SQL and a static dashboard | Accepted |
| [0006](0006-react-explorer-alongside-the-static-dashboard.md) | A React explorer alongside the static dashboard | Accepted |
