@domain:timeline-reporting @area:cost-charts @from:cost-diff/cost-diff
Feature: Charting the daily cost series
  Lets a reader see the shape of daily cost with deploy days marked, in a terminal or a Mermaid-rendering page.

  Background:
    Given the timeline covers 2026-07-13 to 2026-09-10
    And deploy v2.14 landed on 2026-08-21

  @id:timeline-reporting.cost-charts.001 @rule:timeline.charts.deploy-days-marked @verified @source:cost_diff.py#render_chart @test:tests/test_cost_diff.py#test_ascii_chart_marks_deploy_days @test:tests/test_cost_diff.py#test_mermaid_chart_is_a_xychart_with_the_deploy_day_marked
  Scenario Outline: The chart marks every deploy day with ▲ and lists the deploys
    When the operator runs the timeline with --chart <kind>
    Then the Series section shows <chart>
    And 2026-08-21 is marked ▲
    And the deploy is listed as <legend>

    Examples:
      | kind    | chart                                                                                                  | legend                   |
      | ascii   | a block-character column chart titled "UnblendedCost per day — TOTAL" with the max and min on its axis | ▲ 2026-08-21  v2.14      |
      | mermaid | a xychart-beta block with the x-axis label "21▲" and a USD/day y-axis                                  | - ▲ 2026-08-21 — `v2.14` |

  @id:timeline-reporting.cost-charts.002 @rule:timeline.charts.series-and-height-selectable @verified @source:cost_diff.py#render_timeline @test:tests/test_cost_diff.py#test_timeline_defaults_are_the_documented_ones
  Scenario Outline: The operator chooses which series to chart, how tall, or no chart
    When the operator runs the timeline with <flags>
    Then <result>

    Examples:
      | flags                                       | result                                       |
      | no chart flags                              | the TOTAL series is charted 10 rows high     |
      | --chart-group 'Amazon EC2' --chart-height 5 | the Amazon EC2 series is charted 5 rows high |
      | --chart none                                | the report has no Series section             |

  @id:timeline-reporting.cost-charts.003 @rule:timeline.charts.unknown-series-refused @verified @source:cost_diff.py#TimelineReport @test:tests/test_cost_diff.py#test_chart_group_that_does_not_exist_says_which_ones_do
  Scenario: Charting a series that does not exist names the ones that do
    Given the timeline has series for Amazon EC2, Amazon S3 and TOTAL
    When the operator runs the timeline with --chart-group 'Amazon Athena'
    Then the run exits with status 1
    And stderr says "cost-diff: no series for 'Amazon Athena'; try one of: Amazon EC2, Amazon S3, TOTAL"
    And no report is printed, though Cost Explorer was already queried

  @id:timeline-reporting.cost-charts.004 @rule:timeline.charts.degenerate-series-render @verified @source:cost_diff.py#render_ascii_chart @test:tests/test_cost_diff.py#test_ascii_chart_survives_a_flat_and_short_series @test:tests/test_cost_diff.py#test_chart_of_an_empty_range_says_so_instead_of_raising
  Scenario Outline: A flat, short or empty series still produces a chart
    Given <series>
    When the operator runs the timeline
    Then the chart shows <shown>

    Examples:
      | series                   | shown                                                         |
      | 5 days at a flat $10/day | the range as "2026-07-13 → 2026-07-17" in a closed text block |
      | no days in range         | "(no days in range)"                                          |
