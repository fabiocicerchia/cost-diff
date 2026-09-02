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
        resp = client.get_cost_and_usage(**kwargs)
        for row in resp["ResultsByTime"]:
            for group in row.get("Groups", []):
                key = group["Keys"][0]
                amount = float(group["Metrics"][metric]["Amount"])
                results[key] = results.get(key, 0.0) + amount
        token = resp.get("NextPageToken")
        if not token:
            return results


def weekday_count(yyyy_mm):
    """Number of Mon-Fri days in a YYYY-MM period."""
    y, m = (int(x) for x in yyyy_mm.split("-"))
    days_in_month = calendar.monthrange(y, m)[1]
    return sum(1 for d in range(1, days_in_month + 1) if date(y, m, d).weekday() < 5)


def build_diff(old, new, threshold_usd=1.0, old_period=None, new_period=None):
    """Merge two cost maps into sorted change rows.

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
        rows.append(
            {
                "group": key,
                "before": before,
                "after": after,
                "delta": delta,
                "pct": pct,
                "anomaly": anomaly,
            }
        )
    rows.sort(key=lambda r: -abs(r["delta"]))
    return rows


def _totals(rows):
    """(total_before, total_after, total_delta, trend arrow) across all rows."""
    total_before = sum(r["before"] for r in rows)
    total_after = sum(r["after"] for r in rows)
    total_delta = total_after - total_before
    arrow = "▲" if total_delta > 0 else "▼" if total_delta < 0 else "→"
    return total_before, total_after, total_delta, arrow


def _pct_str(r):
    return f" ({r['pct']:+.0f}%)" if r["pct"] is not None else " (new)"


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
    for r in rows[:top]:
        pct = _pct_str(r)
        flag = ""
        if r.get("anomaly"):
            flag = " ⚠"
            any_anomaly = True
        lines.append(
            f"| {'+' if r['delta'] > 0 else '−'}${abs(r['delta']):,.0f}{pct}{flag} "
            f"| {r['group']} | ${r['before']:,.0f} | ${r['after']:,.0f} |"
        )
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
    for r in rows[:top]:
        pct = _pct_str(r)
        lines.append(
            f"| {'+' if r['delta'] > 0 else '−'}${abs(r['delta']):,.0f}{pct} "
            f"| {r['group']} | ${r['before']:,.0f} | ${r['after']:,.0f} |"
        )
    return "\n".join(lines)


def render_slack_blocks(rows, period, vs, top=10):
    """Render the report as Slack Block Kit blocks (mrkdwn, not GFM)."""
    total_before, total_after, total_delta, arrow = _totals(rows)
    table_lines = [
        f"{'+' if r['delta'] > 0 else '−'}${abs(r['delta']):,.0f}"
        f"{' ⚠' if r.get('anomaly') else ''} {r['group']}: ${r['before']:,.0f} → ${r['after']:,.0f}"
        for r in rows[:top]
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


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="cost-diff",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--last-month",
        action="store_true",
        help="previous full month vs the one before",
    )
    g.add_argument("--period", metavar="YYYY-MM", help="period to analyze")
    p.add_argument(
        "--vs",
        metavar="YYYY-MM",
        help="baseline period (default: month before --period)",
    )
    p.add_argument(
        "--group",
        default=SERVICE_DIMENSION,
        choices=GROUP_DIMENSIONS,
    )
    p.add_argument(
        "--metric",
        default=DEFAULT_METRIC,
        choices=COST_METRICS,
        help="Cost Explorer metric; Net* nets out credits/refunds, "
        "Amortized* spreads RI/Savings Plan cost over its term",
    )
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--threshold", type=float, default=1.0, help="ignore changes under $N")
    p.add_argument("--slack", metavar="WEBHOOK", help="post the report to Slack")
    p.add_argument(
        "--why",
        action="store_true",
        help="drill down the biggest mover by USAGE_TYPE (only with --group SERVICE)",
    )
    args = p.parse_args(argv)

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
    if args.why and rows and args.group == SERVICE_DIMENSION:
        biggest = rows[0]["group"]
        why_rows = build_diff(
            fetch_costs(
                vs,
                USAGE_TYPE_DIMENSION,
                metric=args.metric,
                filter_dimension=(SERVICE_DIMENSION, biggest),
            ),
            fetch_costs(
                period,
                USAGE_TYPE_DIMENSION,
                metric=args.metric,
                filter_dimension=(SERVICE_DIMENSION, biggest),
            ),
            args.threshold,
        )
        report += "\n" + render_why(why_rows, biggest)
    print(report)
    if args.slack:
        post_slack(args.slack, render_slack_blocks(rows, period, vs, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
