"""Statistics and exporter (Data package).

Student-style note: this file just keeps counters and can dump a CSV.
I kept it tiny so it's obvious what each stat means.
"""
import time
import csv
from dataclasses import dataclass


class Statistics:
    def __init__(self):
        self.reset()

    def reset(self):
        # counters start from zero, start_time for potential timing
        self.accesses = 0
        self.hits = 0
        self.misses = 0
        self.memory_reads = 0
        self.memory_writes = 0
        self.start_time = time.time()

    def record_access(self, hit: bool):
        # simple counter update: call this for every cache access
        self.accesses += 1
        if hit:
            self.hits += 1
        else:
            self.misses += 1

    @property
    def hit_rate(self):
        return (self.hits / self.accesses) if self.accesses else 0.0

    @property
    def miss_rate(self):
        return (self.misses / self.accesses) if self.accesses else 0.0


class Exporter:
    @staticmethod
    def export_stats_csv(path: str, stats: Statistics):
        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['accesses', 'hits', 'misses', 'hit_rate', 'miss_rate', 'memory_reads', 'memory_writes'])
            writer.writerow([
                stats.accesses, stats.hits, stats.misses, stats.hit_rate, stats.miss_rate,
                stats.memory_reads, stats.memory_writes
            ])
