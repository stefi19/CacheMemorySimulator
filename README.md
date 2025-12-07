# Cache Memory Simulator

Simple Python/Tkinter cache memory simulator.

Features
- Configurable cache size, block size, associativity (ways), replacement policy (LRU/FIFO/Random), write policy (write-through/write-back).
- Two sample scenarios: Matrix Traversal, Random Access.
- Live statistics: accesses, hits, misses, hit rate, memory reads/writes.

Run GUI

Open a terminal and run:

```bash
python run.py
```

Run a headless validation test (no GUI):

```bash
python run.py --nogui
```

Notes
- This is a minimal, educational implementation. You can extend it by adding exporters, more detailed visualizations, or support for multiple cache levels.
