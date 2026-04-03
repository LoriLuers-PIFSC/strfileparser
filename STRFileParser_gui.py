"""
Simple Tkinter GUI for STRFileParser

Features:
- Browse for source CSV file
- Browse for destination folder
- Auto-populate filename prefix as ESD_NCRMP_Temperature_{REGION}_{YEAR}
  (uses regex to locate a 4-digit year and the token before it, falls back to underscore token positions)
- Row limit input
- Run button to execute the parser (imports FileParser from STRFileParser.py)
- Progress/status output area

Run:
    python STRFileParser_gui.py

"""

import os
import sys
import threading
import re
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk

# Try to import the controlled parser and control class from the sibling script
try:
    from STRFileParser import _FileParser_controlled as FileParser_controlled, ParserControl
except Exception:
    thisdir = os.path.dirname(os.path.abspath(__file__))
    if thisdir not in sys.path:
        sys.path.insert(0, thisdir)
    # also allow loading the parser from the _archive subfolder if present
    archive_dir = os.path.join(thisdir, '_archive')
    if os.path.isdir(archive_dir) and archive_dir not in sys.path:
        sys.path.insert(0, archive_dir)
    try:
        from STRFileParser import _FileParser_controlled as FileParser_controlled, ParserControl
    except Exception:
        # re-raise to show the original import error to the caller
        raise


