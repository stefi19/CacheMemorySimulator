"""2-way set associative cache wrapper (moved to src.wrappers).
"""
from src.core.cache import Cache
from src.core.simulator import CacheSimulator

# Student note: this wrapper makes a 2-way cache from UI params and
# exposes a tiny load/store API used by the UI. It's short and explicit.


class Two_way_set_associative_cache:
    def __init__(self, ui):
        self.ui = ui
        self.cache = None
        self.sim = None

    def two_way_set_associative(self):
        block_size = max(1, int(self.ui.block_size.get()))
        # cache_size from UI is total capacity; number of blocks = cache_size // block_size
        raw_cache_size = max(1, int(self.ui.cache_size.get()))
        num_blocks = max(2, raw_cache_size // block_size)
        write_policy = self.ui.write_hit_policy.get()
        replacement = self.ui.replacement_policy.get()
        associativity = 2
        # ensure number of blocks is divisible by associativity
        if num_blocks % associativity != 0:
            num_blocks += (associativity - (num_blocks % associativity))
        self.cache = Cache(num_blocks=num_blocks, block_size=block_size, associativity=associativity,
                           replacement=replacement, write_policy=write_policy,
                           write_miss_policy=self.ui.write_miss_policy.get())
        self.sim = CacheSimulator(self.cache)

    def load_instruction(self, binary_value, hex_value):
        try:
            addr = int(hex_value, 16)
        except Exception:
            addr = int(binary_value, 2) if binary_value else 0
        self.sim.load_sequence([addr], writes=[False])
        return self.sim.step()

    def store_instruction(self, address_binary, data_byte, address_hex):
        try:
            addr = int(address_hex, 16)
        except Exception:
            addr = int(address_binary, 2) if address_binary else 0
        self.sim.load_sequence([addr], writes=[True])
        return self.sim.step()
