from cost_diff import build_diff, month_bounds, previous_month, render, weekday_count


def test_month_arithmetic():
    assert previous_month("2026-01") == "2025-12"
    assert month_bounds("2026-02")[1].day == 28


def test_weekday_count():
    assert weekday_count("2026-06") == 22  # June 2026: 30 days, 8 weekend days


def test_anomaly_flags_unexplained_swings_same_weekday_count():
    # same period twice -> weekday ratio 1 -> expected pct is 0
    rows = build_diff(
        {"EC2": 100.0, "S3": 100.0},
        {"EC2": 1000.0, "S3": 115.0},
        old_period="2026-06",
        new_period="2026-06",
    )
    by_group = {r["group"]: r for r in rows}
    assert by_group["EC2"]["anomaly"] is True  # +900%, nothing explains that
    assert by_group["S3"]["anomaly"] is False  # +15%, below the noise floor


def test_no_anomaly_field_set_without_periods():
    rows = build_diff({"EC2": 100.0}, {"EC2": 1000.0})
    assert rows[0]["anomaly"] is False


def test_render_slack_blocks_uses_mrkdwn_not_gfm():
    from cost_diff import render_slack_blocks

    rows = build_diff({"EC2": 100.0}, {"EC2": 250.0})
    payload = render_slack_blocks(rows, "2026-06", "2026-05")
    blocks = payload["blocks"]
    assert blocks[0]["text"]["text"] == "AWS cost diff: 2026-05 → 2026-06"
    total_text = blocks[1]["text"]["text"]
    assert total_text.startswith("*Total:*") and "**" not in total_text
    assert "EC2" in blocks[2]["text"]["text"]


def test_diff_sorted_by_magnitude_and_thresholded():
    rows = build_diff(
        {"EC2": 1000.0, "S3": 50.0, "Athena": 10.0},
        {"EC2": 1400.0, "S3": 49.5, "RDS": 200.0, "Athena": 10.0},
    )
    assert [r["group"] for r in rows] == ["EC2", "RDS"]  # S3 under threshold, Athena unchanged
    assert rows[1]["pct"] is None  # new service has no baseline pct


def test_render_contains_totals_and_table():
    rows = build_diff({"EC2": 100.0}, {"EC2": 250.0})
    out = render(rows, "2026-06", "2026-05")
    assert "2026-05 → 2026-06" in out and "| EC2 |" in out and "▲ $150" in out


def test_fetch_costs_pagination_shape():
    class FakeCE:
        def __init__(self):
            self.calls = 0

        def get_cost_and_usage(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "ResultsByTime": [
                        {
                            "Groups": [
                                {"Keys": ["EC2"], "Metrics": {"UnblendedCost": {"Amount": "10"}}}
                            ]
                        }
                    ],
                    "NextPageToken": "t",
                }
            return {
                "ResultsByTime": [
                    {"Groups": [{"Keys": ["EC2"], "Metrics": {"UnblendedCost": {"Amount": "5"}}}]}
                ]
            }

    from cost_diff import fetch_costs

    assert fetch_costs("2026-06", client=FakeCE()) == {"EC2": 15.0}


def test_fetch_costs_uses_selected_metric():
    class FakeCE:
        def get_cost_and_usage(self, **kwargs):
            assert kwargs["Metrics"] == ["AmortizedCost"]
            return {
                "ResultsByTime": [
                    {"Groups": [{"Keys": ["EC2"], "Metrics": {"AmortizedCost": {"Amount": "42"}}}]}
                ]
            }

    from cost_diff import fetch_costs

    assert fetch_costs("2026-06", client=FakeCE(), metric="AmortizedCost") == {"EC2": 42.0}


def test_fetch_costs_applies_filter_dimension():
    class FakeCE:
        def get_cost_and_usage(self, **kwargs):
            assert kwargs["Filter"] == {"Dimensions": {"Key": "SERVICE", "Values": ["EC2"]}}
            return {
                "ResultsByTime": [
                    {"Groups": [{"Keys": ["BoxUsage"], "Metrics": {"UnblendedCost": {"Amount": "7"}}}]}
                ]
            }

    from cost_diff import fetch_costs

    result = fetch_costs("2026-06", "USAGE_TYPE", client=FakeCE(), filter_dimension=("SERVICE", "EC2"))
    assert result == {"BoxUsage": 7.0}


def test_render_why_lists_usage_types():
    from cost_diff import build_diff, render_why

    rows = build_diff({"BoxUsage": 100.0}, {"BoxUsage": 300.0})
    out = render_why(rows, "EC2")
    assert "Why EC2 moved" in out and "BoxUsage" in out
