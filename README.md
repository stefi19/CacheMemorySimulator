# Cache Memory Simulator

Simple Python/Tkinter cache memory simulator.

Features
- Configurable cache size, block size, associativity (ways), replacement policy (LRU/FIFO/Random), write policy (write-through/write-back).
- Two sample scenarios: Matrix Traversal, Random Access.
- Live statistics: accesses, hits, misses, hit rate, memory reads/writes.

Run GUI

Open a terminal and run:

```bash
python run.py
# Cache Memory Simulator

A configurable, educational CPU cache + RAM simulator written in Python.
This repository contains the core cache model, a small simulator that
orchestrates cache and RAM accesses, a Tkinter-based UI for visualization,
and a consolidated test suite that verifies core behaviors.

## Quick project layout

- `run.py` — entrypoint / optional UI runner
- `src/core/cache.py` — cache core: sets, ways, replacement logic, dirty/valid bits
- `src/core/ram.py` — RAM backing-store model with bounds checks
- `src/core/simulator.py` — CacheSimulator that sequences accesses and reports mr/mw
- `src/simulation/user_interface.py` — Tkinter UI (visualization)
- `src/wrappers/k_associative_cache.py` — helpers used by the UI
- `src/tests/test_cache_core.py` — consolidated unit tests for the core
- `src/tests/conftest.py` — pytest helper that ensures `src` is importable

## Purpose

The simulator exists to emulate cache behavior for educational and testing
purposes. It supports configurable cache geometry and policies and reports
events (cache hits/misses, memory reads/writes) so the UI or tests can
visualize or assert expected outcomes.

## Functional requirements

- FR-01: Initialize a cache with configurable parameters: `num_blocks`,
	`associativity`, `line_size`, `replacement`, `write_policy`, and
	`write_miss_policy`.
- FR-02: Provide `cache.access(address, is_write=False, write_miss_policy=...)`
	which returns a tuple describing the outcome:
	`(hit: bool, set_index: int|None, way_index: int|None, evicted_block|None, mem_read: bool, mem_write: bool)`.
- FR-03: Implement replacement policies `LRU`, `FIFO`, and `Random`.
- FR-04: Support `write-back` and `write-through` write policies with
	the canonical semantics:
	- `write-back`: on a write-hit set the line's `dirty` bit; write to RAM
		only on eviction (eviction must indicate `mem_write=True`).
	- `write-through`: on a write-hit write immediately to RAM; `dirty`
		remains `False`.
- FR-05: Support write-miss policies `write-allocate` and `write-no-allocate`.
	- `write-allocate`: allocate on write miss (may generate a memory read),
		then perform the write according to the write policy.
	- `write-no-allocate`: do not allocate; write directly to RAM (mem_write).
- FR-06: On eviction under `write-back`, the simulator must perform a
	base-aligned write to RAM for the evicted block (or full-line writeback if
	configured) and return `mem_write=True` in the access result.
- FR-07: RAM supports `read(address)` and `write(address, value)` and raises
	`IndexError` for out-of-range addresses.
- FR-08: `cache.reset()` invalidates all lines and clears dirty bits.
- FR-09: The simulator must expose `mr` and `mw` flags for memory reads and
	writes so tests and the UI can assert or animate I/O.
- FR-10: Address alignment rules apply for `line_size > 1`.
- FR-11: Invalid parameters (e.g. invalid associativity, invalid policy
	string, non-positive `line_size`) must be handled gracefully (raise
	`ValueError` or documented normalization behavior).

## Cache parameters and terms

- `num_blocks` (int): total number of cache blocks/frames.
- `associativity` (int): ways per set (1 = direct-mapped, `num_blocks` = fully associative).
- `line_size` (int): bytes per cache line; affects block-address math.
- `num_sets` = `num_blocks // associativity`.
- `replacement`: `'LRU' | 'FIFO' | 'Random'`.
- `write_policy`: `'write-back' | 'write-through'`.
- `write_miss_policy`: `'write-allocate' | 'write-no-allocate'`.
- Per-line metadata: `tag`, `valid`, `dirty`, optional `data`.

Address translation rules:

- `block_addr = address // line_size`
- `set_index = block_addr % num_sets`
- `tag = block_addr // num_sets`
- `base_address_of_block = block_addr * line_size`

When performing write-back on eviction the simulator writes to
`base_address_of_block` (the implementation may optionally write the
entire line's bytes; tests assume base-aligned behavior unless they are
updated).

## API contract (cache and RAM)

cache.access(address: int, is_write: bool, write_miss_policy: Optional[str]) -> tuple
- Returns `(hit, set_index, way_index, evicted_block, mem_read, mem_write)`.
- `evicted_block` exposes at least `tag`, `dirty`, and `valid`.

RAM.read(address: int) -> value
RAM.write(address: int, value) -> None
- Both raise `IndexError` for invalid addresses.

cache.reset() -> None
- Invalidates all lines and clears dirty bits.

## Tests

All core logic is exercised by the consolidated test module
`src/tests/test_cache_core.py`. Tests cover:

- Replacement policies (LRU/FIFO/Random) with deterministic checks for
	LRU/FIFO and membership checks for Random.
- Write-hit semantics for `write-back` vs `write-through` (dirty bit
	behavior and `mem_write` flags).
- Write-miss policies `write-allocate` and `write-no-allocate`.
- Eviction behavior and write-backs to RAM (evicted dirty lines trigger
	`mem_write` and RAM updates at the base address).
- `line_size` interactions and base-aligned behavior.
- `cache.reset()` semantics.
- RAM bounds checks (IndexError for out-of-range accesses).
- A small randomized stress test and smoke matrix across several cache
	geometries.

Each test includes a short comment block that documents the exact
Input and Expected output (so tests act as executable specifications).

### Running tests

Recommended (macOS / zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip pytest
pytest -q
```

The repository contains `src/tests/conftest.py` which ensures the project
root is available on `sys.path` so tests can import `src.*` directly.

## UI notes

The Tkinter UI lives in `src/simulation/user_interface.py`. It visualizes the
cache sets/ways, highlights memory reads/writes, and shows a `D` indicator
for dirty lines when the write-policy is `write-back`. Unit tests intentionally
exclude the UI and exercise only core behavior.

## Implementation notes & choices

- The simulator currently writes back evicted dirty blocks at the block's
	base-aligned address. If you prefer full-line writebacks (writing all
	bytes of the line), update the simulator and tests accordingly.
- When switching write-policy in the UI from `write-back` to
	`write-through`, the UI code attempts a best-effort flush of dirty
	lines to RAM and clears their dirty bits so behavior matches the
	write-through semantics going forward.
- Random replacement is non-deterministic — tests assert evicted-tag
	membership rather than an exact value.

## CI suggestion (GitHub Actions)

Create `.github/workflows/python-tests.yml` with a matrix for Python
versions (3.10+). Steps:

- checkout
- setup-python
- install pytest
- run `pytest -q`

Optionally add type checks (`mypy`) and linting (`flake8`).

## To-dos / future improvements

- Decide on full-line versus base-address-only writebacks and adjust
	tests if changing semantics.
- Add property-based tests (Hypothesis) for stronger invariants.
- Add CI and pre-commit hooks.

## Contact / contribution

Open issues or PRs for behavior changes (e.g., full-line writeback),
improvements to the UI, expanded test matrices, or CI integrations.

---

_Generated and maintained alongside the test-suite and code. For any
discrepancy between tests and this README, the tests are the source of
truth._
