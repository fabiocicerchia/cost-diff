@domain:cli @area:exit-and-errors @from:cost-diff/cost-diff
Feature: Reporting failures to the operator
  Tells an operator, in one line and with a failing exit status, what to fix when a run cannot complete.

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
