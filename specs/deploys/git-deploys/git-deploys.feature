@domain:deploys @area:git-deploys @from:cost-diff/cost-diff
Feature: Reading deploys from git tags
  Lets a team that tags releases use its own checkout as the deploy log with no extra service.

  Background:
    Given the checkout has tags v2.13 (lightweight) and v2.14 (annotated, created 2026-09-02T18:00Z)

  @id:deploys.git-deploys.001 @rule:deploys.git.tags-as-deploys @verified @source:cost_diff.py#deploys_from_git @test:tests/test_cost_diff.py#test_annotated_tag_reports_the_commit_not_the_tag_object
  Scenario Outline: Each matching tag is a deploy dated by its creation, pointing at its commit
    When the operator runs the timeline with --deploys-git and <pattern>
    Then the deploys are <deploys>
    And v2.14's revision is the commit it tags, not the tag object

    Examples:
      | pattern               | deploys         |
      | no --tag-pattern      | v2.13 and v2.14 |
      | --tag-pattern 'v2.14' | v2.14 only      |

  @id:deploys.git-deploys.002 @rule:deploys.external-tools.failures-reported @inferred @source:cost_diff.py#_run
  Scenario Outline: A missing, failing or hung deploy tool is reported by name
    Given <situation>
    When the operator runs the timeline with <flag>
    Then the run exits with status 1
    And stderr says "cost-diff: <message>"

    Examples:
      | situation                                | flag                       | message                                                |
      | git is not installed                     | --deploys-git              | git is not on PATH — install it, or use --deploys-file |
      | gh is not installed                      | --deploys-github acme/api  | gh is not on PATH — install it, or use --deploys-file  |
      | the path is not a git checkout           | --deploys-git /tmp/nowhere | git failed: <git's last error line>                    |
      | argocd does not answer within 60 seconds | --deploys-argocd checkout  | argocd timed out after 60s                             |
