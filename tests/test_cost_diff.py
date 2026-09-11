import argparse
import json
import random
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

from cost_diff import (
    MEDIAN_MAD,
    PELT,
    TOTAL_GROUP,
    CostDiffError,
    DailyQuery,
    Deploy,
    DetectionConfig,
    ResponseCache,
    Step,
    TimelineReport,
    attribute,
    build_diff,
    build_timeline_report,
    comment_on_pull_requests,
    day_range,
    densify,
    deploys_from_file,
    detect_steps,
    fetch_costs,
    fetch_daily_costs,
    lag_hours,
    month_bounds,
    normalise_argv,
    parse_args,
    previous_month,
    render,
    render_ascii_chart,
    render_mermaid_chart,
    render_pr_comment,
    render_slack_blocks,
    render_timeline,
    render_why,
    timeline_json,
    weekday_count,
)


def test_month_arithmetic() -> None:
    assert previous_month("2026-01") == "2025-12"
    # End is exclusive per the Cost Explorer API: the day *after* the last day
    # of the month, so a TimePeriod covering Feb 2026 includes Feb 28 itself.
    assert month_bounds("2026-02") == (date(2026, 2, 1), date(2026, 3, 1))
    assert month_bounds("2026-12")[1] == date(2027, 1, 1)


def test_weekday_count() -> None:
    assert weekday_count("2026-06") == 22  # June 2026: 30 days, 8 weekend days


def test_anomaly_flags_unexplained_swings_same_weekday_count() -> None:
    # same period twice -> weekday ratio 1 -> expected pct is 0
    rows = build_diff(
        {"EC2": 100.0, "S3": 100.0},
        {"EC2": 1000.0, "S3": 115.0},
        old_period="2026-06",
        new_period="2026-06",
    )
    by_group = {r.group: r for r in rows}
    assert by_group["EC2"].anomaly is True  # +900%, nothing explains that
    assert by_group["S3"].anomaly is False  # +15%, below the noise floor


def test_no_anomaly_field_set_without_periods() -> None:
    rows = build_diff({"EC2": 100.0}, {"EC2": 1000.0})
    assert rows[0].anomaly is False


def test_render_slack_blocks_uses_mrkdwn_not_gfm() -> None:

    rows = build_diff({"EC2": 100.0}, {"EC2": 250.0})
    payload = render_slack_blocks(rows, "2026-06", "2026-05")
    blocks = payload["blocks"]
    assert blocks[0]["text"]["text"] == "AWS cost diff: 2026-05 → 2026-06"
    total_text = blocks[1]["text"]["text"]
    assert total_text.startswith("*Total:*")
    assert "**" not in total_text
    assert "EC2" in blocks[2]["text"]["text"]


def test_diff_sorted_by_magnitude_and_thresholded() -> None:
    rows = build_diff(
        {"EC2": 1000.0, "S3": 50.0, "Athena": 10.0},
        {"EC2": 1400.0, "S3": 49.5, "RDS": 200.0, "Athena": 10.0},
    )
    assert [r.group for r in rows] == [
        "EC2",
        "RDS",
    ]  # S3 under threshold, Athena unchanged
    assert rows[1].pct is None  # new service has no baseline pct


def test_render_contains_totals_and_table() -> None:
    rows = build_diff({"EC2": 100.0}, {"EC2": 250.0})
    out = render(rows, "2026-06", "2026-05")
    assert "2026-05 → 2026-06" in out
    assert "| EC2 |" in out
    assert "▲ $150" in out


def test_render_zero_net_change_uses_neutral_arrow() -> None:
    rows = build_diff({"EC2": 100.0, "S3": 100.0}, {"EC2": 150.0, "S3": 50.0})
    out = render(rows, "2026-06", "2026-05")
    assert "→ $0" in out


def test_render_hidden_rows_message_blames_top_not_threshold() -> None:
    rows = build_diff(
        {"A": 100.0, "B": 100.0, "C": 100.0},
        {"A": 600.0, "B": 600.0, "C": 600.0},
    )
    out = render(rows, "2026-06", "2026-05", top=1)
    assert "above the threshold, not shown" in out


