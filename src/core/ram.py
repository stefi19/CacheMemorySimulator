"""Simple RAM model.

This is a byte-addressable RAM abstraction.
Supports simple read/write operations. The UI exposes a configurable
`ram_size` (in bytes) and the RAM is passed to the core simulator so
cache misses can read/write the backing memory.

Parameters:
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
        # Validate address and raise on out-of-bounds. The previous
        # implementation silently clamped addresses which hid bugs.
        if not isinstance(address, int):
            raise TypeError(f"address must be int, got {type(address).__name__}")
        if address < 0 or address >= self.size:
            raise IndexError(f"address {address} out of range [0, {self.size - 1}]")
        return address

    def read(self, address: int) -> int:
        """Read a byte/word at `address`. Returns stored value or 0 if not present."""
        a = int(address)
        a = self._clamp_addr(a)
        return self.storage.get(a, 0)

    def write(self, address: int, value: Optional[int] = 0):
        """Write a value to `address`. If out of bounds, address is clamped."""
        a = int(address)
        a = self._clamp_addr(a)
        self.storage[a] = 0 if value is None else int(value)

    def reset(self):
        try:
            self.storage.clear()
        except Exception:
            self.storage = {}
