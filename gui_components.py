"""Shared CustomTkinter components."""

from __future__ import annotations

import customtkinter as ctk  # type: ignore

from constants import Colors


class CardFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=Colors.CARD,
            border_color=Colors.BORDER,
            border_width=1,
            corner_radius=8,
            **kwargs,
        )
