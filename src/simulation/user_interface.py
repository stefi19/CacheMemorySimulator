"""The run entrypoint (`run.py`) will import the UI from
`src.simulation.user_interface`.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from src.simulation import Simulation
from src.wrappers.k_associative_cache import K_associative_cache
from src.data.stats_export import export_chart_json as se_export_chart_json, export_chart_pdf_from_canvas as se_export_chart_pdf_from_canvas
from src.core.ram import RAM
import math
import json
import io
import os
import tempfile
import time
from tkinter import filedialog

# wires the widgets to the cache wrappers.

# Reasonable UI limits so users don't enter absurd numbers
MAX_CACHE_SIZE = 64
MAX_LINE_SIZE = 1024
MAX_ADDRESS_WIDTH = 32
MAX_INPUT_TOKENS = 64
MIN_ANIM_SPEED = 1
MAX_ANIM_SPEED = 5000

# Hardcoded scenario sequences (users cannot edit these sequences).
# Each scenario maps to a list of (address, is_write) tuples. These are
# intentionally fixed so 'Run Simulation' will only run these predefined
# scenarios. Manual input is handled by Read/Write buttons below.
PREDEFINED_SCENARIOS = {
    # increase matrix traversal to a 10x10 matrix (~100 addresses) per user request
    'Matrix Traversal': [(i * 10 + j, False) for i in range(10) for j in range(10)],
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
        # show verbose decode debug messages in the eviction/log pane
        # small status string showing applied/clamped values after Apply
        self.effective_info = tk.StringVar(value='')
        self.write_hit_policy = tk.StringVar(value="write-back")
        self.write_miss_policy = tk.StringVar(value="write-allocate")
        self.replacement_policy = tk.StringVar(value="LRU")
        self.instuction = tk.StringVar(value="LOAD")
        # visible cache type (mirrored from algorithm buttons)
        self.cache_type = tk.StringVar(value="Direct-Mapped")
        # live labels for internal counts (displayed under Cache title)
        self.num_blocks_var = tk.StringVar(value='-')
        self.num_sets_var = tk.StringVar(value='-')
        self.capacity = tk.IntVar(value=4)
        self.input = tk.StringVar(value="1,2,3")
        self.scenario_var = tk.StringVar(value='Matrix Traversal')
        # Animation and run controls
        self.num_passes = tk.IntVar(value=3)
        # Fixed animation speed: 1000 ms (1 second) — user control removed
        self.anim_speed = tk.IntVar(value=1000)  # milliseconds per step (fixed)
        self.anim_cap = tk.IntVar(value=256)
        # RAM configuration (default to 64 bytes / lines window)
        self.ram_size = tk.IntVar(value=64)
        self.ram_obj = None
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
        # recent RAM accesses for temporary highlighting: list of (base_addr, is_write, expiry_ts)
        self._recent_ram_accesses = []
        # last computed mapping from cache frames to RAM base addresses
        self._last_mapped_ram_bases = set()
        # mapping label_index -> ram base address for animation
        self._last_label_to_ram_base = {}
        # ram canvas cell bounding boxes: base_addr -> (x1,y1,x2,y2)
        self._ram_cell_bboxes = {}
        # last appended log line (used to prevent immediate duplicate debug lines)
        self._last_log_line = None
        # last debug message (separate from general last log) to avoid Text-wrapping artifacts
        self._last_debug_msg = None
        # resize debounce state
        self._resize_after_id = None
        self._last_window_size = (0, 0)

        # build UI
        self.setup_ui()

        # Ensure RAM backing store exists and draw initial RAM view so the
        # RAM panel isn't empty on first Run/start.
        try:
            self._ensure_ram_object()
            try:
                self.update_ram_display()
            except Exception:
                pass
        except Exception:
            pass

        # Watch parameter changes to re-validate and re-enable controls when fixed
        try:
            try:
                self.cache_size.trace_add('write', lambda *a: self._on_params_changed())
                self.line_size.trace_add('write', lambda *a: self._on_params_changed())
                self.associativity.trace_add('write', lambda *a: self._on_params_changed())
                # update backend when write policy changes in the UI
                try:
                    self.write_hit_policy.trace_add('write', lambda *a: self._on_write_policy_changed())
                except Exception:
                    pass
                try:
                    self.ram_size.trace_add('write', lambda *a: self._on_ram_changed())
                except Exception:
                    pass
            except Exception:
                try:
                    self.cache_size.trace('w', lambda *a: self._on_params_changed())
                    self.line_size.trace('w', lambda *a: self._on_params_changed())
                    self.associativity.trace('w', lambda *a: self._on_params_changed())
                    try:
                        self.write_hit_policy.trace('w', lambda *a: self._on_write_policy_changed())
                    except Exception:
                        pass
                    try:
                        self.ram_size.trace('w', lambda *a: self._on_ram_changed())
                    except Exception:
                        pass
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
        self.cache_size_spinbox = tk.Spinbox(self.configuration_container, from_=1, to=64, textvariable=self.cache_size, width=8)
        self.cache_size_spinbox.grid(row=row_counter, column=1, sticky=tk.W)
        row_counter += 1

        ttk.Label(self.configuration_container, text="Line size:", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        self.line_size_spinbox = tk.Spinbox(self.configuration_container, from_=1, to=64, textvariable=self.line_size, width=8)
        self.line_size_spinbox.grid(row=row_counter, column=1, sticky=tk.W)
        row_counter += 1

        # RAM size
        ttk.Label(self.configuration_container, text="RAM size (bytes):", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        # limit RAM size input to a maximum of 64 bytes in the UI per request
        self.ram_spinbox = tk.Spinbox(self.configuration_container, from_=1, to=64, textvariable=self.ram_size, width=10)
        self.ram_spinbox.grid(row=row_counter, column=1, sticky=tk.W)
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

        # Write policy (hit) dropdown: allow user to choose write-back or write-through
        try:
            ttk.Label(self.configuration_container, text="Write policy:", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
            wp_menu = ttk.OptionMenu(self.configuration_container, self.write_hit_policy, self.write_hit_policy.get(), 'write-back', 'write-through')
            wp_menu.config(width=option_menu_width)
            wp_menu.grid(row=row_counter, column=1, sticky='w')
        except Exception:
            pass
        row_counter += 1

        # Input
        ttk.Label(self.configuration_container, text="Input:", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        inp_entry = tk.Entry(self.configuration_container, textvariable=self.input, width=entry_width)
        inp_entry.grid(row=row_counter, column=1)
        # keep a reference to the Entry so we can rebind events when needed
        self.input_entry = inp_entry
        # Write-values input: comma-separated values used for manual Write operations
        row_counter += 1
        try:
            ttk.Label(self.configuration_container, text="Write values:", font=(self.font_container, 11), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
            self.write_values = tk.StringVar(value="1,2,3")
            self.write_values_entry = tk.Entry(self.configuration_container, textvariable=self.write_values, width=entry_width)
            self.write_values_entry.grid(row=row_counter, column=1)
        except Exception:
            self.write_values = tk.StringVar(value="")
            self.write_values_entry = None
        # install bindings so decode panel updates when the user types
        try:
            self._ensure_input_bindings()
        except Exception:
            # fallback: attempt minimal bindings inline
            try:
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
        # Active Replacement Policy label (shows which replacement is currently selected)
        ttk.Label(self.configuration_container, text="Active Replacement Policy:", font=(self.font_container, 10), foreground=self.font_color_1, background=self.background_container).grid(row=row_counter, column=0, sticky=tk.W, pady=3)
        # create a label that we update via update_replacement_controls()
        self.rep_policy_label = ttk.Label(self.configuration_container, text=self.replacement_policy.get(), font=(self.font_container, 10), foreground='#8BC34A', background=self.background_container)
        self.rep_policy_label.grid(row=row_counter, column=1, sticky=tk.W, pady=3)
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

        # Cache display area (scrollable vertical list)
        self.cache_display_frame = ttk.Frame(container_right, padding="8")
        self.cache_display_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        self.cache_display_frame.configure(style="InputFrame.TFrame")
        # inside cache_display_frame we host a Canvas+Frame to allow vertical scrolling
        try:
            self.cache_canvas = tk.Canvas(self.cache_display_frame, height=240, bg='#0b0b0b', highlightthickness=0)
            self.cache_vscroll = ttk.Scrollbar(self.cache_display_frame, orient='vertical', command=self.cache_canvas.yview)
            self.cache_canvas.configure(yscrollcommand=self.cache_vscroll.set)
            self.cache_canvas.grid(row=0, column=0, sticky='nsew')
            self.cache_vscroll.grid(row=0, column=1, sticky='ns')
            # inner frame that will contain per-line widgets
            self.cache_list_inner = ttk.Frame(self.cache_canvas)
            self.cache_inner_id = self.cache_canvas.create_window((0, 0), window=self.cache_list_inner, anchor='nw')
            # configure resize binding so scrollregion updates
            def _on_cache_inner_config(event):
                try:
                    self.cache_canvas.configure(scrollregion=self.cache_canvas.bbox('all'))
                except Exception:
                    pass
            self.cache_list_inner.bind('<Configure>', _on_cache_inner_config)
            # allow the inner frame to expand to canvas width on resize
            def _on_cache_canvas_config(event):
                try:
                    self.cache_canvas.itemconfig(self.cache_inner_id, width=event.width)
                except Exception:
                    pass
            self.cache_canvas.bind('<Configure>', _on_cache_canvas_config)

            # mouse wheel scrolling when pointer is over the cache list
            def _on_cache_mousewheel(event):
                try:
                    # event.delta works on Windows/macOS (multiples of 120)
                    delta = 0
                    if hasattr(event, 'delta'):
                        delta = int(-1 * (event.delta / 120))
                    else:
                        # fallback for X11 Button-4/5 handled elsewhere
                        delta = 0
                    if delta:
                        self.cache_canvas.yview_scroll(delta, 'units')
                except Exception:
                    pass

            # bind enter/leave to capture wheel events
            try:
                self.cache_list_inner.bind('<Enter>', lambda e: self.cache_canvas.bind_all('<MouseWheel>', _on_cache_mousewheel))
                self.cache_list_inner.bind('<Leave>', lambda e: self.cache_canvas.unbind_all('<MouseWheel>'))
                # also support Linux wheel events
                self.cache_list_inner.bind('<Button-4>', lambda e: self.cache_canvas.yview_scroll(-1, 'units'))
                self.cache_list_inner.bind('<Button-5>', lambda e: self.cache_canvas.yview_scroll(1, 'units'))
            except Exception:
                pass
        except Exception:
            self.cache_canvas = None
            self.cache_vscroll = None
            self.cache_list_inner = None

        # small status row showing num_blocks / num_sets for quick debugging
        try:
            info_frame = ttk.Frame(container_right)
            info_frame.grid(row=2, column=0, sticky='ne', pady=(0, 8), padx=(0, 8))
            ttk.Label(info_frame, text='blocks:', font=(self.font_container, 9), foreground='#AAAAAA', background=self.background_container).grid(row=0, column=0, sticky='e')
            ttk.Label(info_frame, textvariable=self.num_blocks_var, font=(self.font_container, 9, 'bold'), foreground='#8BC34A', background=self.background_container).grid(row=0, column=1, sticky='w', padx=(4, 12))
            ttk.Label(info_frame, text='sets:', font=(self.font_container, 9), foreground='#AAAAAA', background=self.background_container).grid(row=0, column=2, sticky='e')
            ttk.Label(info_frame, textvariable=self.num_sets_var, font=(self.font_container, 9, 'bold'), foreground='#8BC34A', background=self.background_container).grid(row=0, column=3, sticky='w', padx=(4, 0))
        except Exception:
            pass

        # create frame labels based on number of blocks = cache_size // line_size
        try:
            raw_cache_size = max(1, int(self.cache_size.get()))
            line_size = max(1, int(self.line_size.get()))
            num_blocks = max(1, raw_cache_size // line_size)
        except Exception:
            num_blocks = max(1, int(self.capacity.get()))
        self.create_frame_labels(num_blocks)
        try:
            self.update_replacement_controls()
        except Exception:
            pass
        try:
            self.update_rep_set_choices()
            self.update_replacement_panel()
        except Exception:
            pass

        # RAM display panel (visualizes a small window into the backing store)
        try:
            self.ram_frame = ttk.LabelFrame(container_right, text="RAM (backing store)", padding=6)
            self.ram_frame.grid(row=5, column=0, sticky='nsew', pady=(8, 8))
            # Create a scrollable canvas + inner frame to host per-line RAM widgets
            self.ram_canvas = tk.Canvas(self.ram_frame, height=180, bg='#0b0b0b', highlightthickness=0)
            self.ram_vscroll = ttk.Scrollbar(self.ram_frame, orient='vertical', command=self.ram_canvas.yview)
            try:
                self.ram_canvas.configure(yscrollcommand=self.ram_vscroll.set)
            except Exception:
                pass
            self.ram_canvas.grid(row=0, column=0, sticky='nsew')
            self.ram_vscroll.grid(row=0, column=1, sticky='ns')
            # inner frame
            self.ram_list_inner = ttk.Frame(self.ram_canvas)
            self.ram_inner_id = self.ram_canvas.create_window((0, 0), window=self.ram_list_inner, anchor='nw')
            def _on_ram_inner_config(ev):
                try:
                    self.ram_canvas.configure(scrollregion=self.ram_canvas.bbox('all'))
                except Exception:
                    pass
            self.ram_list_inner.bind('<Configure>', _on_ram_inner_config)
            def _on_ram_canvas_config(ev):
                try:
                    self.ram_canvas.itemconfig(self.ram_inner_id, width=ev.width)
                except Exception:
                    pass
            self.ram_canvas.bind('<Configure>', _on_ram_canvas_config)
            # mouse wheel support
            try:
                self.ram_list_inner.bind('<Enter>', lambda e: self.ram_canvas.bind_all('<MouseWheel>', lambda ev: self.ram_canvas.yview_scroll(int(-1*(ev.delta/120)), 'units')))
                self.ram_list_inner.bind('<Leave>', lambda e: self.ram_canvas.unbind_all('<MouseWheel>'))
            except Exception:
                try:
                    self.ram_list_inner.bind('<Button-4>', lambda e: self.ram_canvas.yview_scroll(-1, 'units'))
                    self.ram_list_inner.bind('<Button-5>', lambda e: self.ram_canvas.yview_scroll(1, 'units'))
                except Exception:
                    pass
            # container for entries
            self.ram_line_entries = []
            self._ram_base_to_index = {}
        except Exception:
            self.ram_frame = None
            self.ram_canvas = None

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
        # Last-read value box: shows the value retrieved on the most recent read
        try:
            self.last_read_value = tk.StringVar(value='-')
            ttk.Label(stats_frame, text="Last read:", foreground=self.font_color_1, background=self.background_container, font=(self.font_container, 10)).grid(row=0, column=5, sticky='e', padx=(12, 4))
            self.last_read_value_label = tk.Label(stats_frame, textvariable=self.last_read_value, foreground='#FFFFFF', background='#111111', font=(self.font_container, 10, 'bold'), width=12)
            self.last_read_value_label.grid(row=0, column=6, sticky='w')
        except Exception:
            self.last_read_value = None
        # export buttons for chart: JSON (data) and PS/PDF (graphic)
        try:
            exp_frame = ttk.Frame(stats_frame)
            exp_frame.grid(row=2, column=4, padx=(16,0), pady=(6,0))
            self.export_json_btn = ttk.Button(exp_frame, text='Export JSON', command=self.export_chart_json)
            self.export_json_btn.grid(row=0, column=0, padx=2)
            self.export_pdf_btn = ttk.Button(exp_frame, text='Export PDF', command=self.export_chart_pdf)
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
                # update core replacement policy objects in-place so the
                # running cache/simulator adopts the new policy immediately
                if hasattr(core, 'set_replacement'):
                    try:
                        core.set_replacement(name)
                    except Exception:
                        try:
                            core._replacement_name = name
                        except Exception:
                            pass
                else:
                    try:
                        core._replacement_name = name
                    except Exception:
                        pass
                # Log the active replacement types per-set for debugging so the
                # user can confirm the UI change had effect (appears in Eviction log).
                try:
                    types = [type(p).__name__ for p in getattr(core, 'replacement_policy_objs', [])]
                    self._append_log(f'Replacement changed to {name}: per-set types = {types}')
                except Exception:
                    pass
                # refresh cache display so any visual indicators update
                try:
                    self.update_cache_display({})
                except Exception:
                    pass
            except Exception:
                pass
        # Update the small replacement-policy label in the UI
        try:
            self.update_replacement_controls()
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
                    self.scenario_code.insert('end', 'Matrix Traversal (predefined): sequential accesses over a 10x10 matrix\n\n')
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
            # Expect a plain address token (decimal) or hex with 0x prefix
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
            # capacity is number of blocks (cache_size // line_size)
            # allow a larger number now that the list is scrollable
            capacity = int(max(1, capacity))
            capacity = min(capacity, 256)
            # update live status labels showing number of blocks and sets
            try:
                self.num_blocks_var.set(str(int(capacity)))
                assoc = max(1, int(self.associativity.get()))
                sets = max(1, int(capacity) // assoc)
                self.num_sets_var.set(str(int(sets)))
            except Exception:
                try:
                    self.num_blocks_var.set('-')
                    self.num_sets_var.set('-')
                except Exception:
                    pass
            # Clear previous
            # destroy old widgets
            for entry in getattr(self, 'frame_labels', []):
                try:
                    # entry may be a dict with 'frame'
                    frm = entry.get('frame') if isinstance(entry, dict) else entry
                    if hasattr(frm, 'destroy'):
                        frm.destroy()
                except Exception:
                    pass
            self.frame_labels = []

            # create vertical list of frames inside the scrollable inner frame
            parent = getattr(self, 'cache_list_inner', None) or self.cache_display_frame
            try:
                line_size = max(1, int(self.line_size.get()))
            except Exception:
                line_size = 1
            for i in range(capacity):
                try:
                    line_frame = ttk.Frame(parent, padding=(2, 2))
                    line_frame.grid(row=i, column=0, sticky='ew', pady=2)
                    # index / dirty indicator on the left
                    idx_lbl = tk.Label(line_frame, text=f"#{i}", width=6, bg='#111111', fg='#FFFFFF', relief='ridge')
                    idx_lbl.pack(side='left', padx=(0, 6))
                    # byte container shows each byte/word in the line
                    bytes_frame = ttk.Frame(line_frame)
                    bytes_frame.pack(side='left', fill='x', expand=True)
                    byte_labels = []
                    for b in range(line_size):
                        bl = tk.Label(bytes_frame, text='--', width=6, bg='#222222', fg='#DDDDDD', relief='groove')
                        bl.pack(side='left', padx=2)
                        byte_labels.append(bl)
                    # dirty marker label to the right
                    dirt_lbl = tk.Label(line_frame, text='', width=2, bg='#111111', fg='#FFD54F')
                    dirt_lbl.pack(side='right', padx=(6, 0))
                    self.frame_labels.append({'frame': line_frame, 'index_label': idx_lbl, 'byte_labels': byte_labels, 'dirty_label': dirt_lbl})
                except Exception:
                    pass
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

            # clear RAM display and optionally reset RAM object
            try:
                if getattr(self, 'ram_canvas', None):
                    try:
                        self.ram_canvas.delete('all')
                    except Exception:
                        pass
                # When the canvas is cleared, also clear the cached widget list so
                # update_ram_display() will recreate row widgets and reflect the
                # reinitialized RAM contents visually.
                try:
                    self.ram_line_entries = []
                except Exception:
                    pass
                try:
                    self._ram_base_to_index = {}
                except Exception:
                    pass
                # If we deleted canvas contents above, recreate the inner window
                # so the inner frame is attached again and update_ram_display can
                # recreate row widgets normally.
                try:
                    if getattr(self, 'ram_canvas', None) and getattr(self, 'ram_list_inner', None):
                        try:
                            # create window and store id
                            self.ram_inner_id = self.ram_canvas.create_window((0, 0), window=self.ram_list_inner, anchor='nw')
                        except Exception:
                            pass
                        try:
                            def _on_ram_inner_config(ev):
                                try:
                                    self.ram_canvas.configure(scrollregion=self.ram_canvas.bbox('all'))
                                except Exception:
                                    pass
                            self.ram_list_inner.bind('<Configure>', _on_ram_inner_config)
                        except Exception:
                            pass
                        try:
                            def _on_ram_canvas_config(ev):
                                try:
                                    self.ram_canvas.itemconfig(self.ram_inner_id, width=ev.width)
                                except Exception:
                                    pass
                            self.ram_canvas.bind('<Configure>', _on_ram_canvas_config)
                        except Exception:
                            pass
                        try:
                            # mouse wheel support
                            self.ram_list_inner.bind('<Enter>', lambda e: self.ram_canvas.bind_all('<MouseWheel>', lambda ev: self.ram_canvas.yview_scroll(int(-1*(ev.delta/120)), 'units')))
                            self.ram_list_inner.bind('<Leave>', lambda e: self.ram_canvas.unbind_all('<MouseWheel>'))
                        except Exception:
                            try:
                                self.ram_list_inner.bind('<Button-4>', lambda e: self.ram_canvas.yview_scroll(-1, 'units'))
                                self.ram_list_inner.bind('<Button-5>', lambda e: self.ram_canvas.yview_scroll(1, 'units'))
                            except Exception:
                                pass
                except Exception:
                    pass
                # Reinitialize RAM contents so reset restores default sequential values
                try:
                    if getattr(self, 'ram_obj', None) is not None:
                        try:
                            self.ram_obj.reset()
                        except Exception:
                            # If reset fails, attempt to recreate the RAM object
                            try:
                                self._ensure_ram_object()
                            except Exception:
                                pass
                        # refresh the RAM display to show reinitialized values
                        try:
                            self.update_ram_display()
                        except Exception:
                            pass
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
            # ensure UI params validated before running
            if not self._ensure_valid_or_warn():
                return
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

            # Validate UI values before running. Do not silently clamp critical fields;
            # instead show an error and abort so the user can correct inputs.
            try:
                ok = self._clamp_ui_values()
                if ok is False:
                    # _clamp_ui_values already showed an error message; abort run
                    self._append_log('Run aborted due to invalid UI parameters')
                    return
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
            if not self._ensure_valid_or_warn():
                return
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
            # record RAM access (for highlighting) and refresh RAM display after this step
            try:
                if info and info.get('address') is not None:
                    try:
                        self._note_ram_access(info.get('address'), info.get('is_write'))
                    except Exception:
                        pass
                try:
                    self.update_ram_display()
                except Exception:
                    pass
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
            # record RAM access for UI highlighting and refresh RAM view
            try:
                if addr is not None:
                    try:
                        self._note_ram_access(addr, info.get('is_write'))
                    except Exception:
                        pass
                    try:
                        self.update_ram_display()
                    except Exception:
                        pass
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
            # Update the small "last read" display when this access was a read.
            try:
                if info and not info.get('is_write', False):
                    self._display_last_read(info)
                else:
                    # clear on writes or absent info
                    try:
                        if getattr(self, 'last_read_value', None) is not None:
                            self.last_read_value.set('-')
                    except Exception:
                        pass
            except Exception:
                pass

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

            # Clear all labels to neutral (reset index label and byte labels)
            for entry in getattr(self, 'frame_labels', []):
                try:
                    if isinstance(entry, dict):
                        idx_lbl = entry.get('index_label')
                        if idx_lbl is not None:
                            idx_lbl.configure(bg='#111111')
                        for bl in entry.get('byte_labels', []):
                            try:
                                bl.configure(text='--', bg='#222222', fg='#DDDDDD')
                            except Exception:
                                pass
                        dirt_lbl = entry.get('dirty_label')
                        if dirt_lbl is not None:
                            try:
                                dirt_lbl.configure(text='')
                            except Exception:
                                pass
                    else:
                        try:
                            entry.configure(bg='#111111')
                        except Exception:
                            pass
                except Exception:
                    pass

            # reset mapping cache (will be filled below if we can compute mapping)
            mapped_bases = set()

            # Prefer wrapper cache_contents if present (direct mapped wrapper)
            if hasattr(wrapper, 'cache_contents') and getattr(wrapper, 'cache_contents'):
                for i, line in enumerate(wrapper.cache_contents):
                    valid = line[1] == '1'
                    tag = line[2]
                    entry = self.frame_labels[i] if i < len(self.frame_labels) else None
                    if entry:
                        try:
                            idx_lbl = entry.get('index_label')
                            b_labels = entry.get('byte_labels', [])
                            dirt_lbl = entry.get('dirty_label')
                            if valid:
                                idx_lbl.configure(bg='#444444')
                            else:
                                idx_lbl.configure(bg='#222222')
                            # populate bytes from RAM if tag present
                            try:
                                if valid and tag is not None:
                                    try:
                                        tag_int = int(tag, 0)
                                    except Exception:
                                        try:
                                            tag_int = int(tag)
                                        except Exception:
                                            tag_int = None
                                    if tag_int is not None:
                                        nb = getattr(wrapper, 'num_blocks', None) or getattr(wrapper, 'cache', None) and getattr(wrapper.cache, 'num_blocks', None)
                                        try:
                                            line_size = getattr(wrapper, 'cache', None) and getattr(wrapper.cache, 'line_size', None) or max(1, int(self.line_size.get()))
                                        except Exception:
                                            line_size = max(1, int(self.line_size.get()))
                                        if nb:
                                            block_addr = tag_int * nb + i
                                            base = block_addr * line_size
                                            ram = getattr(self, 'ram_obj', None)
                                            for off in range(len(b_labels)):
                                                try:
                                                    val = ram.read(base + off) if ram is not None else None
                                                    text = f"{val:#02x}" if val is not None else '--'
                                                    b_labels[off].configure(text=text, bg='#333333', fg='#FFFFFF')
                                                except Exception:
                                                    b_labels[off].configure(text='--', bg='#222222', fg='#DDDDDD')
                            except Exception:
                                for bl in b_labels:
                                    try:
                                        bl.configure(text='--', bg='#222222', fg='#DDDDDD')
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                # highlight the specific accessed line if available in info
                set_idx = info.get('set_index')
                way_idx = info.get('way_index')
                try:
                    idx = int(set_idx) if set_idx is not None else None
                    if idx is not None and idx < len(self.frame_labels):
                        entry = self.frame_labels[idx]
                        is_hit = bool(info.get('hit'))
                        color = '#8BC34A' if is_hit else '#F44336'
                        try:
                            # color the index label to indicate hit/miss
                            idx_lbl = entry.get('index_label') if isinstance(entry, dict) else entry
                            idx_lbl.configure(bg=color)
                            # auto-scroll to this label so it's visible
                            try:
                                self._scroll_cache_to_label(idx)
                            except Exception:
                                pass
                        except Exception:
                            pass
                        # only color RAM when this access caused an actual memory read/write
                        try:
                            if info and (info.get('mem_read') or info.get('mem_write')):
                                base = getattr(self, '_last_label_to_ram_base', {}).get(idx)
                                if base is not None:
                                    try:
                                                self._note_ram_access_color(base, color)
                                                try:
                                                    # also auto-scroll RAM to the base
                                                    self._scroll_ram_to_base(base)
                                                except Exception:
                                                    pass
                                                self.update_ram_display()
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                except Exception:
                    pass
                # try to compute mapping into RAM if we can
                try:
                    # number of sets/blocks and line size
                    nb = getattr(wrapper, 'num_blocks', None)
                    if nb is None and hasattr(wrapper, 'cache'):
                        nb = getattr(wrapper.cache, 'num_blocks', None)
                    line_size = None
                    if hasattr(wrapper, 'cache'):
                        line_size = getattr(wrapper.cache, 'line_size', None)
                    if line_size is None:
                        try:
                            line_size = max(1, int(self.line_size.get()))
                        except Exception:
                            line_size = 1
                    # each entry in cache_contents: index -> tag
                    for i, line in enumerate(wrapper.cache_contents):
                        try:
                            if line[1] == '1':
                                t = line[2]
                                try:
                                    tag_int = int(t, 0)
                                except Exception:
                                    try:
                                        tag_int = int(t)
                                    except Exception:
                                        tag_int = None
                                if tag_int is not None and nb:
                                    block_addr = tag_int * nb + i
                                    base = block_addr * line_size
                                    mapped_bases.add(base)
                                    # record which cache label maps to this RAM base
                                    try:
                                        self._last_label_to_ram_base[i] = base
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                except Exception:
                    pass
                # store mapping and refresh RAM view
                try:
                    self._last_mapped_ram_bases = mapped_bases
                    try:
                        self.update_ram_display()
                    except Exception:
                        pass
                except Exception:
                    pass
                # Animate RAM->cache load for a miss (core cache branch)
                try:
                    if info and (not info.get('hit', True)) and info.get('address') is not None:
                        addr = int(info.get('address'))
                        try:
                            line_size = getattr(core, 'line_size', None) or max(1, int(self.line_size.get()))
                        except Exception:
                            line_size = max(1, int(self.line_size.get()))
                        base = (addr // line_size) * line_size
                        tgt_idx = None
                        try:
                            sidx = info.get('set_index')
                            widx = info.get('way_index')
                            if sidx is not None and widx is not None:
                                try:
                                    sidx = int(sidx); widx = int(widx)
                                    tgt_idx = sidx * ways + widx
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        if tgt_idx is None:
                            try:
                                for k, b in getattr(self, '_last_label_to_ram_base', {}).items():
                                    if b == base:
                                        tgt_idx = k
                                        break
                            except Exception:
                                pass
                        try:
                            if tgt_idx is not None:
                                self._animate_ram_to_cache(base, tgt_idx)
                        except Exception:
                            pass
                except Exception:
                    pass
                # Animate RAM->cache load for a miss (if address present and miss)
                try:
                    if info and (not info.get('hit', True)) and info.get('address') is not None:
                        addr = int(info.get('address'))
                        try:
                            line_size = max(1, int(getattr(wrapper.cache, 'line_size', self.line_size.get())))
                        except Exception:
                            line_size = max(1, int(self.line_size.get()))
                        base = (addr // line_size) * line_size
                        # find target label index (prefer set_index/way_index if provided)
                        tgt_idx = None
                        try:
                            sidx = info.get('set_index')
                            widx = info.get('way_index')
                            if sidx is not None and widx is not None:
                                try:
                                    sidx = int(sidx); widx = int(widx)
                                    tgt_idx = sidx if tgt_idx is None else tgt_idx
                                    # for direct mapped wrapper, set_index often equals label index
                                    tgt_idx = int(sidx)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        # fallback: try to find any label mapping to this base
                        if tgt_idx is None:
                            try:
                                for k, b in getattr(self, '_last_label_to_ram_base', {}).items():
                                    if b == base:
                                        tgt_idx = k
                                        break
                            except Exception:
                                pass
                        try:
                            if tgt_idx is not None:
                                self._animate_ram_to_cache(base, tgt_idx)
                        except Exception:
                            pass
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
                        # base appearance for valid/invalid and update byte labels
                        entry = self.frame_labels[k] if k < len(self.frame_labels) else None
                        if entry:
                            try:
                                idx_lbl = entry.get('index_label')
                                b_labels = entry.get('byte_labels', [])
                                dirt_lbl = entry.get('dirty_label')
                                if getattr(block, 'valid', False):
                                    idx_lbl.configure(bg='#444444')
                                else:
                                    idx_lbl.configure(bg='#222222')
                                # populate byte labels from RAM if available
                                try:
                                    line_size = getattr(core, 'line_size', None) or max(1, int(self.line_size.get()))
                                except Exception:
                                    line_size = max(1, int(self.line_size.get()))
                                num_sets = getattr(core, 'num_sets', None) or 1
                                try:
                                    tag = int(getattr(block, 'tag'))
                                except Exception:
                                    tag = None
                                if getattr(block, 'valid', False) and tag is not None:
                                    block_addr = tag * num_sets + s
                                    base = block_addr * line_size
                                    # Prefer per-byte values stored in cache block (so writes
                                    # to dirty blocks are visible). Fall back to RAM when
                                    # block.data is not present.
                                    try:
                                        if getattr(block, 'data', None) is not None:
                                            for off in range(line_size):
                                                try:
                                                    val = block.data[off] if off < len(block.data) else None
                                                except Exception:
                                                    val = None
                                                text = f"{val:#02x}" if val is not None else '--'
                                                if off < len(b_labels):
                                                    b_labels[off].configure(text=text, bg='#333333', fg='#FFFFFF')
                                        else:
                                            ram = getattr(self, 'ram_obj', None)
                                            for off in range(line_size):
                                                val = ram.read(base + off) if ram is not None else None
                                                text = f"{val:#02x}" if val is not None else '--'
                                                if off < len(b_labels):
                                                    b_labels[off].configure(text=text, bg='#333333', fg='#FFFFFF')
                                    except Exception:
                                        for off in range(len(b_labels)):
                                            b_labels[off].configure(text='--', bg='#222222', fg='#DDDDDD')
                                else:
                                    for bl in b_labels:
                                        try:
                                            bl.configure(text='--', bg='#222222', fg='#DDDDDD')
                                        except Exception:
                                            pass
                                # dirty indicator
                                try:
                                    if getattr(block, 'dirty', False) and getattr(core, 'write_policy', '') == 'write-back':
                                        dirt_lbl.configure(text='D')
                                    else:
                                        dirt_lbl.configure(text='')
                                except Exception:
                                    pass
                            except Exception:
                                pass
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
                            entry = self.frame_labels[label_index]
                            is_hit = bool(info.get('hit'))
                            color = '#8BC34A' if is_hit else '#F44336'
                            try:
                                idx_lbl = entry.get('index_label') if isinstance(entry, dict) else entry
                                idx_lbl.configure(bg=color)
                                try:
                                    self._scroll_cache_to_label(label_index)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                            # ensure dirty indicator remains visible if present
                            try:
                                block = sets[sidx][widx]
                                dirt_lbl = entry.get('dirty_label') if isinstance(entry, dict) else None
                                if getattr(block, 'dirty', False) and getattr(core, 'write_policy', '') == 'write-back':
                                    try:
                                        if dirt_lbl is not None:
                                            dirt_lbl.configure(text='D')
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            # sync RAM highlight for mapped base if available
                            try:
                                # only color RAM when this access actually touched memory
                                if info and (info.get('mem_read') or info.get('mem_write')):
                                    base = getattr(self, '_last_label_to_ram_base', {}).get(label_index)
                                    if base is not None:
                                        try:
                                            self._note_ram_access_color(base, color)
                                            self.update_ram_display()
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                except Exception:
                    pass
                # compute mapping from cache blocks to RAM base addresses
                try:
                    mapped_bases = set()
                    line_size = getattr(core, 'line_size', None) or max(1, int(self.line_size.get()))
                    num_sets = getattr(core, 'num_sets', None) or 1
                    for s in range(rows):
                        for w in range(ways):
                            try:
                                block = sets[s][w]
                                if getattr(block, 'valid', False) and getattr(block, 'tag', None) is not None:
                                    tag = int(block.tag)
                                    block_addr = tag * num_sets + s
                                    base = block_addr * line_size
                                    mapped_bases.add(base)
                                    # map label index (row-major) to ram base for animation
                                    try:
                                        label_index = s * ways + w
                                        self._last_label_to_ram_base[label_index] = base
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                except Exception:
                    mapped_bases = set()
                try:
                    self._last_mapped_ram_bases = mapped_bases
                    try:
                        self.update_ram_display()
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

    def _scroll_cache_to_label(self, index: int):
        """Scroll the cache canvas so the given index is centered (if possible)."""
        try:
            if not getattr(self, 'cache_canvas', None) or not getattr(self, 'cache_list_inner', None):
                return
            if index is None or index < 0 or index >= len(getattr(self, 'frame_labels', [])):
                return
            entry = self.frame_labels[index]
            widget = entry.get('frame') if isinstance(entry, dict) else entry
            # ensure sizes are up-to-date
            self.cache_canvas.update_idletasks()
            widget.update_idletasks()
            inner_h = self.cache_list_inner.winfo_height() or 1
            canvas_h = self.cache_canvas.winfo_height() or 1
            y = widget.winfo_y()
            h = widget.winfo_height() or 1
            # target scroll so the widget center aligns with canvas center
            target = y + h / 2 - canvas_h / 2
            max_scroll = max(1, inner_h - canvas_h)
            frac = target / max_scroll if max_scroll > 0 else 0.0
            if frac < 0.0:
                frac = 0.0
            if frac > 1.0:
                frac = 1.0
            try:
                self.cache_canvas.yview_moveto(frac)
            except Exception:
                try:
                    self.cache_canvas.yview_scroll(int(frac * 10), 'units')
                except Exception:
                    pass
        except Exception:
            pass

    def _scroll_ram_to_base(self, base: int):
        """Scroll the RAM canvas so the given base address row is visible/centered."""
        try:
            if not getattr(self, 'ram_canvas', None) or not getattr(self, 'ram_list_inner', None):
                return
            idx = self._ram_base_to_index.get(base)
            if idx is None:
                return
            entry = self.ram_line_entries[idx]
            widget = entry.get('frame')
            self.ram_canvas.update_idletasks()
            widget.update_idletasks()
            inner_h = self.ram_list_inner.winfo_height() or 1
            canvas_h = self.ram_canvas.winfo_height() or 1
            y = widget.winfo_y()
            h = widget.winfo_height() or 1
            target = y + h / 2 - canvas_h / 2
            max_scroll = max(1, inner_h - canvas_h)
            frac = target / max_scroll if max_scroll > 0 else 0.0
            if frac < 0.0:
                frac = 0.0
            if frac > 1.0:
                frac = 1.0
            try:
                self.ram_canvas.yview_moveto(frac)
            except Exception:
                try:
                    self.ram_canvas.yview_scroll(int(frac * 10), 'units')
                except Exception:
                    pass
        except Exception:
            pass

    def update_ram_display(self):
        """Draw a compact view of the RAM backing store on the RAM canvas.

        We show a small window of consecutive line-base addresses (0..N-1)
        where each drawn cell shows the base address and the stored value
        (if any). The view is bounded to avoid drawing thousands of entries.
        """
        try:
            canvas = getattr(self, 'ram_canvas', None)
            ram = getattr(self, 'ram_obj', None)
            if canvas is None or ram is None:
                return
            # build list of lines to show
            try:
                line = max(1, int(getattr(ram, 'line_size', 1)))
            except Exception:
                line = 1
            try:
                total_lines = max(1, ram.size // line)
            except Exception:
                total_lines = 1
            MAX_LINES = 256
            show_lines = min(MAX_LINES, total_lines)

            # purge expired recent-access markers and build a map for fast lookup
            try:
                now = time.time()
                self._recent_ram_accesses = [(b, w, e) for (b, w, e) in getattr(self, '_recent_ram_accesses', []) if e > now]
            except Exception:
                pass
            recent_map = {}
            try:
                for (b, w, e) in getattr(self, '_recent_ram_accesses', []):
                    if b not in recent_map:
                        recent_map[b] = w
            except Exception:
                recent_map = {}

            # create widgets if not present or size changed
            try:
                if not getattr(self, 'ram_line_entries', None) or len(self.ram_line_entries) != show_lines:
                    # destroy existing
                    for ent in getattr(self, 'ram_line_entries', []) or []:
                        try:
                            frm = ent.get('frame')
                            if hasattr(frm, 'destroy'):
                                frm.destroy()
                        except Exception:
                            pass
                    self.ram_line_entries = []
                    self._ram_base_to_index = {}
                    for i in range(show_lines):
                        try:
                            base = i * line
                            row_frm = ttk.Frame(self.ram_list_inner, padding=(2, 2))
                            row_frm.grid(row=i, column=0, sticky='ew', pady=1)
                            # show the RAM line index (0-based) so numbering matches cache lines
                            addr_lbl = tk.Label(row_frm, text=f"#{i}", width=8, bg='#111111', fg='#CCCCCC', relief='ridge')
                            addr_lbl.pack(side='left', padx=(2, 8))
                            bytes_frame = ttk.Frame(row_frm)
                            bytes_frame.pack(side='left', fill='x', expand=True)
                            b_labels = []
                            for off in range(line):
                                bl = tk.Label(bytes_frame, text='--', width=6, bg='#222222', fg='#DDDDDD', relief='groove')
                                bl.pack(side='left', padx=2)
                                b_labels.append(bl)
                            marker_lbl = tk.Label(row_frm, text='', width=2, bg='#111111', fg='#FFFFFF')
                            marker_lbl.pack(side='right', padx=(8, 2))
                            ent = {'frame': row_frm, 'addr': base, 'addr_label': addr_lbl, 'byte_labels': b_labels, 'marker': marker_lbl}
                            self.ram_line_entries.append(ent)
                            self._ram_base_to_index[base] = i
                        except Exception:
                            pass
            except Exception:
                pass

            # populate values and highlight recent accesses
            try:
                for ent in self.ram_line_entries:
                    try:
                        base = ent.get('addr')
                        bytes_labels = ent.get('byte_labels', [])
                        marker = ent.get('marker')
                        is_recent = base in recent_map
                        # set background color
                        bg = '#111111'
                        txt_color = '#DDDDDD'
                        if is_recent:
                            m = recent_map.get(base)
                            if isinstance(m, str):
                                bg = m; txt_color = '#FFFFFF'
                            else:
                                bg = '#F44336' if bool(m) else '#2E7D32'; txt_color = '#FFFFFF'
                        try:
                            ent.get('addr_label').configure(bg=bg, fg=txt_color)
                        except Exception:
                            pass
                        # populate byte values
                        for off, bl in enumerate(bytes_labels):
                            try:
                                val = ram.read(base + off)
                                bl.configure(text=f"{val:#02x}", bg='#333333', fg='#FFFFFF')
                            except Exception:
                                try:
                                    bl.configure(text='--', bg='#222222', fg='#DDDDDD')
                                except Exception:
                                    pass
                        # show mapping outline if base is in last mapped bases
                        try:
                            if getattr(self, '_last_mapped_ram_bases', None) and base in self._last_mapped_ram_bases:
                                marker.configure(text='M')
                            else:
                                marker.configure(text='')
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass

            # update scrollbar (no-op: canvas.bind handlers keep scrollregion updated)
            try:
                self.ram_canvas.update_idletasks()
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
        # Build generic k-associative wrapper with k=1
        try:
            self._ensure_ram_object()
        except Exception:
            pass
        wrapper = K_associative_cache(self, associativity=1)
        wrapper.build()
        self.cache_wrapper = wrapper
        # also set self.cache for compatibility with other code
        self.cache = wrapper
        try:
            nb = getattr(self.cache, 'num_blocks', None) or (getattr(self.cache, 'cache').num_blocks if hasattr(self.cache, 'cache') else None)
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
        try:
            self._ensure_ram_object()
        except Exception:
            pass
        wrapper = K_associative_cache(self, associativity=2)
        wrapper.build()
        self.cache_wrapper = wrapper
        self.cache = wrapper
        try:
            nb = getattr(self.cache, 'num_blocks', None) or (getattr(self.cache, 'cache').num_blocks if hasattr(self.cache, 'cache') else None)
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
        try:
            self._ensure_ram_object()
        except Exception:
            pass
        wrapper = K_associative_cache(self, associativity=4)
        wrapper.build()
        self.cache_wrapper = wrapper
        self.cache = wrapper
        try:
            nb = getattr(self.cache, 'num_blocks', None) or (getattr(self.cache, 'cache').num_blocks if hasattr(self.cache, 'cache') else None)
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
        # Validate UI fields before building cache. Abort if invalid instead of
        # silently clamping so the user can correct the inputs.
        try:
            ok = self._clamp_ui_values()
            if ok is False:
                self._append_log('Apply aborted due to invalid UI parameters')
                return
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
            # ensure RAM backing store matches UI before building cache
            try:
                self._ensure_ram_object()
            except Exception:
                pass
            self.cache_type.set(f"{k}-Way Set" if k != 1 else 'Direct-Mapped')
            wrapper = K_associative_cache(self, associativity=k)
            wrapper.build()
            self.cache_wrapper = wrapper
            # also keep self.cache for compatibility
            self.cache = wrapper
            # create UI frame labels according to number of blocks
            try:
                # compute number of blocks explicitly from UI fields to avoid
                # accidental dependence on wrapper internals; associativity
                # should not change the number of cache frames.
                raw_cache_size = max(1, int(self.cache_size.get()))
                line_size = max(1, int(self.line_size.get()))
                nb = max(1, raw_cache_size // line_size)
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
            # For critical cache parameters (cache_size, line_size, associativity,
            # address_width) we prefer to reject invalid values and prompt the
            # user to fix them rather than silently clamping.
            try:
                cs = int(self.cache_size.get())
            except Exception:
                cs = 1
            if cs < 1:
                messagebox.showerror('Invalid parameter', 'Cache size must be >= 1')
                try:
                    self.cache_size_spinbox.focus_set()
                except Exception:
                    pass
                return False
            if cs > MAX_CACHE_SIZE:
                messagebox.showerror('Invalid parameter', f'Cache size must be <= {MAX_CACHE_SIZE}. Please change the value.')
                try:
                    self.cache_size_spinbox.focus_set()
                except Exception:
                    pass
                return False

            # line/block size
            try:
                bs = int(self.line_size.get())
            except Exception:
                bs = 1
            if bs < 1:
                messagebox.showerror('Invalid parameter', 'Line size must be >= 1')
                try:
                    self.line_size_spinbox.focus_set()
                except Exception:
                    pass
                return False
            if bs > MAX_LINE_SIZE:
                messagebox.showerror('Invalid parameter', f'Line size must be <= {MAX_LINE_SIZE}. Please change the value.')
                try:
                    self.line_size_spinbox.focus_set()
                except Exception:
                    pass
                return False

            # require cache_size to be multiple of line_size
            if cs % bs != 0:
                msg = f'Cache size ({cs}) is not an exact multiple of line size ({bs}). Please choose values where cache_size is a multiple of line_size.'
                try:
                    messagebox.showerror('Cache size / Line size mismatch', msg)
                except Exception:
                    pass
                try:
                    self.cache_size_spinbox.focus_set()
                except Exception:
                    pass
                return False

            # address width
            try:
                aw = int(self.address_width.get())
            except Exception:
                aw = 1
            if aw < 1:
                messagebox.showerror('Invalid parameter', 'Address width must be >= 1')
                try:
                    # if there is no direct widget, just log
                    self._append_log('Address width invalid')
                except Exception:
                    pass
                return False
            if aw > MAX_ADDRESS_WIDTH:
                messagebox.showerror('Invalid parameter', f'Address width must be <= {MAX_ADDRESS_WIDTH}. Please change the value.')
                try:
                    self._append_log('Address width too large')
                except Exception:
                    pass
                return False

            # anim speed clamp (non-critical) — clamp silently
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

            # associativity: ensure it is valid wrt number of blocks
            try:
                assoc = int(self.associativity.get())
            except Exception:
                assoc = 1
            if assoc < 1:
                messagebox.showerror('Invalid parameter', 'Associativity must be >= 1')
                try:
                    self.assoc_spinbox.focus_set()
                except Exception:
                    pass
                return False
            num_blocks = max(1, cs // bs)
            # also enforce maximum UI blocks here to prevent generating too many
            if num_blocks > 20:
                try:
                    messagebox.showerror('Too many blocks', f'Number of cache blocks ({num_blocks}) exceeds UI display limit (20). Please reduce cache_size or increase line_size.')
                except Exception:
                    pass
                try:
                    self.assoc_spinbox.focus_set()
                except Exception:
                    pass
                return False
            if assoc > num_blocks:
                messagebox.showerror('Invalid parameter', f'Associativity ({assoc}) exceeds number of blocks ({num_blocks}). Please reduce associativity or change cache/line size.')
                try:
                    self.assoc_spinbox.focus_set()
                except Exception:
                    pass
                return False
            if num_blocks % assoc != 0:
                messagebox.showerror('Invalid parameter', f'Associativity ({assoc}) does not divide the number of blocks ({num_blocks}). Please choose an associativity that evenly divides number of blocks.')
                try:
                    self.assoc_spinbox.focus_set()
                except Exception:
                    pass
                return False

            # everything critical validated
            return True
        except Exception:
            return False

    def _ensure_ram_object(self):
        """Create or update the RAM backing-store object from current UI fields."""
        try:
            # Clamp RAM size to UI maximum (64) to prevent large drawings / bad input
            size = max(1, int(self.ram_size.get()))
            if size > 64:
                size = 64
        except Exception:
            size = 1024
        try:
            line = max(1, int(self.line_size.get()))
        except Exception:
            line = 1
        try:
            if getattr(self, 'ram_obj', None) is None:
                self.ram_obj = RAM(size_bytes=size, line_size=line)
            else:
                # recreate if size changed
                if getattr(self.ram_obj, 'size', None) != size or getattr(self.ram_obj, 'line_size', None) != line:
                    self.ram_obj = RAM(size_bytes=size, line_size=line)
        except Exception:
            # best-effort: leave ram_obj None on failure
            try:
                self.ram_obj = None
            except Exception:
                pass

    def _on_ram_changed(self, *args):
        """Handler called when the RAM size spinbox changes.

        Recreate the RAM backing store (if needed) and refresh the RAM view.
        """
        try:
            # ensure the internal ram object matches the UI fields
            self._ensure_ram_object()
            # purge any recorded recent accesses (they may map to old size)
            try:
                self._recent_ram_accesses = []
            except Exception:
                pass
            try:
                self.update_ram_display()
            except Exception:
                pass
            try:
                size = getattr(self.ram_obj, 'size', None)
                line = getattr(self.ram_obj, 'line_size', None)
                if size is not None:
                    self._append_log(f"RAM recreated: size={size} bytes, line_size={line}")
            except Exception:
                pass
        except Exception:
            pass

    def _on_write_policy_changed(self, *args):
        """Handler called when the write policy option in the UI changes.

        Update the underlying core cache's `write_policy` to match the UI.
        If switching to `write-through` from `write-back`, flush dirty
        blocks to the backing RAM (best-effort) and clear their dirty bits so
        the UI is consistent. Finally refresh the cache display.
        """
        wp = None
        try:
            wp = self.write_hit_policy.get()
        except Exception:
            pass

        core = self.get_core_cache()
        if core is None:
            return

        # update core object's policy (best-effort)
        try:
            core.write_policy = wp
        except Exception:
            pass

        # If switching to write-through, flush dirty lines to RAM and clear them
        if wp == 'write-through':
            try:
                line_size = int(getattr(core, 'line_size', 1) or 1)
                num_sets = int(getattr(core, 'num_sets', 1) or 1)
                for s in range(len(core.sets)):
                    for w in range(len(core.sets[s])):
                        block = core.sets[s][w]
                        try:
                            if getattr(block, 'dirty', False):
                                # compute evicted block base and write to RAM
                                try:
                                    tag = int(block.tag)
                                    block_addr = tag * num_sets + int(s)
                                    base = block_addr * line_size
                                except Exception:
                                    base = None
                                try:
                                    if base is not None and getattr(self, 'ram_obj', None) is not None:
                                        try:
                                            self.ram_obj.write(base, 1)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                try:
                                    block.dirty = False
                                except Exception:
                                    pass
                        except Exception:
                            pass
            except Exception:
                pass

        # Refresh the cache display so dirty indicators update immediately
        try:
            self.update_cache_display({})
        except Exception:
            pass

    def _note_ram_access(self, addr: int, is_write: bool):
        """Record a recent RAM access (base-aligned) for temporary highlighting.

        We store tuples (base_addr, is_write, expiry_ts) and purge expired
        entries during drawing.
        """
        try:
            if addr is None or getattr(self, 'ram_obj', None) is None:
                return
            try:
                line = max(1, int(getattr(self.ram_obj, 'line_size', 1)))
            except Exception:
                line = 1
            base = (int(addr) // line) * line
            # highlight duration synchronized with animation speed (anim_speed in ms)
            # highlight duration: keep it short (1 second) so highlights are transient
            expiry = time.time() + 1.0
            # append and keep list small
            try:
                self._recent_ram_accesses.append((base, bool(is_write), expiry))
            except Exception:
                self._recent_ram_accesses = [(base, bool(is_write), expiry)]
            # purge expired entries immediately to bound memory
            now = time.time()
            try:
                self._recent_ram_accesses = [(b, w, e) for (b, w, e) in self._recent_ram_accesses if e > now]
            except Exception:
                pass
        except Exception:
            pass

    def _note_ram_access_color(self, base: int, color: str, duration_ms: int = None):
        """Record a recent RAM access with an explicit color string.

        The color should be a CSS hex string like '#8BC34A' or '#F44336'.
        Duration defaults to ~1.2 * anim_speed (same logic as _note_ram_access).
        """
        try:
            if base is None or getattr(self, 'ram_obj', None) is None:
                return
            # fixed short duration for visual clarity: 1 second
            expiry = time.time() + 1.0
            try:
                # store color string as second element; update_ram_display understands both bool and str
                self._recent_ram_accesses.append((base, str(color), expiry))
            except Exception:
                self._recent_ram_accesses = [(base, str(color), expiry)]
            # purge expired entries
            now = time.time()
            try:
                self._recent_ram_accesses = [(b, w, e) for (b, w, e) in self._recent_ram_accesses if e > now]
            except Exception:
                pass
        except Exception:
            pass

    def _display_last_read(self, info: dict):
        """Set the last-read display from the provided access info.

        Prefer showing a value stored in a cache block (so reads reflect
        cached dirty data). If not available, fall back to the RAM backing
        store. If neither is available, show 'N/A'.
        """
        if info is None:
            return
        if info.get('is_write'):
            return
        addr = info.get('address')
        if addr is None:
            return
        try:
            addr = int(addr)
        except Exception:
            return

        val = None
        try:
            core = self.get_core_cache()
        except Exception:
            core = None

        # Attempt to read from cache block data first
        try:
            line_size = getattr(core, 'line_size', None) or max(1, int(self.line_size.get()))
        except Exception:
            try:
                line_size = max(1, int(self.line_size.get()))
            except Exception:
                line_size = 1

        try:
            block_addr = addr // line_size
            offset = addr % line_size
        except Exception:
            block_addr = None
            offset = 0

        try:
            if core is not None and hasattr(core, 'num_sets') and hasattr(core, 'sets') and block_addr is not None:
                num_sets = getattr(core, 'num_sets', 1) or 1
                set_index = block_addr % num_sets
                tag = block_addr // num_sets
                if 0 <= set_index < len(core.sets):
                    # search for a way with matching tag
                    for w in range(len(core.sets[set_index])):
                        candidate = core.sets[set_index][w]
                        try:
                            if getattr(candidate, 'valid', False) and getattr(candidate, 'tag', None) == tag:
                                if getattr(candidate, 'data', None) is not None:
                                    try:
                                        val = candidate.data[offset]
                                    except Exception:
                                        val = None
                                break
                        except Exception:
                            continue
        except Exception:
            val = None

        # fallback to RAM
        if val is None:
            try:
                ram = getattr(self, 'ram_obj', None)
                if ram is None:
                    if getattr(self, 'last_read_value', None) is not None:
                        try:
                            self.last_read_value.set('N/A')
                        except Exception:
                            pass
                    return
                try:
                    val = ram.read(addr)
                except Exception:
                    val = None
            except Exception:
                val = None

        try:
            if val is None:
                self.last_read_value.set('N/A')
            else:
                try:
                    self.last_read_value.set(f"{int(val)} (0x{int(val):02x})")
                except Exception:
                    self.last_read_value.set(str(val))
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

    def _animate_ram_to_cache(self, base_addr: int, label_index: int):
        """Visualize a RAM -> cache load by highlighting the RAM cell and the cache label.

        This is a lightweight animation: we draw a temporary outline around the
        RAM cell and flash the destination cache label background for a short
        duration determined by half the animation speed.
        """
        try:
            canvas = getattr(self, 'ram_canvas', None)
            if canvas is None:
                return
            bbox = getattr(self, '_ram_cell_bboxes', {}).get(base_addr)
            rect_id = None
            try:
                if bbox:
                    x1, y1, x2, y2 = bbox
                    rect_id = canvas.create_rectangle(x1, y1, x2, y2, outline='#FFD54F', width=3)
            except Exception:
                rect_id = None

            lbl = None
            orig_bg = None
            try:
                if 0 <= int(label_index) < len(getattr(self, 'frame_labels', [])):
                    lbl = self.frame_labels[int(label_index)]
                    try:
                        orig_bg = lbl.cget('bg')
                    except Exception:
                        orig_bg = None
                    try:
                        lbl.configure(bg='#FFD54F')
                    except Exception:
                        pass
            except Exception:
                lbl = None

            def _clear_anim():
                try:
                    if rect_id is not None:
                        try:
                            canvas.delete(rect_id)
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if lbl is not None:
                        try:
                            if orig_bg is not None:
                                lbl.configure(bg=orig_bg)
                            else:
                                lbl.configure(bg='#111111')
                        except Exception:
                            pass
                except Exception:
                    pass

            try:
                dur = max(200, int(self.anim_speed.get()) // 2)
            except Exception:
                dur = 400
            try:
                self.window.after(dur, _clear_anim)
            except Exception:
                _clear_anim()
        except Exception:
            pass

    def _ensure_valid_or_warn(self) -> bool:
        """Validate UI parameters and show a popup if invalid.

        Returns True when parameters are valid, False otherwise.
        """
        try:
            ok = self.validate_ui_params()
            if not ok:
                try:
                    messagebox.showwarning('Invalid parameters', 'Please fix input parameters before running actions.')
                except Exception:
                    pass
                return False
            return True
        except Exception:
            try:
                messagebox.showwarning('Invalid parameters', 'Please fix input parameters before running actions.')
            except Exception:
                pass
            return False

    def _ensure_input_bindings(self):
        """Ensure the Input Entry has trace and key bindings so typing always updates the decode preview.

        This is idempotent and safe to call multiple times; some tkinter versions
        expose trace_add while others use trace('w'), so we attempt both.
        """
        try:
            ent = getattr(self, 'input_entry', None)
            if ent is None:
                return
            # variable trace
            try:
                # remove previous traces is tricky; we simply add a trace which is lightweight
                self.input.trace_add('write', lambda *a: self.update_decode_panel())
            except Exception:
                try:
                    self.input.trace('w', lambda *a: self.update_decode_panel())
                except Exception:
                    pass
            # key event on the Entry itself
            try:
                ent.bind('<KeyRelease>', lambda e: self.update_decode_panel())
            except Exception:
                pass
        except Exception:
            pass

    def _on_params_changed(self):
        """Called when cache_size/line_size/associativity change to re-validate params."""
        try:
            ok = self.validate_ui_params()
            # When line_size changes we need the RAM backing-store to reflect
            # the new grouping. Recreate or adjust the RAM object and refresh
            # the RAM and cache displays. _ensure_ram_object is idempotent and
            # will only recreate when size/line_size actually change.
            try:
                self._ensure_ram_object()
            except Exception:
                pass
            try:
                # recompute cache->RAM mapping and redraw views
                try:
                    # update cache display (will call update_ram_display)
                    self.update_cache_display({})
                except Exception:
                    try:
                        self.update_ram_display()
                    except Exception:
                        pass
            except Exception:
                pass
            # validate_ui_params will enable controls if ok; if not, keep them disabled
            # also update live block/set labels even if we didn't recreate frames
            try:
                try:
                    raw_cache_size = max(1, int(self.cache_size.get()))
                except Exception:
                    raw_cache_size = 1
                try:
                    line_size = max(1, int(self.line_size.get()))
                except Exception:
                    line_size = 1
                num_blocks = max(1, raw_cache_size // line_size)
                try:
                    assoc = max(1, int(self.associativity.get()))
                except Exception:
                    assoc = 1
                num_sets = max(1, num_blocks // assoc)
                try:
                    self.num_blocks_var.set(str(int(num_blocks)))
                    self.num_sets_var.set(str(int(num_sets)))
                except Exception:
                    pass
            except Exception:
                pass
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
        # UI display limit: refuse configurations that would create more than 20 blocks
        if num_blocks > 20:
            msg = f'Number of cache blocks ({num_blocks}) exceeds UI display limit (20).\nPlease reduce cache_size or increase line_size.'
            try:
                messagebox.showerror('Too many blocks', msg)
            except Exception:
                pass
            try:
                self._set_controls_enabled(False)
            except Exception:
                pass
            return False
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

    def _draw_ram_to_cache_arrow(self, base_addr: int, label_index: int, color: str = '#FFD54F', duration: int = 400):
        """Draw a temporary arrow from the RAM cell (base_addr) to the cache label (label_index).

        The arrow is drawn on a short-lived overlay canvas placed over the
        cache/RAM right panel so it visually connects the two widgets.
        """
        try:
            # need the source bbox (in ram_canvas coords)
            canvas = getattr(self, 'ram_canvas', None)
            lbl = None
            try:
                if 0 <= int(label_index) < len(getattr(self, 'frame_labels', [])):
                    lbl = self.frame_labels[int(label_index)]
            except Exception:
                lbl = None
            if canvas is None or lbl is None:
                return

            # parent for overlay: choose the common ancestor container where both
            # ram_canvas and cache labels reside. cache_display_frame is in container_right,
            # so use its parent (container_right) if available, else use self.window.
            parent = getattr(self, 'cache_display_frame', None)
            if parent is not None:
                parent = parent.master or self.window
            else:
                parent = self.window

            # ensure geometry info is up-to-date
            try:
                parent.update_idletasks()
            except Exception:
                pass

            # compute parent origin (root coords)
            try:
                p_rootx = parent.winfo_rootx()
                p_rooty = parent.winfo_rooty()
            except Exception:
                p_rootx = self.window.winfo_rootx()
                p_rooty = self.window.winfo_rooty()

            # source center: ram_canvas root + bbox center, then convert to parent coords
            try:
                r_rootx = canvas.winfo_rootx()
                r_rooty = canvas.winfo_rooty()
                bbox = getattr(self, '_ram_cell_bboxes', {}).get(base_addr)
                if not bbox:
                    return
                x1, y1, x2, y2 = bbox
                src_x = (r_rootx - p_rootx) + (x1 + x2) / 2
                src_y = (r_rooty - p_rooty) + (y1 + y2) / 2
            except Exception:
                return

            # destination center: label root coordinates converted to parent coords
            try:
                lbl_rootx = lbl.winfo_rootx()
                lbl_rooty = lbl.winfo_rooty()
                dst_x = (lbl_rootx - p_rootx) + lbl.winfo_width() / 2
                dst_y = (lbl_rooty - p_rooty) + lbl.winfo_height() / 2
            except Exception:
                return

            # create overlay canvas in parent
            try:
                ov = tk.Canvas(parent, width=parent.winfo_width() or 800, height=parent.winfo_height() or 400, bg=self.background_container, highlightthickness=0)
                # place exactly over parent
                ov.place(x=0, y=0, relwidth=1, relheight=1)
                ov.lift()
                # draw a smooth arrow
                arrow_id = ov.create_line(src_x, src_y, dst_x, dst_y, fill=color, width=3, arrow='last', smooth=True)
            except Exception:
                try:
                    ov = None
                except Exception:
                    ov = None
                arrow_id = None

            def _cleanup():
                try:
                    if ov is not None:
                        try:
                            ov.delete('all')
                        except Exception:
                            pass
                        try:
                            ov.place_forget()
                        except Exception:
                            try:
                                ov.destroy()
                            except Exception:
                                pass
                except Exception:
                    pass

            try:
                self.window.after(max(150, int(duration)), _cleanup)
            except Exception:
                _cleanup()
        except Exception:
            pass

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
                # Expect plain addresses (decimal) or hex with 0x prefix.
                tval = t
                try:
                    # int(..., 0) accepts 0x prefixed hex or decimal
                    val = int(tval, 0)
                except Exception:
                    try:
                        # final fallback: try decimal
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
        # ensure input bindings are active after parsing user text
        try:
            self._ensure_input_bindings()
        except Exception:
            pass

    def _prepare_value_tokens(self):
        """Parse the Write values entry into a list of integer values for manual writes."""
        try:
            text = (self.write_values.get() or '').strip() if getattr(self, 'write_values', None) is not None else ''
            if not text:
                self._value_tokens = []
                self._value_index = 0
                self._value_raw_tokens = []
                return
            raw = [t.strip() for part in text.split(',') for t in part.split() if t.strip()]
            self._value_raw_tokens = list(raw)
            vals = []
            for t in raw:
                try:
                    v = int(t, 0)
                except Exception:
                    try:
                        v = int(t)
                    except Exception:
                        # skip invalid tokens
                        continue
                vals.append(int(v))
            # enforce reasonable limit
            if len(vals) > MAX_INPUT_TOKENS:
                vals = vals[:MAX_INPUT_TOKENS]
                self._append_log(f"Write values truncated to first {MAX_INPUT_TOKENS} tokens")
            self._value_tokens = vals
            self._value_index = 0
        except Exception:
            self._value_tokens = []
            self._value_index = 0
            self._value_raw_tokens = []

    def _consume_manual_token(self, is_write: bool):
        """Consume next manual token and perform a single access (read or write).

        Returns the info dict from the simulator step or None.
        """
        try:
            if not self._ensure_valid_or_warn():
                return None
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

            # If this is a manual write, consume the first write value token (if any)
            # and keep it so we can reuse it after the simulator step (avoid
            # consuming tokens twice).
            write_val = None
            if is_write:
                try:
                    if not getattr(self, '_value_tokens', None):
                        self._prepare_value_tokens()
                except Exception:
                    pass
                try:
                    if getattr(self, '_value_tokens', None) and len(self._value_tokens) > 0:
                        try:
                            write_val = int(self._value_tokens.pop(0))
                        except Exception:
                            write_val = None
                except Exception:
                    write_val = None
                # update the write_values entry to remove the consumed raw token
                try:
                    if getattr(self, '_value_raw_tokens', None):
                        remaining = self._value_raw_tokens[1:]
                        try:
                            self.write_values.set(','.join(remaining))
                        except Exception:
                            pass
                        self._value_raw_tokens = remaining
                except Exception:
                    pass

            # pass the consumed write value (may be None) into the simulator so
            # the cache/core can apply it immediately to cache.block.data.
            sim.load_sequence([addr], writes=[is_write], values=[write_val])
            info = sim.step()
            if info:
                action = 'W' if info.get('is_write') else 'R'
                self._append_log(f"Manual {action} Addr {info.get('address')}: {'HIT' if info.get('hit') else 'MISS'}")
                self._update_stats_widgets(info.get('stats', {}))
                try:
                    self.update_cache_display(info)
                except Exception:
                    pass
                # record RAM access (for highlighting) and refresh RAM view when needed
                try:
                    mem_read = bool(info.get('mem_read')) if info.get('mem_read') is not None else False
                    mem_write = bool(info.get('mem_write')) if info.get('mem_write') is not None else False
                except Exception:
                    mem_read = False
                    mem_write = False
                if mem_read or mem_write:
                    try:
                        self._note_ram_access(info.get('address'), info.get('is_write'))
                    except Exception:
                        pass
                try:
                    self.update_ram_display()
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

                # If this was a manual write, apply the same consumed write value
                # to RAM if the simulator indicated an immediate memory write
                # (write-through) or an eviction write was performed.
                if is_write:
                    try:
                        val = write_val
                        # Only write through to RAM if the simulator performed a memory write
                        # (e.g. write-through policy or an eviction write). For write-back
                        # cases where the block becomes dirty, the RAM write should be
                        # deferred until eviction and therefore we must NOT write here.
                        if val is not None and getattr(self, 'ram_obj', None) is not None and bool(mem_write):
                            try:
                                line_size = max(1, int(getattr(self.ram_obj, 'line_size', 1)))
                            except Exception:
                                line_size = 1
                            try:
                                base = (int(addr) // line_size) * line_size
                            except Exception:
                                try:
                                    base = int(addr)
                                except Exception:
                                    base = None
                            try:
                                if base is not None:
                                    self.ram_obj.write(base, val)
                                    # visually note the RAM write
                                    try:
                                        self._note_ram_access(base, True)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        # consume the used raw token from the entry box and update state
                        try:
                            if getattr(self, '_value_raw_tokens', None):
                                remaining = self._value_raw_tokens[1:]
                                try:
                                    self.write_values.set(','.join(remaining))
                                except Exception:
                                    pass
                                self._value_raw_tokens = remaining
                                # reset parsed tokens so future writes reparse
                                self._value_tokens = []
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
            # synchronize internal token state with the updated input so future
            # calls re-parse the newly-typed tokens (prevents "No more manual tokens" when
            # the input box still shows tokens).
            try:
                self._manual_raw_tokens = remaining
                # clear parsed tokens so _prepare_manual_tokens will re-parse on next consume
                self._manual_tokens = []
                self._manual_index = 0
            except Exception:
                pass
            # ensure bindings remain active so further typing is detected
            try:
                self._ensure_input_bindings()
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
