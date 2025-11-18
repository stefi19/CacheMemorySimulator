"""Fully associative cache wrapper (moved to src.wrappers).
"""
from src.core.cache import Cache
from src.core.simulator import CacheSimulator

# Student note: fully associative means associativity == number of blocks.
# We just build the core Cache accordingly and use the simulator for steps.


class Fully_associative_cache:
    def __init__(self, ui):
        self.ui = ui
        self.cache = None
        self.sim = None

    def fully_associative(self):
        # fully associative: associativity == number of blocks
        block_size = max(1, int(self.ui.block_size.get()))
        raw_cache_size = max(1, int(self.ui.cache_size.get()))
        num_blocks = max(1, raw_cache_size // block_size)
        write_policy = self.ui.write_hit_policy.get()
        replacement = self.ui.replacement_policy.get()
        associativity = num_blocks
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
