@domain:cost-steps @area:step-detection @from:cost-diff/cost-diff
Feature: Finding the days the daily bill stepped
  Lets an engineer see only real level shifts in daily cost, not noise, spikes or slow drift, so each one can be matched to a deploy.

  Background:
    Given the timeline covers 60 days of daily cost from 2026-07-13

  @id:cost-steps.step-detection.001 @rule:cost-steps.detection.finds-level-shift-on-its-day @verified @source:cost_diff.py#detect_steps @test:tests/test_cost_diff.py#test_clean_step_is_found_on_the_day_cost_moved @test:tests/test_cost_diff.py#test_step_down_is_found_too
  Scenario Outline: A lasting level change is reported on the day cost moved, by either method
    Given Amazon EC2 cost about <before>/day until 2026-08-21 and about <after>/day from 2026-08-22, with ±2% daily noise
    When the operator runs the timeline with --method <method>
    Then one step is reported for Amazon EC2 starting 2026-08-22
    And its size is about <delta>/day

    Examples:
      | method     | before | after | delta |
      | median-mad | $100   | $141  | +$41  |
      | pelt       | $100   | $141  | +$41  |
      | median-mad | $141   | $100  | −$41  |
      | pelt       | $141   | $100  | −$41  |

  @id:cost-steps.step-detection.002 @rule:cost-steps.detection.ignores-noise-and-spikes @verified @source:cost_diff.py#detect_steps @test:tests/test_cost_diff.py#test_flat_series_has_no_step @test:tests/test_cost_diff.py#test_one_day_spike_is_not_a_step
  Scenario Outline: Steady cost and a one-day spike are not steps
    Given Amazon EC2 cost about $100/day throughout, <shape>
    When the operator runs the timeline with --method <method>
    Then no step is reported for Amazon EC2

    Examples:
      | shape                     | method     |
      | with ±2% daily noise      | median-mad |
      | with ±2% daily noise      | pelt       |
      | except $900 on 2026-08-22 | median-mad |
      | except $900 on 2026-08-22 | pelt       |

  @id:cost-steps.step-detection.003 @rule:cost-steps.detection.ramps-are-not-steps @verified @source:cost_diff.py#_is_step_not_ramp @test:tests/test_cost_diff.py#test_gradual_ramp_is_not_reported_as_a_step @test:tests/test_cost_diff.py#test_steep_ramp_is_still_not_a_step
  Scenario Outline: A gradual ramp is not reported as a step, however steep
    Given Amazon EC2 cost rises by <slope> every day from $100/day for 60 days
    When the operator runs the timeline with --method <method>
    Then no step is reported for Amazon EC2

    Examples:
      | slope | method     |
      | $1.50 | median-mad |
      | $1.50 | pelt       |
      | $8    | median-mad |
      | $8    | pelt       |

  @id:cost-steps.step-detection.004 @rule:cost-steps.detection.minimum-size-and-significance @verified @source:cost_diff.py#_pelt_steps @test:tests/test_cost_diff.py#test_small_steps_are_below_the_dollar_floor @test:tests/test_cost_diff.py#test_threshold_sigma_applies_to_pelt_too
  Scenario Outline: Steps smaller than the dollar floor or the sigma threshold are not reported
    Given Amazon EC2 steps from about $100/day to about <after>/day on 2026-08-22
    When the operator runs the timeline with <settings>
    Then <result>

    Examples:
      | after | settings                             | result               |
      | $103  | the default --min-step 5             | no step is reported  |
      | $141  | --method pelt                        | one step is reported |
      | $141  | --method pelt --threshold-sigma 1000 | no step is reported  |

  @id:cost-steps.step-detection.005 @rule:cost-steps.onset.one-step-on-the-day-the-new-level-holds @verified @source:cost_diff.py#_refine_onset @test:tests/test_cost_diff.py#test_mid_day_deploy_taking_two_days_to_bill_is_one_step @test:tests/test_cost_diff.py#test_one_odd_day_does_not_move_the_step_onto_itself
  Scenario Outline: A step that bills over two days, or follows one odd day, is one step on the right day
    Given <shape>
    When the operator runs the timeline with --method <method>
    Then exactly one step is reported for Amazon EC2
    And it starts on <day>

    Examples:
      | shape                                                                   | method     | day                      |
      | $100/day, then $120 on 2026-08-22, then $141/day                        | median-mad | 2026-08-22 or 2026-08-23 |
      | $100/day, then $120 on 2026-08-22, then $141/day                        | pelt       | 2026-08-22 or 2026-08-23 |
      | $200/day with one $140 day on 2026-08-20, then $100/day from 2026-08-22 | median-mad | 2026-08-22               |
      | $200/day with one $140 day on 2026-08-20, then $100/day from 2026-08-22 | pelt       | 2026-08-22               |

  @id:cost-steps.step-detection.006 @rule:cost-steps.detection.per-group-not-total @verified @source:cost_diff.py#build_timeline_report @test:tests/test_cost_diff.py#test_timeline_end_to_end_picks_the_deploy_out_of_the_series
  Scenario: Steps are reported per service, never for the account total
    Given Amazon EC2 steps from $100/day to $141/day on 2026-08-22
    And Amazon S3 is flat at $20/day
    When the operator runs the timeline
    Then exactly one step is reported, for Amazon EC2
    And no step is reported for TOTAL even though the total also moved

  @id:cost-steps.step-detection.007 @rule:cost-steps.detection.needs-a-window-either-side @verified @source:cost_diff.py#detect_steps @test:tests/test_cost_diff.py#test_detection_needs_a_window_either_side @questionable
  Scenario: A range shorter than two windows yields no steps
    Given the timeline covers 10 days with a clear jump in Amazon EC2
    When the operator runs the timeline with --days 10 and the default 7-day window
    Then no step is reported
    And the report says "No step above $5/day in 10 days — the bill moved gradually or not at all."
