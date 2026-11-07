@domain:cli @area:exit-and-errors @from:cost-diff/cost-diff
Feature: Reporting failures to the operator
  Tells an operator, in one line and with a failing exit status, what to fix when a run cannot complete.

  @id:cli.exit-and-errors.001 @rule:cli.errors.fixable-problems-one-line-exit-1 @verified @source:cost_diff.py#main @test:tests/test_cost_diff.py#test_bad_timeline_flags_are_reported_not_raised
  Scenario Outline: A problem the operator can fix ends the run with a one-line message and status 1
    Given <problem>
    When the operator runs the timeline
    Then stderr says "cost-diff: " followed by what is wrong
    And there is no traceback
    And the run exits with status 1

    Examples:
      | problem                                     |
      | --window-days is 1                          |
      | the deploy file has an unreadable timestamp |
      | the deploy tool is not installed            |
      | the chart group does not exist              |

  @id:cli.exit-and-errors.002 @rule:cli.errors.aws-and-period-failures-untranslated @inferred @source:cost_diff.py#main @questionable
  Scenario Outline: AWS failures and impossible diff periods end in a traceback, not a cost-diff message
    Given <problem>
    When the operator runs <command>
    Then the run ends with a Python traceback and a non-zero status
    And no "cost-diff: " message is printed

    Examples:
      | problem                                   | command                         |
      | no AWS credentials are configured         | cost-diff diff --last-month     |
      | the credentials lack Cost Explorer access | cost-diff timeline              |
      | the period is not a real month            | cost-diff diff --period 2026-13 |
