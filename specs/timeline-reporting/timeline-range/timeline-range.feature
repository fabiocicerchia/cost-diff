@domain:timeline-reporting @area:timeline-range @from:cost-diff/cost-diff
Feature: Choosing what the timeline covers
  Lets the operator pick the days, grouping and tag the timeline pulls, and refuses settings that cannot work before any paid query is made.

  @id:timeline-reporting.timeline-range.001 @rule:timeline.range.days-ending-yesterday-or-given-end @verified @source:cost_diff.py#_timeline_range @test:tests/test_cost_diff.py#test_timeline_defaults_are_the_documented_ones @test:tests/test_cost_diff.py#test_timeline_json_carries_the_numbers_and_the_caveat
  Scenario Outline: The timeline covers whole days ending yesterday or on the given end date
    Given today is 2026-11-07
    When the operator runs the timeline with <flags>
    Then daily cost from <first> to <last> inclusive is used
    And today's partial day is never included unless named by --end

    Examples:
      | flags                      | first      | last       |
      | no range flags             | 2026-09-08 | 2026-11-06 |
      | --days 60 --end 2026-09-10 | 2026-07-13 | 2026-09-10 |
      | --days 7                   | 2026-10-31 | 2026-11-06 |

  @id:timeline-reporting.timeline-range.002 @rule:timeline.range.invalid-settings-refused-before-querying @verified @source:cost_diff.py#_validate_timeline_args @test:tests/test_cost_diff.py#test_bad_timeline_flags_are_reported_not_raised
  Scenario Outline: Settings that cannot work are refused before any cost is fetched
    When the operator runs the timeline with <flag>
    Then the run exits with status 1
    And stderr says "cost-diff: <message>"
    And Cost Explorer is not queried

    Examples:
      | flag                | message                                          |
      | --days 0            | --days must be at least 1, got 0                 |
      | --days -5           | --days must be at least 1, got -5                |
      | --window-days 1     | --window-days must be at least 2, got 1          |
      | --transition-days 0 | --transition-days must be at least 1, got 0      |
      | --chart-height 0    | --chart-height must be at least 1, got 0         |
      | --deploy-window -1  | --deploy-window must be at least 0, got -1       |
      | --cache-ttl -1      | --cache-ttl must be at least 0, got -1           |
      | --end 2026-9-1      | --end '2026-9-1' is not a date — want YYYY-MM-DD |

  @id:timeline-reporting.timeline-range.003 @rule:timeline.range.deploys-checked-before-paid-query @inferred @source:cost_diff.py#build_timeline_report
  Scenario: A broken deploy source fails the run before any cost is fetched
    Given deploys.csv does not exist
    When the operator runs the timeline with --deploys-file deploys.csv
    Then the run exits with status 1 naming deploys.csv
    And Cost Explorer is not queried, so no API charge is incurred

  @id:timeline-reporting.timeline-range.004 @rule:timeline.grouping.service-and-tag-labels @verified @source:cost_diff.py#fetch_daily_costs @test:tests/test_cost_diff.py#test_fetch_daily_costs_groups_by_service_and_tag
  Scenario: With a tag, each series is named by service and tag value
    Given Amazon EC2 spend is tagged Environment=prod on some resources and untagged on others
    When the operator runs the timeline with --tag Environment
    Then series are named "Amazon EC2 / prod" and "Amazon EC2 / Environment: untagged"
    And the report says it is "grouped by SERVICE and tag Environment"

  @id:timeline-reporting.timeline-range.005 @rule:timeline.series.missing-days-are-zero @verified @source:cost_diff.py#densify @test:tests/test_cost_diff.py#test_densify_fills_missing_days_with_zero_and_totals
  Scenario: A day with no cost reported counts as zero spend
    Given EC2 billed $10 on day 1, nothing on day 2, $30 on day 3
    And S3 billed $5 on day 2 only
    When the operator runs the timeline over those 3 days
    Then EC2's series reads 10, 0, 30
    And the TOTAL series reads 10, 5, 30
