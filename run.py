"""Entry point for the Cache Memory Simulator.

Usage:
    python run.py        # starts the Tkinter GUI
    python run.py --nogui # runs a quick headless validation of core logic
"""
import sys
from src.core.cache import Cache
from src.core.simulator import CacheSimulator


def headless_test():
    # Simple scenario to validate cache logic
    cache = Cache(num_blocks=8, line_size=1, associativity=2, replacement='LRU', write_policy='write-back')
    sim = CacheSimulator(cache)
    # small sequence with repetitions to force hits/misses
    seq = [0,1,2,3,0,1,4,5,0,1,6,7]
    sim.load_sequence(seq)
    sim.run_all()
    s = sim.stats
    print('Accesses:', s.accesses)
    print('Hits:', s.hits)
    print('Misses:', s.misses)
    print('Hit rate:', s.hit_rate)
    print('Memory reads:', s.memory_reads)
    print('Memory writes:', s.memory_writes)


def main():
    if '--nogui' in sys.argv:
        headless_test()
    else:
        # Import the UI
        from src.simulation.user_interface import run_ui
        run_ui()


if __name__ == '__main__':
    main()
