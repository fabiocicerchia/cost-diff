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
from datetime import date


def month_bounds(yyyy_mm):
    y, m = (int(x) for x in yyyy_mm.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def previous_month(yyyy_mm):
    y, m = (int(x) for x in yyyy_mm.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def fetch_costs(period, group_by="SERVICE", client=None):
    """Return {group: cost_usd} for a YYYY-MM period from Cost Explorer."""
    if client is None:
        import boto3

        client = boto3.client("ce", region_name="us-east-1")
    start, end = month_bounds(period)
    results, token = {}, None
    while True:
        kwargs = {
            "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
            "Granularity": "MONTHLY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": group_by}],
        }
        if token:
            kwargs["NextPageToken"] = token
        resp = client.get_cost_and_usage(**kwargs)
        for row in resp["ResultsByTime"]:
            for group in row.get("Groups", []):
                key = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                results[key] = results.get(key, 0.0) + amount
        token = resp.get("NextPageToken")
        if not token:
            return results


def build_diff(old, new, threshold_usd=1.0):
    """Merge two cost maps into sorted change rows."""
    rows = []
    for key in sorted(old.keys() | new.keys()):
        before, after = old.get(key, 0.0), new.get(key, 0.0)
        delta = after - before
        if abs(delta) < threshold_usd:
            continue
        pct = (delta / before * 100) if before else None
        rows.append({"group": key, "before": before, "after": after, "delta": delta, "pct": pct})
    rows.sort(key=lambda r: -abs(r["delta"]))
    return rows


def render(rows, period, vs, top=10):
    total_before = sum(r["before"] for r in rows)
    total_after = sum(r["after"] for r in rows)
    total_delta = total_after - total_before
    arrow = "▲" if total_delta > 0 else "▼"
    lines = [
        f"# AWS cost diff: {vs} → {period}",
        "",
        f"**Total: ${total_before:,.0f} → ${total_after:,.0f} ({arrow} ${abs(total_delta):,.0f})**",
        "",
        "| change | service | before | after |",
        "|---|---|---|---|",
    ]
    for r in rows[:top]:
        pct = f" ({r['pct']:+.0f}%)" if r["pct"] is not None else " (new)"
        lines.append(
            f"| {'+' if r['delta'] > 0 else '−'}${abs(r['delta']):,.0f}{pct} "
            f"| {r['group']} | ${r['before']:,.0f} | ${r['after']:,.0f} |"
        )
    hidden = len(rows) - top
    if hidden > 0:
        lines.append(f"\n…and {hidden} smaller changes below the threshold.")
    return "\n".join(lines)


def post_slack(webhook, text):
    if not webhook.startswith("https://"):
        raise ValueError("Slack webhook must be an https:// URL")
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(webhook, data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=15)  # noqa: S310  # nosec B310  scheme checked above


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="cost-diff", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--last-month", action="store_true", help="previous full month vs the one before"
    )
    g.add_argument("--period", metavar="YYYY-MM", help="period to analyze")
    p.add_argument(
        "--vs", metavar="YYYY-MM", help="baseline period (default: month before --period)"
    )
    p.add_argument(
        "--group", default="SERVICE", choices=["SERVICE", "LINKED_ACCOUNT", "USAGE_TYPE", "REGION"]
    )
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--threshold", type=float, default=1.0, help="ignore changes under $N")
    p.add_argument("--slack", metavar="WEBHOOK", help="post the report to Slack")
    args = p.parse_args(argv)

    today = date.today()
    if args.last_month:
        period = previous_month(f"{today.year}-{today.month:02d}")
    else:
        period = args.period
    vs = args.vs or previous_month(period)

    rows = build_diff(fetch_costs(vs, args.group), fetch_costs(period, args.group), args.threshold)
    report = render(rows, period, vs, args.top)
    print(report)
    if args.slack:
        post_slack(args.slack, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