def test_fetch_costs_sends_exclusive_end_date() -> None:
    class FakeCE:
        def get_cost_and_usage(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["TimePeriod"] == {"Start": "2026-02-01", "End": "2026-03-01"}
            return {"ResultsByTime": []}

    fetch_costs("2026-02", client=FakeCE())


def test_fetch_costs_pagination_shape() -> None:
    class FakeCE:
        def __init__(self) -> None:
            self.calls = 0

        def get_cost_and_usage(self, **kwargs: object) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {
                    "ResultsByTime": [
                        {
                            "Groups": [
                                {
                                    "Keys": ["EC2"],
                                    "Metrics": {"UnblendedCost": {"Amount": "10"}},
                                }
                            ]
                        }
                    ],
                    "NextPageToken": "t",
                }
            return {
                "ResultsByTime": [
                    {
                        "Groups": [
                            {
                                "Keys": ["EC2"],
                                "Metrics": {"UnblendedCost": {"Amount": "5"}},
                            }
                        ]
                    }
                ]
            }

    assert fetch_costs("2026-06", client=FakeCE()) == {"EC2": 15.0}


def test_fetch_costs_uses_selected_metric() -> None:
    class FakeCE:
        def get_cost_and_usage(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["Metrics"] == ["AmortizedCost"]
            return {
                "ResultsByTime": [
                    {
                        "Groups": [
                            {
                                "Keys": ["EC2"],
                                "Metrics": {"AmortizedCost": {"Amount": "42"}},
                            }
                        ]
                    }
                ]
            }

    assert fetch_costs("2026-06", client=FakeCE(), metric="AmortizedCost") == {"EC2": 42.0}


def test_fetch_costs_applies_filter_dimension() -> None:
    class FakeCE:
        def get_cost_and_usage(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["Filter"] == {"Dimensions": {"Key": "SERVICE", "Values": ["EC2"]}}
            return {
                "ResultsByTime": [
                    {
                        "Groups": [
                            {
                                "Keys": ["BoxUsage"],
                                "Metrics": {"UnblendedCost": {"Amount": "7"}},
                            }
                        ]
                    }
                ]
            }

    result = fetch_costs("2026-06", "USAGE_TYPE", client=FakeCE(), filter_dimension=("SERVICE", "EC2"))
    assert result == {"BoxUsage": 7.0}


def test_render_why_lists_usage_types() -> None:

    rows = build_diff({"BoxUsage": 100.0}, {"BoxUsage": 300.0})
    out = render_why(rows, "EC2")
    assert "Why EC2 moved" in out
    assert "BoxUsage" in out


# --------------------------------------------------------------------------
# Timeline: step detection on synthetic daily series.
#
# Every series below is 60 days long and carries ±2% of deterministic jitter,
# because a real daily bill is never flat and a detector that only works on
# straight lines would pass a test and fail a bill.
# --------------------------------------------------------------------------

START = date(2026, 7, 13)
DAYS = day_range(START, START + timedelta(days=60))
STEP_DAY = 40  # index into DAYS: 2026-08-22
METHODS = [MEDIAN_MAD, PELT]


def jitter(seed: int = 11) -> Callable[[float], float]:
    rng = random.Random(seed)  # noqa: S311 — jitter for a fixture, not a secret
    return lambda value: value * (1 + rng.uniform(-0.02, 0.02))


def clean_step(before: float = 100.0, after: float = 141.0, seed: int = 11) -> list[float]:
    noise = jitter(seed)
    return [noise(before if day < STEP_DAY else after) for day in range(len(DAYS))]


@pytest.mark.parametrize("method", METHODS)
def test_clean_step_is_found_on_the_day_cost_moved(method: str) -> None:
    steps = detect_steps("Amazon EC2", DAYS, clean_step(), DetectionConfig(method=method))
    assert len(steps) == 1
    assert steps[0].day == DAYS[STEP_DAY]
    assert 38 < steps[0].delta < 44  # the $41/day the series steps by
    assert steps[0].method == method


@pytest.mark.parametrize("method", METHODS)
def test_flat_series_has_no_step(method: str) -> None:
    noise = jitter()
    values = [noise(100.0) for _ in DAYS]
    assert detect_steps("Amazon EC2", DAYS, values, DetectionConfig(method=method)) == []


@pytest.mark.parametrize("method", METHODS)
def test_gradual_ramp_is_not_reported_as_a_step(method: str) -> None:
    # +$1.50/day, every day, for two months: $88/day dearer by the end and not
    # one day where it stepped. Whatever is happening here, no deploy did it.
    noise = jitter()
    values = [noise(100.0 + 1.5 * day) for day in range(len(DAYS))]
    assert detect_steps("Amazon EC2", DAYS, values, DetectionConfig(method=method)) == []


@pytest.mark.parametrize("method", METHODS)
def test_steep_ramp_is_still_not_a_step(method: str) -> None:
    # The ramp guard is a ratio, so it does not care how steep the ramp is:
    # a line only ever delivers its slope over the transition, never its level.
    noise = jitter()
    values = [noise(100.0 + 8.0 * day) for day in range(len(DAYS))]
    assert detect_steps("Amazon EC2", DAYS, values, DetectionConfig(method=method)) == []


@pytest.mark.parametrize("method", METHODS)
def test_one_day_spike_is_not_a_step(method: str) -> None:
    noise = jitter()
    values = [noise(100.0) for _ in DAYS]
    values[STEP_DAY] = 900.0  # a one-off batch job, not a new level
    assert detect_steps("Amazon EC2", DAYS, values, DetectionConfig(method=method)) == []


@pytest.mark.parametrize("method", METHODS)
def test_step_down_is_found_too(method: str) -> None:
    steps = detect_steps("Amazon EC2", DAYS, clean_step(141.0, 100.0), DetectionConfig(method=method))
    assert len(steps) == 1
    assert steps[0].delta < 0
    assert steps[0].day == DAYS[STEP_DAY]


@pytest.mark.parametrize("method", METHODS)
def test_mid_day_deploy_taking_two_days_to_bill_is_one_step(method: str) -> None:
    # A deploy at lunchtime bills half a day at the new rate, so the level
    # arrives over two days. That is still one step, not two.
    noise = jitter()
    values = [noise(100.0 if day < STEP_DAY else (120.0 if day == STEP_DAY else 141.0)) for day in range(len(DAYS))]
    steps = detect_steps("Amazon EC2", DAYS, values, DetectionConfig(method=method))
    assert len(steps) == 1
    assert steps[0].day in {DAYS[STEP_DAY], DAYS[STEP_DAY + 1]}


def test_small_steps_are_below_the_dollar_floor() -> None:
    steps = detect_steps("Amazon EC2", DAYS, clean_step(100.0, 103.0), DetectionConfig(min_delta=5.0))
    assert steps == []


def test_detection_needs_a_window_either_side() -> None:
    short = DAYS[:10]
    assert detect_steps("Amazon EC2", short, clean_step()[:10], DetectionConfig(window=7)) == []


# --------------------------------------------------------------------------
# Attribution: which deploy, and how sure.
# --------------------------------------------------------------------------


def deploy_at(when: str, label: str = "v2.14", revision: str | None = "9f3a1c2") -> Deploy:
    return Deploy(datetime.fromisoformat(when).replace(tzinfo=timezone.utc), label, "file", revision)


def one_step() -> list[Step]:
    return detect_steps("Amazon EC2", DAYS, clean_step(), DetectionConfig())


def test_one_deploy_in_window_is_attributed_with_high_confidence() -> None:
    deploy = deploy_at("2026-08-21T18:00:00")  # 6h before the step day starts
    [attribution] = attribute(one_step(), [deploy])
    assert attribution.deploy == deploy
    assert attribution.confidence == "high"
    assert lag_hours(attribution.step, deploy) == 6.0


def test_two_deploys_in_window_are_listed_rather_than_guessed() -> None:
    earlier = deploy_at("2026-08-21T20:00:00", "v2.14")
    later = deploy_at("2026-08-22T02:00:00", "v2.15")
    [attribution] = attribute(one_step(), [earlier, later])
    assert attribution.deploy is None  # no guessing between them
    assert [d.label for d in attribution.candidates] == ["v2.15", "v2.14"]  # newest first
    assert attribution.confidence == "medium"


def test_three_deploys_in_window_drop_to_low_confidence() -> None:
    deploys = [
        deploy_at("2026-08-21T06:00:00", "v2.13"),
        deploy_at("2026-08-21T20:00:00", "v2.14"),
        deploy_at("2026-08-22T02:00:00", "v2.15"),
    ]
    [attribution] = attribute(one_step(), deploys)
    assert attribution.confidence == "low"
    assert len(attribution.candidates) == 3


def test_deploy_outside_the_window_is_not_attributed() -> None:
    [attribution] = attribute(one_step(), [deploy_at("2026-08-20T18:00:00")])  # 30h before
    assert attribution.candidates == []
    assert attribution.confidence == "none"


def test_deploy_during_the_step_day_is_in_window_with_a_negative_lag() -> None:
    deploy = deploy_at("2026-08-22T14:00:00")
    [attribution] = attribute(one_step(), [deploy])
    assert attribution.deploy == deploy
    assert lag_hours(attribution.step, deploy) == -14.0


def test_window_is_configurable() -> None:
    deploy = deploy_at("2026-08-20T18:00:00")  # 30h before the step day
    assert attribute(one_step(), [deploy], window_hours=48)[0].deploy == deploy


# --------------------------------------------------------------------------
# Deploy sources: the file loader anyone can feed.
# --------------------------------------------------------------------------


def test_deploys_from_csv_with_a_header(tmp_path: Path) -> None:
    path = tmp_path / "deploys.csv"
    path.write_text("timestamp,label,revision\n2026-08-21T18:00:00Z,v2.14,9f3a1c2\n", encoding="utf-8")
    [deploy] = deploys_from_file(path)
    assert deploy.label == "v2.14"
    assert deploy.revision == "9f3a1c2"
    assert deploy.when == datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc)


def test_deploys_from_csv_without_a_header(tmp_path: Path) -> None:
    path = tmp_path / "deploys.csv"
    path.write_text("2026-08-21T18:00:00Z,v2.14\n2026-08-01T09:30:00Z,v2.13\n", encoding="utf-8")
    assert [d.label for d in deploys_from_file(path)] == ["v2.14", "v2.13"]


def test_deploys_from_json_objects(tmp_path: Path) -> None:
    path = tmp_path / "deploys.json"
    path.write_text(json.dumps([{"time": "2026-08-21T18:00:00Z", "name": "v2.14", "sha": "abc1234"}]), encoding="utf-8")
    [deploy] = deploys_from_file(path)
    assert (deploy.label, deploy.revision) == ("v2.14", "abc1234")


def test_deploys_from_json_pairs(tmp_path: Path) -> None:
    path = tmp_path / "deploys.json"
    path.write_text(json.dumps([["2026-08-21T18:00:00Z", "v2.14"]]), encoding="utf-8")
    assert deploys_from_file(path)[0].label == "v2.14"


def test_naive_deploy_timestamps_are_read_as_utc(tmp_path: Path) -> None:
    path = tmp_path / "deploys.csv"
    path.write_text("timestamp,label\n2026-08-21 18:00:00,v2.14\n", encoding="utf-8")
    assert deploys_from_file(path)[0].when == datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc)


def test_an_offset_timestamp_is_converted_not_dropped(tmp_path: Path) -> None:
    path = tmp_path / "deploys.csv"
    path.write_text("timestamp,label\n2026-08-21T20:00:00+02:00,v2.14\n", encoding="utf-8")
    assert deploys_from_file(path)[0].when == datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc)


