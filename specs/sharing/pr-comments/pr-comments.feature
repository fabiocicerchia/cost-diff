@domain:sharing @area:pr-comments @from:cost-diff/cost-diff
Feature: Commenting cost steps on the pull request behind a deploy
  Lets a team tell the authors of a change, on its pull request, that cost stepped after it shipped, without claiming the change caused it.

  Background:
    Given Amazon EC2 stepped up on 2026-08-22
    And the repository is acme/api

  @id:sharing.pr-comments.001 @rule:sharing.pr-comments.single-deploy-with-pr-only @verified @source:cost_diff.py#comment_on_pull_requests @test:tests/test_cost_diff.py#test_pr_comment_skips_a_step_with_no_single_deploy_to_blame @test:tests/test_cost_diff.py#test_pr_comment_skips_a_deploy_with_no_revision
  Scenario Outline: Only a step with one deploy that has a revision and a pull request gets a comment
    Given <situation>
    When the operator runs the timeline with --pr-comment --repo acme/api
    Then the report is printed as usual
    And stderr notes "Amazon EC2 2026-08-22: <note>"

    Examples:
      | situation                                                             | note                                       |
      | only v2.14 (revision 9f3a1c2) is in the window and it came from PR #7 | commented on acme/api#7                    |
      | v2.14 and v2.15 are both in the window                                | 2 deploys in window, no comment posted     |
      | no deploy is in the window                                            | 0 deploys in window, no comment posted     |
      | only v2.14 is in the window and it has no revision                    | `v2.14` has no revision to look a PR up by |
      | only v2.14 is in the window and its commit is in no pull request      | no pull request points at `v2.14`          |

  @id:sharing.pr-comments.002 @rule:sharing.pr-comments.body-quotes-step-and-caveat @verified @source:cost_diff.py#render_pr_comment @test:tests/test_cost_diff.py#test_pr_comment_body_quotes_the_step_and_the_caveat
  Scenario: The comment states the step, its evidence and that attribution is temporal
    Given only v2.14 (revision 9f3a1c2) landed 6 hours before the step
    When the operator runs the timeline with --pr-comment --dry-run
    Then the comment starts "### cost-diff: +$41/day in Amazon EC2 starting 2026-08-22, 6h after `v2.14` — one deploy in window, high confidence."
    And it lists the before/after levels and the deploy line
    And it ends with the detection method, the number of days and the temporal-not-causal caveat

  @id:sharing.pr-comments.003 @rule:sharing.pr-comments.dry-run-posts-nothing @verified @source:cost_diff.py#comment_on_pull_requests @test:tests/test_cost_diff.py#test_one_unreachable_pull_request_does_not_drop_the_other_steps
  Scenario: A dry run shows the comment it would post and posts nothing
    Given only v2.14 (revision 9f3a1c2) is in the window and it came from PR #7
    When the operator runs the timeline with --pr-comment --dry-run
    Then no comment is posted
    And stderr notes "Amazon EC2 2026-08-22: would comment on acme/api#7:" followed by the comment

  @id:sharing.pr-comments.004 @rule:sharing.pr-comments.one-failure-does-not-stop-others @verified @source:cost_diff.py#comment_on_pull_requests @test:tests/test_cost_diff.py#test_one_unreachable_pull_request_does_not_drop_the_other_steps
  Scenario: A step whose comment fails does not stop comments for the other steps
    Given looking up the PR for v2.14 fails with "gh failed: HTTP 422 no commit found"
    And a later Amazon RDS step's only deploy v2.15 came from PR #7
    When the operator runs the timeline with --pr-comment
    Then stderr notes "could not comment for `v2.14`: gh failed: HTTP 422 no commit found"
    And the Amazon RDS step is still commented on acme/api#7
    And the run exits with status 0

  @id:sharing.pr-comments.005 @rule:sharing.pr-comments.repository-inferred-or-required @inferred @source:cost_diff.py#_infer_repo @questionable
  Scenario Outline: The repository to comment on is taken from the flags or the checkout, else the run fails after the report
    Given the deploy source is <source>
    When the operator runs the timeline with --pr-comment and no --repo
    Then <result>

    Examples:
      | source                                    | result                                                                                             |
      | --deploys-github acme/api                 | comments go to acme/api                                                                            |
      | --deploys-git . in a checkout of acme/api | comments go to acme/api, as gh repo view reports it                                                |
      | --deploys-file deploys.csv                | the report is printed, then the run exits 1 with "cost-diff: --pr-comment needs --repo OWNER/REPO" |
