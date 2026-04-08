# Memory Unification Blueprint (LanceDB-Pro Style)

This document is the current memory inventory and normalization blueprint for this repository.
Goal: unify a mixed multi-generation memory layout into one clear architecture while preserving data safety.

Reference style:
- <https://github.com/coosin/memory-lancedb-pro.git>
- <https://github.com/CortexReach/memory-lancedb-pro>

## 1) Current Inventory (Scanned)

### 1.1 Active runtime memory chain
- `MainController` -> `UnifiedMemorySystem` -> `OptimizedMemorySystem` -> `MemoryGateway`
- `MemoryGateway` is the public entrypoint used by controller/API.
- Main files:
  - `src/modules/main_controller.py`
  - `src/modules/core/unified_memory_system.py`
  - `src/modules/core/optimized_memory_system.py`
  - `src/modules/memory/memory_gateway.py`
  - `src/modules/memory/providers/native.py`

### 1.2 Memory roots currently present on disk
- `workspace/memory` (active and being written)
- `data/memory` (active-ish + legacy mix)
- `memory` (legacy tree, small)

Observed sizes:
- `workspace/memory`: ~200K
- `data/memory`: ~1004K
- `memory`: ~24K

### 1.3 Memory-adjacent persistence
- `data/memory.db` (legacy-style sqlite artifact)
- `data/historical_data.db` (trade/history data storage)
- `data/trade_history/trades.jsonl` (trade history backup/log path)

### 1.4 Workspace long-term profile docs (journal/governance layer)
- `workspace/SOUL.md`
- `workspace/IDENTITY.md`
- `workspace/USER.md`
- `workspace/INSTRUCTIONS.md`
- `workspace/TRADING.md`
- `workspace/MEMORY.md`

These are useful, but should be treated as "journal/governance memory", not the primary semantic recall store.

## 2) Current Problem

Memory is functionally available, but storage structure is mixed across old and new generations:
- Structured memory exists in both `workspace/memory` and `data/memory`.
- Legacy JSON artifacts coexist with current layer folders.
- Some paths/directories appear to be leftovers from earlier architecture revisions.

Result: hard to reason about "single source of truth".

## 3) Target Unified Architecture

Follow dual-layer pattern (same philosophy as memory-lancedb-pro):

1) **Structured Recall Layer (single source of truth)**
- One canonical root only:
  - Local/dev: `workspace/memory`
  - Container/prod: `/app/data/memory`
- Subdirs kept:
  - `core/`
  - `working/`
  - `experience/`
  - `history/`
  - `sessions/` (if used)
  - `trades/` (if used by active code path)

2) **Journal/Governance Layer**
- Keep workspace markdown docs:
  - `SOUL.md`, `IDENTITY.md`, `USER.md`, `INSTRUCTIONS.md`, `TRADING.md`, `MEMORY.md`
- Human-curated memory + persona/constraints + operational notes.
- Not treated as vector/semantic recall primary source.

## 4) Canonical Rules

1. One write-authority root for structured memory.
2. `MemoryGateway` remains the only public memory interface.
3. Journal docs are read for startup/persona/context only.
4. Legacy files are archived first, then removed in phases.
5. No hard deletion before checksum + rollback snapshot.

## 5) Legacy/Noise Candidates (Do Not Delete Blindly)

Candidates to archive first:
- `data/memory/ai_memory.json`
- `data/memory/enhanced_memory.json`
- `data/memory/unified_memory.json`
- `data/memory.db`
- root `memory/` tree
- legacy folders in `data/memory` and `workspace/memory` not used by active code

Risk policy:
- Medium/High risk until migration snapshot is stored.
- Move to archive path before cleanup:
  - `data/memory/_archive/<YYYYMMDD_HHMM>/...`

## 6) Three-Phase Execution Plan

### Phase A: Freeze + Inventory (current step)
- Completed: topology scan, active chain confirmation, risk list.

### Phase B: Non-destructive normalization
- Add a memory inventory report generator (read-only).
- Add runtime path diagnostics endpoint:
  - "which memory root is active now?"
  - "last write path / write permission / fallback path"
- Add archive migration command (move old files to `_archive` only).

### Phase C: Controlled cleanup + hardening
- Remove archived legacy files only after validation window.
- Ensure one structured root in each environment.
- Update docs:
  - `ARCHITECTURE.md`
  - `DEVELOPMENT.md`
  - `docs/MEMORY_ARCHITECTURE_ALIGNMENT.md`

## 7) Alignment With memory-lancedb-pro Template

Aligned concepts:
- Dual-memory responsibilities (structured recall vs markdown journal)
- Scope-aware retrieval semantics
- Centralized memory gateway contract

Recommended next alignment (optional):
- Pluggable provider interface (`native`/`lancedb`/`pro-compatible`)
- Retrieval trace visibility and rerank pipeline observability
- Data lifecycle governance (dedup/decay/quality scoring)

