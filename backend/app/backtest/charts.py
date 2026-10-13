"""Data for charts: results reduced to what a chart can show."""

from itertools import pairwise

import numpy as np
import pandas as pd


def downsample_equity(equity: pd.Series, max_points: int = 1_000) -> pd.Series:
    """At most `max_points` points of an equity curve, in time order: the first and the last,
    and the lowest and highest of each of equal buckets in between, so that sharp drawdowns
    and spikes stay visible."""
    if len(equity) <= max_points:
        return equity
    values = equity.to_numpy()
    edges = np.linspace(1, len(values) - 1, (max_points - 2) // 2 + 1).astype(int)
    keep = {0, len(values) - 1}
    for start, end in pairwise(edges):
        if end > start:
            bucket = values[start:end]
            keep.update((start + int(bucket.argmin()), start + int(bucket.argmax())))
    return equity.iloc[sorted(keep)]
