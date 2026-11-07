@domain:period-diff @area:diff-report @from:cost-diff/cost-diff
Feature: Reading the period diff report
  Gives the reader of a diff a Markdown table they can paste anywhere, with a total and signed dollar changes.

  Background:
    Given the diff compares 2026-05 → 2026-06

  @id:period-diff.diff-report.001 @rule:period-diff.report.total-with-trend-arrow @verified @source:cost_diff.py#render @test:tests/test_cost_diff.py#test_render_contains_totals_and_table @test:tests/test_cost_diff.py#test_render_zero_net_change_uses_neutral_arrow
  Scenario Outline: The report heads with the total before and after and which way it moved
    Given the listed services cost <before> in 2026-05 and <after> in 2026-06
    When the operator runs the diff
    Then the title is "# AWS cost diff: 2026-05 → 2026-06"
    And the total line reads "**Total: <before> → <after> (<trend>)**"

    Examples:
      | before | after | trend  |
      | $100   | $250  | ▲ $150 |
      | $200   | $200  | → $0   |
      | $300   | $120  | ▼ $180 |

  @id:period-diff.diff-report.002 @rule:period-diff.report.total-excludes-sub-threshold-services @inferred @source:cost_diff.py#_totals @questionable
  Scenario: Services that moved less than the threshold are left out of the total
    Given EC2 went from $100 to $250
    And S3 went from $50 to $50.50
    When the operator runs the diff with the default $1 threshold
    Then the total line reads "**Total: $100 → $250 (▲ $150)**"
    And S3's $50 is in neither side of the total

  @id:period-diff.diff-report.003 @rule:period-diff.report.top-n-with-hidden-count @verified @source:cost_diff.py#render @test:tests/test_cost_diff.py#test_render_hidden_rows_message_blames_top_not_threshold
  Scenario: Only the top movers are shown, with a count of the rest
    Given 5 services each moved by more than the threshold
    When the operator runs the diff with --top 3
    Then 3 service rows are listed
    And the report says "…and 2 more changes above the threshold, not shown (see --top)."

  @id:period-diff.diff-report.004 @rule:period-diff.report.signed-whole-dollar-changes @verified @source:cost_diff.py#_change_row @test:tests/test_cost_diff.py#test_render_contains_totals_and_table @questionable
  Scenario Outline: Each change is a signed whole-dollar amount with its percentage
    Given <service> went from <before> to <after>
    When the operator runs the diff with --threshold 0
    Then its row reads "<row>"

    Examples:
      | service | before | after | row                                           |
      | EC2     | $100   | $250  | \| +$150 (+150%) \| EC2 \| $100 \| $250 \|   |
      | S3      | $100   | $60   | \| −$40 (-40%) \| S3 \| $100 \| $60 \|       |
      | RDS     | $0     | $200  | \| +$200 (new) \| RDS \| $0 \| $200 \|       |
      | Lambda  | $80    | $80   | \| −$0 (+0%) \| Lambda \| $80 \| $80 \|      |
