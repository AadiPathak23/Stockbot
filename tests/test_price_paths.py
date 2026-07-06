import numpy as np
import pandas as pd
import pytest

from engine import fixed_move, from_csv, monte_carlo_gbm


def test_fixed_move_compounds():
    assert fixed_move(100.0, 0.05, 3) == pytest.approx(
        [100.0, 105.0, 110.25, 115.7625]
    )


def test_fixed_move_negative():
    assert fixed_move(100.0, -0.10, 2) == pytest.approx([100.0, 90.0, 81.0])


def test_fixed_move_validation():
    with pytest.raises(ValueError):
        fixed_move(0.0, 0.05, 3)
    with pytest.raises(ValueError):
        fixed_move(100.0, 0.05, 0)
    with pytest.raises(ValueError):
        fixed_move(100.0, -1.0, 3)


def test_from_csv_happy_path_sorts_by_date():
    df = pd.DataFrame(
        {"Date": ["2026-01-03", "2026-01-01", "2026-01-02"],
         "Close": [120.0, 100.0, 110.0]}
    )
    assert from_csv(df) == [100.0, 110.0, 120.0]


def test_from_csv_requires_close_column():
    with pytest.raises(ValueError, match="close"):
        from_csv(pd.DataFrame({"price": [1, 2]}))


def test_from_csv_rejects_bad_prices():
    with pytest.raises(ValueError):
        from_csv(pd.DataFrame({"close": [100.0, -5.0]}))
    with pytest.raises(ValueError):
        from_csv(pd.DataFrame({"close": [100.0, "oops"]}))
    with pytest.raises(ValueError):
        from_csv(pd.DataFrame({"close": [100.0]}))  # too short


def test_gbm_shape_and_start():
    paths = monte_carlo_gbm(4700.0, 0.08, 0.25, n_steps=50, n_paths=7, seed=1)
    assert paths.shape == (7, 51)
    assert np.allclose(paths[:, 0], 4700.0)
    assert (paths > 0).all()


def test_gbm_seed_reproducible():
    a = monte_carlo_gbm(100.0, 0.1, 0.2, 30, 5, seed=42)
    b = monte_carlo_gbm(100.0, 0.1, 0.2, 30, 5, seed=42)
    c = monte_carlo_gbm(100.0, 0.1, 0.2, 30, 5, seed=43)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_gbm_zero_vol_is_pure_drift():
    paths = monte_carlo_gbm(100.0, 0.10, 0.0, n_steps=10, n_paths=3, seed=0)
    expected = 100.0 * np.exp(0.10 * np.arange(11) / 252)
    assert np.allclose(paths, np.tile(expected, (3, 1)))
