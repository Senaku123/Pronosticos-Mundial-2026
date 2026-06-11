"""Tests for reproducible random-seed control."""

from __future__ import annotations

import numpy as np

from wc26.utils.seeds import make_rng, set_global_seed


def test_global_seed_is_reproducible() -> None:
    set_global_seed(123)
    first = np.random.rand(5)
    set_global_seed(123)
    second = np.random.rand(5)
    assert np.array_equal(first, second)


def test_make_rng_is_reproducible_and_independent() -> None:
    assert np.array_equal(make_rng(7).random(4), make_rng(7).random(4))
    assert not np.array_equal(make_rng(7).random(4), make_rng(8).random(4))
