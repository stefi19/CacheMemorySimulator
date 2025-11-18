"""Replacement policy implementations adapted for the CacheMemorySimulator.

This module provides three policies with a small, consistent API so the
rest of the simulator can call them interchangeably:

- LRUReplacement(capacity)
- FIFOReplacement(capacity)
- RandomReplacement(capacity)

API (methods):
- access(key): notify policy that `key` was accessed (may update state)
- evict(): choose and remove a victim according to policy, return key
- peek(): return current keys in the policy's internal order (for UI/debug)
- reset(): clear policy state

These implementations avoid printing in the core methods; UI can inspect
state and log messages if required.
# Student-style note: I kept these policies small and simple so the UI can
# call them without dealing with internals. They're easy to read and tweak.
"""

import random
from collections import OrderedDict, deque
from typing import Any, List, Optional


class LRUReplacement:
    """Least-Recently-Used replacement using OrderedDict.

    OrderedDict keeps insertion order; we move accessed items to the end so
    the least recently used item is at the beginning.
    """

    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        self._od = OrderedDict()

    def access(self, key: Any) -> None:
        """Register access to `key`"""
        if key in self._od:
            # mark as most recently used
            self._od.move_to_end(key)
        else:
            # insert as MRU
            self._od[key] = True
            # evict if over capacity
            if len(self._od) > self.capacity:
                self._od.popitem(last=False)

    def evict(self) -> Optional[Any]:
        """Evict the LRU item and return its key, or None if empty."""
        if not self._od:
            return None
        key, _ = self._od.popitem(last=False)
        return key

    def peek(self) -> List[Any]:
        """Return keys from LRU->MRU as list."""
        return list(self._od.keys())

    def reset(self) -> None:
        self._od.clear()


class FIFOReplacement:
    """First-In-First-Out replacement using deque."""

    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        self._dq = deque()
        self._set = set()

    def access(self, key: Any) -> None:
        """On access, if key not in cache, append to queue (no reordering)."""
        if key in self._set:
            return
        self._dq.append(key)
        self._set.add(key)
        if len(self._dq) > self.capacity:
            ev = self._dq.popleft()
            self._set.discard(ev)

    def evict(self) -> Optional[Any]:
        if not self._dq:
            return None
        key = self._dq.popleft()
        self._set.discard(key)
        return key

    def peek(self) -> List[Any]:
        return list(self._dq)

    def reset(self) -> None:
        self._dq.clear()
        self._set.clear()


class RandomReplacement:
    """Random replacement picks a random key when eviction required."""

    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        self._set = set()

    def access(self, key: Any) -> None:
        if key in self._set:
            return
        self._set.add(key)
        if len(self._set) > self.capacity:
            # remove a random element
            victim = random.choice(tuple(self._set))
            self._set.discard(victim)

    def evict(self) -> Optional[Any]:
        if not self._set:
            return None
        victim = random.choice(tuple(self._set))
        self._set.discard(victim)
        return victim

    def peek(self) -> List[Any]:
        return list(self._set)

    def reset(self) -> None:
        self._set.clear()


__all__ = ["LRUReplacement", "FIFOReplacement", "RandomReplacement"]
