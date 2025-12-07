"""Simple RAM model used as backing store for the cache simulator.

This is a lightweight, byte-addressable RAM abstraction. It's not a
full memory emulator — it stores values in a dict keyed by address and
supports simple read/write operations. The UI exposes a configurable
`ram_size` (in bytes) and the RAM is passed to the core simulator so
cache misses can read/write the backing memory.

The contract is intentionally small:
- RAM(size_bytes, line_size)
- read(address) -> returns stored value or 0
- write(address, value=0) -> stores value at address
- reset() -> clears memory
"""
from typing import Optional


class RAM:
    def __init__(self, size_bytes: int = 1024, line_size: int = 1):
        try:
            self.size = max(1, int(size_bytes))
        except Exception:
            self.size = 1024
        try:
            self.line_size = max(1, int(line_size))
        except Exception:
            self.line_size = 1
        # store memory as a sparse dict: address -> value (int)
        self.storage = {}

    def _clamp_addr(self, address: int) -> int:
        try:
            if address < 0:
                return 0
            if address >= self.size:
                # clamp to last valid address
                return self.size - 1
            return address
        except Exception:
            return 0

    def read(self, address: int) -> int:
        """Read a byte/word at `address`. Returns stored value or 0 if not present."""
        try:
            a = self._clamp_addr(int(address))
            return self.storage.get(a, 0)
        except Exception:
            return 0

    def write(self, address: int, value: Optional[int] = 0):
        """Write a value to `address`. If out of bounds, address is clamped."""
        try:
            a = self._clamp_addr(int(address))
            self.storage[a] = 0 if value is None else int(value)
        except Exception:
            pass

    def reset(self):
        try:
            self.storage.clear()
        except Exception:
            self.storage = {}