def compute_prefix_from_filename(fname: str) -> str:
    """Attempt to compute REGION and YEAR from filename.

    Strategy:
    - Use regex to find a 4-digit year (19xx or 20xx). If found, take the token before it as REGION.
    - Tokens are split on underscore. If regex fails, fall back to tokens[3] and tokens[4] (1-based positions used in original script).
    - If still missing, leave placeholders.
    """
    base = os.path.splitext(os.path.basename(fname))[0]
    tokens = base.split('_')

    # look for YYYY
    m = re.search(r"\b(19|20)\d{2}\b", base)
    if m:
        year = m.group(0)
        # find which token contains the year
        for i, t in enumerate(tokens):
            if re.search(r"\b(19|20)\d{2}\b", t):
                region = tokens[i-1] if i-1 >= 0 else 'REGION'
                return f"ESD_NCRMP_Temperature_{region}_{year}"

    # fallback to positional tokens (original script used PART4 and PART5)
    region = tokens[3] if len(tokens) >= 4 else 'REGION'
    year = tokens[4] if len(tokens) >= 5 else 'YEAR'
    return f"ESD_NCRMP_Temperature_{region}_{year}"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title('STR File Parser')

        frm = tk.Frame(root, padx=10, pady=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # Source file
        tk.Label(frm, text='Source STR (.csv) file:').grid(row=0, column=0, sticky='w')
        self.src_var = tk.StringVar()
        self.src_entry = tk.Entry(frm, textvariable=self.src_var, width=60)
        self.src_entry.grid(row=1, column=0, columnspan=2, sticky='we')
        tk.Button(frm, text='Browse...', command=self.browse_source).grid(row=1, column=2, padx=5)

        # Destination folder
        tk.Label(frm, text='Destination folder:').grid(row=2, column=0, sticky='w', pady=(8,0))
        self.dst_var = tk.StringVar()
        self.dst_entry = tk.Entry(frm, textvariable=self.dst_var, width=60)
        self.dst_entry.grid(row=3, column=0, columnspan=2, sticky='we')
        tk.Button(frm, text='Browse...', command=self.browse_dest).grid(row=3, column=2, padx=5)

        # Filename prefix
        tk.Label(frm, text='Filename prefix (editable):').grid(row=4, column=0, sticky='w', pady=(8,0))
        self.pref_var = tk.StringVar()
        self.pref_entry = tk.Entry(frm, textvariable=self.pref_var, width=60)
        self.pref_entry.grid(row=5, column=0, columnspan=2, sticky='we')
        tk.Button(frm, text='Auto', command=self.autofill_prefix).grid(row=5, column=2, padx=5)

        # Row limit
        tk.Label(frm, text='Row limit per file:').grid(row=6, column=0, sticky='w', pady=(8,0))
        self.row_var = tk.StringVar(value='1000000')
        self.row_entry = tk.Entry(frm, textvariable=self.row_var, width=20)
        # make entry span two columns so it doesn't collide with buttons
        self.row_entry.grid(row=6, column=0, columnspan=2, sticky='we')

        # Run / Pause / Resume / Cancel buttons (on next row)
        self.run_btn = tk.Button(frm, text='Run', width=12, command=self.on_run)
        self.run_btn.grid(row=7, column=2, sticky='e')

        self.pause_btn = tk.Button(frm, text='Pause', width=8, command=self.on_pause, state='disabled')
        self.pause_btn.grid(row=7, column=1, sticky='e')
        self.cancel_btn = tk.Button(frm, text='Cancel', width=8, command=self.on_cancel, state='disabled')
        self.cancel_btn.grid(row=7, column=0, sticky='w')

        # Status / log
        tk.Label(frm, text='Status:').grid(row=8, column=0, sticky='w', pady=(8,0))
        self.log = scrolledtext.ScrolledText(frm, height=12, width=80, state='disabled')
        self.log.grid(row=9, column=0, columnspan=3, pady=(4,0))

        # Progress bar and ETA
        self.progress = ttk.Progressbar(frm, orient='horizontal', length=400, mode='determinate')
        self.progress.grid(row=10, column=0, columnspan=2, sticky='we', pady=(8,0))
        self.eta_label = tk.Label(frm, text='ETA: N/A')
        self.eta_label.grid(row=10, column=2, sticky='e', padx=(8,0))

        # configure grid weights
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(2, weight=0)

    def browse_source(self):
        path = filedialog.askopenfilename(title='Select STR file', filetypes=[('STR Files', ('*.csv')), ('All files','*.*')])
        if path:
            self.src_var.set(path)
            self.autofill_prefix()

    def browse_dest(self):
        path = filedialog.askdirectory(title='Select destination folder')
        if path:
            self.dst_var.set(path)

    def autofill_prefix(self):
        src = self.src_var.get()
        if not src:
            messagebox.showinfo('Info', 'Select a source file first')
            return
        pref = compute_prefix_from_filename(src)
        # ensure suffix _part is present (parser normalizes it too)
        if not pref.endswith('_part'):
            pref = pref + '_part'
        self.pref_var.set(pref)

    def log_write(self, *msgs, newline=True):
        self.log.configure(state='normal')
        text = ' '.join(str(m) for m in msgs)
        if newline:
            text += '\n'
        self.log.insert(tk.END, text)
        self.log.configure(state='disabled')
        self.log.see(tk.END)

    def set_controls_state(self, enabled: bool):
        state = 'normal' if enabled else 'disabled'
        self.src_entry.configure(state=state)
        self.dst_entry.configure(state=state)
        self.pref_entry.configure(state=state)
        self.row_entry.configure(state=state)
        self.run_btn.configure(state=state)
        # Pause and cancel handled separately
        if enabled:
            self.pause_btn.configure(state='disabled')
            self.cancel_btn.configure(state='disabled')

    def on_run(self):
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        pref = self.pref_var.get().strip()
        row_s = self.row_var.get().strip()

        if not src:
            messagebox.showerror('Error', 'Please select a source file')
            return
        if not dst:
            messagebox.showerror('Error', 'Please select a destination folder')
            return
        try:
            row_limit = int(row_s)
            if row_limit <= 0:
                raise ValueError()
        except Exception:
            messagebox.showerror('Error', 'Row limit must be a positive integer')
            return

        # prepare control object and start parser thread
        self.control = ParserControl()
        self.pause_btn.configure(state='normal', text='Pause')
        self.cancel_btn.configure(state='normal')
        t = threading.Thread(target=self._run_parser_thread, args=(src, dst, pref, row_limit, self.control), daemon=True)
        t.start()

    def on_pause(self):
        if not hasattr(self, 'control'):
            return
        if self.control.pause_event.is_set():
            # currently paused; resume
            self.control.pause_event.clear()
            self.pause_btn.configure(text='Pause')
            self.log_write('Resuming...')
        else:
            self.control.pause_event.set()
            self.pause_btn.configure(text='Resume')
            self.log_write('Paused')

    def on_cancel(self):
        if not hasattr(self, 'control'):
            return
        self.control.stop_event.set()
        self.log_write('Cancel requested...')

    def _run_parser_thread(self, src, dst, pref, row_limit, control):
        try:
            self.set_controls_state(False)
            self.log_write('Starting parser...')
            self.log_write(f'Source: {src}')
            self.log_write(f'Destination: {dst}')
            self.log_write(f'Prefix: {pref}')
            self.log_write(f'Row limit: {row_limit}')

            # reset progress
            self.progress['value'] = 0
            self.eta_label.configure(text='ETA: N/A')

            # ensure destination exists
            os.makedirs(dst, exist_ok=True)

            # Track totals
            totals = {'records': 0, 'files': 0}

            # Call the controlled parser with progress callback and control
            def progress_cb(info):
                # schedule UI updates on main thread
                self.root.after(1, self._handle_progress, info)
                 # Capture final totals from last progress update
                if info.get('records') is not None:
                    totals['records'] = info['records']
                if info.get('files_written') is not None:
                    totals['files'] = info['files_written']

            FileParser_controlled(src, dst, pref, row_limit, progress_cb, control)

            # === After parser finishes, write stats in README ===
            readme_path = os.path.join(dst, "README.txt")
            # Extract region and year if possible from the prefix
            region, year = "UNKNOWN", "UNKNOWN"
            try:
                parts = pref.split("_")
                if len(parts) >= 4:
                    region = parts[2]
                    year = parts[3]
            except Exception:
                pass

            readme_content = f"""\
        {pref}
        Total Records: {totals['records']}
        Total Split Files: {totals['files']}

        Temperature data for the {region} collected in {year} are provided as a single data file in ZIP and CSV format. 
        Additionally, the single data file has been SPLIT into a series of {totals['files']} CSV files (1-million rows each, except for the last CSV file in the series). These split files are provided in a single zip file and as a series of CSV files.

        0-DATA contains: README, {pref}.zip, and {pref}_split.zip
        ===> 0-DATA > UNZIPPED contains: {pref}.csv
            ===> 0-DATA > UNZIPPED > SPLIT contains: series of split CSV files ({pref}_part#.csv)
        """

            with open(readme_path, "w", encoding="utf-8") as readme:
                readme.write(readme_content)

            print("Parsing Complete!")
            print("README written to:", readme_path)


            self.log_write('Parser finished successfully')
            messagebox.showinfo('Done', 'Parsing complete')
        except Exception as e:
            self.log_write('Error during parsing:')
            self.log_write(traceback.format_exc())
            messagebox.showerror('Error', f'Parsing failed: {e}')
        finally:
            # ensure buttons/state reset
            self.set_controls_state(True)
            self.pause_btn.configure(state='disabled', text='Pause')
            self.cancel_btn.configure(state='disabled')
            # clear control
            try:
                del self.control
            except Exception:
                pass

    def _handle_progress(self, info):
        # info may contain bytes_read, total_bytes, percent, records, files_written, elapsed, eta
        # Only log file-writing messages to keep log concise
        if 'message' in info:
            msg = info['message']
            if isinstance(msg, str) and msg.startswith('Writing '):
                self.log_write(msg)

        # Always update progress bar and ETA silently
        percent = info.get('percent')
        eta = info.get('eta')
        if percent is not None:
            self.progress['value'] = percent
        if eta is not None:
            try:
                eta_s = int(eta)
                if eta_s < 60:
                    s = f"{eta_s}s"
                else:
                    m = eta_s // 60
                    s2 = eta_s % 60
                    s = f"{m}m {s2}s"
            except Exception:
                s = 'N/A'
            self.eta_label.configure(text=f'ETA: {s}')


if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
