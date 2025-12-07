"""Generic k-way set-associative cache wrapper.

This wrapper builds a core Cache with an explicit associativity `k` (1..num_blocks).
UI should call this when the user wants a generic k-associative configuration.

Student note: this is a thin wrapper that mirrors the other wrappers' API
(load_instruction/store_instruction) so the UI can drive it uniformly.
"""
from src.core.cache import Cache
from src.core.simulator import CacheSimulator


class K_associative_cache:
    def __init__(self, ui, associativity: int = None):
        self.ui = ui
        self.cache = None
        self.sim = None
        self.associativity = associativity

    def build(self):
        # Read UI parameters
        line_size = max(1, int(self.ui.line_size.get()))
        raw_cache_size = max(1, int(self.ui.cache_size.get()))
        num_blocks = max(1, raw_cache_size // line_size)

        # Determine associativity (k). Prefer explicit constructor value,
        # otherwise read from UI variable.
        k = int(self.associativity) if self.associativity is not None else max(1, int(self.ui.associativity.get()))
        if k < 1:
            k = 1
        # If requested associativity exceeds number of blocks, clamp to fully-assoc
        if k > num_blocks:
            k = num_blocks
        associativity = k
        # Do NOT mutate number of blocks here. The UI validation ensures
        # `num_blocks % associativity == 0`. If the values are invalid the
        # wrapper will still build but the core Cache may further adjust; in
        # practice the UI prevents invalid combos.

        write_policy = self.ui.write_hit_policy.get()
        replacement = self.ui.replacement_policy.get()

        # Create core cache and simulator
        self.cache = Cache(num_blocks=num_blocks, line_size=line_size, associativity=associativity,
                           replacement=replacement, write_policy=write_policy,
                           write_miss_policy=self.ui.write_miss_policy.get())
        # forward optional RAM from UI
        self.sim = CacheSimulator(self.cache, ram=getattr(self.ui, 'ram_obj', None))

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
