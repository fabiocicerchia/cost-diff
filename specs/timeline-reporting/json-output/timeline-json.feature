@domain:timeline-reporting @area:json-output @from:cost-diff/cost-diff
Feature: Exporting the timeline as JSON
  Gives other tools a machine-readable timeline with the same numbers as the Markdown report.

  Background:
    Given Amazon EC2 stepped from about $100/day to about $141/day on 2026-08-22
    And deploy v2.14 landed at 2026-08-21T18:00Z

  @id:timeline-reporting.json-output.001 @rule:timeline.json.steps-with-confidence-and-lag @verified @source:cost_diff.py#timeline_json @test:tests/test_cost_diff.py#test_timeline_json_carries_the_numbers_and_the_caveat
  Scenario: Each step is exported with its numbers, confidence and deploys with lag
    When the operator runs the timeline with --format json
    Then only JSON is printed, with no chart
    And steps[0] has group "Amazon EC2", day "2026-08-22", before/after/delta in USD per day, pct, score_sigma, method and confidence "high"
    And steps[0].deploys[0] has when "2026-08-21T18:00Z", label "v2.14", source "file" and lag_hours 6.0
    And attribution has window_hours 24 and the temporal-not-causal basis

  @id:timeline-reporting.json-output.002 @rule:timeline.json.detection-settings-recorded @verified @source:cost_diff.py#timeline_json @test:tests/test_cost_diff.py#test_timeline_json_carries_the_numbers_and_the_caveat
  Scenario: The export records the range, metric, grouping and every detection setting
    When the operator runs the timeline with --format json --method pelt --pelt-penalty 5
    Then range, metric, group_by and tag_key are present
    And detection has method "pelt", method_label, window_days, threshold_sigma, min_delta_usd_per_day, ramp_fraction, transition_days and pelt_penalty 5

  @id:timeline-reporting.json-output.003 @rule:timeline.json.series-total-and-stepped-groups @verified @source:cost_diff.py#timeline_json @test:tests/test_cost_diff.py#test_timeline_json_carries_the_numbers_and_the_caveat
  Scenario: Daily series are exported for the total and for groups that stepped
    Given Amazon S3 was flat at $20/day
    When the operator runs the timeline with --format json
    Then days lists all 60 dates
    And series has TOTAL and Amazon EC2
    And series has no Amazon S3
