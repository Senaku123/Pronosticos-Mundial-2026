"""Centralized random-seed control for reproducible runs (addendum §8).

Every model_run / tournament_simulation must persist the seed it used so that a run
can be reproduced bit-for-bit.
"""

from __future__ import annotations

import os
import random

import numpy as np


def set_global_seed(seed: int) -> None:
    """Seed the Python and NumPy global RNGs."""
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)


def make_rng(seed: int) -> np.random.Generator:
    """Return an independent NumPy ``Generator`` for explicit, local randomness.

    Prefer this over the global RNG inside the Monte Carlo engine; spawn independent
    streams per worker with ``np.random.SeedSequence(seed).spawn(n)``.
    """
    return np.random.default_rng(seed)
