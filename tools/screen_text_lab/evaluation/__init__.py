"""Offline evaluation of already-produced OCR records; never runs a model."""

from .core import DEFAULT_RECIPE, analyze_pair, assess, compare_three_way
from .io import load_crop_run

__all__ = ["DEFAULT_RECIPE", "analyze_pair", "assess", "compare_three_way", "load_crop_run"]
