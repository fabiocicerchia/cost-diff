#!/usr/bin/env python3
"""cost-diff — which deploy moved the AWS bill.

cost-diff timeline --deploys-git .              # daily cost, steps, the deploy before each
cost-diff timeline --deploys-file deploys.csv --format json
cost-diff diff --last-month                     # the period-over-period report
"""

import argparse
import calendar
import csv
import fnmatch
import hashlib
import itertools
import json
import math
import shutil
import statistics
import subprocess
import sys
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, cast

# Cost Explorer is a global service: its only endpoint lives in us-east-1,
# whatever region the caller's profile points at.
CE_REGION = "us-east-1"

SERVICE_DIMENSION = "SERVICE"
USAGE_TYPE_DIMENSION = "USAGE_TYPE"
GROUP_DIMENSIONS = [SERVICE_DIMENSION, "LINKED_ACCOUNT", USAGE_TYPE_DIMENSION, "REGION"]

DEFAULT_METRIC = "UnblendedCost"
COST_METRICS = [
    DEFAULT_METRIC,
    "BlendedCost",
    "NetUnblendedCost",
    "AmortizedCost",
    "NetAmortizedCost",
]

# A row is flagged when the swing is big enough to care about and sits further
# than this tolerance away from what the business-day-count difference explains.
ANOMALY_MIN_PCT = 10
ANOMALY_TOLERANCE_PCT = 20


# {group: cost in USD} for one period, as Cost Explorer reports it.
DECEMBER = 12
# Monday..Friday are 0..4, so anything below this is a business day.
SATURDAY = 5
_HTTP_TIMEOUT_SECONDS = 15
_SUBPROCESS_TIMEOUT_SECONDS = 60

Costs = dict[str, float]


class CostExplorer(Protocol):
    """The one Cost Explorer call this tool makes.

    A protocol rather than boto3's own client type: boto3 ships no annotations,
    and the tests pass a stub that has this method and nothing else. Writing it
    out also says what the tool needs from AWS -- one paginated call, no
    client-wide surface.
    """

    def get_cost_and_usage(self, **kwargs: Any) -> dict[str, Any]: ...


class CostDiffError(RuntimeError):
    """Anything the user can fix: a missing binary, an unreadable deploy file."""


def _ce_client() -> CostExplorer:
    """A live Cost Explorer client. Only the live paths call this."""
    # Only the live path needs boto3; the tests pass a client and must not
    # require it installed.
    import boto3  # noqa: PLC0415

    # boto3 ships no annotations for its client factory -- boto3-stubs types
    # one service per extra and leaves the rest Unknown, which is a dev
    # dependency and a 2,000-line overload set for one call. This is the single
    # place an untyped value crosses into the typed part of the tool, and the
    # protocol above says what it has to be.
    return cast(
        "CostExplorer",
        boto3.client("ce", region_name=CE_REGION),  # pyright: ignore[reportUnknownMemberType]
    )


@dataclass(frozen=True)
class Change:
    """One group's cost movement between the two periods."""

    group: str
    before: float
    after: float
    delta: float
    pct: float | None  # None when the group is new: no baseline to divide by
    anomaly: bool


# --------------------------------------------------------------------------
# Period diff: two Cost Explorer periods, what moved between them.
# --------------------------------------------------------------------------
def month_bounds(yyyy_mm: str) -> tuple[date, date]:
    y, m = (int(x) for x in yyyy_mm.split("-"))
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == DECEMBER else date(y, m + 1, 1)
    return start, end


def previous_month(yyyy_mm: str) -> str:
    y, m = (int(x) for x in yyyy_mm.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def fetch_costs(
    period: str,
    group_by: str = SERVICE_DIMENSION,
    client: CostExplorer | None = None,
    metric: str = DEFAULT_METRIC,
    filter_dimension: tuple[str, str] | None = None,
) -> Costs:
    """Return {group: cost_usd} for a YYYY-MM period from Cost Explorer.

    filter_dimension, if given, is a (key, value) pair restricting the query
    (e.g. narrowing a USAGE_TYPE breakdown to a single SERVICE).
    """
    if client is None:
        client = _ce_client()
    start, end = month_bounds(period)
    results: Costs = {}
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
            "Granularity": "MONTHLY",
            "Metrics": [metric],
            "GroupBy": [{"Type": "DIMENSION", "Key": group_by}],
        }
        if filter_dimension:
            key, value = filter_dimension
            kwargs["Filter"] = {"Dimensions": {"Key": key, "Values": [value]}}
        if token:
            kwargs["NextPageToken"] = token
        page = client.get_cost_and_usage(**kwargs)
        for result in page["ResultsByTime"]:
            for group in result.get("Groups", []):
                key = group["Keys"][0]
                amount = float(group["Metrics"][metric]["Amount"])
                results[key] = results.get(key, 0.0) + amount
        token = page.get("NextPageToken")
        if not token:
            return results


def weekday_count(yyyy_mm: str) -> int:
    """Number of Mon-Fri days in a YYYY-MM period."""
    y, m = (int(x) for x in yyyy_mm.split("-"))
    days_in_month = calendar.monthrange(y, m)[1]
    return sum(1 for d in range(1, days_in_month + 1) if date(y, m, d).weekday() < SATURDAY)


def build_diff(
    old: Costs,
    new: Costs,
    threshold_usd: float = 1.0,
    old_period: str | None = None,
    new_period: str | None = None,
) -> list[Change]:
    """Merge two cost maps into Change rows, biggest absolute mover first.

    If old_period/new_period are given, flags rows whose % change isn't
    explained by the difference in business-day count between the two
    periods (a naive but cheap anomaly hint).
    """
    weekday_ratio = None
    if old_period and new_period:
        old_weekdays = weekday_count(old_period)
        if old_weekdays:
            weekday_ratio = weekday_count(new_period) / old_weekdays
    rows: list[Change] = []
    for key in sorted(old.keys() | new.keys()):
        before, after = old.get(key, 0.0), new.get(key, 0.0)
        delta = after - before
        if abs(delta) < threshold_usd:
            continue
        pct = (delta / before * 100) if before else None
        anomaly = False
        if weekday_ratio is not None and pct is not None:
            expected_pct = (weekday_ratio - 1) * 100
            anomaly = abs(pct) > ANOMALY_MIN_PCT and abs(pct - expected_pct) > ANOMALY_TOLERANCE_PCT
        rows.append(Change(key, before, after, delta, pct, anomaly))
    rows.sort(key=lambda row: -abs(row.delta))
    return rows


def _totals(rows: list[Change]) -> tuple[float, float, float, str]:
    """(total_before, total_after, total_delta, trend arrow) across all rows."""
    total_before = sum(row.before for row in rows)
    total_after = sum(row.after for row in rows)
    total_delta = total_after - total_before
    arrow = "▲" if total_delta > 0 else "▼" if total_delta < 0 else "→"
    return total_before, total_after, total_delta, arrow


def _pct_str(row: Change) -> str:
    return f" ({row.pct:+.0f}%)" if row.pct is not None else " (new)"


def _signed_usd(amount: float) -> str:
    """`+$1,234` / `−$1,234` — U+2212 minus, not a hyphen, in every table."""
    return f"{'+' if amount > 0 else '−'}${abs(amount):,.0f}"


def _change_row(row: Change, flag: str = "") -> str:
    """One Markdown row, shared by the service table and the usage-type table."""
    change = _signed_usd(row.delta) + _pct_str(row) + flag
    return f"| {change} | {row.group} | ${row.before:,.0f} | ${row.after:,.0f} |"


