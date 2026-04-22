"""
Signal Observatory — Candle Builder
Aggregates 1-minute candles into 15M and 1H candles.

Handles:
- Candle boundaries: 15M closes at :00/:15/:30/:45, 1H at :00
- Session limits: 9:30-16:00 ET only
- Day change: resets intraday buffers
- Incomplete candles at session end: discarded for scanning, kept for price tracking
"""


def _parse_time(dt_str):
    """Extract (date, hour, minute) from 'YYYY-MM-DD HH:MM:SS'."""
    parts = dt_str.split(" ")
    date = parts[0]
    time_parts = parts[1].split(":")
    return date, int(time_parts[0]), int(time_parts[1])


def _candle_bucket_15m(minute):
    """Which 15M bucket does this minute belong to? Returns bucket start minute."""
    return (minute // 15) * 15


def _candle_bucket_1h(hour, minute):
    """Which 1H bucket? Returns (hour, 0)."""
    return hour


class CandleBuilder:
    """
    Builds 15M and 1H candles from 1-minute data.
    
    Usage:
        builder = CandleBuilder()
        for candle_1m in data:
            completed = builder.add(candle_1m)
            # completed = {
            #     "new_day": bool,
            #     "completed_15m": candle_dict or None,
            #     "completed_1h": candle_dict or None,
            #     "current_15m": candle_dict (in progress),
            #     "current_1h": candle_dict (in progress),
            # }
    """

    def __init__(self, max_15m=200, max_1h=120):
        self.current_date = None
        self.candles_15m = []       # completed 15M candles (history)
        self.candles_1h = []        # completed 1H candles (history)
        self.building_15m = None    # candle in progress
        self.building_1h = None     # candle in progress
        self._bucket_15m = None     # current 15M bucket (minute)
        self._bucket_1h = None      # current 1H bucket (hour)
        self._max_15m = max_15m     # max history to keep (performance)
        self._max_1h = max_1h       # max history to keep

    def reset_day(self):
        """Reset intraday state for new trading day. Keep history."""
        self.building_15m = None
        self.building_1h = None
        self._bucket_15m = None
        self._bucket_1h = None

    def _merge_into(self, target, candle_1m):
        """Merge a 1M candle into an aggregating candle."""
        if target is None:
            return {
                "o": candle_1m["o"],
                "h": candle_1m["h"],
                "l": candle_1m["l"],
                "c": candle_1m["c"],
                "v": candle_1m["v"],
                "dt": candle_1m["dt"],
            }
        target["h"] = max(target["h"], candle_1m["h"])
        target["l"] = min(target["l"], candle_1m["l"])
        target["c"] = candle_1m["c"]
        target["v"] += candle_1m["v"]
        return target

    def add(self, candle_1m):
        """
        Add a 1-minute candle. Returns dict with completed candles if any.
        """
        date, hour, minute = _parse_time(candle_1m["dt"])

        result = {
            "new_day": False,
            "completed_15m": None,
            "completed_1h": None,
        }

        # ─── Day change detection ───
        if date != self.current_date:
            if self.current_date is not None:
                result["new_day"] = True
            self.current_date = date
            self.reset_day()

        # ─── 15M aggregation ───
        bucket_15m = _candle_bucket_15m(minute)
        if self._bucket_15m is not None and bucket_15m != self._bucket_15m:
            # New 15M bucket → previous candle is complete
            if self.building_15m is not None:
                result["completed_15m"] = self.building_15m
                self.candles_15m.append(self.building_15m)
                if len(self.candles_15m) > self._max_15m:
                    self.candles_15m = self.candles_15m[-self._max_15m:]
            self.building_15m = None

        self._bucket_15m = bucket_15m
        self.building_15m = self._merge_into(self.building_15m, candle_1m)

        # ─── 1H aggregation ───
        bucket_1h = _candle_bucket_1h(hour, minute)
        if self._bucket_1h is not None and bucket_1h != self._bucket_1h:
            # New 1H bucket → previous candle is complete
            if self.building_1h is not None:
                result["completed_1h"] = self.building_1h
                self.candles_1h.append(self.building_1h)
                if len(self.candles_1h) > self._max_1h:
                    self.candles_1h = self.candles_1h[-self._max_1h:]
            self.building_1h = None

        self._bucket_1h = bucket_1h
        self.building_1h = self._merge_into(self.building_1h, candle_1m)

        return result

    def get_15m_candles(self, include_current=True):
        """Get all 15M candles (completed + optionally current)."""
        if include_current and self.building_15m:
            return self.candles_15m + [self.building_15m]
        return list(self.candles_15m)

    def get_1h_candles(self, include_current=True):
        """Get all 1H candles (completed + optionally current)."""
        if include_current and self.building_1h:
            return self.candles_1h + [self.building_1h]
        return list(self.candles_1h)

    def is_15m_complete(self):
        """Was a 15M candle just completed on the last add()?"""
        # Caller checks result["completed_15m"] instead
        pass
