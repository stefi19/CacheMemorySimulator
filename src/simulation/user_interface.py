"""User interface moved into the simulation package.

This file is the same UI implementation previously at `src/user_interface.py`.
It was relocated here to keep the top-level `src/` directory focused on
core packages. The run entrypoint (`run.py`) will import the UI from
`src.simulation.user_interface`.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from src.simulation import Simulation
from src.wrappers.direct_mapped_cache import Direct_mapped_cache
from src.wrappers.fully_associative_cache import Fully_associative_cache
from src.wrappers.two_way_set_associative_cache import Two_way_set_associative_cache
from src.wrappers.four_way_set_associative_cache import Four_way_set_associative_cache
from src.wrappers.k_associative_cache import K_associative_cache
from src.data.stats_export import export_chart_json as se_export_chart_json, export_chart_pdf_from_canvas as se_export_chart_pdf_from_canvas
import math
import json
import io
import os
import tempfile
from tkinter import filedialog

# This UI is a big single class that wires the widgets to the cache wrappers.

# Reasonable UI limits so users don't enter absurd numbers
MAX_CACHE_SIZE = 4096
MAX_LINE_SIZE = 1024
MAX_ADDRESS_WIDTH = 32
MAX_INPUT_TOKENS = 256
MIN_ANIM_SPEED = 1
MAX_ANIM_SPEED = 5000

# Hardcoded scenario sequences (users cannot edit these sequences).
# Each scenario maps to a list of (address, is_write) tuples. These are
# intentionally fixed so 'Run Simulation' will only run these predefined
# scenarios. Manual input is handled by Read/Write buttons below.
PREDEFINED_SCENARIOS = {
    'Matrix Traversal': [(i * 4 + j, False) for i in range(4) for j in range(4)],
    'Random Access': [(i * 7 + 3, False) for i in range(16)],
}

class UserInterface:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Cache Simulator Simulator")
        self.window.geometry("1080x1000")
        self.window.configure(bg="#23967F")
        self.center_window()

        # Colors and fonts
        self.font_color_1 = "white"
        self.background_main = "#23967F"
        self.background_container = "#292F36"
        self.color_pink = "#E56B70"
        self.font_container = "Cascadia Code"
        self.btn_color = "#6874E8"

        # User input variables
        self.cache_size = tk.IntVar(value=16)
        self.address_width = tk.IntVar(value=6)
        self.line_size = tk.IntVar(value=2)
        self.associativity = tk.IntVar(value=1)
        # show verbose decode debug messages in the eviction/log pane (removed checkbox)
        # small status string showing applied/clamped values after Apply
        self.effective_info = tk.StringVar(value='')
        self.write_hit_policy = tk.StringVar(value="write-back")
        self.write_miss_policy = tk.StringVar(value="write-allocate")
        self.replacement_policy = tk.StringVar(value="LRU")
        self.instuction = tk.StringVar(value="LOAD")
        # visible cache type (mirrored from algorithm buttons)
        self.cache_type = tk.StringVar(value="Direct-Mapped")
        self.capacity = tk.IntVar(value=4)
        self.input = tk.StringVar(value="1,2,3")
        self.scenario_var = tk.StringVar(value='Matrix Traversal')
        # Animation and run controls
        self.num_passes = tk.IntVar(value=3)
        # Fixed animation speed: 1000 ms (1 second) — user control removed
        self.anim_speed = tk.IntVar(value=1000)  # milliseconds per step (fixed)
        # removed display_hex and fast_mode checkboxes per user request
        # (these UI toggles were removed to simplify the interface)
        self.anim_cap = tk.IntVar(value=256)
        # state used by mapping mode
        self.dir = 0
        self.binary_value = 0
        self.text_boxes = []

        self.cache_wrapper = None
        self.frame_labels = []

        # animation/playback state
        self._is_running = False
        self._is_paused = False
        self._do_step = False
        self._anim_results = []
        self.hit_rate_history = []
        self._after_id = None
        # last appended log line (used to prevent immediate duplicate debug lines)
        self._last_log_line = None
        # last debug message (separate from general last log) to avoid Text-wrapping artifacts
        self._last_debug_msg = None
        # resize debounce state
        self._resize_after_id = None
        self._last_window_size = (0, 0)

        # build UI
        self.setup_ui()

        # Watch parameter changes to re-validate and re-enable controls when fixed
        try:
            # trace_add available in modern tkinter; fall back to trace
            try:
                self.cache_size.trace_add('write', lambda *a: self._on_params_changed())
                self.line_size.trace_add('write', lambda *a: self._on_params_changed())
                self.associativity.trace_add('write', lambda *a: self._on_params_changed())
            except Exception:
                try:
                    self.cache_size.trace('w', lambda *a: self._on_params_changed())
                    self.line_size.trace('w', lambda *a: self._on_params_changed())
                    self.associativity.trace('w', lambda *a: self._on_params_changed())
                except Exception:
                    pass
        except Exception:
            pass

        # Open fullscreen
        try:
            self.window.attributes('-fullscreen', True)
        except Exception:
            # fallback: maximize window
            try:
                self.window.state('zoomed')
            except Exception:
                pass
        # allow Escape to exit fullscreen
        self.window.bind('<Escape>', lambda e: self.window.attributes('-fullscreen', False))

    def center_window(self):
        try:
            self.window.update_idletasks()
            w = self.window.winfo_width()
            h = self.window.winfo_height()
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
            self.window.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def get_core_cache(self):
        """Return the underlying core Cache instance if available.

        The UI holds wrapper objects in `self.cache` which may expose a
        `.cache` attribute containing the core Cache. This helper normalizes
        access to the core Cache object.
        """
        try:
            if hasattr(self, 'cache'):
                wrapper = getattr(self, 'cache')
                # wrapper may be the core Cache itself
                if hasattr(wrapper, 'num_sets') and hasattr(wrapper, 'sets'):
                    return wrapper
                # or wrapper may hold a .cache attribute
                if hasattr(wrapper, 'cache'):
                    core = getattr(wrapper, 'cache')
                    if hasattr(core, 'num_sets') and hasattr(core, 'sets'):
                        return core
        except Exception:
            pass
        return None

    def update_rep_set_choices(self):
        """Replacement-set UI removed — keep method as no-op for compatibility."""
        return

    def update_replacement_panel(self):
        """Replacement panel removed — no-op kept for compatibility."""
        return

    def setup_ui(self):
        """Construct the main UI. This method centralizes layout and widget creation.
        """
        # top-level container
        container = ttk.Frame(self.window, padding=12)
        container.grid(row=0, column=0, sticky='nsew')
        self.window.rowconfigure(0, weight=1)
        self.window.columnconfigure(0, weight=1)

        # left and right panes
        container_left = ttk.Frame(container, padding=8)
        container_left.grid(row=0, column=0, sticky='nw')
        container_right = ttk.Frame(container, padding=8)
        container_right.grid(row=0, column=1, sticky='nsew')
        container.grid_columnconfigure(1, weight=1)
        container_right.grid_rowconfigure(2, weight=1)

        # configuration area on left
        self.configuration_container = ttk.Frame(container_left, padding=8)
        self.configuration_container.grid(row=0, column=0, sticky='nw')

        entry_width = 28
        option_menu_width = 18

        row_counter = 0

        # Cache size and block size
        ttk.Label(self.configuration_container, text="Cache size:", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        self.cache_size_spinbox = tk.Spinbox(self.configuration_container, from_=1, to=1024, textvariable=self.cache_size, width=8)
        self.cache_size_spinbox.grid(row=row_counter, column=1, sticky=tk.W)
        row_counter += 1

        ttk.Label(self.configuration_container, text="Line size:", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        self.line_size_spinbox = tk.Spinbox(self.configuration_container, from_=1, to=64, textvariable=self.line_size, width=8)
        self.line_size_spinbox.grid(row=row_counter, column=1, sticky=tk.W)
        row_counter += 1

        # Replacement policy
        ttk.Label(self.configuration_container, text="Replacement policy:", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        rep_btn_frame = ttk.Frame(self.configuration_container)
        rep_btn_frame.grid(row=row_counter, column=1, sticky='w')
        self.rep_buttons = {}
        self.rep_buttons['LRU'] = ttk.Button(rep_btn_frame, text='LRU', width=6, command=lambda: self._set_replacement('LRU'))
        self.rep_buttons['LRU'].grid(row=0, column=0, padx=2)
        self.rep_buttons['Random'] = ttk.Button(rep_btn_frame, text='Random', width=6, command=lambda: self._set_replacement('Random'))
        self.rep_buttons['Random'].grid(row=0, column=1, padx=2)
        self.rep_buttons['FIFO'] = ttk.Button(rep_btn_frame, text='FIFO', width=6, command=lambda: self._set_replacement('FIFO'))
        self.rep_buttons['FIFO'].grid(row=0, column=2, padx=2)
        row_counter += 1

        # Input
        ttk.Label(self.configuration_container, text="Input (addr or action:addr e.g. R:0x10,W:32):", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        inp_entry = tk.Entry(self.configuration_container, textvariable=self.input, width=entry_width)
        inp_entry.grid(row=row_counter, column=1)
        # update decode panel in real-time as the user types
        try:
            # trace_add available in Python 3.6+
            self.input.trace_add('write', lambda *a: self.update_decode_panel())
        except Exception:
            try:
                self.input.trace('w', lambda *a: self.update_decode_panel())
            except Exception:
                pass
        try:
            inp_entry.bind('<KeyRelease>', lambda e: self.update_decode_panel())
        except Exception:
            pass
        row_counter += 1

        # Manual read/write buttons (consume input tokens one at a time)
        try:
            btn_frame = ttk.Frame(self.configuration_container)
            btn_frame.grid(row=row_counter, column=0, columnspan=2, pady=(6, 6), sticky='w')
            self.read_next_btn = ttk.Button(btn_frame, text='Read Next', command=self.read_next)
            self.read_next_btn.grid(row=0, column=0, padx=(0, 6))
            self.write_next_btn = ttk.Button(btn_frame, text='Write Next', command=self.write_next)
            self.write_next_btn.grid(row=0, column=1, padx=(0, 6))
        except Exception:
            pass
        row_counter += 1


        # Scenario selector
        ttk.Label(self.configuration_container, text="Scenario:", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        scen_menu = ttk.OptionMenu(self.configuration_container, self.scenario_var, 'Matrix Traversal', 'Matrix Traversal', 'Random Access', command=self._on_scenario_change)
        scen_menu.config(width=option_menu_width)
        scen_menu.grid(row=row_counter, column=1)
        row_counter += 1

        # Passes
        ttk.Label(self.configuration_container, text="Passes:", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        tk.Spinbox(self.configuration_container, from_=1, to=10, textvariable=self.num_passes, width=6).grid(row=row_counter, column=1, sticky=tk.W)
        row_counter += 1

        # Animation speed control removed; using fixed 1000 ms per step
        row_counter += 1

        # decode debug verbosity toggle removed from UI

        # scenario code area (shows generated sequence/pseudocode)
        ttk.Label(self.configuration_container, text="Scenario code:", font=(self.font_container, 10), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, columnspan=2, sticky='w', pady=(8, 3))
        row_counter += 1
        self.scenario_code = tk.Text(self.configuration_container, width=50, height=5, font=(self.font_container, 9))
        self.scenario_code.grid(row=row_counter, column=0, columnspan=2, pady=(0, 4), sticky='ew')
        self.scenario_code.configure(state='disabled', bg='#111111', fg='#DDDDDD')
        row_counter += 1

        # Display current cache type and replacement policy
        ttk.Label(self.configuration_container, text="Active cache:", font=(self.font_container, 10), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        ttk.Label(self.configuration_container, textvariable=self.cache_type, font=(self.font_container, 10), foreground='#8BC34A', background=self.background_container).grid(row=row_counter, column=1, sticky=tk.W, pady=3)
        row_counter += 1

        # Eviction log
        ttk.Label(self.configuration_container, text="Eviction log:", font=(self.font_container, 10), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, columnspan=2, sticky=tk.W, pady=(8, 3))
        row_counter += 1
        self.log_text = tk.Text(self.configuration_container, width=50, height=8, font=(self.font_container, 9), bg='#111111', fg='#DDDDDD')
        self.log_text.grid(row=row_counter, column=0, columnspan=2, sticky='nsew', pady=(0, 8))
        try:
            self.log_text.configure(state='disabled')
        except Exception:
            pass
        row_counter += 1


        row_counter += 1

        # Run/Reset buttons
        self.run_button = ttk.Button(container_left, text="Run Simulation", command=self.run_simulation, style='Orange.TButton')
        self.run_button.grid(row=1, column=0, pady=(8, 4), ipadx=12, ipady=6, sticky='ew')

        self.reset_button = ttk.Button(container_left, text="Reset", command=self.reset_simulation, style='Orange.TButton')
        self.reset_button.grid(row=2, column=0, pady=4, ipadx=12, ipady=6, sticky='ew')

        # playback controls
        playback_frame = ttk.Frame(container_left, padding="2")
        playback_frame.grid(row=3, column=0, pady=(6, 0), sticky='ew')
        self.play_btn = ttk.Button(playback_frame, text="Play", command=self.play_animation, style='Orange.TButton')
        self.play_btn.grid(row=0, column=0, padx=2, ipadx=8, sticky='ew')
        self.pause_btn = ttk.Button(playback_frame, text="Pause", command=self.pause_animation, style='Orange.TButton')
        self.pause_btn.grid(row=0, column=1, padx=2, ipadx=8, sticky='ew')
        self.step_btn = ttk.Button(playback_frame, text="Step", command=self.step_animation, style='Orange.TButton')
        self.step_btn.grid(row=0, column=2, padx=2, ipadx=8, sticky='ew')
        playback_frame.columnconfigure(0, weight=1)
        playback_frame.columnconfigure(1, weight=1)
        playback_frame.columnconfigure(2, weight=1)


        playback_frame.columnconfigure(2, weight=1)

        # Right panel: algorithm buttons + cache visual
        algorithm_buttons_frame = ttk.Frame(container_right, padding="4")
        algorithm_buttons_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(algorithm_buttons_frame, text="Associativity (k):", font=(self.font_container, 11, 'bold'), foreground=self.font_color_1).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 4))
        # Spinbox to choose k (1 = direct mapped, k = number of blocks => fully associative)
        self.assoc_spinbox = tk.Spinbox(algorithm_buttons_frame, from_=1, to=256, textvariable=self.associativity, width=6)
        self.assoc_spinbox.grid(row=1, column=0, padx=3, pady=2)
        self.apply_assoc_btn = ttk.Button(algorithm_buttons_frame, text="Apply", command=self.apply_associativity, style='Orange.TButton')
        self.apply_assoc_btn.grid(row=1, column=1, padx=3, pady=2, ipadx=6, ipady=4)
        # Keep backward-compat labels for display
        self.assoc_info_label = ttk.Label(algorithm_buttons_frame, textvariable=self.cache_type, font=(self.font_container, 10), foreground='#8BC34A')
        self.assoc_info_label.grid(row=1, column=2, padx=8)

        # Address decode panel (shows how address maps to set/tag/way)
        decode_frame = ttk.LabelFrame(container_right, text="Address Decode (Last Access)", padding=6)
        decode_frame.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.decode_addr_label = ttk.Label(decode_frame, text="Address: -", font=(self.font_container, 10, 'bold'), foreground='#8BC34A')
        self.decode_addr_label.grid(row=0, column=0, sticky='w', padx=4, pady=2)
        self.decode_calc_label = ttk.Label(decode_frame, text="block_addr = addr ÷ line_size  |  set = block_addr mod num_sets  |  tag = block_addr ÷ num_sets", font=(self.font_container, 9), foreground='#AAAAAA')
        self.decode_calc_label.grid(row=1, column=0, sticky='w', padx=4, pady=2)
        # Canvas for graphical binary + segment arrows
        self.decode_result_canvas = tk.Canvas(decode_frame, height=84, bg='#111111', highlightthickness=0)
        self.decode_result_canvas.grid(row=2, column=0, sticky='we', padx=4, pady=2)
        # keep compatibility name for older code
        self.decode_result_label = None

        # Replacement policy state panel removed (simplified UI)

        # Cache display area
        self.cache_display_frame = ttk.Frame(container_right, padding="8")
        self.cache_display_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        self.cache_display_frame.configure(style="InputFrame.TFrame")

        self.create_frame_labels(self.capacity.get())
        try:
            self.update_replacement_controls()
        except Exception:
            pass
        try:
            self.update_rep_set_choices()
            self.update_replacement_panel()
        except Exception:
            pass

        # Legend
        legend = ttk.Frame(container_right, padding="4")
        legend.grid(row=3, column=0, sticky="w", pady=(0, 8))
        tk.Label(legend, text="Hit", bg="#8BC34A", fg='white', width=8, font=(self.font_container, 9, 'bold')).grid(row=0, column=0, padx=4)
        tk.Label(legend, text="Miss", bg="#F44336", fg='white', width=8, font=(self.font_container, 9, 'bold')).grid(row=0, column=1, padx=4)

        # Stats display
        stats_frame = ttk.Frame(container_right, padding="6")
        stats_frame.grid(row=4, column=0, sticky="ew", pady=(0, 0))
        tk.Label(stats_frame, text="Accesses:", foreground=self.font_color_1, background=self.background_container, font=(self.font_container, 10)).grid(row=0, column=0, sticky='w')
        self.stat_accesses = tk.Label(stats_frame, text="0", foreground='#8BC34A', background=self.background_container, font=(self.font_container, 12, 'bold'))
        self.stat_accesses.grid(row=0, column=1, sticky='w', padx=6)
        tk.Label(stats_frame, text="Hits:", foreground=self.font_color_1, background=self.background_container, font=(self.font_container, 10)).grid(row=0, column=2, sticky='w', padx=(12, 0))
        self.stat_hits = tk.Label(stats_frame, text="0", foreground='#8BC34A', background=self.background_container, font=(self.font_container, 12, 'bold'))
        self.stat_hits.grid(row=0, column=3, sticky='w', padx=6)
        tk.Label(stats_frame, text="Misses:", foreground=self.font_color_1, background=self.background_container, font=(self.font_container, 10)).grid(row=1, column=0, sticky='w')
        self.stat_misses = tk.Label(stats_frame, text="0", foreground='#F44336', background=self.background_container, font=(self.font_container, 12, 'bold'))
        self.stat_misses.grid(row=1, column=1, sticky='w', padx=6)
        tk.Label(stats_frame, text="Hit rate:", foreground=self.font_color_1, background=self.background_container, font=(self.font_container, 10)).grid(row=1, column=2, sticky='w', padx=(12, 0))
        self.stat_hit_rate = tk.Label(stats_frame, text="0.000", foreground='#FFA500', background=self.background_container, font=(self.font_container, 12, 'bold'))
        self.stat_hit_rate.grid(row=1, column=3, sticky='w', padx=6)

        # small hit-rate chart
        self.hit_canvas = tk.Canvas(stats_frame, width=180, height=52, bg=self.background_container, highlightthickness=0)
        self.hit_canvas.grid(row=0, column=4, rowspan=2, padx=(16, 0))
        # export buttons for chart: JSON (data) and PS/PDF (graphic)
        try:
            exp_frame = ttk.Frame(stats_frame)
            exp_frame.grid(row=2, column=4, padx=(16,0), pady=(6,0))
            self.export_json_btn = ttk.Button(exp_frame, text='Export JSON', command=self.export_chart_json)
            self.export_json_btn.grid(row=0, column=0, padx=2)
            self.export_pdf_btn = ttk.Button(exp_frame, text='Export PDF/PS', command=self.export_chart_pdf)
            self.export_pdf_btn.grid(row=0, column=1, padx=2)
        except Exception:
            pass

        # initialize scenario display and styles
        self._on_scenario_change(self.scenario_var.get())
        try:
            self.apply_button_palette()
        except Exception:
            pass
        try:
            self.window.bind('<Configure>', self._on_window_configure)
        except Exception:
            pass
        try:
            self.update_replacement_controls()
        except Exception:
            pass

    # Implementations for methods that were omitted during relocation.
    def _set_replacement(self, name: str):
        """Select replacement policy (button handler)."""
        try:
            self.replacement_policy.set(name)
        except Exception:
            pass
        # If core cache exists, record the chosen name for UI display
        core = self.get_core_cache()
        if core is not None:
            try:
                core._replacement_name = name
            except Exception:
                pass
        try:
            self.update_replacement_panel()
        except Exception:
            pass

    def _on_scenario_change(self, selection):
        """Handle scenario selection change and populate the scenario_code box."""
        try:
            self.scenario_code.configure(state='normal')
            self.scenario_code.delete('1.0', 'end')
            # Use only predefined scenario descriptions (non-editable sequences)
            if selection in PREDEFINED_SCENARIOS:
                # Short human-friendly description
                if selection == 'Matrix Traversal':
                    self.scenario_code.insert('end', 'Matrix Traversal (predefined): sequential accesses over a 4x4 matrix\n\n')
                elif selection == 'Random Access':
                    self.scenario_code.insert('end', 'Random Access (predefined): fixed pseudo-random pattern\n\n')
                # (previously had a third predefined scenario; removed)
                else:
                    self.scenario_code.insert('end', f'Selected: {selection} (predefined)\n\n')
                # Show the actual hardcoded sequence (one per line)
                try:
                    seq = PREDEFINED_SCENARIOS.get(selection, [])
                    for (a, w) in seq:
                        prefix = 'W' if w else 'R'
                        self.scenario_code.insert('end', f"{prefix}: {hex(a)} ({a})\n")
                except Exception:
                    pass
            else:
                # custom / free input mode
                self.scenario_code.insert('end', 'Custom input mode: enter addresses into the Input field and use Read Next / Write Next buttons to consume them.')
            self.scenario_code.configure(state='disabled')
        except Exception:
            pass

    def apply_button_palette(self):
        """Apply a small style palette for buttons (safe no-op if ttk not available)."""
        try:
            style = ttk.Style()
            style.configure('Orange.TButton', foreground='white', background=self.btn_color)
        except Exception:
            pass

    def _on_window_configure(self, event):
        """Window resize handler (debounced)."""
        # Minimal implementation: no expensive layout work here.
        try:
            size = (event.width, event.height)
            if size != self._last_window_size:
                self._last_window_size = size
        except Exception:
            pass

    def update_decode_panel(self, *_):
        """Decode the current address in the Input field and show Tag/Index/Offset."""
        try:
            text = (self.input.get() or '').strip()
            if not text:
                try:
                    self.decode_addr_label.configure(text="Address: -")
                    if getattr(self, 'decode_result_canvas', None):
                        try:
                            self.decode_result_canvas.delete('all')
                        except Exception:
                            pass
                except Exception:
                    pass
                return
            token = text.split(',')[0].strip()
            # allow optional action prefix like R:0x10 or W:32
            if ':' in token:
                parts = token.split(':', 1)
                addr_token = parts[1].strip()
            else:
                addr_token = token
            # parse integer (auto-detect 0x prefix). fall back to decimal
            addr = None
            try:
                addr = int(addr_token, 0)
            except Exception:
                try:
                    addr = int(addr_token, 16)
                except Exception:
                    try:
                        addr = int(addr_token)
                    except Exception:
                        addr = 0

            # fetch line_size and num_sets
            try:
                line_size = max(1, int(self.line_size.get()))
            except Exception:
                line_size = 1
            # try to get core cache values
            num_sets = None
            index_bits = 0
            offset_bits = 0
            try:
                core = self.get_core_cache()
                if core is not None:
                    num_sets = getattr(core, 'num_sets', None)
                    bs = getattr(core, 'line_size', None)
                    if bs:
                        line_size = bs
            except Exception:
                core = None

            if num_sets is None:
                try:
                    raw_cache_size = max(1, int(self.cache_size.get()))
                    associativity = max(1, int(self.associativity.get()))
                    num_blocks = max(1, raw_cache_size // line_size)
                    num_sets = max(1, num_blocks // associativity)
                except Exception:
                    num_sets = 1

            # compute sizes in bits
            try:
                offset_bits = (line_size - 1).bit_length() if line_size > 1 else 0
                index_bits = (num_sets - 1).bit_length() if num_sets > 1 else 0
            except Exception:
                offset_bits = 0
                index_bits = 0

            block_addr = addr // line_size
            set_index = block_addr % num_sets if num_sets > 0 else 0
            tag = block_addr // num_sets if num_sets > 0 else block_addr
            offset = addr % line_size

            # Diagnostic logging for debugging freezes on specific addresses
            try:
                # compute preliminary bits for logging (safe guards)
                try:
                    aw_preview = max(1, int(self.address_width.get()))
                except Exception:
                    aw_preview = max(1, index_bits + offset_bits + 1)
                tb_preview = max(0, aw_preview - (index_bits + offset_bits))
                bin_preview = bin(addr)[2:].zfill(aw_preview)
                # Only append debug info when enabled and avoid repeating identical lines
                try:
                    if getattr(self, 'show_decode_debug', None) and self.show_decode_debug.get():
                        debug_msg = f"DECODE DEBUG: addr={addr} line_size={line_size} num_sets={num_sets} index_bits={index_bits} offset_bits={offset_bits} aw={aw_preview} tb={tb_preview} bin={bin_preview}"
                        # compare against the last debug message (separate from last_log_line)
                        if getattr(self, '_last_debug_msg', None) != debug_msg:
                            self._append_log(debug_msg)
                            try:
                                self._last_debug_msg = debug_msg
                            except Exception:
                                pass
                except Exception:
                    pass
            except Exception:
                pass
            # build binary representations
            try:
                aw = max(1, int(self.address_width.get()))
            except Exception:
                aw = max(1, index_bits + offset_bits + 1)
            # ensure the address width is large enough to display all segments
            min_aw = max(1, index_bits + offset_bits + 1)
            aw = max(aw, min_aw)
            # base binary address
            raw_bin = bin(addr)[2:]
            bin_addr = raw_bin.zfill(aw)
            # slice binary into tag/index/offset based on bit widths
            tb = max(0, aw - (index_bits + offset_bits))
            # use slices of bin_addr to avoid mismatches when tag/index/offset
            # were computed numerically and converted separately
            tag_bin = bin_addr[:tb] if tb > 0 else ''
            idx_bin = bin_addr[tb:tb + index_bits] if index_bits > 0 else ''
            off_bin = bin_addr[tb + index_bits:] if offset_bits > 0 else ''

            # update graphical canvas with binary segments and calculation
            try:
                self.decode_addr_label.configure(text=f"Address: {hex(addr)} ({addr})")
                canvas = getattr(self, 'decode_result_canvas', None)
                if canvas is None:
                    return
                canvas.delete('all')
                # determine drawing size
                try:
                    w = int(canvas.winfo_width()) or 420
                except Exception:
                    w = 420
                try:
                    h = int(canvas.winfo_height()) or 84
                except Exception:
                    h = 84
                bits = bin_addr
                n = len(bits)
                # box dimensions
                margin = 8
                avail_w = max(100, w - 2 * margin)
                box_w = max(12, min(28, avail_w // max(1, n)))
                box_h = 28
                start_x = margin
                y_box = 8
                # bit boxes with segment colors
                tb = max(0, aw - (index_bits + offset_bits))
                for i, b in enumerate(bits):
                    if i < tb:
                        color = '#6FA8DC'  # tag (blue)
                    elif i < tb + index_bits:
                        color = '#93C47D'  # index (green)
                    else:
                        color = '#F9CB9C'  # offset (orange)
                    x = start_x + i * box_w
                    try:
                        canvas.create_rectangle(x, y_box, x + box_w - 2, y_box + box_h, fill=color, outline='#222222')
                        canvas.create_text(x + box_w / 2, y_box + box_h / 2, text=b, fill='black', font=(self.font_container, 10))
                    except Exception:
                        pass

                # draw segment labels centered
                segs = [
                    ('TAG', 0, tb),
                    ('INDEX', tb, tb + index_bits),
                    ('OFFSET', tb + index_bits, n),
                ]
                for label, s, e in segs:
                    if e > s:
                        x1 = start_x + s * box_w
                        x2 = start_x + e * box_w - 2
                        cx = (x1 + x2) / 2
                        try:
                            canvas.create_text(cx, y_box + box_h + 12, text=label, fill='#FFFFFF', font=(self.font_container, 9, 'bold'))
                            canvas.create_line(cx, y_box + box_h + 6, cx, y_box + box_h, fill='#FFFFFF', arrow='last')
                        except Exception:
                            pass

                # calculation detail line
                calc = f"block_addr = {block_addr} (addr // line_size={line_size}); set = {set_index} (block_addr % {num_sets}); tag = {tag} (block_addr // {num_sets})"
                try:
                    canvas.create_text(start_x, y_box + box_h + 34, anchor='w', text=calc, fill='#FFA500', font=(self.font_container, 9))
                except Exception:
                    pass
            except Exception:
                import traceback as _tb
                try:
                    self._append_log('Error in decode canvas drawing:')
                    self._append_log(''.join(_tb.format_exception_only(*_tb.sys.exc_info()[:2])))
                except Exception:
                    pass
        except Exception:
            import traceback as _tb
            try:
                self._append_log('Exception in update_decode_panel:')
                self._append_log(''.join(_tb.format_exception_only(*_tb.sys.exc_info()[:2])))
            except Exception:
                pass

    def update_replacement_controls(self):
        """Update replacement-policy related controls (no-op minimal)."""
        try:
            # Sync label text
            self.rep_policy_label.configure(text=self.replacement_policy.get())
        except Exception:
            pass

    def create_frame_labels(self, capacity: int):
        """Create simple rectangular labels representing cache frames."""
        try:
            # Clear previous
            for w in getattr(self, 'frame_labels', []):
                try:
                    w.destroy()
                except Exception:
                    pass
            self.frame_labels = []

            cols = min(8, max(1, int(math.sqrt(max(1, capacity)))))
            r = 0
            c = 0
            for i in range(capacity):
                lbl = tk.Label(self.cache_display_frame, text=f"{i}", relief='ridge', width=8, height=3, bg='#111111', fg='#FFFFFF')
                lbl.grid(row=r, column=c, padx=4, pady=4)
                self.frame_labels.append(lbl)
                c += 1
                if c >= cols:
                    c = 0
                    r += 1
        except Exception:
            pass

    def reset_simulation(self):
        """Reset UI state and stop any running animation."""
        try:
            self._is_running = False
            self._is_paused = False
            if self._after_id:
                try:
                    self.window.after_cancel(self._after_id)
                except Exception:
                    pass
                self._after_id = None
            # reset stats display
            self.stat_accesses.configure(text='0')
            self.stat_hits.configure(text='0')
            self.stat_misses.configure(text='0')
            self.stat_hit_rate.configure(text='0.000')
            # clear hit-rate history and canvas
            try:
                self.hit_rate_history = []
                self.hit_canvas.delete('all')
            except Exception:
                pass
            # clear logs
            try:
                self.log_text.configure(state='normal')
                self.log_text.delete('1.0', 'end')
                self.log_text.configure(state='disabled')
            except Exception:
                pass
            # reset underlying simulator and cache if present
            try:
                wrapper = getattr(self, 'cache_wrapper', None) or getattr(self, 'cache', None)
                if wrapper is not None:
                    if hasattr(wrapper, 'sim') and getattr(wrapper, 'sim') is not None:
                        try:
                            wrapper.sim.reset()
                        except Exception:
                            pass
                    core_cache = getattr(wrapper, 'cache', None) or (wrapper if hasattr(wrapper, 'sets') else None)
                    if core_cache is not None and hasattr(core_cache, 'reset'):
                        try:
                            core_cache.reset()
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass

    def _append_log(self, text: str):
        try:
            self.log_text.configure(state='normal')
            self.log_text.insert('end', text + '\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')
            try:
                self._last_log_line = text
            except Exception:
                pass
        except Exception:
            pass

    def _update_stats_widgets(self, stats):
        try:
            self.stat_accesses.configure(text=str(stats.get('accesses', 0)))
            self.stat_hits.configure(text=str(stats.get('hits', 0)))
            self.stat_misses.configure(text=str(stats.get('misses', 0)))
            hr = stats.get('hit_rate', 0.0)
            self.stat_hit_rate.configure(text=f"{hr:.3f}")
            # redraw small hit-rate chart whenever stats update
            try:
                self._draw_hit_chart()
            except Exception:
                pass
        except Exception:
            pass

    def run_simulation(self):
        """Parse input addresses, run the simulator (blocking) and update UI with results."""
        # Ensure a cache wrapper exists
        try:
            # Only allow Run Simulation for predefined scenarios
            selection = self.scenario_var.get()
            if selection not in PREDEFINED_SCENARIOS:
                self._append_log('Run Simulation is only available for predefined scenarios. Use Read Next / Write Next for manual input.')
                return
            if not hasattr(self, 'cache') or self.cache is None:
                # default to current associativity (use generic k-associative wrapper)
                self.apply_associativity()

            # For predefined scenarios, load the fixed sequence
            seq = PREDEFINED_SCENARIOS.get(selection, [])
            addresses = [a for (a, w) in seq]
            writes = [w for (a, w) in seq]

            if not addresses:
                self._append_log('No addresses to simulate')
                return

            # clamp UI values again and enforce token/address limits
            try:
                self._clamp_ui_values()
            except Exception:
                pass
            # enforce token limit to avoid huge sequences
            if len(addresses) > MAX_INPUT_TOKENS:
                self._append_log(f"Input truncated to first {MAX_INPUT_TOKENS} addresses (too many tokens)")
                addresses = addresses[:MAX_INPUT_TOKENS]
                writes = writes[:MAX_INPUT_TOKENS]
            # enforce address magnitude wrt address_width
            try:
                aw = max(1, int(self.address_width.get()))
            except Exception:
                aw = MAX_ADDRESS_WIDTH
            max_addr = (1 << min(aw, MAX_ADDRESS_WIDTH)) - 1
            norm_addresses = []
            norm_writes = []
            for i, a in enumerate(addresses):
                if a is None:
                    continue
                if a < 0:
                    self._append_log(f"Negative address skipped: {a}")
                    continue
                if a > max_addr:
                    self._append_log(f"Address {a} exceeds address width, clamped to {max_addr}")
                    a = max_addr
                norm_addresses.append(a)
                norm_writes.append(writes[i] if i < len(writes) else False)
            addresses = norm_addresses
            writes = norm_writes

            # Use the wrapper's simulator if available
            sim = None
            if hasattr(self.cache, 'sim') and getattr(self.cache, 'sim') is not None:
                sim = self.cache.sim
            elif hasattr(self.cache_wrapper, 'sim') and getattr(self.cache_wrapper, 'sim') is not None:
                sim = self.cache_wrapper.sim

            if sim is None:
                self._append_log('No simulator available')
                return

            # Load sequence and run using a non-blocking animation loop
            passes = max(1, int(self.num_passes.get()))
            full_addresses = addresses * passes
            full_writes = writes * passes
            sim.load_sequence(full_addresses, writes=full_writes)
            # store running simulator
            self._running_sim = sim
            self._is_running = True
            self._is_paused = False
            # clear any existing after handler
            if self._after_id:
                try:
                    self.window.after_cancel(self._after_id)
                except Exception:
                    pass
                self._after_id = None
            # start stepping
            self._animation_step()
        except Exception as e:
            self._append_log(f'Error running simulation: {e}')

    def play_animation(self):
        # Resume if paused or start fresh
        try:
            if getattr(self, '_is_paused', False) and getattr(self, '_running_sim', None):
                self._is_paused = False
                self._animation_step()
            else:
                self.run_simulation()
        except Exception:
            pass

    def pause_animation(self):
        # Not implemented; placeholder
        self._is_paused = True

    def step_animation(self):
        # Single-step: run only the next address
        try:
            if not hasattr(self, 'cache') or self.cache is None:
                self.apply_associativity()
            sim = None
            if hasattr(self.cache, 'sim') and getattr(self.cache, 'sim') is not None:
                sim = self.cache.sim
            elif hasattr(self.cache_wrapper, 'sim') and getattr(self.cache_wrapper, 'sim') is not None:
                sim = self.cache_wrapper.sim
            if sim is None:
                self._append_log('No simulator available')
                return
            if not sim.has_next():
                # Reload sequence from input
                self.run_simulation()
                return
            info = sim.step()
            if info:
                action = 'W' if info.get('is_write') else 'R'
                self._append_log(f"Step Addr {info.get('address')} ({action}): {'HIT' if info.get('hit') else 'MISS'}")
                self._update_stats_widgets(info.get('stats', {}))
                # update cache display to highlight the most recent access
                try:
                    self.update_cache_display(info)
                except Exception:
                    pass
                # update decode panel to reflect this stepped address as well
                try:
                    addr = info.get('address')
                    if addr is not None:
                        try:
                            self._update_decode_from_address(addr)
                        except Exception:
                            # fallback to generic decode update
                            try:
                                self.update_decode_panel()
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

    def start(self):
        try:
            self.window.mainloop()
        except Exception:
            pass

    def _animation_step(self):
        """Perform one simulator step and schedule the next one via after()."""
        try:
            if not getattr(self, '_is_running', False) or getattr(self, '_is_paused', False):
                return
            sim = getattr(self, '_running_sim', None)
            if sim is None:
                return
            info = sim.step()
            if info is None:
                # finished
                self._is_running = False
                self._running_sim = None
                self._after_id = None
                return
            # update UI for this step
            hit = info.get('hit', False)
            addr = info.get('address')
            action = 'W' if info.get('is_write') else 'R'
            self._append_log(f"Addr {addr} ({action}): {'HIT' if hit else 'MISS'}")
            self._update_stats_widgets(info.get('stats', {}))
            try:
                self.update_cache_display(info)
            except Exception:
                pass
            # update decode panel to reflect last access (do not change input field)
            try:
                if addr is not None:
                    try:
                        self._update_decode_from_address(addr)
                    except Exception:
                        # fall back to updating from input if helper fails
                        try:
                            self.update_decode_panel()
                        except Exception:
                            pass
            except Exception:
                pass

            # update hit-rate history & redraw chart
            try:
                hr = info.get('stats', {}).get('hit_rate', None)
                if hr is None:
                    # compute from stats dict if not present
                    s = info.get('stats', {})
                    accesses = s.get('accesses', 0)
                    hits = s.get('hits', 0)
                    hr = (hits / accesses) if accesses else 0.0
                self.hit_rate_history.append(hr)
                # cap history length
                max_len = 200
                if len(self.hit_rate_history) > max_len:
                    self.hit_rate_history = self.hit_rate_history[-max_len:]
                self._draw_hit_chart()
            except Exception:
                pass

            # schedule next
            delay = max(1, int(self.anim_speed.get()))
            self._after_id = self.window.after(delay, self._animation_step)
        except Exception:
            pass

    def _update_decode_from_address(self, addr: int):
        """Update the decode canvas for a specific address (used by animation steps).

        This is similar to update_decode_panel but operates on a provided address
        and does not alter the user's input field.
        """
        try:
            if addr is None:
                return
            # update header label to show last accessed address
            try:
                self.decode_addr_label.configure(text=f"Address: {hex(addr)} ({addr})")
            except Exception:
                pass
            # determine block size and num_sets (same logic as update_decode_panel)
            try:
                line_size = max(1, int(self.line_size.get()))
            except Exception:
                line_size = 1
            try:
                core = self.get_core_cache()
                if core is not None:
                    num_sets = getattr(core, 'num_sets', None)
                    bs = getattr(core, 'line_size', None)
                    if bs:
                        line_size = bs
                else:
                    num_sets = None
            except Exception:
                core = None
                num_sets = None
            if num_sets is None:
                try:
                    raw_cache_size = max(1, int(self.cache_size.get()))
                    associativity = max(1, int(self.associativity.get()))
                    num_blocks = max(1, raw_cache_size // line_size)
                    num_sets = max(1, num_blocks // associativity)
                except Exception:
                    num_sets = 1

            try:
                offset_bits = (line_size - 1).bit_length() if line_size > 1 else 0
                index_bits = (num_sets - 1).bit_length() if num_sets > 1 else 0
            except Exception:
                offset_bits = 0
                index_bits = 0

            block_addr = addr // line_size
            set_index = block_addr % num_sets if num_sets > 0 else 0
            tag = block_addr // num_sets if num_sets > 0 else block_addr
            offset = addr % line_size

            try:
                aw = max(1, int(self.address_width.get()))
            except Exception:
                aw = max(1, index_bits + offset_bits + 1)
            min_aw = max(1, index_bits + offset_bits + 1)
            aw = max(aw, min_aw)
            bin_addr = bin(addr)[2:].zfill(aw)

            # draw on canvas
            canvas = getattr(self, 'decode_result_canvas', None)
            if canvas is None:
                return
            canvas.delete('all')
            try:
                w = int(canvas.winfo_width()) or 420
            except Exception:
                w = 420
            try:
                h = int(canvas.winfo_height()) or 84
            except Exception:
                h = 84
            bits = bin_addr
            n = len(bits)
            margin = 8
            avail_w = max(100, w - 2 * margin)
            box_w = max(12, min(28, avail_w // max(1, n)))
            box_h = 28
            start_x = margin
            y_box = 8
            tb = max(0, aw - (index_bits + offset_bits))
            for i, b in enumerate(bits):
                if i < tb:
                    color = '#6FA8DC'
                elif i < tb + index_bits:
                    color = '#93C47D'
                else:
                    color = '#F9CB9C'
                x = start_x + i * box_w
                try:
                    canvas.create_rectangle(x, y_box, x + box_w - 2, y_box + box_h, fill=color, outline='#222222')
                    canvas.create_text(x + box_w / 2, y_box + box_h / 2, text=b, fill='black', font=(self.font_container, 10))
                except Exception:
                    pass
            segs = [
                ('TAG', 0, tb),
                ('INDEX', tb, tb + index_bits),
                ('OFFSET', tb + index_bits, n),
            ]
            for label, s, e in segs:
                if e > s:
                    x1 = start_x + s * box_w
                    x2 = start_x + e * box_w - 2
                    cx = (x1 + x2) / 2
                    try:
                        canvas.create_text(cx, y_box + box_h + 12, text=label, fill='#FFFFFF', font=(self.font_container, 9, 'bold'))
                        canvas.create_line(cx, y_box + box_h + 6, cx, y_box + box_h, fill='#FFFFFF', arrow='last')
                    except Exception:
                        pass
            calc = f"block_addr = {block_addr} (addr // line_size={line_size}); set = {set_index} (block_addr % {num_sets}); tag = {tag} (block_addr // {num_sets})"
            try:
                canvas.create_text(start_x, y_box + box_h + 34, anchor='w', text=calc, fill='#FFA500', font=(self.font_container, 9))
            except Exception:
                pass
        except Exception:
            try:
                self._append_log('Exception in _update_decode_from_address')
            except Exception:
                pass

    def update_cache_display(self, info: dict):
        """Color the cache frame labels according to the latest access.

        The UI supports either wrapper-specific `cache_contents` (Direct-mapped)
        or the core cache object (`wrapper.cache.sets`). This method will
        inspect available structures and color labels accordingly.
        """
        try:
            # determine core cache
            core = None
            wrapper = getattr(self, 'cache_wrapper', None)
            if wrapper is None:
                wrapper = getattr(self, 'cache', None)
            if wrapper is None:
                return
            if hasattr(wrapper, 'cache') and wrapper.cache is not None:
                core = wrapper.cache
            elif hasattr(wrapper, 'sets'):
                core = wrapper

            # Clear all labels to neutral
            for lbl in getattr(self, 'frame_labels', []):
                try:
                    lbl.configure(bg='#111111')
                except Exception:
                    pass

            # Prefer wrapper cache_contents if present (direct mapped wrapper)
            if hasattr(wrapper, 'cache_contents') and getattr(wrapper, 'cache_contents'):
                for i, line in enumerate(wrapper.cache_contents):
                    valid = line[1] == '1'
                    tag = line[2]
                    lbl = self.frame_labels[i] if i < len(self.frame_labels) else None
                    if lbl:
                        if valid:
                            lbl.configure(bg='#444444')
                        else:
                            lbl.configure(bg='#222222')
                # highlight the specific accessed line if available in info
                set_idx = info.get('set_index')
                way_idx = info.get('way_index')
                try:
                    idx = int(set_idx) if set_idx is not None else None
                    if idx is not None and idx < len(self.frame_labels):
                        lbl = self.frame_labels[idx]
                        lbl.configure(bg='#8BC34A' if info.get('hit') else '#F44336')
                except Exception:
                    pass
                return

            # Otherwise, use core Cache sets/ways representation
            if core is not None and hasattr(core, 'sets'):
                sets = core.sets
                rows = len(sets)
                ways = len(sets[0]) if rows > 0 else 0
                # map labels to (set,way) in row-major order
                k = 0
                for s in range(rows):
                    for w in range(ways):
                        if k >= len(self.frame_labels):
                            break
                        block = sets[s][w]
                        lbl = self.frame_labels[k]
                        if block.valid:
                            lbl.configure(bg='#444444')
                        else:
                            lbl.configure(bg='#222222')
                        k += 1

                # highlight accessed set/way
                try:
                    sidx = info.get('set_index')
                    widx = info.get('way_index')
                    if sidx is not None and widx is not None:
                        sidx = int(sidx)
                        widx = int(widx)
                        label_index = sidx * ways + widx
                        if label_index < len(self.frame_labels):
                            lbl = self.frame_labels[label_index]
                            lbl.configure(bg='#8BC34A' if info.get('hit') else '#F44336')
                except Exception:
                    pass
        except Exception:
            pass

    def _draw_hit_chart(self):
        try:
            canvas = self.hit_canvas
            canvas.delete('all')
            w = int(canvas['width'])
            h = int(canvas['height'])
            data = list(self.hit_rate_history)
            n = len(data)
            if n == 0:
                return
            # draw background grid
            for y in range(0, h, 10):
                canvas.create_line(0, y, w, y, fill='#1f1f1f')
            # plot line scaled to height
            max_points = w
            step = max(1, n / max_points)
            points = []
            for i in range(n):
                x = int((i / max(1, n - 1)) * (w - 4)) if n > 1 else 0
                y = int((1.0 - data[i]) * (h - 4))
                points.append((x + 2, y + 2))
            # draw polyline
            flat = []
            for (x, y) in points:
                flat.extend([x, y])
            if len(flat) >= 4:
                canvas.create_line(*flat, fill='#FFA500', width=2, smooth=True)
            # draw last point marker colored by last hit rate
            last = data[-1]
            cx = points[-1][0]
            cy = points[-1][1]
            color = '#8BC34A' if last >= 0.75 else ('#F44336' if last < 0.5 else '#FFA500')
            canvas.create_oval(cx-3, cy-3, cx+3, cy+3, fill=color, outline='')
        except Exception:
            pass

    # --- Export helpers for charts ---
    def export_chart_json(self):
        """Wrapper: gather UI stats and call data-layer JSON exporter."""
        try:
            stats = {
                'accesses': int(self.stat_accesses.cget('text')) if hasattr(self, 'stat_accesses') else 0,
                'hits': int(self.stat_hits.cget('text')) if hasattr(self, 'stat_hits') else 0,
                'misses': int(self.stat_misses.cget('text')) if hasattr(self, 'stat_misses') else 0,
                'hit_rate': float(self.stat_hit_rate.cget('text')) if hasattr(self, 'stat_hit_rate') else 0.0,
            }
            path = se_export_chart_json(self.hit_rate_history, stats)
            if path:
                self._append_log(f'Chart JSON exported to {path}')
        except Exception as e:
            self._append_log(f'Failed to export JSON: {e}')

    def export_chart_pdf(self):
        """Wrapper: export the hit-rate canvas via data-layer exporter."""
        try:
            canvas = getattr(self, 'hit_canvas', None)
            path = se_export_chart_pdf_from_canvas(canvas, self.hit_rate_history)
            if path:
                self._append_log(f'Chart exported to {path}')
        except Exception as e:
            self._append_log(f'Failed to export chart: {e}')

    def direct_mapped_algorithm(self):
        self.associativity.set(1)
        self.cache_type.set('Direct-Mapped')
        self.cache_wrapper = Direct_mapped_cache(self)
        self.cache_wrapper.direct_mapped()
        # also set self.cache for mapping single-step mode
        self.cache = self.cache_wrapper
        # create labels sized to the core cache's number of blocks if available
        try:
            nb = getattr(self.cache, 'num_blocks', None) or (getattr(self.cache, 'num_blocks', None) if hasattr(self.cache, 'num_blocks') else None)
            if nb is None and hasattr(self.cache, 'cache') and hasattr(self.cache.cache, 'num_blocks'):
                nb = self.cache.cache.num_blocks
            if nb is None and hasattr(self.cache, 'num_blocks'):
                nb = self.cache.num_blocks
            if nb is None:
                # fallback: use UI cache_size as approximate
                nb = max(1, int(self.cache_size.get()))
        except Exception:
            nb = max(1, int(self.cache_size.get()))
        self.create_frame_labels(nb)
        try:
            self.update_replacement_controls()
        except Exception:
            pass
        try:
            self.update_rep_set_choices()
            self.update_replacement_panel()
        except Exception:
            pass

    def fully_associative_algorithm(self):
        self.associativity.set(self.cache_size.get())
        self.cache_type.set('Fully-Associative')
        self.cache_wrapper = Fully_associative_cache(self)
        self.cache_wrapper.fully_associative()
        self.cache = self.cache_wrapper
        try:
            nb = getattr(self.cache, 'num_blocks', None) or (self.cache.cache.num_blocks if hasattr(self.cache, 'cache') else None)
            if nb is None:
                nb = max(1, int(self.cache_size.get()))
        except Exception:
            nb = max(1, int(self.cache_size.get()))
        self.create_frame_labels(nb)
        try:
            self.update_replacement_controls()
        except Exception:
            pass
        try:
            self.update_rep_set_choices()
            self.update_replacement_panel()
        except Exception:
            pass

    def two_set_associative_algorithm(self):
        self.associativity.set(2)
        self.cache_type.set('2-Way Set')
        self.cache_wrapper = Two_way_set_associative_cache(self)
        self.cache_wrapper.two_way_set_associative()
        self.cache = self.cache_wrapper
        try:
            nb = getattr(self.cache, 'num_blocks', None) or (self.cache.cache.num_blocks if hasattr(self.cache, 'cache') else None)
            if nb is None:
                nb = max(1, int(self.cache_size.get()))
        except Exception:
            nb = max(1, int(self.cache_size.get()))
        self.create_frame_labels(nb)
        try:
            self.update_replacement_controls()
        except Exception:
            pass
        try:
            self.update_rep_set_choices()
            self.update_replacement_panel()
        except Exception:
            pass

    def four_set_associative_algorithm(self):
        self.associativity.set(4)
        self.cache_type.set('4-Way Set')
        self.cache_wrapper = Four_way_set_associative_cache(self)
        self.cache_wrapper.four_way_set_associative()
        self.cache = self.cache_wrapper
        try:
            nb = getattr(self.cache, 'num_blocks', None) or (self.cache.cache.num_blocks if hasattr(self.cache, 'cache') else None)
            if nb is None:
                nb = max(1, int(self.cache_size.get()))
        except Exception:
            nb = max(1, int(self.cache_size.get()))
        self.create_frame_labels(nb)
        try:
            self.update_replacement_controls()
        except Exception:
            pass
        try:
            self.update_rep_set_choices()
            self.update_replacement_panel()
        except Exception:
            pass

    def apply_associativity(self):
        """Apply the user-selected associativity (k) and build a k-associative cache.

        This uses the generic K_associative_cache wrapper so the backend honors
        any k in the range [1, num_blocks].
        """
        # clamp UI fields to reasonable limits before building cache
        try:
            self._clamp_ui_values()
        except Exception:
            pass
        try:
            k = max(1, int(self.associativity.get()))
        except Exception:
            k = 1
        # Validate UI params and warn if something looks off
        try:
            ok = self.validate_ui_params()
            if not ok:
                self._append_log('Invalid parameters - fix inputs before applying')
                return
        except Exception:
            pass
        # Build K-associative wrapper
        try:
            self.cache_type.set(f"{k}-Way Set" if k != 1 else 'Direct-Mapped')
            wrapper = K_associative_cache(self, associativity=k)
            wrapper.build()
            self.cache_wrapper = wrapper
            # also keep self.cache for compatibility
            self.cache = wrapper
            # create UI frame labels according to number of blocks
            try:
                nb = getattr(wrapper.cache, 'num_blocks', None) or max(1, int(self.cache_size.get()))
            except Exception:
                nb = max(1, int(self.cache_size.get()))
            self.create_frame_labels(nb)
            try:
                self.update_replacement_controls()
            except Exception:
                pass
            try:
                self.update_rep_set_choices()
                self.update_replacement_panel()
            except Exception:
                pass
            # reset manual token state when a new cache is built
            try:
                self._manual_tokens = []
                self._manual_index = 0
            except Exception:
                pass
        except Exception as e:
            try:
                self._append_log(f"Error applying associativity {k}: {e}")
            except Exception:
                pass

    def _clamp_ui_values(self):
        """Clamp and normalize UI inputs to reasonable bounds.

        This prevents users from creating extremely large caches or entering
        addresses that won't fit the configured address width. We log when
        values are clamped so users see what happened.
        """
        try:
            # cache size
            try:
                cs = int(self.cache_size.get())
            except Exception:
                cs = 1
            if cs < 1:
                cs = 1
            if cs > MAX_CACHE_SIZE:
                self._append_log(f"Cache size {cs} too large, clamped to {MAX_CACHE_SIZE}")
                cs = MAX_CACHE_SIZE
            self.cache_size.set(cs)
            # line/block size
            try:
                bs = int(self.line_size.get())
            except Exception:
                bs = 1
            if bs < 1:
                bs = 1
            if bs > MAX_LINE_SIZE:
                self._append_log(f"Line size {bs} too large, clamped to {MAX_LINE_SIZE}")
                bs = MAX_LINE_SIZE
            self.line_size.set(bs)
            # address width
            try:
                aw = int(self.address_width.get())
            except Exception:
                aw = 1
            if aw < 1:
                aw = 1
            if aw > MAX_ADDRESS_WIDTH:
                self._append_log(f"Address width {aw} too large, clamped to {MAX_ADDRESS_WIDTH}")
                aw = MAX_ADDRESS_WIDTH
            self.address_width.set(aw)
            # anim speed clamp
            try:
                s = int(self.anim_speed.get())
            except Exception:
                s = MIN_ANIM_SPEED
            if s < MIN_ANIM_SPEED:
                s = MIN_ANIM_SPEED
            if s > MAX_ANIM_SPEED:
                s = MAX_ANIM_SPEED
            self.anim_speed.set(s)
            # num_passes clamp (keep small)
            try:
                p = int(self.num_passes.get())
            except Exception:
                p = 1
            if p < 1:
                p = 1
            if p > 10:
                self._append_log('Passes limited to 10')
                p = 10
            self.num_passes.set(p)
            # associativity cannot exceed number of blocks (clamped later in wrapper)
            try:
                assoc = int(self.associativity.get())
            except Exception:
                assoc = 1
            if assoc < 1:
                assoc = 1
            # basic upper bound to prevent silly values
            if assoc > max(1, cs):
                self._append_log(f"Associativity {assoc} too large, clamped to {max(1, cs)}")
                assoc = max(1, cs)
            self.associativity.set(assoc)
        except Exception:
            pass

    def _set_controls_enabled(self, enabled: bool):
        """Enable or disable interactive controls when parameters are invalid.

        This method is defensive: if a control doesn't exist yet we ignore it.
        """
        state = 'normal' if enabled else 'disabled'
        try:
            if hasattr(self, 'read_next_btn') and self.read_next_btn is not None:
                try:
                    self.read_next_btn.configure(state=state)
                except Exception:
                    pass
            if hasattr(self, 'write_next_btn') and self.write_next_btn is not None:
                try:
                    self.write_next_btn.configure(state=state)
                except Exception:
                    pass
            if hasattr(self, 'run_button') and self.run_button is not None:
                try:
                    self.run_button.configure(state=state)
                except Exception:
                    pass
            if hasattr(self, 'apply_assoc_btn') and self.apply_assoc_btn is not None:
                try:
                    self.apply_assoc_btn.configure(state=state)
                except Exception:
                    pass
            # playback controls
            if hasattr(self, 'play_btn') and self.play_btn is not None:
                try:
                    self.play_btn.configure(state=state)
                except Exception:
                    pass
            if hasattr(self, 'pause_btn') and self.pause_btn is not None:
                try:
                    self.pause_btn.configure(state=state)
                except Exception:
                    pass
            if hasattr(self, 'step_btn') and self.step_btn is not None:
                try:
                    self.step_btn.configure(state=state)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_params_changed(self):
        """Called when cache_size/line_size/associativity change to re-validate params."""
        try:
            ok = self.validate_ui_params()
            # validate_ui_params will enable controls if ok; if not, keep them disabled
            return ok
        except Exception:
            return False

    def validate_ui_params(self) -> bool:
        """Validate UI parameter combinations and alert the user for problematic inputs.

        Returns True if parameters are acceptable (warnings may still have been shown).
        """
        try:
            cs = int(self.cache_size.get())
        except Exception:
            cs = 1
        try:
            ls = int(self.line_size.get())
        except Exception:
            ls = 1
        try:
            assoc = int(self.associativity.get())
        except Exception:
            assoc = 1

        # basic invalid cases
        if ls <= 0:
            messagebox.showwarning('Invalid parameter', 'Line size must be >= 1')
            try:
                self._set_controls_enabled(False)
            except Exception:
                pass
            return False
        if cs <= 0:
            messagebox.showwarning('Invalid parameter', 'Cache size must be >= 1')
            try:
                self._set_controls_enabled(False)
            except Exception:
                pass
            return False

        # cache size must be exact multiple of line size for simplicity
        if cs % ls != 0:
            msg = (
                f'Cache size ({cs}) is not an exact multiple of line size ({ls}).\n'
                'Please choose values where cache_size is a multiple of line_size.'
            )
            try:
                messagebox.showwarning('Cache size / Line size mismatch', msg)
            except Exception:
                pass
            self._append_log(msg)
            try:
                self._set_controls_enabled(False)
            except Exception:
                pass
            return False

        # compute number of blocks and warn if associativity > blocks
        num_blocks = max(1, cs // ls)
        if assoc > num_blocks:
            msg = f'Associativity ({assoc}) exceeds number of blocks ({num_blocks}). Please reduce associativity or increase cache/line size.'
            try:
                messagebox.showwarning('Associativity too large', msg)
            except Exception:
                pass
            self._append_log(msg)
            try:
                self._set_controls_enabled(False)
            except Exception:
                pass
            return False

        # ensure associativity divides number of blocks (otherwise mapping is ambiguous)
        if num_blocks % assoc != 0:
            msg = f'Associativity ({assoc}) does not divide the number of blocks ({num_blocks}). Please choose an associativity that evenly divides number of blocks.'
            try:
                messagebox.showwarning('Associativity mismatch', msg)
            except Exception:
                pass
            self._append_log(msg)
            try:
                self._set_controls_enabled(False)
            except Exception:
                pass
            return False

        # all good -> enable controls
        try:
            self._set_controls_enabled(True)
        except Exception:
            pass
        return True

    # --- Manual input consumption helpers ---
    def _prepare_manual_tokens(self):
        """Parse the Input field into a list of integer addresses for manual mode.

        This ignores any R:/W: prefixes — the Read/Write buttons decide the action.
        """
        try:
            text = (self.input.get() or '').strip()
            if not text:
                self._manual_tokens = []
                self._manual_index = 0
                return
            # split on commas and whitespace
            raw = [t.strip() for part in text.split(',') for t in part.split() if t.strip()]
            tokens = []
            # keep the original raw tokens (for updating the input field as we consume)
            self._manual_raw_tokens = list(raw)
            for t in raw:
                # ignore optional action prefix for manual mode
                if ':' in t:
                    parts = t.split(':', 1)
                    tval = parts[1].strip()
                else:
                    tval = t
                try:
                    val = int(tval, 0)
                except Exception:
                    try:
                        val = int(tval, 16)
                    except Exception:
                        try:
                            val = int(tval)
                        except Exception:
                            self._append_log(f"Skipped invalid token in manual input: {t}")
                            continue
                tokens.append(val)
            # enforce token limit
            if len(tokens) > MAX_INPUT_TOKENS:
                self._append_log(f"Manual input truncated to first {MAX_INPUT_TOKENS} tokens")
                tokens = tokens[:MAX_INPUT_TOKENS]
            # clamp addresses by address_width
            try:
                aw = max(1, int(self.address_width.get()))
            except Exception:
                aw = MAX_ADDRESS_WIDTH
            max_addr = (1 << min(aw, MAX_ADDRESS_WIDTH)) - 1
            norm = []
            for a in tokens:
                if a < 0:
                    self._append_log(f"Negative address skipped: {a}")
                    continue
                if a > max_addr:
                    self._append_log(f"Address {a} exceeds address width, clamped to {max_addr}")
                    a = max_addr
                norm.append(a)
            self._manual_tokens = norm
            self._manual_index = 0
        except Exception:
            self._manual_tokens = []
            self._manual_index = 0
            self._manual_raw_tokens = []

    def _consume_manual_token(self, is_write: bool):
        """Consume next manual token and perform a single access (read or write).

        Returns the info dict from the simulator step or None.
        """
        try:
            if not hasattr(self, 'cache') or self.cache is None:
                self.apply_associativity()
            if not hasattr(self, '_manual_tokens') or not self._manual_tokens:
                self._prepare_manual_tokens()
            if not getattr(self, '_manual_tokens', None):
                self._append_log('No manual input tokens available')
                return None
            if self._manual_index >= len(self._manual_tokens):
                self._append_log('No more manual tokens')
                return None
            addr = self._manual_tokens[self._manual_index]
            self._manual_index += 1

            # Use wrapper's simulator for consistency
            sim = None
            if hasattr(self.cache, 'sim') and getattr(self.cache, 'sim') is not None:
                sim = self.cache.sim
            elif hasattr(self.cache_wrapper, 'sim') and getattr(self.cache_wrapper, 'sim') is not None:
                sim = self.cache_wrapper.sim
            if sim is None:
                self._append_log('No simulator available for manual access')
                return None

            sim.load_sequence([addr], writes=[is_write])
            info = sim.step()
            if info:
                action = 'W' if info.get('is_write') else 'R'
                self._append_log(f"Manual {action} Addr {info.get('address')}: {'HIT' if info.get('hit') else 'MISS'}")
                self._update_stats_widgets(info.get('stats', {}))
                try:
                    self.update_cache_display(info)
                except Exception:
                    pass
                # update hit-rate history and redraw small chart (same logic as animation step)
                try:
                    hr = info.get('stats', {}).get('hit_rate', None)
                    if hr is None:
                        s = info.get('stats', {})
                        accesses = s.get('accesses', 0)
                        hits = s.get('hits', 0)
                        hr = (hits / accesses) if accesses else 0.0
                    self.hit_rate_history.append(hr)
                    if len(self.hit_rate_history) > 200:
                        self.hit_rate_history = self.hit_rate_history[-200:]
                    try:
                        self._draw_hit_chart()
                    except Exception:
                        pass
                except Exception:
                    pass
            # update the input box to remove the consumed raw token
            try:
                remaining = self._manual_raw_tokens[self._manual_index:]
                self.input.set(','.join(remaining))
                # refresh decode preview
                try:
                    self.update_decode_panel()
                except Exception:
                    pass
            except Exception:
                pass
            return info
        except Exception as e:
            self._append_log(f"Error performing manual access: {e}")
            return None

    def read_next(self):
        try:
            self._consume_manual_token(is_write=False)
        except Exception:
            pass

    def write_next(self):
        try:
            self._consume_manual_token(is_write=True)
        except Exception:
            pass

def run_ui():
    ui = UserInterface()
    ui.start()


if __name__ == '__main__':
    run_ui()