def test_unreadable_timestamp_says_what_it_wanted(tmp_path: Path) -> None:
    path = tmp_path / "deploys.csv"
    path.write_text("timestamp,label\nlast tuesday,v2.14\n", encoding="utf-8")
    with pytest.raises(CostDiffError, match="ISO 8601"):
        deploys_from_file(path)


def test_a_row_without_a_timestamp_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "deploys.csv"
    path.write_text("label\nv2.14\n", encoding="utf-8")
    with pytest.raises(CostDiffError, match=str(path)):
        deploys_from_file(path)


# --------------------------------------------------------------------------
# Daily fetch and the optional response cache.
# --------------------------------------------------------------------------


class FakeDailyCE:
    """A Cost Explorer that bills one service a step and another a flat rate."""

    def __init__(self, keys: tuple[str, ...] = ("Amazon EC2",), pages: int = 1) -> None:
        self.keys = keys
        self.pages = pages
        self.calls: list[dict[str, object]] = []

    def get_cost_and_usage(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        period = cast("dict[str, str]", kwargs["TimePeriod"])
        start, end = date.fromisoformat(period["Start"]), date.fromisoformat(period["End"])
        metric = cast("list[str]", kwargs["Metrics"])[0]
        noise = jitter()
        results: list[dict[str, object]] = []
        for offset in range((end - start).days):
            day = start + timedelta(days=offset)
            amount = noise(100.0 if offset < STEP_DAY else 141.0)
            results.append(
                {
                    "TimePeriod": {"Start": day.isoformat(), "End": (day + timedelta(days=1)).isoformat()},
                    "Groups": [
                        {"Keys": list(self.keys), "Metrics": {metric: {"Amount": f"{amount:.4f}"}}},
                        {"Keys": ["Amazon S3", *self.keys[1:]], "Metrics": {metric: {"Amount": "20.0"}}},
                    ],
                }
            )
        page: dict[str, object] = {"ResultsByTime": results}
        if len(self.calls) < self.pages:
            page["NextPageToken"] = "more"
        return page


def test_fetch_daily_costs_asks_for_daily_granularity() -> None:
    client = FakeDailyCE()
    query = DailyQuery(START, START + timedelta(days=3))
    fetch_daily_costs(query, client=client)
    assert client.calls[0]["Granularity"] == "DAILY"
    assert client.calls[0]["TimePeriod"] == {"Start": "2026-07-13", "End": "2026-07-16"}


def test_fetch_daily_costs_groups_by_service_and_tag() -> None:
    client = FakeDailyCE(keys=("Amazon EC2", "Environment$prod"))
    query = DailyQuery(START, START + timedelta(days=2), tag_key="Environment")
    costs = fetch_daily_costs(query, client=client)
    assert client.calls[0]["GroupBy"] == [
        {"Type": "DIMENSION", "Key": "SERVICE"},
        {"Type": "TAG", "Key": "Environment"},
    ]
    assert "Amazon EC2 / prod" in costs  # Cost Explorer's `Key$value`, read as the value


def test_fetch_daily_costs_follows_pagination() -> None:
    client = FakeDailyCE(pages=2)
    costs = fetch_daily_costs(DailyQuery(START, START + timedelta(days=1)), client=client)
    assert len(client.calls) == 2
    assert costs["Amazon EC2"][START] > 190  # the same day counted from both pages


def test_response_cache_saves_a_second_call(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path, ttl_hours=24)
    query = DailyQuery(START, START + timedelta(days=5))
    client = FakeDailyCE()
    first = fetch_daily_costs(query, client=client, cache=cache)
    second = fetch_daily_costs(query, client=client, cache=cache)
    assert first == second
    assert len(client.calls) == 1  # the second answer came off disk


def test_expired_cache_entry_is_a_miss(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path, ttl_hours=0)
    query = DailyQuery(START, START + timedelta(days=5))
    client = FakeDailyCE()
    fetch_daily_costs(query, client=client, cache=cache)
    fetch_daily_costs(query, client=client, cache=cache)
    assert len(client.calls) == 2


def test_densify_fills_missing_days_with_zero_and_totals() -> None:
    days = day_range(START, START + timedelta(days=3))
    series = densify({"EC2": {days[0]: 10.0, days[2]: 30.0}, "S3": {days[1]: 5.0}}, days)
    assert series["EC2"] == [10.0, 0.0, 30.0]  # a gap is a real zero, not a hole
    assert series[TOTAL_GROUP] == [10.0, 5.0, 30.0]


# --------------------------------------------------------------------------
# Rendering: Markdown, charts, JSON.
# --------------------------------------------------------------------------


def timeline_args(extra: list[str] | None = None) -> argparse.Namespace:
    return parse_args(
        [
            "timeline",
            "--days",
            "60",
            "--end",
            (START + timedelta(days=59)).isoformat(),
            *(extra or []),
        ]
    )


def report_with(deploy_lines: str, tmp_path: Path, extra: list[str] | None = None) -> TimelineReport:
    path = tmp_path / "deploys.csv"
    path.write_text(deploy_lines, encoding="utf-8")
    args = timeline_args(["--deploys-file", str(path), *(extra or [])])
    return build_timeline_report(args, FakeDailyCE())


def test_timeline_markdown_names_the_deploy_the_lag_and_the_confidence(tmp_path: Path) -> None:
    report = report_with("timestamp,label\n2026-08-21T18:00:00Z,v2.14\n", tmp_path)
    out = render_timeline(report)
    assert "in Amazon EC2 starting 2026-08-22" in out
    assert "6h after `v2.14`" in out
    assert "one deploy in window, high confidence" in out
    assert "rolling median with a MAD threshold" in out  # says which method
    assert "temporal, not causal" in out


def test_timeline_markdown_lists_both_deploys_when_two_are_in_window(tmp_path: Path) -> None:
    report = report_with(
        "timestamp,label\n2026-08-21T20:00:00Z,v2.14\n2026-08-22T02:00:00Z,v2.15\n",
        tmp_path,
    )
    out = render_timeline(report)
    assert "2 deploys in window, medium confidence" in out
    assert "`v2.14`" in out
    assert "`v2.15`" in out


def test_timeline_markdown_says_so_when_nothing_stepped(tmp_path: Path) -> None:
    days = day_range(START, START + timedelta(days=60))
    noise = jitter()
    report = report_with("timestamp,label\n2026-08-21T18:00:00Z,v2.14\n", tmp_path)
    flat = {group: [noise(50.0) for _ in days] for group in report.series}
    quiet = TimelineReport(
        query=report.query,
        config=report.config,
        window_hours=report.window_hours,
        days=report.days,
        series=flat,
        attributions=[],
        deploys=report.deploys,
    )
    assert "No step above" in render_timeline(quiet)


def test_ascii_chart_marks_deploy_days(tmp_path: Path) -> None:
    report = report_with("timestamp,label\n2026-08-21T18:00:00Z,v2.14\n", tmp_path)
    chart = render_ascii_chart(report.days, report.series[TOTAL_GROUP], report.deploys, "TOTAL")
    marker_row = next(line for line in chart.splitlines() if line.strip() == "▲")
    assert marker_row.index("▲") == 10 + (date(2026, 8, 21) - report.days[0]).days
    assert "▲ 2026-08-21  v2.14" in chart


def test_mermaid_chart_is_a_xychart_with_the_deploy_day_marked(tmp_path: Path) -> None:
    report = report_with("timestamp,label\n2026-08-21T18:00:00Z,v2.14\n", tmp_path)
    chart = render_mermaid_chart(report.days, report.series[TOTAL_GROUP], report.deploys, "TOTAL")
    assert chart.startswith("```mermaid\nxychart-beta")
    assert '"21▲"' in chart  # the deploy day, in the axis itself
    assert "- ▲ 2026-08-21 — `v2.14`" in chart


def test_timeline_json_carries_the_numbers_and_the_caveat(tmp_path: Path) -> None:
    report = report_with("timestamp,label\n2026-08-21T18:00:00Z,v2.14\n", tmp_path)
    payload = json.loads(json.dumps(timeline_json(report)))  # must be serialisable as-is
    [step] = payload["steps"]
    assert step["group"] == "Amazon EC2"
    assert step["day"] == "2026-08-22"
    assert step["confidence"] == "high"
    assert step["deploys"][0]["lag_hours"] == 6.0
    assert payload["detection"]["method"] == "median-mad"
    assert "temporal, not causal" in payload["attribution"]["basis"]
    assert len(payload["days"]) == 60
    assert payload["series"]["Amazon EC2"]


def test_pr_comment_body_quotes_the_step_and_the_caveat(tmp_path: Path) -> None:
    report = report_with("timestamp,label,revision\n2026-08-21T18:00:00Z,v2.14,9f3a1c2\n", tmp_path)
    body = render_pr_comment(report.attributions[0], report)
    assert body.startswith("### cost-diff: +$")
    assert "in Amazon EC2 starting 2026-08-22, 6h after `v2.14`" in body
    assert "`v2.14`" in body
    assert "temporal, not causal" in body


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_bare_flags_still_mean_the_diff_subcommand() -> None:
    assert normalise_argv(["--last-month"]) == ["diff", "--last-month"]
    assert normalise_argv(["timeline", "--days", "30"]) == ["timeline", "--days", "30"]
    assert normalise_argv(["--help"]) == ["--help"]  # the top-level parser's own
    assert parse_args(["--last-month", "--top", "3"]).command == "diff"


def test_timeline_defaults_are_the_documented_ones() -> None:
    args = parse_args(["timeline"])
    assert (args.days, args.method, args.deploy_window, args.window_days) == (60, "median-mad", 24.0, 7)
    assert (args.chart, args.format, args.chart_group) == ("ascii", "markdown", TOTAL_GROUP)


def test_timeline_end_to_end_picks_the_deploy_out_of_the_series(tmp_path: Path) -> None:
    path = tmp_path / "deploys.csv"
    path.write_text(
        "timestamp,label\n2026-07-30T09:00:00Z,v2.13\n2026-08-21T18:00:00Z,v2.14\n",
        encoding="utf-8",
    )
    report = build_timeline_report(timeline_args(["--deploys-file", str(path)]), FakeDailyCE())
    [attribution] = report.attributions
    assert attribution.step.group == "Amazon EC2"
    assert attribution.deploy is not None
    assert attribution.deploy.label == "v2.14"  # v2.13 is three weeks away
    assert attribution.confidence == "high"


def test_timeline_without_deploys_reports_the_step_unattributed() -> None:
    report = build_timeline_report(timeline_args(), FakeDailyCE())
    [attribution] = report.attributions
    assert attribution.candidates == []
    assert "unattributed" in render_timeline(report)


def test_chart_group_that_does_not_exist_says_which_ones_do() -> None:
    report = build_timeline_report(timeline_args(), FakeDailyCE())
    with pytest.raises(CostDiffError, match="Amazon EC2"):
        render_timeline(report, chart_group="Amazon Athena")


def test_pr_comment_skips_a_step_with_no_single_deploy_to_blame(tmp_path: Path) -> None:
    report = report_with(
        "timestamp,label\n2026-08-21T20:00:00Z,v2.14\n2026-08-22T02:00:00Z,v2.15\n",
        tmp_path,
    )
    # Two candidates: nothing is posted, and the note says why. gh is never
    # reached, so this holds on a machine that does not have it.
    assert comment_on_pull_requests(report, "acme/api") == [
        "Amazon EC2 2026-08-22: 2 deploys in window, no comment posted"
    ]


def test_pr_comment_skips_a_deploy_with_no_revision(tmp_path: Path) -> None:
    report = report_with("timestamp,label\n2026-08-21T18:00:00Z,v2.14\n", tmp_path)
    [note] = comment_on_pull_requests(report, "acme/api")
    assert note.endswith("`v2.14` has no revision to look a PR up by")


def test_ascii_chart_survives_a_flat_and_short_series() -> None:
    days = day_range(START, START + timedelta(days=5))
    chart = render_ascii_chart(days, [10.0] * 5, [], "TOTAL", height=4)
    assert "2026-07-13 → 2026-07-17" in chart
    assert chart.endswith("```")
