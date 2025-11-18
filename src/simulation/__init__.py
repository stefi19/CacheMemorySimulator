"""Simulation package shim.

This module exposes the Simulation class at `src.simulation` so existing
imports such as `from src.simulation import Simulation` continue to work.
"""
from .simulation import Simulation

__all__ = ["Simulation"]
