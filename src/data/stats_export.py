"""Statistics and exporter (Data package).

Student-style note: this file just keeps counters and can dump a CSV.
I kept it tiny so it's obvious what each stat means.
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

    If fpath is None, a save dialog will be shown.
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
    """Export a canvas as PDF. Attempts Pillow -> matplotlib -> ps2pdf -> fallback PS.

    Returns the path of the saved file (pdf or ps) or None on cancel/failure.
    """
    try:
        if canvas is None:
            return None
        if not fpath:
            fpath = filedialog.asksaveasfilename(defaultextension='.pdf', filetypes=[('PDF files','*.pdf'), ('PostScript','*.ps')], title='Save chart as PDF/PS')
        if not fpath:
            return None

        ps = canvas.postscript(colormode='color')
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.ps')
        try:
            tmp.write(ps.encode('utf-8'))
            tmp.close()
            # if user requested PS explicitly
            if fpath.lower().endswith('.ps'):
                os.replace(tmp.name, fpath)
                return fpath

            # Prefer matplotlib-based direct PDF rendering (uses hit_rate_history)
            try:
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
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
                return fpath
            except Exception:
                # matplotlib not available or failed — try Pillow conversion next
                pass

            # Try Pillow conversion (from the canvas PostScript)
            try:
                from PIL import Image
                img = Image.open(tmp.name)
                if img.mode in ('RGBA', 'LA'):
                    bg = Image.new('RGB', img.size, (255,255,255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                else:
                    img = img.convert('RGB')
                img.save(fpath, 'PDF', resolution=300)
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
                return fpath
            except Exception:
                pass

            # Try ps2pdf conversion
            try:
                import subprocess
                dest_ps = os.path.splitext(fpath)[0] + '.ps'
                os.replace(tmp.name, dest_ps)
                res = subprocess.run(['ps2pdf', dest_ps, fpath], check=False, capture_output=True)
                if res.returncode == 0 and os.path.exists(fpath):
                    try:
                        os.unlink(dest_ps)
                    except Exception:
                        pass
                    return fpath
                # leave ps in place
                return dest_ps
            except Exception:
                # final fallback: move tmp to basename.ps
                dest_ps = os.path.splitext(fpath)[0] + '.ps'
                try:
                    os.replace(tmp.name, dest_ps)
                    return dest_ps
                except Exception:
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                    return None
        finally:
            # ensure temporary removed if still present
            try:
                if os.path.exists(tmp.name):
                    pass
            except Exception:
                pass
    except Exception:
        return None


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
