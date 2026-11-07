@domain:operations @area:container-image @from:cost-diff/dockerfile
Feature: Running cost-diff from the container image
  Operators who prefer containers can run the cost-diff CLI from a published image that behaves like the installed command, runs unprivileged and contains only verified dependencies.

  Background:
    Given the operator has the cost-diff container image

  @id:operations.container-image.001 @rule:operations.container-image.runs-cost-diff-command @inferred @source:Dockerfile#ENTRYPOINT
  Scenario Outline: Arguments given to the container go straight to the cost-diff command
    When the operator runs the container with the arguments "<arguments>"
    Then the cost-diff command runs with "<arguments>"
    And the output is the same as running "cost-diff <arguments>" from an installed copy, given the same AWS credentials and files are available inside the container

    Examples:
      | arguments                             |
      | timeline --deploys-file deploys.csv   |
      | diff --last-month                     |
      | --help                                |

  @id:operations.container-image.002 @rule:operations.container-image.runs-as-non-root @inferred @source:Dockerfile#USER
  Scenario: The container runs the CLI as an unprivileged user
    When the operator runs the container without overriding the user
    Then the cost-diff command runs as the user "app" with uid 10001
    And the process has no root privileges inside the container

  @id:operations.container-image.003 @rule:operations.container-image.only-hash-verified-dependencies @inferred @source:Dockerfile#build
  Scenario: The image is built only from dependencies whose hashes match the lockfiles
    Given a dependency downloaded during the image build does not match the hash in its lockfile
    When the release pipeline builds the image
    Then the build fails
    And no image is produced
