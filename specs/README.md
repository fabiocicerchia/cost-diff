# Specifications of cost-diff

What this code does, one atomic Gherkin scenario per behaviour, read from the code by code-atlas.
Tags: `@verified` a test asserts it · `@inferred` read from the code only · `@gap` an entry point no test covers · `@human` written or amended by a person, never rewritten.

## Deploy attribution
Matching each cost step to the deploy that came just before it, by time only and never as cause.

- **Temporal matching**: [Pairing each cost step with the deploys before it](attribution/temporal-matching/deploy-attribution.feature) (4)

## Command line
How users call the tool and how it starts up.

- **Exit codes and errors**: [Reporting failures to the operator](cli/exit-and-errors/exit-and-errors.feature) (2)
- **Subcommands and flags**: [Running cost-diff from the command line](cli/subcommands/cli-commands.feature) (3)

## Cost data
Getting cost figures out of AWS Cost Explorer and into a shape the reports can use.

- **Response cache**: [Reusing Cost Explorer answers between runs](cost-data/response-cache/response-cache.feature) (4)

## Cost step detection
Spotting lasting jumps or drops in daily cost, using explainable stdlib statistics.

- **Step detection**: [Finding the days the daily bill stepped](cost-steps/step-detection/step-detection.feature) (7)

## Deploy history
Collecting the deploy events that cost steps are lined up against.

- **Deploy files**: [Importing deploys from a file](deploys/file-deploys/deploy-files.feature) (4)
- **Git tags**: [Reading deploys from git tags](deploys/git-deploys/git-deploys.feature) (2)
- **GitHub Deployments**: [Reading deploys from GitHub Deployments and Argo CD](deploys/github-deploys/github-argocd-deploys.feature) (3)

## Distribution and developer tooling
Installing, packaging and building the CLI, and the developer workflow around it.

- **Container image**: [Running cost-diff from the container image](operations/container-image/container-image.feature) (3)
- **One-line installer**: [Installing cost-diff with one command](operations/installer/one-line-installer.feature) (2)

## Period comparison
The diff report that compares one month's spend with an earlier month.

- **Change ranking**: [Comparing a month's AWS cost with an earlier month](period-diff/change-ranking/month-over-month-diff.feature) (5)
- **Diff report**: [Reading the period diff report](period-diff/diff-report/diff-report.feature) (4)

## Notifications and sharing
Sending findings to the places teams already work.

- **Pull request comments**: [Commenting cost steps on the pull request behind a deploy](sharing/pr-comments/pr-comments.feature) (5)
- **Slack posts**: [Posting the diff to Slack](sharing/slack/slack-posts.feature) (3)

## Timeline reports
Showing detected steps and their matched deploys to people and to tools.

- **Cost charts**: [Charting the daily cost series](timeline-reporting/cost-charts/cost-charts.feature) (4)
- **JSON output**: [Exporting the timeline as JSON](timeline-reporting/json-output/timeline-json.feature) (3)
- **Timeline range and grouping**: [Choosing what the timeline covers](timeline-reporting/timeline-range/timeline-range.feature) (5)
- **Timeline narrative**: [Reading the timeline report](timeline-reporting/timeline-text/timeline-narrative.feature) (4)
