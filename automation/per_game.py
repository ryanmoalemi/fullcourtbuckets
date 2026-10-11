"""One-decimal per-game averages that match the official counting totals.

Provider rows store a short decimal of total/games. Formatting that float with
``f'{n:.1f}'`` does two different wrong things:

* Some decimals are not exact in binary. ``16.95`` is stored as
  ``16.94999...``, so formatting never reaches the halfway point and prints
  ``16.9``. ``14.45`` prints ``14.4`` for the same reason.
* Values that are exact in binary, such as ``8.25``, use half-even rounding.
  ``f'{8.25:.1f}'`` is ``8.2``.

The integer counting total is recovered from the stored average and the games
played, then total/games is rounded half up with ``Decimal``. That is the
figure WNBA.com prints: 729 points in 43 games is 17.0, not 16.9.
"""
from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP

_TENTH = Decimal('0.1')


def counting_total(average, games) -> int | None:
    """Integer total implied by a provider per-game average.

    Counting stats are whole numbers. The stored average is that total divided
    by games, kept to a short decimal. Multiplying back and rounding half up
    recovers the total.
    """
    if isinstance(average, bool) or not isinstance(average, (int, float)):
        return None
    if isinstance(games, bool) or not isinstance(games, (int, float)):
        return None
    if isinstance(games, float) and not games.is_integer():
        return None
    if not math.isfinite(average):
        return None
    played = int(games)
    if played <= 0:
        return None
    product = Decimal(str(average)) * Decimal(played)
    return int(product.to_integral_value(rounding=ROUND_HALF_UP))


def shown_average(average, games) -> str | None:
    """One decimal, half up, from the recovered counting total."""
    total = counting_total(average, games)
    if total is None:
        return None
    played = int(games)
    shown = (Decimal(total) / Decimal(played)).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return f'{shown:.1f}'


def shown_mean(values) -> str | None:
    """One decimal, half up, from an exact sum of counting stats."""
    if not values:
        return None
    total = Decimal(0)
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        total += Decimal(str(value))
    shown = (total / Decimal(len(values))).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return f'{shown:.1f}'
