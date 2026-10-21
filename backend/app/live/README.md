# Live execution boundary

This package is release preparation. It does not expose a live activation API or connect an order writer. Generic CCXT production execution remains disabled.

`binance_readonly.py` performs fixed-host signed GET verification. A saved credential is not a verified account; a verified account is not an active trading run.

`ledger.py` is an internal persist-before-send component. Its caller must acquire `account_lock` for a bounded account operation, use a fresh guard and a dedicated transaction/session, and close or roll back that session on errors. PostgreSQL's advisory lock uses its own connection so ledger commits do not release ownership. Successful replay paths finish their transactions. A replacement owner changes the persisted fence token. Network cancellation leaves SENDING persisted; restarting does not resend it.

An ENTRY pins an entry cycle. STOP, TP and CLOSE intents belong to that cycle, and their client IDs include it. Reusing another cycle's order is rejected. Responses require matching client and exchange identity. Known fill quantities never decrease; malformed data retains known identity. A conditional FINISHED/TRIGGERED status remains unresolved until its resulting order and actual position are reconciled. It cannot establish a position fill on its own. Not-found responses never authorize resubmission.

`SubmissionFailure(ambiguous=False)` is reserved for a proven exchange rejection. Timeout, transport interruption, malformed response and process death are ambiguous. No adapter may turn a generic HTTP error or missing query result into a definitive rejection without its exchange-specific contract and tests.

These guarantees do not constitute a complete execution service. The caller still needs validated pinned graphs, current exchange filters/account state, explicit operator and user limits, transfer-adjusted persistent risk accounting, protection confirmation, independent recovery/monitoring, user-stream and REST reconciliation, fill/fee/funding accounting and durable alerts. `entries_allowed` is an internal orchestrator input, not a public release toggle or authorization mechanism. It must remain unreachable from a user-supplied request until the complete orchestrator and acceptance evidence exist.

See [the multi-user release record](../../docs/MULTI_USER_RELEASE.md) for the current blockers and isolated verification commands.
