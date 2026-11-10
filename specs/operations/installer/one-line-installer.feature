@domain:operations @area:installer @from:cost-diff/install
Feature: Installing cost-diff with one command
  Gives operators a single curl-pipe command that installs the cost-diff CLI from GitHub with whatever Python installer the machine already has.

  Background:
    Given the operator pipes the cost-diff install script from GitHub into bash

  @id:operations.installer.001 @rule:operations.installer.prefers-pipx-falls-back-to-pip-user @inferred @source:install.sh @questionable
  Scenario Outline: The installer uses pipx when present and otherwise pip for the current user
    Given <installer> is the Python installer available on the machine
    When the operator runs the one-line installer
    Then cost-diff is installed from the GitHub repository's default branch with <command>
    And the operator sees "cost-diff installed. Run: cost-diff --help"

    Examples:
      | installer          | command                                                            |
      | pipx               | pipx install git+https://github.com/fabiocicerchia/cost-diff       |
      | pip only (no pipx) | pip install --user git+https://github.com/fabiocicerchia/cost-diff |

  @id:operations.installer.002 @rule:operations.installer.failure-aborts-without-success-message @inferred @source:install.sh
  Scenario: A failed install stops the installer without claiming success
    Given the install step fails, e.g. no network access to GitHub or neither pipx nor pip is available
    When the operator runs the one-line installer
    Then the installer exits with a non-zero status
    And the operator sees the underlying installer or shell error
    And the message "cost-diff installed" is not shown
