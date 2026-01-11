"""Small UI helper functions for the cache simulator UI.

This module contains utility routines shared by the UI class. It was
added to keep the main file more focused and to host the scrolling helper.
"""


def clamp01(x: float) -> float:
    try:
        if x < 0.0:
            return 0.0
        if x > 1.0:
            return 1.0
        return float(x)
    except Exception:
        return 0.0
