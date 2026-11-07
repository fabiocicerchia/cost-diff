@domain:period-diff @area:change-ranking @from:cost-diff/cost-diff
Feature: Comparing a month's AWS cost with an earlier month
  Lets a FinOps owner see which AWS services moved between two months, biggest mover first, and why the top one moved.

  Background:
    Given Cost Explorer has monthly cost for the account

  @id:period-diff.change-ranking.001 @rule:period-diff.periods.baseline-defaults-to-previous-month @verified @source:cost_diff.py#_run_diff @test:tests/test_cost_diff.py#test_month_arithmetic
  Scenario Outline: The baseline is the month before the analysed month unless one is named
    Given today is 2026-11-07
    When the operator runs cost-diff diff with <flags>
    Then the report compares <baseline> → <period>

    Examples:
      | flags                         | baseline | period  |
      | --last-month                  | 2026-09  | 2026-10 |
      | --period 2026-01              | 2025-12  | 2026-01 |
      | --period 2026-06 --vs 2026-03 | 2026-03  | 2026-06 |

  @id:period-diff.change-ranking.002 @rule:period-diff.ranking.largest-absolute-change-first @verified @source:cost_diff.py#build_diff @test:tests/test_cost_diff.py#test_diff_sorted_by_magnitude_and_thresholded
  Scenario: Changes are listed biggest absolute mover first and small changes are left out
    Given EC2 went from $1,000 to $1,400
    And RDS went from $0 to $200
    And S3 went from $50 to $49.50
    And Athena stayed at $10
    When the operator runs the diff with the default $1 threshold
    Then the rows are EC2 then RDS
    And S3 and Athena are not listed
    And RDS shows "(new)" instead of a percentage

  @id:period-diff.change-ranking.003 @rule:period-diff.weekdays.flag-unexplained-swings @verified @source:cost_diff.py#build_diff @test:tests/test_cost_diff.py#test_anomaly_flags_unexplained_swings_same_weekday_count @test:tests/test_cost_diff.py#test_weekday_count
  Scenario Outline: A swing the difference in weekdays cannot explain is flagged
    Given <baseline> has <old_weekdays> weekdays and <period> has <new_weekdays>
    And <service> went from <before> to <after>
    When the operator runs the diff for <period> against <baseline>
    Then the <service> row <flagged> marked ⚠
    And when any row is marked, the report explains "⚠ = change not explained by the business-day-count difference between periods."

    Examples:
      | baseline | period  | old_weekdays | new_weekdays | service | before | after  | flagged |
      | 2026-06  | 2026-06 | 22           | 22           | EC2     | $100   | $1,000 | is      |
      | 2026-06  | 2026-06 | 22           | 22           | S3      | $100   | $115   | is not  |
      | 2026-02  | 2026-03 | 20           | 22           | S3      | $100   | $125   | is not  |
      | 2026-02  | 2026-03 | 20           | 22           | EC2     | $100   | $140   | is      |

  @id:period-diff.change-ranking.004 @rule:period-diff.usage-breakdown.top-service-by-usage-type @verified @source:cost_diff.py#_usage_type_breakdown @test:tests/test_cost_diff.py#test_render_why_lists_usage_types @questionable
  Scenario Outline: The biggest service mover can be broken down by usage type
    Given EC2 is the biggest mover between 2026-05 and 2026-06
    And within EC2, BoxUsage went from $100 to $300
    When the operator runs the diff with --why and <group>
    Then the report <outcome>

    Examples:
      | group                        | outcome                                                                                             |
      | the default SERVICE grouping | ends with a "### Why EC2 moved (by usage type)" table listing BoxUsage +$200, at most 5 usage types |
      | --group REGION               | has no usage-type section and no warning that --why was ignored                                     |

  @id:period-diff.change-ranking.005 @rule:cost-data.metrics.chosen-metric-is-reported @verified @source:cost_diff.py#fetch_costs @test:tests/test_cost_diff.py#test_fetch_costs_uses_selected_metric
  Scenario Outline: The operator chooses which cost measure is compared
    Given Cost Explorer reports both unblended and amortized cost
    When the operator runs cost-diff <command> <flags>
    Then the costs shown are the <metric> amounts
    And <named>

    Examples:
      | command  | flags                     | metric           | named                                                         |
      | diff     | --metric AmortizedCost    | AmortizedCost    | the diff table holds amortized amounts                        |
      | timeline | --metric NetUnblendedCost | NetUnblendedCost | the timeline says "Daily NetUnblendedCost from Cost Explorer" |
      | timeline | with no --metric          | UnblendedCost    | the timeline says "Daily UnblendedCost from Cost Explorer"    |
