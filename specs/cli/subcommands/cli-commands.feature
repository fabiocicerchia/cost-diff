@domain:cli @area:subcommands @from:cost-diff/cost-diff
Feature: Running cost-diff from the command line
  Gives operators two subcommands with documented defaults while keeping old diff command lines working.

  @id:cli.subcommands.001 @rule:cli.legacy.leading-flag-means-diff @verified @source:cost_diff.py#normalise_argv @test:tests/test_cost_diff.py#test_bare_flags_still_mean_the_diff_subcommand
  Scenario Outline: An old command line that starts with a flag still runs the diff
    When the operator runs cost-diff <args>
    Then it runs <runs>

    Examples:
      | args                 | runs                                         |
      | --last-month --top 3 | the diff for last month, top 3               |
      | timeline --days 30   | the timeline over 30 days                    |
      | --help               | the top-level help listing timeline and diff |

  @id:cli.subcommands.002 @rule:cli.timeline.documented-defaults @verified @source:cost_diff.py#_add_timeline_parser @test:tests/test_cost_diff.py#test_timeline_defaults_are_the_documented_ones
  Scenario: The timeline runs with documented defaults when no options are given
    When the operator runs cost-diff timeline
    Then it covers 60 days, grouped by SERVICE, with UnblendedCost
    And it detects steps with median-mad, a 7-day window, 4σ and a $5/day floor
    And it attributes within 24 hours and prints Markdown with an ASCII chart of TOTAL

  @id:cli.subcommands.003 @rule:cli.arguments.usage-errors-refused @inferred @source:cost_diff.py#_build_parser
  Scenario Outline: Missing or conflicting arguments are refused with a usage message
    When the operator runs cost-diff <args>
    Then a usage error naming the problem is printed
    And the run exits with status 2 without querying AWS

    Examples:
      | args                                                |
      | (nothing)                                           |
      | diff                                                |
      | diff --last-month --period 2026-06                  |
      | timeline --deploys-git . --deploys-file deploys.csv |
      | timeline --group TEAM                               |
      | timeline --method kmeans                            |
