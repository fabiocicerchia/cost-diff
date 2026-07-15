from cost_diff import build_diff, month_bounds, previous_month, render


def test_month_arithmetic():
    assert previous_month("2026-01") == "2025-12"
    assert month_bounds("2026-02")[1].day == 28


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
