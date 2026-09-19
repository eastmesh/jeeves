# Claude Code Project Guidance

## Purpose
Jeeves is the MeshCore PathBot: it listens for commands on configured channels, resolves received paths, replies on channels, and serves admin/guest web dashboards.

## Repository and ownership
- Canonical repository: `https://github.com/eastmesh/jeeves`
- Canonical checkout root: `/home/hermes/workspace/repos/jeeves`
- Approved owner scope: `eastmesh`
- Do not push, open PRs, merge, deploy, or change production radios/services without explicit coordinator approval.
- Do not commit secrets, live `config.toml`, radio credentials, channel keys, or generated databases.

## Commands
- Setup: `uv sync --extra dev`
- Tests: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Build/package smoke check: `uv build`
- Structural index refresh: `codebase-memory-mcp cli --json index_repository --repo-path . --mode moderate`

## Conventions
- Keep changes focused and minimal; preserve existing admin/guest behavior.
- Python source is under `src/meshcore_pathbot/`; tests are under `tests/`.
- Use async patterns already present and preserve MeshCore event/error handling.
- Region/flood scope is a device-global state; serialize state-changing radio commands and verify command results.
- Preserve multibyte path hashes and channel correlation behavior.

## Review and verification
- Discovery, implementation, review, and release are separate phases.
- Add regression tests for every behavioral fix, including provider/radio error paths.
- Inspect tracked and untracked changes and run targeted tests, full pytest, Ruff, and build before handoff.
- A separate independent review is required before any remote publication.

## Rollback and operational boundaries
- Prefer a small revertable change; document any configuration or radio-state implications.
- Do not exercise real radio sends during local tests unless explicitly approved and a controlled device/test channel is identified.
- If a scope-setting or send operation fails, preserve the error and leave the device in a known scope state; do not silently claim delivery.
