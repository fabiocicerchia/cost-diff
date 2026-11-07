@domain:attribution @area:temporal-matching @from:cost-diff/cost-diff
Feature: Pairing each cost step with the deploys before it
  Tells an engineer which deploy, if any, landed just before a cost step, and how sure that pairing is, without claiming cause.

  Background:
    Given Amazon EC2 stepped up on 2026-08-22
    And the deploy window is the default 24 hours

  @id:attribution.temporal-matching.001 @rule:attribution.matching.window-before-and-during-step-day @verified @source:cost_diff.py#attribute @test:tests/test_cost_diff.py#test_one_deploy_in_window_is_attributed_with_high_confidence @test:tests/test_cost_diff.py#test_deploy_during_the_step_day_is_in_window_with_a_negative_lag @test:tests/test_cost_diff.py#test_deploy_outside_the_window_is_not_attributed @test:tests/test_cost_diff.py#test_timeline_markdown_names_the_deploy_the_lag_and_the_confidence
  Scenario Outline: A deploy counts if it landed within the window before the step day or during it
    Given the only deploy, v2.14, landed at <when>
    When the operator runs the timeline with that deploy
    Then the step <attributed>
    And <phrase>

    Examples:
      | when              | attributed             | phrase                                                     |
      | 2026-08-21T18:00Z | is attributed to v2.14 | the headline says "6h after `v2.14`"                       |
      | 2026-08-22T14:00Z | is attributed to v2.14 | the headline says "with `v2.14` 14h into that day"         |
      | 2026-08-20T18:00Z | is unattributed        | the headline says "no deploy in the window — unattributed" |
      | 2026-08-23T00:00Z | is unattributed        | the headline says "no deploy in the window — unattributed" |

  @id:attribution.temporal-matching.002 @rule:attribution.matching.window-is-configurable @verified @source:cost_diff.py#attribute @test:tests/test_cost_diff.py#test_window_is_configurable
  Scenario: The operator can widen how far back of a step deploys are looked for
    Given the only deploy, v2.14, landed at 2026-08-20T18:00Z, 30 hours before the step day
    When the operator runs the timeline with --deploy-window 48
    Then the step is attributed to v2.14
    And the report says deploys were "attributed within 48h"

  @id:attribution.temporal-matching.003 @rule:attribution.confidence.by-deploys-in-window @verified @source:cost_diff.py#Attribution @test:tests/test_cost_diff.py#test_two_deploys_in_window_are_listed_rather_than_guessed @test:tests/test_cost_diff.py#test_three_deploys_in_window_drop_to_low_confidence @test:tests/test_cost_diff.py#test_timeline_markdown_lists_both_deploys_when_two_are_in_window @test:tests/test_cost_diff.py#test_timeline_without_deploys_reports_the_step_unattributed
  Scenario Outline: Confidence depends on how many deploys share the window, and several are listed rather than picked
    Given <count> deploys landed in the step's window
    When the operator runs the timeline
    Then the step's confidence is <confidence>
    And the headline ends "<phrase>."
    And every deploy in the window is listed under the step, newest first

    Examples:
      | count | confidence | phrase                                                       |
      | 0     | none       | no deploy in the window — unattributed                       |
      | 1     | high       | one deploy in window, high confidence                        |
      | 2     | medium     | 2 deploys in window, medium confidence — listed, not guessed |
      | 3     | low        | 3 deploys in window, low confidence — listed, not guessed    |

  @id:attribution.temporal-matching.004 @rule:attribution.confidence.temporal-not-causal-disclaimer @verified @source:cost_diff.py#_source_summary @test:tests/test_cost_diff.py#test_timeline_markdown_names_the_deploy_the_lag_and_the_confidence @test:tests/test_cost_diff.py#test_timeline_json_carries_the_numbers_and_the_caveat @test:tests/test_cost_diff.py#test_pr_comment_body_quotes_the_step_and_the_caveat
  Scenario Outline: Every attributed output says the pairing is temporal, not causal
    Given deploys were supplied
    When the operator produces the timeline as <output>
    Then it contains "Attribution is temporal, not causal: the deploy preceded the step, which is not proof that it caused it."

    Examples:
      | output                        |
      | Markdown                      |
      | JSON, under attribution.basis |
      | a pull request comment        |
