# ADR-004: Durable approval state

Status: accepted. Approval persistence uses a backend-neutral contract. SQLite is
limited to local/test execution; staging and production fail closed unless an
authenticated PostgreSQL or Redis URL is configured. PostgreSQL is the intended
system of record. Decisions use conditional atomic updates, and raw queries are
represented only by SHA-256 digests.
