@domain:timeline-reporting @area:timeline-text @from:cost-diff/cost-diff
Feature: Reading the timeline report
  Gives an engineer a Markdown account of each cost step, its size and the deploys around it, plus what settings found it.

  Background:
    Given the timeline covers 2026-07-13 to 2026-09-10 grouped by SERVICE with default detection settings

  @id:timeline-reporting.timeline-text.001 @rule:timeline.text.header-states-method-and-sources @verified @source:cost_diff.py#render_timeline @test:tests/test_cost_diff.py#test_timeline_markdown_names_the_deploy_the_lag_and_the_confidence
  Scenario: The report opens with its range, data, detection settings and deploy sources
    Given one deploy was read from a deploy file
    When the operator runs the timeline
    Then the title is "# AWS cost timeline: 2026-07-13 → 2026-09-10"
    And it says "Daily UnblendedCost from Cost Explorer, grouped by SERVICE."
    And it says "Steps: rolling median with a MAD threshold (window 7d, threshold 4σ). Steps under $5/day, and level changes that take longer than 2d to complete, are not reported."
    And it says "1 deploys from file, attributed within 24h." followed by the temporal-not-causal caveat

  @id:timeline-reporting.timeline-text.002 @rule:timeline.text.step-entry-shows-levels-and-deploys @verified @source:cost_diff.py#render_timeline_entry @test:tests/test_cost_diff.py#test_timeline_markdown_names_the_deploy_the_lag_and_the_confidence
  Scenario: Each step shows its daily size, before and after levels and every deploy in its window
    Given Amazon EC2 stepped from $100/day to $141/day on 2026-08-22
    And deploy v2.14 with revision 9f3a1c2 landed at 2026-08-21T18:00Z
    When the operator runs the timeline
    Then the step reads "+$41/day in Amazon EC2 starting 2026-08-22, 6h after `v2.14` — one deploy in window, high confidence."
    And below it: "$100/day → $141/day (+41%), <n>σ over the window's noise"
    And below it: "`v2.14` — 2026-08-21T18:00Z (`9f3a1c2`, file, 6h before the step day)"

  @id:timeline-reporting.timeline-text.003 @rule:timeline.text.lag-in-readable-units @inferred @source:cost_diff.py#_hours
  Scenario Outline: The time between deploy and step is shown in hours, or days past 48 hours
    Given the only deploy in the window landed <lag> before the step day
    When the operator runs the timeline with --deploy-window 72
    Then the headline says "<shown> after `v2.14`"

    Examples:
      | lag        | shown |
      | 30 minutes | <1h   |
      | 6 hours    | 6h    |
      | 47 hours   | 47h   |
      | 60 hours   | 2.5d  |

  @id:timeline-reporting.timeline-text.004 @rule:timeline.text.no-step-and-no-deploy-messages @verified @source:cost_diff.py#render_timeline @test:tests/test_cost_diff.py#test_timeline_markdown_says_so_when_nothing_stepped @test:tests/test_cost_diff.py#test_timeline_without_deploys_reports_the_step_unattributed
  Scenario Outline: The report says plainly when nothing stepped or no deploys were given
    Given <situation>
    When the operator runs the timeline
    Then the report says "<message>"

    Examples:
      | situation                                       | message                                                                   |
      | no group moved by more than $5/day over 60 days | No step above $5/day in 60 days — the bill moved gradually or not at all. |
      | no deploy source was given                      | No deploys given — steps are reported unattributed (see --deploys-*).     |
