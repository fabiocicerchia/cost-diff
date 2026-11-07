@domain:deploys @area:github-deploys @from:cost-diff/cost-diff
Feature: Reading deploys from GitHub Deployments and Argo CD
  Lets teams that already record deploys in GitHub or Argo CD use that history through the CLIs they are signed in to.

  @id:deploys.github-deploys.001 @rule:deploys.github.environment-ref-labels @inferred @source:cost_diff.py#deploys_from_github
  Scenario Outline: GitHub deployments are labelled by environment and ref
    Given acme/api has a deployment to <environment> of ref <ref>, id 123, created 2026-08-21T18:00:00Z
    When the operator runs the timeline with --deploys-github acme/api
    Then a deploy labelled <label> at 2026-08-21T18:00Z is used
    And its link is the deployment's html_url when present

    Examples:
      | environment | ref    | label            |
      | production  | v2.14  | production/v2.14 |
      | (none)      | v2.14  | v2.14            |
      | (none)      | (none) | deployment 123   |

  @id:deploys.github-deploys.002 @rule:deploys.github.most-recent-100-only @inferred @source:cost_diff.py#deploys_from_github @questionable
  Scenario: Only the most recent 100 GitHub deployments are read
    Given acme/api has 250 deployments
    When the operator runs the timeline with --deploys-github acme/api
    Then at most 100 deployments are used
    And nothing in the report says older deployments were not read

  @id:deploys.github-deploys.003 @rule:deploys.argocd.sync-history @inferred @source:cost_diff.py#deploys_from_argocd @questionable
  Scenario Outline: Argo CD sync history entries become deploys labelled by app and revision
    Given Argo CD app checkout has history entries <entries>
    When the operator runs the timeline with --deploys-argocd checkout
    Then the deploys used are <deploys>

    Examples:
      | entries                                                    | deploys                               |
      | id 4, revision 9f3a1c2d8e, deployedAt 2026-08-21T18:00:00Z | checkout@9f3a1c2 at 2026-08-21T18:00Z |
      | id 5, no revision, deployedAt 2026-08-25T09:00:00Z         | checkout#5 at 2026-08-25T09:00Z       |
      | id 6, revision abc, no time                                | none: the entry is skipped            |
