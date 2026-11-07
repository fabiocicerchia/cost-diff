@domain:sharing @area:slack @from:cost-diff/cost-diff
Feature: Posting the diff to Slack
  Lets a team get the monthly diff in a Slack channel through an incoming webhook.

  Background:
    Given the diff compares 2026-05 → 2026-06 and EC2 went from $100 to $250

  @id:sharing.slack.001 @rule:sharing.slack.posts-header-total-and-movers @verified @source:cost_diff.py#render_slack_blocks @test:tests/test_cost_diff.py#test_render_slack_blocks_uses_mrkdwn_not_gfm
  Scenario: The Slack post carries the title, the total and the top movers
    When the operator runs the diff with --slack https://hooks.slack.example.com/services/T000/B000/XXXX
    Then the Markdown report is printed first
    And Slack receives a header "AWS cost diff: 2026-05 → 2026-06"
    And then "*Total:* $100 → $250 (▲ $150)" in Slack's own bold
    And then a code block with "+$150 EC2: $100 → $250", one line per mover up to --top, with ⚠ right after the amount on flagged ones

  @id:sharing.slack.002 @rule:sharing.slack.https-webhooks-only @inferred @source:cost_diff.py#post_slack @questionable
  Scenario: A Slack webhook that is not https is refused
    When the operator runs the diff with --slack http://hooks.example.com/abc
    Then the report is still printed
    And nothing is sent to the webhook
    And the run stops with "Slack webhook must be an https:// URL" in a Python traceback rather than a cost-diff: message

  @id:sharing.slack.003 @rule:sharing.slack.delivery-failure-not-translated @inferred @source:cost_diff.py#post_slack @questionable
  Scenario: A Slack delivery failure ends the run with a traceback
    Given the webhook answers with an HTTP error or does not answer within 15 seconds
    When the operator runs the diff with --slack <a valid https webhook>
    Then the report is still printed
    And the run ends with a Python traceback and a non-zero exit
