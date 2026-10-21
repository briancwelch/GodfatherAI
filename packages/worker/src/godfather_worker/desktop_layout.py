"""Native expanding layouts; scroll only genuinely overflowing table rows."""

import tkinter as tk
from tkinter import ttk


def window_size(window: tk.Tk | tk.Toplevel, width: int = 1120, height: int = 760) -> None:
    available_width = max(640, window.winfo_screenwidth() - 64)
    available_height = max(480, window.winfo_screenheight() - 96)
    window.minsize(min(760, available_width), min(540, available_height))
    window.geometry(f"{min(width, available_width)}x{min(height, available_height)}")


def content_frame(window: tk.Tk | tk.Toplevel, *, maximum_width: int = 1120) -> ttk.Frame:
    window_size(window, width=maximum_width)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    return frame


def table_scroll(parent: ttk.Frame, table: ttk.Treeview) -> ttk.Scrollbar:
    scroll = ttk.Scrollbar(parent, orient="vertical", command=table.yview)

    def changed(first: float, last: float) -> None:
        scroll.set(first, last)
        if float(first) > 0 or float(last) < 1:
            scroll.grid(row=0, column=1, sticky="ns")
        else:
            scroll.grid_remove()

    table.configure(yscrollcommand=changed)
    return scroll
