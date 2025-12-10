"""Simulation wrapper used by the UI

Converts UI inputs into a sequence of addresses and forwards 
them to the cache wrapper.
"""
from src.wrappers.k_associative_cache import K_associative_cache


class Simulation:
    def __init__(self, ui):
        self.ui = ui
        self.cache_wrapper = None

    def _create_cache_from_ui(self):
        # Only create a cache wrapper if one does not already exist.
        if getattr(self, 'cache_wrapper', None) is not None:
            return
        assoc = int(self.ui.associativity.get())
        wrapper = K_associative_cache(self.ui, associativity=assoc)
        wrapper.build()
        self.cache_wrapper = wrapper

    def run_simulation(self, num_passes: int = 1):
        # Create cache wrapper according to UI if not already present.
        # This preserves state (replacement policy metadata, dirty bits,
        # etc.) across multiple traversals of predefined scenarios.
        self._create_cache_from_ui()
        # If the UI has an explicit input string, use it; otherwise, generate sequence from selected scenario
        seq_str = self.ui.input.get().strip()
        items = []
        if seq_str:
            items = list(map(str.strip, seq_str.split(',')))
        else:
            # generate based on scenario selection in UI (if present)
            scen = getattr(self.ui, 'scenario_var', None)
            scen_name = scen.get() if scen is not None else 'Matrix Traversal'
            items = self._generate_sequence_for_scenario(scen_name)
        results = []
        # helper: normalize an address string to a plain hex string (no 0x prefix)
        def _addr_to_hex_str(s: str) -> str:
            s = s.strip()
            if s.startswith('0x') or s.startswith('0X'):
                return s[2:]
            # if contains hex letters, treat as hex
            if any(c in 'abcdefABCDEF' for c in s):
                return s
            # otherwise treat as decimal and convert to hex
            try:
                return format(int(s, 10), 'x')
            except Exception:
                # fallback: return original
                return s

    # Run the sequence for num_passes times
        for p in range(num_passes):
            for idx, it in enumerate(items):
                try:
                    # integer items treat as hex value
                    if isinstance(it, int):
                        info = self.cache_wrapper.load_instruction(None, format(it, 'x'))
                    else:
                        # store syntax: "addr-data" (hex addr, data payload)
                        if '-' in it:
                            addr, data = map(str.strip, it.split('-'))
                            hex_addr = _addr_to_hex_str(addr)
                            # pass both binary and hex forms to the wrapper
                            try:
                                bin_addr = bin(int(hex_addr, 16))[2:]
                            except Exception:
                                bin_addr = None
                            info = self.cache_wrapper.store_instruction(bin_addr, data, hex_addr)
                            # attach store value so UI can display what was written
                            if isinstance(info, dict):
                                info['value'] = data
                        else:
                            # otherwise treat as a load (hex string)
                            hex_addr = _addr_to_hex_str(it)
                            info = self.cache_wrapper.load_instruction(None, hex_addr)

                    if isinstance(info, dict):
                        info['_pass'] = p
                        info['_idx'] = idx

                    results.append(info)
                except Exception as e:
                    results.append({'error': str(e), 'input': it, '_pass': p, '_idx': idx})

        return results

    def _generate_sequence_for_scenario(self, name: str):
        # Produce a list of hex strings (or integers) for predefined scenarios
        if name == 'Matrix Traversal':
            N = 10
            seq = []
            for i in range(N):
                for j in range(N):
                    seq.append(format(i * N + j, 'x'))
            return seq
        elif name == 'Random Access':
            import random
            return [format(random.randint(0, 255), 'x') for _ in range(16)]
        else:
            # Fallback
            instr = list(range(0, 32))
            data = [100 + (i % 8) for i in range(32)]
            seq = []
            for i in range(max(len(instr), len(data))):
                if i < len(instr):
                    seq.append(format(instr[i], 'x'))
                if i < len(data):
                    seq.append(format(data[i], 'x'))
            return seq