def render(rows: list[Change], period: str, vs: str, top: int = 10) -> str:
    total_before, total_after, total_delta, arrow = _totals(rows)
    lines = [
        f"# AWS cost diff: {vs} → {period}",
        "",
        f"**Total: ${total_before:,.0f} → ${total_after:,.0f} ({arrow} ${abs(total_delta):,.0f})**",
        "",
        "| change | service | before | after |",
        "|---|---|---|---|",
    ]
    any_anomaly = False
    for row in rows[:top]:
        flag = ""
        if row.anomaly:
            flag = " ⚠"
            any_anomaly = True
        lines.append(_change_row(row, flag))
    hidden = len(rows) - top
    if hidden > 0:
        lines.append(f"\n…and {hidden} more changes above the threshold, not shown (see --top).")
    if any_anomaly:
        lines.append("\n⚠ = change not explained by the business-day-count difference between periods.")
    return "\n".join(lines)


def render_why(rows: list[Change], group_label: str, top: int = 5) -> str:
    """Render a USAGE_TYPE breakdown explaining why `group_label` moved."""
    lines = [
        f"\n### Why {group_label} moved (by usage type)",
        "",
        "| change | usage type | before | after |",
        "|---|---|---|---|",
    ]
    lines.extend(_change_row(row) for row in rows[:top])
    return "\n".join(lines)


def render_slack_blocks(rows: list[Change], period: str, vs: str, top: int = 10) -> dict[str, Any]:
    """Render the report as Slack Block Kit blocks (mrkdwn, not GFM)."""
    total_before, total_after, total_delta, arrow = _totals(rows)
    table_lines = [
        f"{_signed_usd(row.delta)}{' ⚠' if row.anomaly else ''} {row.group}: ${row.before:,.0f} → ${row.after:,.0f}"
        for row in rows[:top]
    ]
    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"AWS cost diff: {vs} → {period}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Total:* ${total_before:,.0f} → ${total_after:,.0f} ({arrow} ${abs(total_delta):,.0f})",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "```\n" + "\n".join(table_lines) + "\n```",
                },
            },
        ]
    }


def post_slack(webhook: str, payload: dict[str, Any]) -> None:
    if not webhook.startswith("https://"):
        raise ValueError("Slack webhook must be an https:// URL")
    body = json.dumps(payload).encode()
    req = urllib.request.Request(  # noqa: S310 — scheme checked above
        webhook, data=body, headers={"Content-Type": "application/json"}
    )
    # `nosec` is bandit's marker; ruff reads `noqa`. The https check above is
    # the reason either of them is here.
    urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS)  # noqa: S310 — scheme checked above


# --------------------------------------------------------------------------
# Timeline: daily cost, the steps in it, and the deploy each step followed.
# --------------------------------------------------------------------------

# The synthetic group holding every other group's cost, for the chart.
TOTAL_GROUP = "TOTAL"

DEFAULT_TIMELINE_DAYS = 60
DEFAULT_DEPLOY_WINDOW_HOURS = 24.0

MEDIAN_MAD = "median-mad"
PELT = "pelt"
DETECTION_METHODS = [MEDIAN_MAD, PELT]
METHOD_LABELS = {
    MEDIAN_MAD: "rolling median with a MAD threshold",
    PELT: "PELT (exact changepoints, L2 segment cost)",
}

# Turns a median absolute deviation into a standard deviation for normal-ish
# data. The series is daily cost, which is not normal, but the constant is what
# makes "4 sigma" mean the usual thing.
MAD_TO_SIGMA = 1.4826
# A flat series has a MAD of zero, which would make every cent an infinite
# number of sigmas. Floor the noise estimate at this share of the level.
NOISE_FLOOR_PCT = 2.0
_EPSILON_USD = 0.01
# Days of series either side of a transition used to read the level off.
# Three is enough for the median to ignore one odd day, and short enough
# that a gradual ramp cannot deliver its rise inside it.
_LOCAL_LEVEL_DAYS = 3

CONFIDENCE_NONE = "none"
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
# How isolated the deploy is in the window: one deploy is a name, three are a
# shortlist. Anything past this table is "low".
CONFIDENCE_BY_DEPLOY_COUNT = {0: CONFIDENCE_NONE, 1: CONFIDENCE_HIGH, 2: CONFIDENCE_MEDIUM}

# What the tool claims, said once and repeated in every output format.
TEMPORAL_DISCLAIMER = (
    "Attribution is temporal, not causal: the deploy preceded the step, which is not proof that it caused it."
)

# {group: {day: cost in USD}}, as Cost Explorer reports it day by day.
DailyCosts = dict[str, dict[date, float]]


