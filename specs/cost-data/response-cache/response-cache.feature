@domain:cost-data @area:response-cache @from:cost-diff/cost-diff
Feature: Reusing Cost Explorer answers between runs
  Saves the operator Cost Explorer charges when re-running a timeline while tuning detection settings.

  Background:
    Given each Cost Explorer query is billed

  @id:cost-data.response-cache.001 @rule:cost-data.cache.reuse-within-lifetime @verified @source:cost_diff.py#fetch_daily_costs @test:tests/test_cost_diff.py#test_response_cache_saves_a_second_call
  Scenario: A repeated timeline within the cache lifetime does not query Cost Explorer again
    Given the operator ran the timeline for the same range, metric, grouping and tag with --cache-dir ~/.cache/cost-diff 2 hours ago
    When the operator runs it again with --cache-dir ~/.cache/cost-diff and a different --threshold-sigma
    Then the same daily costs are used
    And Cost Explorer is not queried

  @id:cost-data.response-cache.002 @rule:cost-data.cache.expires-after-ttl @verified @source:cost_diff.py#ResponseCache @test:tests/test_cost_diff.py#test_expired_cache_entry_is_a_miss
  Scenario Outline: A saved answer older than the cache lifetime is fetched again
    Given the operator ran the same timeline with --cache-dir ~/.cache/cost-diff <age> ago
    When the operator runs it again with --cache-ttl <ttl>
    Then Cost Explorer <queried>

    Examples:
      | age      | ttl            | queried          |
      | 30 hours | the default 24 | is queried again |
      | 2 hours  | 24             | is not queried   |
      | 1 minute | 0              | is queried again |

  @id:cost-data.response-cache.003 @rule:cost-data.cache.damaged-entry-never-fails-run @verified @source:cost_diff.py#ResponseCache @test:tests/test_cost_diff.py#test_a_corrupt_cache_entry_is_a_miss
  Scenario: A damaged saved answer is ignored rather than failing the run
    Given the saved answer for this timeline has been hand-edited into an unreadable state
    When the operator runs the timeline with the same --cache-dir
    Then Cost Explorer is queried again
    And the report is produced

  @id:cost-data.response-cache.004 @rule:cost-data.cache.opt-in-timeline-only @inferred @source:cost_diff.py#build_timeline_report
  Scenario Outline: Answers are only kept on disk when the operator asks, and only for the timeline
    When the operator runs <command>
    Then <result>

    Examples:
      | command                                           | result                                                        |
      | cost-diff timeline                                | Cost Explorer is queried and nothing is written to disk       |
      | cost-diff timeline --cache-dir ~/.cache/cost-diff | the answer is saved under ~/.cache/cost-diff                  |
      | cost-diff diff --last-month                       | Cost Explorer is queried every time; there is no cache option |
