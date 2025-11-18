"""Direct-mapped cache wrapper used by the UI (moved into src.wrappers).

This file was moved from the top-level `src/` into `src/wrappers/` and uses
absolute imports to reference the canonical core implementations in
`src.core`.
"""
# Student note: this wrapper keeps a human-friendly cache_contents array
# for the UI and also creates a core Cache+CacheSimulator for real logic.
from src.core.cache import Cache
from src.core.simulator import CacheSimulator


class Direct_mapped_cache:
    def __init__(self, ui):
        self.ui = ui
        self.cache = None
        self.sim = None
        
        # Cache parameters
        self.cache_size = 0
        self.block_size = 0
        self.address_width = 0
        self.replacement_policy = ""
        
        # Cache structure for detailed tracking
        self.cache_contents = []  # List of cache lines: [index, valid, tag, ...block_data...]
        
        # Instruction breakdown (Tag, Index, Offset)
        self.num_blocks = 0
        self.block_offset_bits = 0
        self.index_bits = 0
        self.tag_bits = 0
        self.tag = '0'
        self.index = '0'
        self.offset = '0'

    def direct_mapped(self):
        """Initialize direct-mapped cache with current UI parameters."""
        self.cache_size = max(1, int(self.ui.cache_size.get()))
        self.block_size = max(1, int(self.ui.block_size.get()))
        self.address_width = max(1, int(self.ui.address_width.get()))
        self.replacement_policy = self.ui.replacement_policy.get()
        
        # Calculate cache parameters
        self.num_blocks = self.cache_size // self.block_size
        self.block_offset_bits = (self.block_size - 1).bit_length() if self.block_size > 1 else 0
        self.index_bits = (self.num_blocks - 1).bit_length() if self.num_blocks > 1 else 0
        self.tag_bits = self.address_width - (self.index_bits + self.block_offset_bits)
        
        print(f"Direct-Mapped Cache Initialized:")
        print(f"  Cache size: {self.cache_size}")
        print(f"  Block size: {self.block_size}")
        print(f"  Num blocks: {self.num_blocks}")
        print(f"  Tag bits: {self.tag_bits}, Index bits: {self.index_bits}, Offset bits: {self.block_offset_bits}")
        
        # Initialize cache structure
        self.cache_contents = []
        for i in range(self.num_blocks):
            # Each cache line: [index, valid_bit, tag, ...block_data...]
            cache_line = [str(i), "0", "-"] + ["-"] * self.block_size
            self.cache_contents.append(cache_line)
        
        # Initialize core cache for compatibility
        write_policy = self.ui.write_hit_policy.get()
        self.cache = Cache(num_blocks=self.num_blocks, block_size=self.block_size, associativity=1,
                           replacement=self.replacement_policy, write_policy=write_policy,
                           write_miss_policy=self.ui.write_miss_policy.get())
        self.sim = CacheSimulator(self.cache)

    def update_tio(self, binary_number):
        """Update Tag, Index, Offset from binary address."""
        binary_number = str(binary_number).zfill(self.address_width)
        
        self.tag = binary_number[:self.tag_bits] if self.tag_bits > 0 else ''
        self.index = binary_number[self.tag_bits:self.tag_bits + self.index_bits] if self.index_bits > 0 else '0'
        self.offset = binary_number[self.tag_bits + self.index_bits:] if self.block_offset_bits > 0 else '0'
        
        print(f"  Tag: {self.tag if self.tag else '(none)'}")
        print(f"  Index: {self.index}")
        print(f"  Offset: {self.offset if self.offset else '0'}")

    def load_instruction(self, binary_value, hex_value):
        """Perform a LOAD (read) operation."""
        try:
            addr = int(hex_value, 16)
        except Exception:
            addr = int(binary_value, 2) if binary_value else 0
        
        # Convert address to binary for TIO breakdown
        binary_addr = bin(addr)[2:].zfill(self.address_width)
        self.update_tio(binary_addr)
        
        # Check cache hit or miss
        cache_index = int(self.index, 2) if self.index else 0
        offset_value = int(self.offset, 2) if self.offset else 0
        
        if cache_index < len(self.cache_contents):
            cache_line = self.cache_contents[cache_index]
            cache_valid = cache_line[1]
            cache_tag = cache_line[2]
            
            # Check for hit
            is_hit = cache_valid == "1" and self.tag == cache_tag
            
            if is_hit:
                print(f"  CACHE HIT at index {cache_index}")
                data = cache_line[3 + offset_value] if 3 + offset_value < len(cache_line) else "-"
                print(f"  Data: {data}")
            else:
                print(f"  CACHE MISS at index {cache_index}")
                # Load block from memory (simulate)
                self.cache_contents[cache_index][1] = "1"  # Set valid bit
                self.cache_contents[cache_index][2] = self.tag  # Set tag
                # Simulate loading data (use address as data for now)
                for i in range(self.block_size):
                    self.cache_contents[cache_index][3 + i] = f"0x{addr + i:X}"
                print(f"  Block loaded into cache index {cache_index}")
        
        # Use existing simulator for compatibility
        self.sim.load_sequence([addr], writes=[False])
        return self.sim.step()

    def store_instruction(self, address_binary, data_byte, address_hex):
        """Perform a STORE (write) operation."""
        try:
            addr = int(address_hex, 16)
        except Exception:
            addr = int(address_binary, 2) if address_binary else 0
        
        # Convert address to binary for TIO breakdown
        binary_addr = bin(addr)[2:].zfill(self.address_width)
        self.update_tio(binary_addr)
        
        # Check cache hit or miss
        cache_index = int(self.index, 2) if self.index else 0
        offset_value = int(self.offset, 2) if self.offset else 0
        
        if cache_index < len(self.cache_contents):
            cache_line = self.cache_contents[cache_index]
            cache_valid = cache_line[1]
            cache_tag = cache_line[2]
            
            # Check for hit
            is_hit = cache_valid == "1" and self.tag == cache_tag
            
            if is_hit:
                print(f"  CACHE HIT (STORE) at index {cache_index}")
                # Update cache with new data
                if 3 + offset_value < len(cache_line):
                    cache_line[3 + offset_value] = data_byte
                print(f"  Data written: {data_byte}")
            else:
                print(f"  CACHE MISS (STORE) at index {cache_index}")
                # Load block first, then write
                self.cache_contents[cache_index][1] = "1"  # Set valid bit
                self.cache_contents[cache_index][2] = self.tag  # Set tag
                # Load block (simulate)
                for i in range(self.block_size):
                    self.cache_contents[cache_index][3 + i] = f"0x{addr + i:X}"
                # Write new data
                if 3 + offset_value < len(cache_line):
                    self.cache_contents[cache_index][3 + offset_value] = data_byte
                print(f"  Block loaded and data written at index {cache_index}")
        
        # Use existing simulator for compatibility
        self.sim.load_sequence([addr], writes=[True])
        return self.sim.step()
