#!/usr/bin/env python3
"""cost-diff — diff two AWS Cost Explorer periods into "what changed and why".

cost-diff --last-month                     # vs the month before
cost-diff --period 2026-06 --vs 2026-05
cost-diff --last-month --group SERVICE --top 15 --slack $WEBHOOK_URL
"""

import argparse
import calendar
import json
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone

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


@dataclass(frozen=True)
class Change:
    """One group's cost movement between the two periods."""

    group: str
    before: float
    after: float
    delta: float
    pct: float | None  # None when the group is new: no baseline to divide by
    anomaly: bool


def month_bounds(yyyy_mm):
    y, m = (int(x) for x in yyyy_mm.split("-"))
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end


def previous_month(yyyy_mm):
    y, m = (int(x) for x in yyyy_mm.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def fetch_costs(
    period,
    group_by=SERVICE_DIMENSION,
    client=None,
    metric=DEFAULT_METRIC,
    filter_dimension=None,
):
    """Return {group: cost_usd} for a YYYY-MM period from Cost Explorer.

    filter_dimension, if given, is a (key, value) pair restricting the query
    (e.g. narrowing a USAGE_TYPE breakdown to a single SERVICE).
    """
    if client is None:
        import boto3

        client = boto3.client("ce", region_name=CE_REGION)
    start, end = month_bounds(period)
    results, token = {}, None
    while True:
        kwargs = {
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


def weekday_count(yyyy_mm):
    """Number of Mon-Fri days in a YYYY-MM period."""
    y, m = (int(x) for x in yyyy_mm.split("-"))
    days_in_month = calendar.monthrange(y, m)[1]
    return sum(1 for d in range(1, days_in_month + 1) if date(y, m, d).weekday() < 5)


def build_diff(old, new, threshold_usd=1.0, old_period=None, new_period=None):
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
    rows = []
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


def _totals(rows):
    """(total_before, total_after, total_delta, trend arrow) across all rows."""
    total_before = sum(row.before for row in rows)
    total_after = sum(row.after for row in rows)
    total_delta = total_after - total_before
    arrow = "▲" if total_delta > 0 else "▼" if total_delta < 0 else "→"
    return total_before, total_after, total_delta, arrow


def _pct_str(row):
    return f" ({row.pct:+.0f}%)" if row.pct is not None else " (new)"


def _signed_usd(amount):
    """`+$1,234` / `−$1,234` — U+2212 minus, not a hyphen, in every table."""
    return f"{'+' if amount > 0 else '−'}${abs(amount):,.0f}"


def _change_row(row, flag=""):
    """One Markdown row, shared by the service table and the usage-type table."""
    change = _signed_usd(row.delta) + _pct_str(row) + flag
    return f"| {change} | {row.group} | ${row.before:,.0f} | ${row.after:,.0f} |"


def render(rows, period, vs, top=10):
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
        lines.append(
            "\n⚠ = change not explained by the business-day-count difference between periods."
        )
    return "\n".join(lines)


def render_why(rows, group_label, top=5):
    """Render a USAGE_TYPE breakdown explaining why `group_label` moved."""
    lines = [
        f"\n### Why {group_label} moved (by usage type)",
        "",
        "| change | usage type | before | after |",
        "|---|---|---|---|",
    ]
    lines.extend(_change_row(row) for row in rows[:top])
    return "\n".join(lines)


def render_slack_blocks(rows, period, vs, top=10):
    """Render the report as Slack Block Kit blocks (mrkdwn, not GFM)."""
    total_before, total_after, total_delta, arrow = _totals(rows)
    table_lines = [
        f"{_signed_usd(row.delta)}{' ⚠' if row.anomaly else ''} "
        f"{row.group}: ${row.before:,.0f} → ${row.after:,.0f}"
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
                    "text": f"*Total:* ${total_before:,.0f} → ${total_after:,.0f} "
                    f"({arrow} ${abs(total_delta):,.0f})",
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


def post_slack(webhook, payload):
    if not webhook.startswith("https://"):
        raise ValueError("Slack webhook must be an https:// URL")
    body = json.dumps(payload).encode()
    req = urllib.request.Request(webhook, data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=15)  # nosec B310  scheme checked above


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="cost-diff",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    return parser


def _usage_type_breakdown(service, vs, period, metric, threshold):
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


def main(argv=None):
    args = _build_parser().parse_args(argv)

    today = datetime.now(tz=timezone.utc).date()
    if args.last_month:
        period = previous_month(f"{today.year}-{today.month:02d}")
    else:
        period = args.period
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
        report += "\n" + _usage_type_breakdown(
            rows[0].group, vs, period, args.metric, args.threshold
        )
    print(report)
    if args.slack:
        post_slack(args.slack, render_slack_blocks(rows, period, vs, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
