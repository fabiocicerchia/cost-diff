@domain:documentation-site @area:site-theme @from:stylesheets/extra
Feature: Presenting the documentation in one consistent, offline-safe theme
  Gives readers of the cost-diff docs and splash page one recognisable look in light and dark mode without the pages fetching anything from third-party servers.

  Background:
    Given the cost-diff documentation site and splash page are published

  @id:docs.documentation-site.site-theme.001 @rule:documentation-site.site-theme.no-network-assets @inferred @source:docs/stylesheets/extra.css#:root
  Scenario: The docs render with system fonts and fetch no web fonts
    Given the reader's device has its own system fonts
    When a reader opens any documentation page
    Then body text is shown in the device's system sans-serif font
    And code is shown in the device's system monospace font
    And no font or stylesheet is downloaded from a third-party server

  @id:docs.documentation-site.site-theme.003 @rule:documentation-site.site-theme.legible-links-per-scheme @inferred @source:docs/stylesheets/extra.css#[data-md-color-scheme="slate"]
  Scenario Outline: Links stay legible in both light and dark mode
    Given the reader has chosen <mode> mode
    When a reader opens any documentation page
    Then the page background is <background>
    And links are shown in <link colour>

    Examples:
      | mode  | background         | link colour    |
      | light | white              | indigo #6366f1 |
      | dark  | near-black #0b0f1a | cyan #22d3ee   |

  @id:docs.documentation-site.site-theme.004 @rule:documentation-site.site-theme.no-stand-in-logo @inferred @source:docs/stylesheets/extra.css#.md-header__button.md-logo
  Scenario: The docs header shows no placeholder logo
    Given the project has no logo configured
    When a reader opens any documentation page
    Then the header and the navigation title show no logo icon
    And the generic book icon the theme would substitute is not shown

  @id:docs.documentation-site.site-theme.005 @rule:documentation-site.site-theme.wide-tables-scroll @inferred @source:docs/stylesheets/extra.css#.md-typeset table:not([class]) @questionable
  Scenario: Wide tables on narrow screens scroll rather than being cut off
    Given a documentation page contains a table wider than the reader's screen
    When a reader opens that page on a narrow screen
    Then the table is shown as a rounded, bordered card
    And the columns beyond the screen edge can be reached by scrolling sideways