@dataclass(frozen=True)
class DailyQuery:
    """One daily Cost Explorer query — also the cache key for its answer."""

    start: date
    end: date  # exclusive, as the API wants it
    metric: str = DEFAULT_METRIC
    group_by: str = SERVICE_DIMENSION
    tag_key: str | None = None  # a cost-allocation tag key, grouped alongside

    def key(self) -> str:
        canonical = json.dumps(
            {
                "start": self.start.isoformat(),
                "end": self.end.isoformat(),
                "metric": self.metric,
                "group_by": self.group_by,
                "tag_key": self.tag_key,
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class Deploy:
    """One deploy event, whatever source it came from."""

    when: datetime  # always tz-aware UTC
    label: str
    source: str
    revision: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class Step:
    """A level change in one group's daily cost, in dollars per day."""

    group: str
    day: date  # the first day at the new level
    before: float
    after: float
    delta: float
    score: float  # the size of the step in robust sigmas
    method: str

    @property
    def pct(self) -> float | None:
        """None when the group had no spend before: no baseline to divide by."""
        return (self.delta / self.before * 100) if self.before else None


@dataclass(frozen=True)
class Attribution:
    """A step and every deploy that landed in its window."""

    step: Step
    candidates: list[Deploy] = field(default_factory=list)  # newest first

    @property
    def deploy(self) -> Deploy | None:
        """The one deploy in the window, or None when there isn't exactly one.

        With several deploys in the window there is no way to tell them apart
        from the cost series alone, so the report lists them instead of picking.
        """
        return self.candidates[0] if len(self.candidates) == 1 else None

    @property
    def confidence(self) -> str:
        return CONFIDENCE_BY_DEPLOY_COUNT.get(len(self.candidates), CONFIDENCE_LOW)


@dataclass(frozen=True)
class DetectionConfig:
    """Every knob the step detector has, and what each one is worth."""

    method: str = MEDIAN_MAD
    window: int = 7  # days either side of a candidate step
    threshold: float = 4.0  # sigmas, median-mad only
    min_delta: float = 5.0  # dollars per day
    ramp_fraction: float = 0.6  # share of the level change due inside the transition
    transition_days: int = 2  # days a step is allowed to take to complete
    penalty: float = 3.0  # PELT only: multiples of sigma^2 * ln(n)

    def describe(self) -> str:
        if self.method == PELT:
            detail = f"penalty {self.penalty:g}·σ²·ln n, minimum segment {self.window}d"
        else:
            detail = f"window {self.window}d, threshold {self.threshold:g}σ"
        return (
            f"{METHOD_LABELS[self.method]} ({detail}). Steps under "
            f"${self.min_delta:,.0f}/day, and level changes that take longer than "
            f"{self.transition_days}d to complete, are not reported."
        )


@dataclass(frozen=True)
class ResponseCache:
    """Cost Explorer answers on disk — the only state the tool keeps.

    Opt-in, because it is a cache of billing data: each call costs $0.01, and
    re-running a 60-day timeline while tuning a threshold otherwise pays for
    the same 60 days again.
    """

    directory: Path
    ttl_hours: float = 24.0

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> DailyCosts | None:
        try:
            payload = json.loads(self._path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # a missing or corrupt entry is a miss, not an error
        stored_at = payload.get("stored_at")
        costs = payload.get("costs")
        if not isinstance(stored_at, (int, float)) or not isinstance(costs, dict):
            return None
        age_hours = (_utcnow().timestamp() - float(stored_at)) / 3600
        if age_hours > self.ttl_hours:
            return None
        return _decode_daily(cast("dict[str, dict[str, float]]", costs))

    def put(self, key: str, costs: DailyCosts) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"stored_at": _utcnow().timestamp(), "costs": _encode_daily(costs)}
        self._path(key).write_text(json.dumps(payload), encoding="utf-8")


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _encode_daily(costs: DailyCosts) -> dict[str, dict[str, float]]:
    return {group: {day.isoformat(): value for day, value in days.items()} for group, days in costs.items()}


def _decode_daily(payload: dict[str, dict[str, float]]) -> DailyCosts:
    return {
        group: {date.fromisoformat(day): float(value) for day, value in days.items()} for group, days in payload.items()
    }


def _tag_label(key: str) -> str:
    """Cost Explorer returns a tag group as `Key$value`; the value is the label."""
    if "$" not in key:
        return key
    name, _, value = key.partition("$")
    return value or f"{name}: untagged"


def fetch_daily_costs(
    query: DailyQuery,
    client: CostExplorer | None = None,
    cache: ResponseCache | None = None,
) -> DailyCosts:
    """Return {group: {day: cost_usd}} for the query's range.

    With a tag key the group label is `service / tag-value`: Cost Explorer
    allows two GroupBy keys, which is exactly one dimension plus one tag.
    """
    if cache is not None:
        hit = cache.get(query.key())
        if hit is not None:
            return hit
    if client is None:
        client = _ce_client()
    group_by: list[dict[str, str]] = [{"Type": "DIMENSION", "Key": query.group_by}]
    if query.tag_key:
        group_by.append({"Type": "TAG", "Key": query.tag_key})
    results: DailyCosts = {}
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "TimePeriod": {"Start": query.start.isoformat(), "End": query.end.isoformat()},
            "Granularity": "DAILY",
            "Metrics": [query.metric],
            "GroupBy": group_by,
        }
        if token:
            kwargs["NextPageToken"] = token
        page = client.get_cost_and_usage(**kwargs)
        for result in page["ResultsByTime"]:
            day = date.fromisoformat(result["TimePeriod"]["Start"])
            for group in result.get("Groups", []):
                label = " / ".join(_tag_label(key) for key in group["Keys"])
                amount = float(group["Metrics"][query.metric]["Amount"])
                bucket = results.setdefault(label, {})
                bucket[day] = bucket.get(day, 0.0) + amount
        token = page.get("NextPageToken")
        if not token:
            break
    if cache is not None:
        cache.put(query.key(), results)
    return results


def day_range(start: date, end: date) -> list[date]:
    """Every day in [start, end) — the days the series is indexed by."""
    return [start + timedelta(days=offset) for offset in range((end - start).days)]


def densify(costs: DailyCosts, days: Sequence[date]) -> dict[str, list[float]]:
    """{group: cost per day} over exactly `days`, missing days read as $0.

    A gap is a real zero to a step detector: a service that stops billing has
    stepped down, and leaving the day out would hide that.
    """
    series = {group: [values.get(day, 0.0) for day in days] for group, values in costs.items()}
    series[TOTAL_GROUP] = [sum(values.get(day, 0.0) for values in costs.values()) for day in days]
    return series


# --------------------------------------------------------------------------
# Step detection. Two methods, both explainable, neither a dependency.
# --------------------------------------------------------------------------


def _mad(values: Sequence[float]) -> float:
    """Median absolute deviation: a spread that a single spike cannot inflate."""
    middle = statistics.median(values)
    return statistics.median([abs(value - middle) for value in values])


def _noise_scale(before: Sequence[float], after: Sequence[float]) -> float:
    """The bigger of the two windows' noise, floored so flat series stay finite."""
    scale = max(_mad(before), _mad(after)) * MAD_TO_SIGMA
    level = max(abs(statistics.median(before)), abs(statistics.median(after)))
    return max(scale, level * NOISE_FLOOR_PCT / 100, _EPSILON_USD)


def _noise_sigma(values: Sequence[float]) -> float:
    """Day-to-day noise, estimated from first differences rather than levels.

    A series with a step in it has a huge spread and small day-to-day noise;
    differencing measures the second, which is what a step has to beat.
    """
    diffs = [abs(second - first) for first, second in itertools.pairwise(values)]
    if not diffs:
        return _EPSILON_USD
    return max(statistics.median(diffs) * MAD_TO_SIGMA / math.sqrt(2), _EPSILON_USD)


def _sign(value: float) -> float:
    return 1.0 if value >= 0 else -1.0


def _is_step_not_ramp(values: Sequence[float], index: int, delta: float, config: DetectionConfig) -> bool:
    """True when the level change lands in the transition instead of trickling in.

    A step reaches its new level in a day or two; a ramp gets there a little at
    a time. So compare the change across the transition itself with the change
    across a horizon several times longer: a step delivers all of it in the
    transition, while a line sloping through the horizon delivers only the few
    days' worth the transition is wide, however steep it is.

    Both levels are medians of a few days rather than single readings — one
    spike either side of the transition should not be able to make a ramp look
    like a step, or the other way round.
    """
    transition_end = index + config.transition_days - 1
    horizon = 2 * config.window
    before = values[max(0, index - _LOCAL_LEVEL_DAYS) : index]
    after = values[transition_end : transition_end + _LOCAL_LEVEL_DAYS]
    long_before = values[max(0, index - horizon) : index]
    long_after = values[transition_end : transition_end + horizon]
    if not before or not after:
        return False
    local = statistics.median(after) - statistics.median(before)
    over_horizon = statistics.median(long_after) - statistics.median(long_before)
    # Whichever is larger: a step has to account for the level change the
    # detector found *and* for everything the series does around it.
    scale = max(abs(over_horizon), abs(delta), _EPSILON_USD)
    return local * _sign(delta) / scale >= config.ramp_fraction


def _keep_strongest(
    found: list[tuple[int, float, float, float]], min_gap: int
) -> list[tuple[int, float, float, float]]:
    """One step per neighbourhood: the strongest, not each day it shows up on."""
    kept: list[tuple[int, float, float, float]] = []
    for candidate in sorted(found, key=lambda item: -item[3]):
        if all(abs(candidate[0] - other[0]) >= min_gap for other in kept):
            kept.append(candidate)
    return sorted(kept)


def _median_mad_steps(values: Sequence[float], config: DetectionConfig) -> list[tuple[int, float, float, float]]:
    """Compare the median of the days before each day with the days after."""
    window = config.window
    found: list[tuple[int, float, float, float]] = []
    for index in range(window, len(values) - window + 1):
        before, after = values[index - window : index], values[index : index + window]
        level_before, level_after = statistics.median(before), statistics.median(after)
        delta = level_after - level_before
        if abs(delta) < config.min_delta:
            continue
        score = abs(delta) / _noise_scale(before, after)
        if score < config.threshold:
            continue
        if not _is_step_not_ramp(values, index, delta, config):
            continue
        found.append((index, level_before, level_after, score))
    return _keep_strongest(found, window)


def _pelt(values: Sequence[float], penalty: float, min_size: int) -> list[int]:
    """Minimal PELT: the optimal segmentation under an L2 cost plus a penalty.

    Optimal partitioning with the pruning step that makes it PELT — a start
    point that is already worse than the best path to `end` can never win
    later, so it is dropped for good.
    """
    count = len(values)
    sums = [0.0] * (count + 1)
    squares = [0.0] * (count + 1)
    for index, value in enumerate(values):
        sums[index + 1] = sums[index] + value
        squares[index + 1] = squares[index] + value * value

    def segment_cost(start: int, end: int) -> float:
        """Sum of squared deviations from the segment mean, from prefix sums."""
        span = end - start
        total = sums[end] - sums[start]
        return (squares[end] - squares[start]) - total * total / span

    best = [math.inf] * (count + 1)
    best[0] = -penalty
    previous = [0] * (count + 1)
    starts = [0]
    for end in range(min_size, count + 1):
        for start in starts:
            if end - start < min_size:
                continue
            cost = best[start] + segment_cost(start, end) + penalty
            if cost < best[end]:
                best[end], previous[end] = cost, start
        if math.isinf(best[end]):
            continue
        starts = [s for s in starts if best[s] + segment_cost(s, end) <= best[end]]
        starts.append(end)

    breaks: list[int] = []
    cursor = count
    while cursor > 0:
        start = previous[cursor]
        if start == 0:
            break
        breaks.append(start)
        cursor = start
    return sorted(breaks)


def _pelt_steps(values: Sequence[float], config: DetectionConfig) -> list[tuple[int, float, float, float]]:
    """Score PELT's changepoints the same way, so both methods filter alike."""
    sigma = _noise_sigma(values)
    penalty = config.penalty * sigma * sigma * math.log(len(values))
    bounds = [0, *_pelt(values, penalty, config.window), len(values)]
    found: list[tuple[int, float, float, float]] = []
    for position in range(1, len(bounds) - 1):
        index = bounds[position]
        level_before = statistics.fmean(values[bounds[position - 1] : index])
        level_after = statistics.fmean(values[index : bounds[position + 1]])
        delta = level_after - level_before
        if abs(delta) < config.min_delta:
            continue
        if not _is_step_not_ramp(values, index, delta, config):
            continue
        found.append((index, level_before, level_after, abs(delta) / sigma))
    return found


def _refine_onset(values: Sequence[float], index: int, before: float, after: float, config: DetectionConfig) -> int:
    """The first day cost actually moved, within a transition of the candidate.

    A rolling median reports a step as soon as most of its window sits at the
    new level, which can be a day before the level changed; PELT can land a day
    late for the mirror-image reason. Both are fixed by walking the candidate's
    neighbourhood and taking the first day that is at least halfway to the new
    level — that is the day a deploy has to precede.
    """
    midpoint = (before + after) / 2
    direction = _sign(after - before)
    for candidate in range(
        max(0, index - config.transition_days), min(len(values), index + config.transition_days + 1)
    ):
        if (values[candidate] - midpoint) * direction >= 0:
            return candidate
    return index


def detect_steps(
    group: str,
    days: Sequence[date],
    values: Sequence[float],
    config: DetectionConfig | None = None,
) -> list[Step]:
    """Find the days `group`'s daily cost moved to a new level and stayed there."""
    config = config or DetectionConfig()
    if len(values) < 2 * config.window:
        return []  # not enough days either side of anything to call it a step
    found = _pelt_steps(values, config) if config.method == PELT else _median_mad_steps(values, config)
    return [
        Step(
            group,
            days[_refine_onset(values, index, before, after, config)],
            before,
            after,
            after - before,
            score,
            config.method,
        )
        for index, before, after, score in found
    ]


# --------------------------------------------------------------------------
# Attribution: which deploy came before the step.
# --------------------------------------------------------------------------


def step_onset(step: Step) -> datetime:
    """Midnight UTC at the start of the step day — where the lag is measured from."""
    return datetime(step.day.year, step.day.month, step.day.day, tzinfo=timezone.utc)


def lag_hours(step: Step, deploy: Deploy) -> float:
    """Hours from the deploy to the start of the step day.

    Negative when the deploy landed during the step day itself, which a deploy
    can do and still be the cause: a mid-afternoon deploy only bills a part day.
    """
    return (step_onset(step) - deploy.when).total_seconds() / 3600


def attribute(
    steps: Iterable[Step],
    deploys: Iterable[Deploy],
    window_hours: float = DEFAULT_DEPLOY_WINDOW_HOURS,
) -> list[Attribution]:
    """Pair each step with every deploy in its window, newest first.

    The window runs from `window_hours` before the step day to the end of it.
    Both halves earn their place: a deploy the evening before shows up as a full
    day of new cost, and a deploy at noon shows up as half of one.
    """
    ordered = sorted(deploys, key=lambda deploy: deploy.when)
    attributions: list[Attribution] = []
    for step in steps:
        onset = step_onset(step)
        earliest = onset - timedelta(hours=window_hours)
        latest = onset + timedelta(days=1)
        candidates = [deploy for deploy in ordered if earliest <= deploy.when < latest]
        attributions.append(Attribution(step, list(reversed(candidates))))
    return attributions


# --------------------------------------------------------------------------
# Deploy sources. Four, because everyone's deploy log lives somewhere else —
# and the last one is a file, so nobody is locked out.
# --------------------------------------------------------------------------

GIT_SOURCE = "git"
GITHUB_SOURCE = "github"
ARGOCD_SOURCE = "argocd"
FILE_SOURCE = "file"

# How many deployments to read from the GitHub API: one page, no pagination,
# because a timeline is 60 days and a token is rate-limited.
_GITHUB_DEPLOYMENT_PAGE = 100

_TIME_KEYS = ("timestamp", "time", "when", "date", "datetime", "deployed_at", "created_at", "at")
_LABEL_KEYS = ("label", "name", "tag", "version", "release", "ref", "message")
_REVISION_KEYS = ("revision", "sha", "commit")
_URL_KEYS = ("url", "link", "html_url")
# The columns a headerless CSV or a JSON pair is read as, in order.
_FILE_COLUMNS: tuple[str, ...] = ("timestamp", "label", "revision", "url")


def _binary(name: str) -> str:
    """Absolute path to a required command, or a message naming what to install."""
    found = shutil.which(name)
    if found is None:
        raise CostDiffError(f"{name} is not on PATH — install it, or use --deploys-file")
    return found


def _run(command: list[str], stdin: str | None = None, cwd: Path | None = None) -> str:
    """Run a fixed argument list and return stdout, with the failure spelled out."""
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell, path from shutil.which
            command,
            capture_output=True,
            text=True,
            check=True,
            input=stdin,
            cwd=cwd,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise CostDiffError(f"{Path(command[0]).name} timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip().splitlines()
        raise CostDiffError(f"{Path(command[0]).name} failed: {detail[-1] if detail else exc}") from exc
    return completed.stdout


def _parse_time(text: str) -> datetime:
    """Any reasonable timestamp into an aware UTC datetime."""
    raw = text.strip()
    if not raw:
        raise CostDiffError("empty deploy timestamp")
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    if raw.endswith(("Z", "z")):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise CostDiffError(f"unreadable deploy timestamp {text!r} — want ISO 8601, e.g. 2026-09-02T18:00:00Z") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)  # naive timestamps are read as UTC
    return parsed.astimezone(timezone.utc)


def _load_json(text: str, what: str) -> Any:
    try:
        return json.loads(text)
    except ValueError as exc:
        raise CostDiffError(f"could not read {what} as JSON") from exc


def _json_list(payload: Any, wrapper_key: str, complaint: str) -> list[Any]:
    """A JSON list, whether it came bare or wrapped in an object under one key."""
    entries: Any = cast("dict[str, Any]", payload).get(wrapper_key, []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise CostDiffError(complaint)
    return cast("list[Any]", entries)


def _pick(row: dict[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return None


def deploys_from_git(repo: Path, pattern: str = "*") -> list[Deploy]:
    """Tags in a checkout, dated by when they were created.

    Annotated tags carry their own date; a lightweight tag borrows its commit's,
    which is the date the code landed rather than the date it shipped.
    """
    output = _run(
        [
            _binary("git"),
            "-C",
            str(repo),
            "for-each-ref",
            "--sort=creatordate",
            "--format=%(refname:short)%09%(creatordate:iso-strict)%09%(objectname)",
            "refs/tags",
        ]
    )
    deploys: list[Deploy] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:  # noqa: PLR2004 — the three fields the format asks for
            continue
        name, when, sha = parts
        if not fnmatch.fnmatch(name, pattern):
            continue
        deploys.append(Deploy(_parse_time(when), name, GIT_SOURCE, sha))
    return deploys


def deploys_from_github(repo: str) -> list[Deploy]:
    """The GitHub Deployments API, through `gh` so it uses the caller's auth."""
    payload = _load_json(
        _run([_binary("gh"), "api", f"repos/{repo}/deployments?per_page={_GITHUB_DEPLOYMENT_PAGE}"]),
        "GitHub deployments",
    )
    if not isinstance(payload, list):
        raise CostDiffError(f"unexpected GitHub deployments payload for {repo}")
    deploys: list[Deploy] = []
    for item in cast("list[dict[str, Any]]", payload):
        environment = str(item.get("environment") or "")
        ref = str(item.get("ref") or "")
        label = "/".join(part for part in (environment, ref) if part) or f"deployment {item.get('id')}"
        deploys.append(
            Deploy(
                _parse_time(str(item.get("created_at", ""))),
                label,
                GITHUB_SOURCE,
                _pick(item, _REVISION_KEYS),
                _pick(item, _URL_KEYS),
            )
        )
    return deploys


def deploys_from_argocd(app: str) -> list[Deploy]:
    """`argocd app history <app> -o json` — the sync history Argo CD already keeps."""
    payload = _load_json(_run([_binary("argocd"), "app", "history", app, "-o", "json"]), "Argo CD history")
    entries = _json_list(payload, "items", f"unexpected Argo CD history payload for {app}")
    deploys: list[Deploy] = []
    for item in cast("list[dict[str, Any]]", entries):
        when = _pick(item, ("deployedAt", "deployStartedAt", *_TIME_KEYS))
        if when is None:
            continue
        revision = _pick(item, _REVISION_KEYS)
        label = f"{app}@{revision[:7]}" if revision else f"{app}#{item.get('id')}"
        deploys.append(Deploy(_parse_time(when), label, ARGOCD_SOURCE, revision))
    return deploys


def _deploy_from_row(row: dict[str, Any], where: str) -> Deploy:
    when = _pick(row, _TIME_KEYS)
    if when is None:
        raise CostDiffError(f"{where}: no timestamp column — want one of {', '.join(_TIME_KEYS[:4])}")
    label = _pick(row, _LABEL_KEYS) or when
    return Deploy(_parse_time(when), label, FILE_SOURCE, _pick(row, _REVISION_KEYS), _pick(row, _URL_KEYS))


def _is_time(text: str) -> bool:
    try:
        _parse_time(text)
    except CostDiffError:
        return False
    return True


def _rows_from_csv(text: str, where: str) -> list[dict[str, Any]]:
    """Rows from a CSV, with or without a header line.

    A header is recognised by naming a timestamp column; a file with no header
    starts with one. Anything else is a file whose first column this tool has no
    way to read, and saying so beats reading the header row as a deploy.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = next(csv.reader([lines[0]]))
    if any(cell.strip().lower() in _TIME_KEYS for cell in header):
        return [dict(row) for row in csv.DictReader(lines)]
    if not header or not _is_time(header[0]):
        raise CostDiffError(
            f"{where}: no timestamp column — give the file a header naming one of "
            f"{', '.join(_TIME_KEYS[:4])}, or put the timestamp first"
        )
    return [dict(zip(_FILE_COLUMNS, row, strict=False)) for row in csv.reader(lines) if row]


def deploys_from_file(path: Path) -> list[Deploy]:
    """A CSV or JSON list of timestamp + label — the escape hatch for everyone else.

    JSON may be a list of objects or a list of [timestamp, label] pairs; CSV may
    have a header or be timestamp,label[,revision[,url]] columns.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CostDiffError(f"cannot read deploy file {path}: {exc}") from exc
    where = str(path)
    if path.suffix.lower() == ".json" or text.lstrip().startswith(("[", "{")):
        entries = _json_list(_load_json(text, where), "deploys", f"{where}: want a JSON list of deploys")
        rows: list[dict[str, Any]] = [
            dict(zip(_FILE_COLUMNS, cast("list[Any]", item), strict=False))
            if isinstance(item, list)
            else cast("dict[str, Any]", item)
            for item in entries
        ]
    else:
        rows = _rows_from_csv(text, where)
    return [_deploy_from_row(row, where) for row in rows]


def load_deploys(args: argparse.Namespace) -> list[Deploy]:
    """Whichever source the flags picked, filtered and sorted."""
    if args.deploys_git is not None:
        deploys = deploys_from_git(Path(args.deploys_git), args.tag_pattern)
    elif args.deploys_github:
        deploys = deploys_from_github(args.deploys_github)
    elif args.deploys_argocd:
        deploys = deploys_from_argocd(args.deploys_argocd)
    elif args.deploys_file:
        deploys = deploys_from_file(Path(args.deploys_file))
    else:
        return []
    matched = [deploy for deploy in deploys if fnmatch.fnmatch(deploy.label, args.deploy_match)]
    return sorted(matched, key=lambda deploy: deploy.when)


# --------------------------------------------------------------------------
# Rendering: Markdown, a chart, JSON. Same numbers, three readers.
# --------------------------------------------------------------------------

MARKDOWN_FORMAT = "markdown"
JSON_FORMAT = "json"
OUTPUT_FORMATS = [MARKDOWN_FORMAT, JSON_FORMAT]

ASCII_CHART = "ascii"
MERMAID_CHART = "mermaid"
NO_CHART = "none"
CHART_KINDS = [ASCII_CHART, MERMAID_CHART, NO_CHART]

_BLOCKS = " ▁▂▃▄▅▆▇"
_CHART_GUTTER = 10
_MAX_CHART_LEGEND = 12
_HOURS_PER_DAY = 24
_LABEL_SPACE = 22


@dataclass(frozen=True)
class TimelineReport:
    """Everything a renderer needs, assembled once."""

    query: DailyQuery
    config: DetectionConfig
    window_hours: float
    days: list[date]
    series: dict[str, list[float]]
    attributions: list[Attribution]
    deploys: list[Deploy]

    def chart_series(self, group: str) -> list[float]:
        if group not in self.series:
            known = ", ".join(sorted(self.series)[:10])
            raise CostDiffError(f"no series for {group!r}; try one of: {known}")
        return self.series[group]


def _iso_z(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _hours(value: float) -> str:
    if value < 1:
        return "<1h"
    if value < 2 * _HOURS_PER_DAY:
        return f"{value:.0f}h"
    return f"{value / _HOURS_PER_DAY:.1f}d"


def _per_day(amount: float) -> str:
    return f"{_signed_usd(amount)}/day"


def _deploy_phrase(step: Step, deploy: Deploy) -> str:
    """How the one deploy in the window sits against the step day."""
    lag = lag_hours(step, deploy)
    if lag >= 0:
        return f"{_hours(lag)} after `{deploy.label}`"
    return f"with `{deploy.label}` {_hours(-lag)} into that day"


def _confidence_phrase(attribution: Attribution) -> str:
    count = len(attribution.candidates)
    if count == 0:
        return "no deploy in the window — unattributed"
    if count == 1:
        return "one deploy in window, high confidence"
    return f"{count} deploys in window, {attribution.confidence} confidence — listed, not guessed"


def _headline(attribution: Attribution) -> str:
    step = attribution.step
    head = f"**{_per_day(step.delta)} in {step.group} starting {step.day.isoformat()}**"
    deploy = attribution.deploy
    if deploy is not None:
        head += f", {_deploy_phrase(step, deploy)}"
    return f"{head} — {_confidence_phrase(attribution)}."


def _level_line(step: Step) -> str:
    pct = f" ({step.pct:+.0f}%)" if step.pct is not None else " (from nothing)"
    return f"${step.before:,.0f}/day → ${step.after:,.0f}/day{pct}, {step.score:.1f}σ over the window's noise"


def _deploy_line(step: Step, deploy: Deploy) -> str:
    lag = lag_hours(step, deploy)
    when = f"{_hours(lag)} before the step day" if lag >= 0 else f"{_hours(-lag)} into the step day"
    parts = [f"`{deploy.label}`", _iso_z(deploy.when), deploy.source, when]
    if deploy.revision:
        parts.insert(2, f"`{deploy.revision[:7]}`")
    return " — ".join(parts[:2]) + " (" + ", ".join(parts[2:]) + ")"


def render_timeline_entry(attribution: Attribution) -> str:
    """One step as a Markdown bullet, with its evidence underneath."""
    lines = [f"- {_headline(attribution)}", f"  - {_level_line(attribution.step)}"]
    lines.extend(f"  - {_deploy_line(attribution.step, deploy)}" for deploy in attribution.candidates)
    return "\n".join(lines)


def _chart_marker_row(days: Sequence[date], deploys: Iterable[Deploy]) -> list[str]:
    marker = [" "] * len(days)
    for deploy in deploys:
        index = (deploy.when.date() - days[0]).days
        if 0 <= index < len(marker):
            marker[index] = "▲"
    return marker


def render_ascii_chart(
    days: Sequence[date],
    values: Sequence[float],
    deploys: Sequence[Deploy],
    title: str,
    height: int = 10,
) -> str:
    """A column chart in a fenced block, with a ▲ under every deploy day."""
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    columns = [((value - low) / span * height) for value in values]
    lines = ["```text", title, ""]
    for row in range(height, 0, -1):
        cells: list[str] = []
        for filled in columns:
            full = int(filled)
            if full >= row:
                cells.append("█")
            elif full == row - 1 and int((filled - full) * len(_BLOCKS)) > 0:
                cells.append(_BLOCKS[int((filled - full) * len(_BLOCKS))])
            else:
                cells.append(" ")
        label = f"{high:,.0f}" if row == height else (f"{low:,.0f}" if row == 1 else "")
        lines.append(f"{label:>8} ┤{''.join(cells)}")
    lines.append(f"{'':>8} └{'─' * len(values)}")
    lines.append((" " * _CHART_GUTTER + "".join(_chart_marker_row(days, deploys))).rstrip())
    if len(days) >= _LABEL_SPACE:
        gap = len(days) - _LABEL_SPACE + 2
        lines.append(" " * _CHART_GUTTER + days[0].isoformat() + " " * gap + days[-1].isoformat())
    else:
        lines.append(" " * _CHART_GUTTER + f"{days[0].isoformat()} → {days[-1].isoformat()}")
    in_range = [deploy for deploy in deploys if days[0] <= deploy.when.date() <= days[-1]]
    legend = " " * (_CHART_GUTTER + 1)
    lines.extend(
        f"{legend}▲ {deploy.when.date().isoformat()}  {deploy.label}" for deploy in in_range[:_MAX_CHART_LEGEND]
    )
    if len(in_range) > _MAX_CHART_LEGEND:
        lines.append(f"{legend}… and {len(in_range) - _MAX_CHART_LEGEND} more deploys")
    lines.append("```")
    return "\n".join(lines)


def render_mermaid_chart(
    days: Sequence[date],
    values: Sequence[float],
    deploys: Sequence[Deploy],
    title: str,
    height: int = 10,  # unused: the two chart renderers share one signature
) -> str:
    """The same series as a Mermaid xychart, deploy days marked in the axis."""
    marker = _chart_marker_row(days, deploys)
    labels = ", ".join(f'"{day.day:02d}{mark.strip()}"' for day, mark in zip(days, marker, strict=True))
    top = math.ceil(max(values) * 1.1) or 1
    return "\n".join(
        [
            "```mermaid",
            "xychart-beta",
            f'    title "{title} (▲ = deploy)"',
            f"    x-axis [{labels}]",
            f'    y-axis "USD/day" 0 --> {top}',
            f"    line [{', '.join(f'{value:.2f}' for value in values)}]",
            "```",
            "",
            *(
                f"- ▲ {deploy.when.date().isoformat()} — `{deploy.label}`"
                for deploy in deploys
                if days[0] <= deploy.when.date() <= days[-1]
            ),
        ]
    )


def render_chart(report: TimelineReport, kind: str, group: str, height: int = 10) -> str:
    values = report.chart_series(group)
    title = f"{report.query.metric} per day — {group}"
    if kind == MERMAID_CHART:
        return render_mermaid_chart(report.days, values, report.deploys, title, height)
    return render_ascii_chart(report.days, values, report.deploys, title, height)


def _source_summary(report: TimelineReport) -> str:
    if not report.deploys:
        return "No deploys given — steps are reported unattributed (see --deploys-*)."
    sources = sorted({deploy.source for deploy in report.deploys})
    return (
        f"{len(report.deploys)} deploys from {', '.join(sources)}, "
        f"attributed within {report.window_hours:g}h. {TEMPORAL_DISCLAIMER}"
    )


def render_timeline(
    report: TimelineReport, chart: str = ASCII_CHART, chart_group: str = TOTAL_GROUP, height: int = 10
) -> str:
    """The whole timeline as Markdown: what moved, after what, how sure."""
    grouping = report.query.group_by + (f" and tag {report.query.tag_key}" if report.query.tag_key else "")
    last_day = report.days[-1].isoformat() if report.days else report.query.end.isoformat()
    lines = [
        f"# AWS cost timeline: {report.query.start.isoformat()} → {last_day}",
        "",
        f"Daily {report.query.metric} from Cost Explorer, grouped by {grouping}.",
        f"Steps: {report.config.describe()}",
        _source_summary(report),
        "",
        "## Steps",
        "",
    ]
    if report.attributions:
        lines.extend(render_timeline_entry(attribution) for attribution in report.attributions)
    else:
        lines.append(
            f"No step above ${report.config.min_delta:,.0f}/day in "
            f"{len(report.days)} days — the bill moved gradually or not at all."
        )
    if chart != NO_CHART:
        lines.extend(["", "## Series", "", render_chart(report, chart, chart_group, height)])
    return "\n".join(lines)


def _deploy_json(deploy: Deploy) -> dict[str, Any]:
    return {
        "when": _iso_z(deploy.when),
        "label": deploy.label,
        "source": deploy.source,
        "revision": deploy.revision,
        "url": deploy.url,
    }


def timeline_json(report: TimelineReport) -> dict[str, Any]:
    """The same report as data: every number the Markdown shows, and the series."""
    charted = {TOTAL_GROUP, *(attribution.step.group for attribution in report.attributions)}
    return {
        "generated_at": _iso_z(_utcnow()),
        "range": {"start": report.query.start.isoformat(), "end": report.query.end.isoformat()},
        "metric": report.query.metric,
        "group_by": report.query.group_by,
        "tag_key": report.query.tag_key,
        "detection": {
            "method": report.config.method,
            "method_label": METHOD_LABELS[report.config.method],
            "window_days": report.config.window,
            "threshold_sigma": report.config.threshold,
            "min_delta_usd_per_day": report.config.min_delta,
            "ramp_fraction": report.config.ramp_fraction,
            "transition_days": report.config.transition_days,
        },
        "attribution": {"window_hours": report.window_hours, "basis": TEMPORAL_DISCLAIMER},
        "steps": [
            {
                "group": attribution.step.group,
                "day": attribution.step.day.isoformat(),
                "before_usd_per_day": round(attribution.step.before, 4),
                "after_usd_per_day": round(attribution.step.after, 4),
                "delta_usd_per_day": round(attribution.step.delta, 4),
                "pct": round(attribution.step.pct, 2) if attribution.step.pct is not None else None,
                "score_sigma": round(attribution.step.score, 2),
                "method": attribution.step.method,
                "confidence": attribution.confidence,
                "deploys": [
                    {**_deploy_json(deploy), "lag_hours": round(lag_hours(attribution.step, deploy), 2)}
                    for deploy in attribution.candidates
                ],
            }
            for attribution in report.attributions
        ],
        "deploys": [_deploy_json(deploy) for deploy in report.deploys],
        "days": [day.isoformat() for day in report.days],
        "series": {
            group: [round(value, 4) for value in values] for group, values in report.series.items() if group in charted
        },
    }


# --------------------------------------------------------------------------
# Posting a timeline entry back on the pull request the deploy came from.
# --------------------------------------------------------------------------


def render_pr_comment(attribution: Attribution, report: TimelineReport) -> str:
    """What gets posted on the PR: the entry, and what it does and doesn't claim."""
    return "\n".join(
        [
            f"### cost-diff: {_headline(attribution).replace('**', '')}",
            "",
            f"- {_level_line(attribution.step)}",
            *(f"- {_deploy_line(attribution.step, deploy)}" for deploy in attribution.candidates),
            "",
            f"Detected with {METHOD_LABELS[attribution.step.method]} over "
            f"{len(report.days)} days of daily Cost Explorer data. {TEMPORAL_DISCLAIMER}",
        ]
    )


def pr_for_revision(repo: str, revision: str) -> int | None:
    """The pull request a commit landed in, or None if it landed straight on a branch."""
    payload = _load_json(_run([_binary("gh"), "api", f"repos/{repo}/commits/{revision}/pulls"]), "pull requests")
    if not isinstance(payload, list) or not payload:
        return None
    first = cast("dict[str, Any]", payload[0])
    number = first.get("number")
    return int(number) if isinstance(number, int) else None


def post_pr_comment(repo: str, number: int, body: str) -> None:
    _run([_binary("gh"), "pr", "comment", str(number), "--repo", repo, "--body-file", "-"], stdin=body)


def comment_on_pull_requests(report: TimelineReport, repo: str, dry_run: bool = False) -> list[str]:
    """Post each confidently attributed step on the PR its deploy points at.

    Only steps with a single deploy in the window: with two candidates there is
    no one PR to tell, and a comment on both would be a guess wearing a number.
    """
    notes: list[str] = []
    for attribution in report.attributions:
        deploy = attribution.deploy
        step = attribution.step
        if deploy is None:
            notes.append(f"{step.group} {step.day}: {len(attribution.candidates)} deploys in window, no comment posted")
            continue
        if not deploy.revision:
            notes.append(f"{step.group} {step.day}: `{deploy.label}` has no revision to look a PR up by")
            continue
        number = pr_for_revision(repo, deploy.revision)
        if number is None:
            notes.append(f"{step.group} {step.day}: no pull request points at `{deploy.label}`")
            continue
        body = render_pr_comment(attribution, report)
        if dry_run:
            notes.append(f"{step.group} {step.day}: would comment on {repo}#{number}:\n{body}")
            continue
        post_pr_comment(repo, number, body)
        notes.append(f"{step.group} {step.day}: commented on {repo}#{number}")
    return notes


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

DIFF_COMMAND = "diff"
TIMELINE_COMMAND = "timeline"


def _add_diff_parser(subparsers: Any) -> None:
    """The original period-over-period report, now a subcommand."""
    parser = cast(
        "argparse.ArgumentParser",
        subparsers.add_parser(
            DIFF_COMMAND,
            help="diff two Cost Explorer periods (the original report)",
            description="Diff two AWS Cost Explorer periods into what changed, biggest mover first.",
        ),
    )
    period_group = parser.add_mutually_exclusive_group(required=True)
    period_group.add_argument(
        "--last-month",
        action="store_true",
        help="previous full month vs the one before",
    )
    period_group.add_argument("--period", metavar="YYYY-MM", help="period to analyze")
    parser.add_argument(
        "--vs",
        metavar="YYYY-MM",
        help="baseline period (default: month before --period)",
    )
    parser.add_argument(
        "--group",
        default=SERVICE_DIMENSION,
        choices=GROUP_DIMENSIONS,
    )
    parser.add_argument(
        "--metric",
        default=DEFAULT_METRIC,
        choices=COST_METRICS,
        help="Cost Explorer metric; Net* nets out credits/refunds, "
        "Amortized* spreads RI/Savings Plan cost over its term",
    )
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=1.0, help="ignore changes under $N")
    parser.add_argument("--slack", metavar="WEBHOOK", help="post the report to Slack")
    parser.add_argument(
        "--why",
        action="store_true",
        help="drill down the biggest mover by USAGE_TYPE (only with --group SERVICE)",
    )


def _add_deploy_source_flags(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--deploys-git",
        metavar="PATH",
        nargs="?",
        const=".",
        help="tags in a git checkout, dated by when they were created",
    )
    source.add_argument("--deploys-github", metavar="OWNER/REPO", help="the GitHub Deployments API, via gh")
    source.add_argument("--deploys-argocd", metavar="APP", help="argocd app history, via the argocd CLI")
    source.add_argument("--deploys-file", metavar="PATH", help="a CSV or JSON list of timestamp + label")
    parser.add_argument(
        "--tag-pattern",
        default="*",
        metavar="GLOB",
        help="which git tags count as deploys (default: all)",
    )
    parser.add_argument(
        "--deploy-match",
        default="*",
        metavar="GLOB",
        help="keep only deploys whose label matches (e.g. 'production/*')",
    )


def _add_detection_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--method",
        default=MEDIAN_MAD,
        choices=DETECTION_METHODS,
        help="step detection: rolling median + MAD threshold, or PELT changepoints",
    )
    parser.add_argument("--window-days", type=int, default=7, help="days either side of a step (default 7)")
    parser.add_argument(
        "--threshold-sigma",
        type=float,
        default=4.0,
        help="how far past the window's noise a step has to be (default 4)",
    )
    parser.add_argument("--min-step", type=float, default=5.0, help="ignore steps under $N/day (default 5)")
    parser.add_argument(
        "--ramp-fraction",
        type=float,
        default=0.6,
        help="share of the level change that must land inside the transition (default 0.6) — "
        "this is what keeps a gradual ramp from being reported as a step",
    )
    parser.add_argument(
        "--transition-days",
        type=int,
        default=2,
        help="days a step may take to complete (default 2: a deploy mid-day bills a part day)",
    )
    parser.add_argument("--pelt-penalty", type=float, default=3.0, help="PELT penalty, in σ²·ln n (default 3)")


def _add_timeline_parser(subparsers: Any) -> None:
    parser = cast(
        "argparse.ArgumentParser",
        subparsers.add_parser(
            TIMELINE_COMMAND,
            help="daily cost, the steps in it, and the deploy each step followed",
            description="Pull daily cost, find the days it stepped, and name the deploy that preceded each step.",
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_TIMELINE_DAYS,
        help=f"days of daily cost to pull (default {DEFAULT_TIMELINE_DAYS})",
    )
    parser.add_argument("--end", metavar="YYYY-MM-DD", help="last day to include (default: yesterday)")
    parser.add_argument("--group", default=SERVICE_DIMENSION, choices=GROUP_DIMENSIONS)
    parser.add_argument("--tag", metavar="KEY", help="also group by this cost-allocation tag key")
    parser.add_argument("--metric", default=DEFAULT_METRIC, choices=COST_METRICS)
    _add_detection_flags(parser)
    _add_deploy_source_flags(parser)
    parser.add_argument(
        "--deploy-window",
        type=float,
        default=DEFAULT_DEPLOY_WINDOW_HOURS,
        metavar="HOURS",
        help=f"how far back of a step to look for deploys (default {DEFAULT_DEPLOY_WINDOW_HOURS:g})",
    )
    parser.add_argument("--format", default=MARKDOWN_FORMAT, choices=OUTPUT_FORMATS)
    parser.add_argument("--chart", default=ASCII_CHART, choices=CHART_KINDS)
    parser.add_argument("--chart-group", default=TOTAL_GROUP, metavar="GROUP", help="which series to chart")
    parser.add_argument("--chart-height", type=int, default=10, metavar="ROWS")
    parser.add_argument(
        "--pr-comment",
        action="store_true",
        help="post each confidently attributed step on the PR its deploy points at, via gh",
    )
    parser.add_argument("--repo", metavar="OWNER/REPO", help="repository for --pr-comment (default: inferred)")
    parser.add_argument("--dry-run", action="store_true", help="with --pr-comment, print instead of posting")
    parser.add_argument("--cache-dir", metavar="PATH", help="cache Cost Explorer answers here")
    parser.add_argument("--cache-ttl", type=float, default=24.0, metavar="HOURS", help="cache lifetime (default 24)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cost-diff",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    _add_timeline_parser(subparsers)
    _add_diff_parser(subparsers)
    return parser


def _usage_type_breakdown(service: str, vs: str, period: str, metric: str, threshold: float) -> str:
    """Render the USAGE_TYPE drilldown for the service that moved most."""
    rows = build_diff(
        fetch_costs(
            vs,
            USAGE_TYPE_DIMENSION,
            metric=metric,
            filter_dimension=(SERVICE_DIMENSION, service),
        ),
        fetch_costs(
            period,
            USAGE_TYPE_DIMENSION,
            metric=metric,
            filter_dimension=(SERVICE_DIMENSION, service),
        ),
        threshold,
    )
    return render_why(rows, service)


def _run_diff(args: argparse.Namespace) -> int:
    today = _utcnow().date()
    period = previous_month(f"{today.year}-{today.month:02d}") if args.last_month else args.period
    vs = args.vs or previous_month(period)

    rows = build_diff(
        fetch_costs(vs, args.group, metric=args.metric),
        fetch_costs(period, args.group, metric=args.metric),
        args.threshold,
        old_period=vs,
        new_period=period,
    )
    report = render(rows, period, vs, args.top)
    wants_usage_breakdown = args.why and rows and args.group == SERVICE_DIMENSION
    if wants_usage_breakdown:
        report += "\n" + _usage_type_breakdown(rows[0].group, vs, period, args.metric, args.threshold)
    print(report)  # noqa: T201 — the tool's output
    if args.slack:
        post_slack(args.slack, render_slack_blocks(rows, period, vs, args.top))
    return 0


def _timeline_range(args: argparse.Namespace) -> tuple[date, date]:
    """[start, end) for the query. Today is excluded: it is a part day of cost."""
    end = (date.fromisoformat(args.end) + timedelta(days=1)) if args.end else _utcnow().date()
    return end - timedelta(days=args.days), end


def _detection_config(args: argparse.Namespace) -> DetectionConfig:
    return DetectionConfig(
        method=args.method,
        window=args.window_days,
        threshold=args.threshold_sigma,
        min_delta=args.min_step,
        ramp_fraction=args.ramp_fraction,
        transition_days=args.transition_days,
        penalty=args.pelt_penalty,
    )


def _infer_repo(args: argparse.Namespace) -> str:
    """The repo to comment on: told, or read out of the checkout deploys came from."""
    if args.repo:
        return args.repo
    if args.deploys_github:
        return args.deploys_github
    if args.deploys_git is not None:
        return _run(
            [_binary("gh"), "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            cwd=Path(args.deploys_git),
        ).strip()
    raise CostDiffError("--pr-comment needs --repo OWNER/REPO")


def build_timeline_report(args: argparse.Namespace, client: CostExplorer | None = None) -> TimelineReport:
    """Pull the series, find the steps, pair them with deploys."""
    start, end = _timeline_range(args)
    # Deploys first: reading them is free and local, and a typo in a path should
    # not cost a Cost Explorer call to find out about.
    deploys = load_deploys(args)
    query = DailyQuery(start, end, args.metric, args.group, args.tag)
    cache = ResponseCache(Path(args.cache_dir), args.cache_ttl) if args.cache_dir else None
    days = day_range(start, end)
    series = densify(fetch_daily_costs(query, client=client, cache=cache), days)
    config = _detection_config(args)
    steps: list[Step] = []
    for group, values in series.items():
        if group == TOTAL_GROUP:
            continue  # a step in one service is what a total hides
        steps.extend(detect_steps(group, days, values, config))
    steps.sort(key=lambda step: (step.day, -abs(step.delta)))
    return TimelineReport(
        query=query,
        config=config,
        window_hours=args.deploy_window,
        days=days,
        series=series,
        attributions=attribute(steps, deploys, args.deploy_window),
        deploys=deploys,
    )


def _run_timeline(args: argparse.Namespace, client: CostExplorer | None = None) -> int:
    report = build_timeline_report(args, client)
    if args.format == JSON_FORMAT:
        print(json.dumps(timeline_json(report), indent=2))  # noqa: T201 — the tool's output
    else:
        print(render_timeline(report, args.chart, args.chart_group, args.chart_height))  # noqa: T201
    if args.pr_comment:
        for note in comment_on_pull_requests(report, _infer_repo(args), args.dry_run):
            print(note, file=sys.stderr)  # noqa: T201 — a log line, not the report
    return 0


def normalise_argv(argv: Sequence[str]) -> list[str]:
    """`cost-diff --last-month` predates the subcommands and still means the diff.

    Only a leading flag is rewritten: anything else is a subcommand, a typo
    argparse should name, or `--help`, which belongs to the top-level parser.
    """
    args = list(argv)
    if args and args[0].startswith("-") and args[0] not in {"-h", "--help"}:
        args.insert(0, DIFF_COMMAND)
    return args


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse a command line, legacy flag-first form included."""
    return _build_parser().parse_args(normalise_argv(argv))


def main(argv: list[str] | None = None) -> int:
    parsed = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return _run_timeline(parsed) if parsed.command == TIMELINE_COMMAND else _run_diff(parsed)
    except CostDiffError as exc:
        print(f"cost-diff: {exc}", file=sys.stderr)  # noqa: T201 — the error path
        return 1


if __name__ == "__main__":
    sys.exit(main())
