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

    def load_sequence(self, addresses: List[int], writes: Optional[List[bool]] = None, values: Optional[List[Optional[int]]] = None):
        """Load a sequence of addresses with optional write flags and optional write values.

        `values` should be a list parallel to addresses where each element is the
        integer value to write for write operations (or None to write no explicit value).
        """
        if writes is None:
            writes = [False] * len(addresses)
        if values is None:
            values = [None] * len(addresses)
        # store triplets (address, is_write, value)
        self.sequence = list(zip(addresses, writes, values))
        self.index = 0
        # sequence is a list of (addr, is_write). We step
        # through it with `step()` which advances self.index.

    def has_next(self) -> bool:
        return self.index < len(self.sequence)

    def step(self) -> Optional[dict]:
        if not self.has_next():
            return None

        address, is_write, value = self.sequence[self.index]
        self.index += 1

        # pass through write-miss policy from cache object
        write_miss_policy = getattr(self.cache, 'write_miss_policy', 'write-allocate')
        hit, set_index, way_index, evicted, mem_read, mem_write = self.cache.access(
            address, is_write=is_write, write_miss_policy=write_miss_policy, write_value=value
        )
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
                        # read each byte of the line and, if the cache just allocated
                        # the block (set_index/way_index present), populate its data
                        line_vals = []
                        for off in range(int(line_size)):
                            try:
                                v = self.ram.read(base + off)
                            except Exception:
                                v = 0
                            line_vals.append(v)
                        # if cache block exists, store loaded bytes into it
                        try:
                            if set_index is not None and way_index is not None and getattr(self.cache, 'sets', None) is not None:
                                try:
                                    blk = self.cache.sets[int(set_index)][int(way_index)]
                                    try:
                                        blk.data = list(line_vals)
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                                # If this access was a write and a write value was provided,
                                # apply the write to the just-loaded block so the written
                                # value is visible immediately in cache (and will be
                                # written-through below if mem_write is True).
                                try:
                                    if is_write and value is not None:
                                        try:
                                            off = int(address) % int(line_size)
                                            blk.data[off] = int(value)
                                            # For write-back policy, mark dirty; for
                                            # write-through, mem_write will trigger RAM write
                                            try:
                                                if getattr(self.cache, 'write_policy', '') == 'write-back':
                                                    blk.dirty = True
                                            except Exception:
                                                pass
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                        except Exception:
                            pass
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
                            # perform a write of the whole evicted line to RAM
                            try:
                                if getattr(evicted, 'data', None) is not None:
                                    for off, v in enumerate(evicted.data):
                                        try:
                                            self.ram.write(base + off, v)
                                        except Exception:
                                            pass
                                else:
                                    # fallback: single-byte marker write
                                    try:
                                        self.ram.write(base, 0)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        except Exception:
                            # fallback: write the accessed address
                            try:
                                self.ram.write(address, 0)
                            except Exception:
                                pass
                    else:
                        # write-through or other explicit mem write: write base-aligned address
                        try:
                            base = (int(address) // int(line_size)) * int(line_size)
                            # for write-through we expect the cache's block.data to have the updated value
                            # if present, write the whole line; otherwise write a single byte marker
                            try:
                                blk = None
                                try:
                                    if set_index is not None and way_index is not None:
                                        blk = self.cache.sets[int(set_index)][int(way_index)]
                                except Exception:
                                    blk = None
                                if blk is not None and getattr(blk, 'data', None) is not None:
                                    for off, v in enumerate(blk.data):
                                        try:
                                            self.ram.write(base + off, v)
                                        except Exception:
                                            pass
                                else:
                                    try:
                                        self.ram.write(base, 0)
                                    except Exception:
                                        pass
                            except Exception:
                                try:
                                    self.ram.write(base, 0)
                                except Exception:
                                    pass
                        except Exception:
                            try:
                                self.ram.write(address, 0)
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
