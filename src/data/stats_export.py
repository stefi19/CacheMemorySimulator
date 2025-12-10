"""Statistics and exporter.
"""
import time
import csv
from dataclasses import dataclass
import json
import os
import tempfile
from typing import List, Dict, Optional
from tkinter import filedialog


def export_chart_json(hit_rate_history: List[float], stats: Dict[str, float], fpath: Optional[str] = None) -> Optional[str]:
    """Export hit-rate history and stats to a JSON file. Returns saved path or None.
    """
    try:
        if not fpath:
            fpath = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON files','*.json')], title='Save chart data as JSON')
        if not fpath:
            return None
        data = {
            'hit_rate_history': list(hit_rate_history),
            'stats': stats
        }
        with open(fpath, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2)
        return fpath
    except Exception:
        return None


def export_chart_pdf_from_canvas(canvas, hit_rate_history: List[float], fpath: Optional[str] = None) -> Optional[str]:
    """Render the hit-rate history to a PDF using matplotlib and save it.
    Uses `hit_rate_history` to draw the chart. 
    Returns the saved file path or None on cancel/failure.
    """
    try:
        if not fpath:
            fpath = filedialog.asksaveasfilename(defaultextension='.pdf', filetypes=[('PDF files','*.pdf')], title='Save chart as PDF')
        if not fpath:
            return None

        # Use matplotlib
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        data = list(hit_rate_history) or [0]
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.plot(range(len(data)), data, color='#FFA500', linewidth=2)
        ax.fill_between(range(len(data)), data, color='#FFA500', alpha=0.1)
        ax.set_ylim(0, 1)
        ax.set_xlabel('Sample')
        ax.set_ylabel('Hit rate')
        ax.grid(False)
        fig.tight_layout()
        fig.savefig(fpath, format='pdf', dpi=150)
        plt.close(fig)
        return fpath
    except Exception:
        return None


class Statistics:
    def __init__(self):
        self.reset()

    def reset(self):
        # counters start from zero
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
