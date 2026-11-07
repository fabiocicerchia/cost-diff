@domain:deploys @area:file-deploys @from:cost-diff/cost-diff
Feature: Importing deploys from a file
  Lets any team whose deploy log is not git, GitHub or Argo CD feed deploys to the timeline from a CSV or JSON export.

  @id:deploys.file-deploys.001 @rule:deploys.file.accepted-layouts @verified @source:cost_diff.py#deploys_from_file @test:tests/test_cost_diff.py#test_deploys_from_csv_with_a_header @test:tests/test_cost_diff.py#test_csv_header_is_read_case_insensitively @test:tests/test_cost_diff.py#test_deploys_from_csv_without_a_header @test:tests/test_cost_diff.py#test_deploys_from_json_objects @test:tests/test_cost_diff.py#test_deploys_from_json_pairs
  Scenario Outline: CSV with or without a header and JSON objects or pairs are all read
    Given deploys.<ext> contains <content>
    When the operator runs the timeline with --deploys-file deploys.<ext>
    Then one deploy v2.14 at 2026-08-21T18:00Z is used<revision>

    Examples:
      | ext  | content                                                                | revision           |
      | csv  | timestamp,label,revision / 2026-08-21T18:00:00Z,v2.14,9f3a1c2          | , revision 9f3a1c2 |
      | csv  | Timestamp,Label,Revision / 2026-08-21T18:00:00Z,v2.14,9f3a1c2          | , revision 9f3a1c2 |
      | csv  | 2026-08-21T18:00:00Z,v2.14                                             |                    |
      | json | [{"time": "2026-08-21T18:00:00Z", "name": "v2.14", "sha": "abc1234"}]  | , revision abc1234 |
      | json | [["2026-08-21T18:00:00Z", "v2.14"]]                                    |                    |
      | json | {"deploys": [{"timestamp": "2026-08-21T18:00:00Z", "label": "v2.14"}]} |                    |

  @id:deploys.file-deploys.002 @rule:deploys.file.timestamps-normalised-to-utc @verified @source:cost_diff.py#_parse_time @test:tests/test_cost_diff.py#test_deploys_from_csv_with_a_header @test:tests/test_cost_diff.py#test_naive_deploy_timestamps_are_read_as_utc @test:tests/test_cost_diff.py#test_an_offset_timestamp_is_converted_not_dropped @test:tests/test_cost_diff.py#test_epoch_timestamps_in_seconds_and_milliseconds
  Scenario Outline: Deploy times are read in common formats and treated as UTC
    Given the deploy file has a timestamp of <written>
    When the operator runs the timeline with that file
    Then the deploy is placed at <utc>

    Examples:
      | written                   | utc               |
      | 2026-08-21T18:00:00Z      | 2026-08-21T18:00Z |
      | 2026-08-21 18:00:00       | 2026-08-21T18:00Z |
      | 2026-08-21T20:00:00+02:00 | 2026-08-21T18:00Z |
      | 1756800000                | 2025-09-02T08:00Z |
      | 1756800000000             | 2025-09-02T08:00Z |

  @id:deploys.file-deploys.003 @rule:deploys.file.unreadable-input-refused @verified @source:cost_diff.py#deploys_from_file @test:tests/test_cost_diff.py#test_unreadable_timestamp_says_what_it_wanted @test:tests/test_cost_diff.py#test_a_number_that_is_not_an_epoch_gets_the_iso_message @test:tests/test_cost_diff.py#test_a_row_without_a_timestamp_names_the_file @test:tests/test_cost_diff.py#test_a_misnamed_json_wrapper_key_is_an_error_not_an_empty_timeline
  Scenario Outline: A deploy file the tool cannot read is refused with a message saying what it wants
    Given deploys.<ext> <problem>
    When the operator runs the timeline with --deploys-file deploys.<ext>
    Then the run exits with status 1
    And stderr says "cost-diff: <message>"
    And no report is printed

    Examples:
      | ext  | problem                                     | message                                                                                                                         |
      | csv  | has a timestamp of "last tuesday"           | unreadable deploy timestamp 'last tuesday' — want ISO 8601, e.g. 2026-09-02T18:00:00Z                                           |
      | csv  | has a timestamp of 175680000000 (12 digits) | unreadable deploy timestamp '175680000000' — want ISO 8601, e.g. 2026-09-02T18:00:00Z                                           |
      | csv  | has only a label column                     | deploys.csv: no timestamp column — give the file a header naming one of timestamp, time, when, date, or put the timestamp first |
      | json | wraps its list under "deployments"          | deploys.json: want a JSON list of deploys — a JSON object needs them under 'deploys'                                            |
      | csv  | does not exist                              | cannot read deploy file deploys.csv: ...                                                                                        |

  @id:deploys.file-deploys.004 @rule:deploys.filter.label-glob @inferred @source:cost_diff.py#load_deploys
  Scenario: Only deploys whose label matches the chosen pattern are used
    Given the deploy source lists production/v2.14 and staging/v2.15
    When the operator runs the timeline with --deploy-match 'production/*'
    Then only production/v2.14 is attributed, charted and counted
