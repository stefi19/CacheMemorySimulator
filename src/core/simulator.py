"""CacheSimulator coordinates cache accesses and statistics.
Feeds addresses into the core Cache and updates simple stats. 
"""
from typing import List, Tuple, Optional, Callable
from .cache import Cache, CacheBlock
from .ram import RAM
from ..data.stats_export import Statistics


class CacheSimulator: 
    def __init__(self, cache: Cache, stats: Optional[Statistics] = None, ram: Optional[RAM] = None):
        self.cache = cache
        self.stats = stats or Statistics()
        self.ram = ram
        self.sequence: List[Tuple[int, bool]] = []
        self.index = 0

    def reset(self):
        # clear stats and rewind the sequence pointer
        self.stats.reset()
        self.index = 0
        # also clear cache contents
        self.cache.reset()

    def load_sequence(self, addresses: List[int], writes: Optional[List[bool]] = None):
        if writes is None:
            writes = [False] * len(addresses)
        self.sequence = list(zip(addresses, writes))
        self.index = 0
        # sequence is a list of (addr, is_write). We step
        # through it with `step()` which advances self.index.

    def has_next(self) -> bool:
        return self.index < len(self.sequence)

    def step(self) -> Optional[dict]:
        if not self.has_next():
            return None
        address, is_write = self.sequence[self.index]
        self.index += 1

        # pass through write-miss policy from cache object
        write_miss_policy = getattr(self.cache, 'write_miss_policy', 'write-allocate')
        hit, set_index, way_index, evicted, mem_read, mem_write = self.cache.access(address, is_write=is_write, write_miss_policy=write_miss_policy)
        self.stats.record_access(hit)

        # perform backing-store operations when requested
        if mem_read:
            self.stats.memory_reads += 1
            try:
                if self.ram is not None:
                    # read the whole cache line (use base-aligned address)
                    line_size = getattr(self.cache, 'line_size', 1) or 1
                    base = (int(address) // int(line_size)) * int(line_size)
                    try:
                        self.ram.read(base)
                    except Exception:
                        # best-effort single-byte read fallback
                        try:
                            self.ram.read(address)
                        except Exception:
                            pass
            except Exception:
                pass

        if mem_write:
            self.stats.memory_writes += 1
            try:
                if self.ram is not None:
                    # If an evicted dirty block triggered the write (write-back),
                    # write back the evicted block's base address. Otherwise,
                    # for write-through, write the accessed address (or its base).
                    line_size = getattr(self.cache, 'line_size', 1) or 1
                    if evicted is not None and getattr(evicted, 'dirty', False) and getattr(self.cache, 'write_policy', '') == 'write-back':
                        # compute evicted block base address: block_addr = tag * num_sets + set_index
                        try:
                            num_sets = getattr(self.cache, 'num_sets', 1) or 1
                            block_addr = int(evicted.tag) * int(num_sets) + int(set_index)
                            base = block_addr * int(line_size)
                            # perform a write to the base address of the evicted line
                            self.ram.write(base, 1)
                        except Exception:
                            # fallback: write the accessed address
                            try:
                                self.ram.write(address, 1)
                            except Exception:
                                pass
                    else:
                        # write-through or other explicit mem write: write base-aligned address
                        try:
                            base = (int(address) // int(line_size)) * int(line_size)
                            self.ram.write(base, 1)
                        except Exception:
                            try:
                                self.ram.write(address, 1)
                            except Exception:
                                pass
            except Exception:
                pass

        return {
            'address': address,
            'is_write': is_write,
            'hit': hit,
            'set_index': set_index,
            'way_index': way_index,
            'mem_read': mem_read,
            'mem_write': mem_write,
            'stats': {
                'accesses': self.stats.accesses,
                'hits': self.stats.hits,
                'misses': self.stats.misses,
                'hit_rate': self.stats.hit_rate,
                'miss_rate': self.stats.miss_rate,
                'memory_reads': self.stats.memory_reads,
                'memory_writes': self.stats.memory_writes,
            },
            'evicted': evicted,
        }

    def run_all(self, callback: Optional[Callable[[dict], None]] = None):
        while self.has_next():
            info = self.step()
            if callback:
                callback(info)
