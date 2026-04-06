# Memory Architecture Alignment

This document records the alignment work between this project and the
memory-oriented architecture used by `memory-lancedb-pro`.

Reference: <https://github.com/coosin/memory-lancedb-pro.git>

## What was integrated

1. Single memory entrypoint
   - Added `MemoryGateway` as the only public memory interface for controller/API.
   - `MainController.ai_memory_manager` now points to `MemoryGateway` (compatible alias).

2. Scope-ready memory contract
   - `MemoryGateway.store/recall` supports `scope` metadata filtering.
   - Default scope is `global`, with support for caller-defined scopes such as
     `agent:<id>`, `user:<id>`, `project:<id>`.

3. Dual-layer memory responsibilities
   - Structured memory (`OptimizedMemorySystem`) is the recall source.
   - Workspace markdown files (`SOUL.md`, `IDENTITY.md`, `USER.md`,
     `INSTRUCTIONS.md`, `TRADING.md`) are managed as journaling/operational docs.

4. Unified API surface
   - Added `/api/v1/ai/memory/store` and `/api/v1/ai/memory/recall`.
   - Existing endpoints (`instruction`, `preference`, `stats`, `workspace-file`)
     route through the same gateway.

5. Config unification
   - Added `memory` section in `ConfigManager.DEFAULT_CONFIG`:
     provider/scopes/dual_layer/retrieval/auto_capture/auto_recall.

## Compatibility guarantees

- Legacy methods used by existing modules are preserved in gateway:
  - `retrieve_memories`
  - `add_memory`
  - `process_user_input`
  - `add_system_instruction`
  - `add_user_preference`
  - `summarize_trade_history`
  - `get_workspace_memory`
  - `update_workspace_memory`

## Next deepening steps

1. Provider adapter layer
   - Introduce provider plugins under `src/modules/memory/providers/`
     (`native`, `lancedb`, `lancedb_pro_compatible`).

2. True hybrid retrieval
   - Add vector + BM25 fusion and optional rerank stage.
   - Keep gateway contract stable while swapping internals.

3. Memory quality governance
   - Dedup, decay, and category-aware merge policies.
   - Add retrieval audit traces for explainability.
