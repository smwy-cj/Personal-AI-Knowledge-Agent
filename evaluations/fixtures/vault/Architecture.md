# Agent Runtime Architecture

The runtime stores structured task state and an append-only checkpoint history. Interrupted work supports durable recovery with at-least-once semantics, so workflows with side effects must be idempotent.

Execution leases and heartbeats prevent two active owners from updating the same task. A stale owner must verify its lease before writing another checkpoint.
