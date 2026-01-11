"""Core cache implementation

This file provides a simple set-associative cache model used by the simulator and UI.
Behavior:
- Cache is composed of sets; each set has `associativity` ways.
  block_addr = address // line_size
  set_index = block_addr % num_sets
  tag = block_addr // num_sets
- Access returns (hit:bool, set_index:int, way_index:Optional[int], evicted:Optional[CacheBlock], mem_read:bool, mem_write:bool)
"""

from dataclasses import dataclass
from typing import Optional, List
import time
import random

from src.core.replacement_policies import LRUReplacement, FIFOReplacement, RandomReplacement


@dataclass
class CacheBlock:
    """container for a cache line (way).

    Fields:
    - tag: the tag stored in the line
    - valid: whether the line currently holds useful data
    - dirty: whether the line was written (for write-back)
    - last_access_time / load_time: helpers used by policies LRU/FIFO
    """

    tag: Optional[int] = None
    valid: bool = False
    dirty: bool = False
    last_access_time: float = 0.0
    load_time: float = 0.0
    # per-byte data stored in this cache block (length = line_size)
    data: Optional[list] = None


class Cache:
    """Simple set-associative cache model.
    """

    def __init__(
        self,
        num_blocks: int = 16,
        line_size: int = 1,
        associativity: int = 1,
        replacement: str = "LRU",
        write_policy: str = "write-through",
        write_miss_policy: str = "write-allocate",
    ):
        # basic checks and normalization
        if associativity <= 0:
            raise ValueError("associativity must be >= 1")
        if num_blocks < 1:
            num_blocks = 1
        # Do not change total number of blocks to satisfy associativity.
        # Instead, if the requested associativity does not divide evenly into
        # num_blocks, reduce associativity to the largest divisor <= associativity.
        if num_blocks % associativity != 0:
            # find the largest divisor of num_blocks that is <= associativity
            for a in range(min(associativity, num_blocks), 0, -1):
                if num_blocks % a == 0:
                    associativity = a
                    break

        self.num_blocks = num_blocks
        self.line_size = line_size if line_size > 0 else 1
        self.associativity = associativity
        self.num_sets = max(1, num_blocks // associativity)
        self.write_policy = write_policy
        self.write_miss_policy = write_miss_policy
        self._replacement_name = replacement
        self.replacement_policy_objs: List[object] = []
        for _ in range(self.num_sets):
            if replacement == "LRU":
                self.replacement_policy_objs.append(LRUReplacement(self.associativity))
            elif replacement == "FIFO":
                self.replacement_policy_objs.append(FIFOReplacement(self.associativity))
            elif replacement == "Random":
                self.replacement_policy_objs.append(RandomReplacement(self.associativity))
            else:
                # fallback to LRU
                self.replacement_policy_objs.append(LRUReplacement(self.associativity))

        # allocate the sets matrix: num_sets x associativity
        # allocate the sets matrix and initialize per-block data lists according
        # to configured line_size so CacheBlock.data is available for reads/writes
        self.sets: List[List[CacheBlock]] = []
        for _ in range(self.num_sets):
            row = []
            for _ in range(self.associativity):
                b = CacheBlock()
                # initialize per-byte storage
                try:
                    b.data = [0 for _ in range(self.line_size)]
                except Exception:
                    b.data = [0]
                row.append(b)
            self.sets.append(row)

    def _decode(self, address: int):
        """Decode address into (set_index, tag)."""

        bs = self.line_size if self.line_size > 0 else 1
        block_addr = address // bs
        # num_sets should already be >=1, but be sure
        if self.num_sets <= 0:
            return 0, block_addr
        set_index = block_addr % self.num_sets
        tag = block_addr // self.num_sets
        return set_index, tag

    def access(self, address: int, is_write: bool = False, write_miss_policy: Optional[str] = None, write_value: Optional[int] = None):
        """Perform a cache access.

        Returns a tuple:
        (hit: bool, set_index: int, way_index: Optional[int], evicted: Optional[CacheBlock], mem_read: bool, mem_write: bool)

        - hit: whether the access hit in cache
        - evicted: copy of the evicted block if eviction happened
        - mem_read: True if a memory read was performed
        - mem_write: True if a memory write was performed (write-through or write-back eviction)
        """

        if write_miss_policy is None:
            write_miss_policy = self.write_miss_policy

        set_index, tag = self._decode(address)
        cache_set = self.sets[set_index]

        # search for hit
        # wi = way-index
        for wi, block in enumerate(cache_set):
            if block.valid and block.tag == tag:
                # hit: update timestamps and notify policy
                now = time.time()
                block.last_access_time = now
                try:
                    self.replacement_policy_objs[set_index].access(wi)
                except Exception:
                    #ignore if method missing
                    pass

                mem_read = False
                mem_write = False
                if is_write:
                    # compute byte offset within line
                    try:
                        offset = int(address) % int(self.line_size)
                    except Exception:
                        offset = 0
                        # on write, update block's data if available
                        try:
                            if block.data is None:
                                block.data = [0 for _ in range(self.line_size)]
                            # if a write_value was passed, assign it to the byte offset
                            if write_value is not None:
                                try:
                                    block.data[offset] = int(write_value)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    if self.write_policy == "write-back":
                        block.dirty = True
                        mem_write = False
                    else:
                        # write-through, so immediate mem write
                        mem_write = True
                return True, set_index, wi, None, mem_read, mem_write

        # miss handling
        if is_write and write_miss_policy in ("write-no-allocate"):
            # don't allocate on write miss: write directly to memory
            return False, set_index, None, None, False, True

        # try to find a free way
        for wi, block in enumerate(cache_set):
            if not block.valid:
                # fill 
                now = time.time()
                block.tag = tag
                block.valid = True
                block.dirty = is_write and (self.write_policy == "write-back")
                block.last_access_time = now
                block.load_time = now
                # initialize block data container
                try:
                    if block.data is None:
                        block.data = [0 for _ in range(self.line_size)]
                except Exception:
                    block.data = [0 for _ in range(self.line_size)]
                mem_read = True
                mem_write = False
                # If this was a write and write-through policy apply mem_write
                if is_write and self.write_policy == "write-through":
                    mem_write = True
                # if this was a write and a write_value was provided, update the newly allocated block
                if is_write and write_value is not None:
                    try:
                        off = int(address) % int(self.line_size)
                        try:
                            block.data[off] = int(write_value)
                        except Exception:
                            pass
                    except Exception:
                        pass
                try:
                    self.replacement_policy_objs[set_index].access(wi)
                except Exception:
                    pass
                return False, set_index, wi, None, mem_read, mem_write

        # need to evict: ask policy for a victim
        victim_index = None
        try:
            victim_index = self.replacement_policy_objs[set_index].evict()
        except Exception:
            victim_index = None

        # fallback: choose LRU by last_access_time
        if victim_index is None or not (0 <= victim_index < len(cache_set)):
            victim_index = min(range(len(cache_set)), key=lambda i: cache_set[i].last_access_time)

        victim = cache_set[victim_index]
        # make a copy of the evicted block
        evicted = CacheBlock(
            tag=victim.tag,
            valid=victim.valid,
            dirty=victim.dirty,
            last_access_time=victim.last_access_time,
            load_time=victim.load_time,
        )
        # copy per-byte data if present
        try:
            evicted.data = list(victim.data) if getattr(victim, 'data', None) is not None else None
        except Exception:
            try:
                evicted.data = None
            except Exception:
                pass

        mem_write = False
        if evicted and evicted.dirty and self.write_policy == "write-back":
            mem_write = True

        # place the new block into victim slot
        now = time.time()
        victim.tag = tag
        victim.valid = True
        victim.dirty = is_write and (self.write_policy == "write-back")
        victim.last_access_time = now
        victim.load_time = now
        try:
            self.replacement_policy_objs[set_index].access(victim_index)
        except Exception:
            pass
        # if write_value provided, update the newly-placed victim block's data
        try:
            if write_value is not None:
                try:
                    if victim.data is None:
                        victim.data = [0 for _ in range(self.line_size)]
                except Exception:
                    victim.data = [0 for _ in range(self.line_size)]
                try:
                    off = int(address) % int(self.line_size)
                    victim.data[off] = int(write_value)
                except Exception:
                    pass
        except Exception:
            pass
        mem_read = True
        if is_write and self.write_policy == "write-through":
            mem_write = True
        return False, set_index, victim_index, evicted, mem_read, mem_write

    def reset(self):
        """Clear cache contents and reset replacement policies.
        """

        for s in self.sets:
            for b in s:
                b.tag = None
                b.valid = False
                b.dirty = False
                b.last_access_time = 0.0
                b.load_time = 0.0

        for p in self.replacement_policy_objs:
            try:
                p.reset()
            except Exception:
                pass

    def set_replacement(self, replacement: str):
        """Change the replacement policy for all sets at runtime.

        This will recreate the per-set replacement policy objects to the
        requested type. Existing policy state is discarded.
        """
        try:
            self._replacement_name = replacement
            new_objs: List[object] = []
            for _ in range(self.num_sets):
                if replacement == "LRU":
                    new_objs.append(LRUReplacement(self.associativity))
                elif replacement == "FIFO":
                    new_objs.append(FIFOReplacement(self.associativity))
                elif replacement == "Random":
                    new_objs.append(RandomReplacement(self.associativity))
                else:
                    new_objs.append(LRUReplacement(self.associativity))
            self.replacement_policy_objs = new_objs
        except Exception:
            # keep existing policies on failure
            pass

