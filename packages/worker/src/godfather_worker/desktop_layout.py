"""Bounded, scrollable native windows for short screens and larger text."""

import tkinter as tk
from tkinter import ttk
from typing import Any


def content_frame(window: tk.Tk | tk.Toplevel, *, maximum_width: int = 900) -> ttk.Frame:
    max_width = min(maximum_width, window.winfo_screenwidth() - 40)
    max_height = min(900, window.winfo_screenheight() - 80)
    window.minsize(min(540, max_width), min(580, max_height))
    window.maxsize(max_width, max_height)
    window.geometry(f"{min(900, max_width)}x{min(760, max_height)}")
    canvas = tk.Canvas(window, highlightthickness=0, background="#F4F8FC")
    scroll = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    frame = ttk.Frame(canvas, padding=24)
    content = canvas.create_window((0, 0), window=frame, anchor="nw")

    def resize(event: tk.Event[Any]) -> None:
        canvas.itemconfigure(content, width=event.width)
        for widget in frame.winfo_children():
            if isinstance(widget, ttk.Label):
                widget.configure(wraplength=max(180, event.width - 48))

    canvas.bind("<Configure>", resize)

    def content_size(_: tk.Event[Any]) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        window.maxsize(max_width, min(max_height, max(580, frame.winfo_reqheight())))

    frame.bind("<Configure>", content_size)

    def wheel(event: tk.Event[Any]) -> None:
        if canvas.bbox("all") and frame.winfo_reqheight() > canvas.winfo_height():
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    window.bind("<MouseWheel>", wheel)
    canvas.bind("<Button-4>", lambda _: canvas.yview_scroll(-1, "units"))
    canvas.bind("<Button-5>", lambda _: canvas.yview_scroll(1, "units"))
    return frame
