from decimal import Decimal

from coupled.core.registry import (
    REVIEWED_HEADER,
    FileRef,
    Registry,
    Reviewed,
    ReviewedSite,
    Unparseable,
    entry_text,
    parse,
    with_reviewed,
)
from coupled.core.relations import (
    Arith,
    Formula,
    JudgedOp,
    Kind,
    Relation,
    SetOp,
    TextOp,
    ValueOp,
    kind_of,
    parse_relation,
)

TEXT = """version = 1

["COUPLED:upload-limit:"]
relations = ["proxy >= app", "proxy = limits * 1024", "app = env"]
has-no-marker.limits = "./limits.json#/upload_mb"
has-no-marker.env = { file = "./.env?", regex = 'MAX=(\\d+)' }
"""


def registry(text: str) -> Registry:
    parsed = parse(text)
    assert isinstance(parsed, Registry), parsed
    return parsed


def group_of(table: str) -> tuple[str, ...]:
    """The problems with a group's table, written below its header."""
    return registry(f'version = 1\n["COUPLED:o:"]\n{table}\n').groups["o"].problems


def test_a_relation_relates_two_sites_by_their_labels() -> None:
    assert parse_relation("proxy >= app") == Relation("proxy", ValueOp.GE, "app", None)


def test_a_relation_can_put_the_second_value_through_a_formula() -> None:
    assert parse_relation("timeout > idle * 1000") == Relation(
        "timeout", ValueOp.GT, "idle", Formula(Arith.MUL, Decimal(1000))
    )


def test_a_relation_can_relate_sets_text_and_prose_about_code() -> None:
    for text, op in (
        ("web subset-of app", SetOp.SUBSET_OF),
        ("app superset-of web", SetOp.SUPERSET_OF),
        ("model same-set table", SetOp.SAME_SET),
        ("ci same-text release", TextOp.SAME_TEXT),
        ("readme description-of cli", JudgedOp.DESCRIPTION_OF),
        ("cli described-by readme", JudgedOp.DESCRIBED_BY),
    ):
        left, _, right = text.split()
        assert parse_relation(text) == Relation(left, op, right, None)


def test_each_op_is_of_one_kind() -> None:
    assert {kind_of(op) for op in ValueOp} == {Kind.VALUE}
    assert {kind_of(op) for op in SetOp} == {Kind.SET}
    assert {kind_of(op) for op in TextOp} == {Kind.TEXT}
    assert {kind_of(op) for op in JudgedOp} == {Kind.JUDGED}


def test_a_relation_with_an_unknown_op_or_a_bad_label_says_how_to_write_it() -> None:
    assert isinstance(parse_relation("a ~ b"), str)
    assert isinstance(parse_relation("A = b"), str)
    assert isinstance(parse_relation("a = b +"), str)


def test_an_op_alone_is_not_a_relation() -> None:
    assert parse_relation("=") == (
        "Write `=` as `<label> <op> <label> [<arith> <number>]`, separated by spaces"
    )


def test_a_relation_names_a_file_by_its_label_not_its_path() -> None:
    problem = parse_relation("app = ./package.json#/engines/node")
    assert isinstance(problem, str)
    assert "A file that can't hold a marker gets a label in `has-no-marker`" in problem


def test_a_group_s_table_gives_its_relations_labelled_files_and_their_regexes() -> None:
    group = registry(TEXT).groups["upload-limit"]
    assert group.problems == ()
    assert group.relations[0] == Relation("proxy", ValueOp.GE, "app", None)
    assert group.local_files == (
        ("env", FileRef(None, ".env", True, None)),
        ("limits", FileRef(None, "limits.json", False, "/upload_mb")),
    )
    assert group.regex("env") == "MAX=(\\d+)"
    assert group.regex("limits") is None


def test_a_file_s_regex_is_part_of_its_group_s_definition() -> None:
    plain = registry(TEXT.replace("MAX=", "LIMIT=")).groups["upload-limit"]
    assert plain.definition != registry(TEXT).groups["upload-limit"].definition


def test_a_file_s_table_may_leave_out_its_regex() -> None:
    group = registry(
        'version = 1\n["COUPLED:o:"]\nrelations = ["a = env"]\n'
        'has-no-marker = { env = { file = "./.env" } }\n'
    ).groups["o"]
    assert group.problems == ()
    assert group.local_files == (("env", FileRef(None, ".env", False, None)),)
    assert group.regex("env") is None


def test_a_file_s_table_gives_the_same_definition_as_its_string() -> None:
    table = 'version = 1\n["COUPLED:o:"]\nrelations = ["a = env"]\nhas-no-marker = { env = %s }\n'
    as_string = registry(table % '"./.env"').groups["o"].definition
    assert registry(table % '{ file = "./.env" }').groups["o"].definition == as_string


def test_a_file_s_table_must_give_its_file_and_only_file_and_regex() -> None:
    assert any(
        "Give `env` in `has-no-marker` its file" in problem
        for problem in group_of(
            'relations = ["a = env"]\nhas-no-marker = { env = { regex = "x" } }'
        )
    )
    assert any(
        "Drop `pattern`" in problem
        for problem in group_of(
            'relations = ["a = env"]\n'
            "has-no-marker = { env = { file = './.env', regex = 'x', pattern = 'y' } }"
        )
    )


def test_a_file_s_regex_that_does_not_compile_is_reported() -> None:
    assert any(
        "Fix the regex /(x/ for `env`" in problem
        for problem in group_of(
            'relations = ["a = env"]\nhas-no-marker = { env = { file = "./.env", regex = "(x" } }'
        )
    )


def test_a_select_table_asks_for_each_regex_to_move_to_its_site() -> None:
    [problem] = group_of('relations = ["a = b"]\nselect = { a = "x" }')
    assert "after its marker's label" in problem and "regex = '<regex>'" in problem


def test_a_file_in_another_repository_that_keeps_no_group_is_given_a_label() -> None:
    group = registry(
        'version = 1\n["COUPLED:o:"]\nrelations = ["writer same-shape schema"]\n'
        'has-no-marker = { schema = "//github.com/o/n/schema.json#/defs" }\nwhy = "x"\n'
    ).groups["o"]
    assert group.problems == ()
    assert group.local_files == ()
    assert group.remote_files == (
        ("schema", FileRef("github.com/o/n", "schema.json", False, "/defs")),
    )


def test_a_site_of_another_repository_that_keeps_the_group_is_named_by_its_repository() -> None:
    group = registry(
        'version = 1\n["COUPLED:o:"]\nrelations = ["writer same-shape schema"]\n'
        'in-another-registry = { schema = "//github.com/o/n" }\nwhy = "x"\n'
    ).groups["o"]
    assert group.problems == ()
    assert group.other_registries == (("schema", "github.com/o/n"),)


def test_a_group_s_table_names_where_each_site_with_no_file_is_set() -> None:
    group = registry(
        'version = 1\n["COUPLED:o:"]\nrelations = ["app = google"]\n'
        'has-no-file = { google = "Google Cloud console > Credentials" }\n'
    ).groups["o"]
    assert group.no_file_sites == (("google", "Google Cloud console > Credentials"),)
    assert group.problems == ()


def test_a_labelled_site_written_in_the_wrong_form_is_reported() -> None:
    assert group_of('relations = ["a = b"]\nhas-no-marker = { b = "f" }') == (
        'Write `b` in `has-no-marker` as `b = "./<path>[?][#<pointer>]"`, or for a file '
        'in another repository, `b = "//<git-host>/<owner>/<name>/<path>[#<pointer>]"`, or '
        "with a regex picking its value out, as "
        "`b = { file = \"./<path>[?]\", regex = '<regex>' }`",
    )
    assert group_of('relations = ["a = b"]\nin-another-registry = { b = "./f" }') == (
        'Write `b` in `in-another-registry` as `b = "//<git-host>/<owner>/<name>"`',
    )
    assert group_of('relations = ["a = b"]\nin-another-registry = { b = "//github.com/o/n/f?" }')
    assert group_of('relations = ["a = google"]\nhas-no-file = { Google = "x", google = " " }') == (
        "Name each site in `has-no-file` by a label, in lowercase letters and digits joined "
        "by single hyphens: `Google` isn't one",
        'Write `google` in `has-no-file` as `google = "where it\'s set"`',
    )


def test_a_label_given_in_two_fields_is_reported() -> None:
    assert group_of(
        'relations = ["a = b"]\nhas-no-marker = { b = "./f" }\nhas-no-file = { b = "x" }'
    ) == ("Give `b` one entry: it's in both `has-no-marker` and `has-no-file`",)


def test_a_registry_without_its_version_cannot_be_read() -> None:
    assert isinstance(parse('["COUPLED:x:"]\nrelations = ["a = b"]\n'), Unparseable)


def test_text_that_is_not_toml_cannot_be_read() -> None:
    assert isinstance(parse("version = 1\n[[["), Unparseable)


def test_a_table_not_named_as_a_marker_is_searched_for_is_reported() -> None:
    assert registry('version = 1\n[upload-limit]\nrelations = ["a = b"]\n').problems


def test_a_group_with_no_relations_or_an_unknown_field_is_reported() -> None:
    problems = group_of('files = ["./a"]\nnote = "y"')
    assert any("relations" in problem for problem in problems)
    assert any("Drop `files`" in problem for problem in problems)
    assert any("Drop `note`" in problem for problem in problems)


def test_a_group_s_fields_in_their_order_are_not_reported() -> None:
    assert (
        group_of(
            'relations = ["a = b", "a = c", "a = d"]\n'
            'has-no-marker = { b = "./b.json" }\n'
            'in-another-registry = { c = "//github.com/o/r" }\n'
            'has-no-file = { d = "a console" }\n'
            'why = "y"'
        )
        == ()
    )


def test_a_group_s_fields_out_of_their_order_are_reported_at_the_first_out_of_place() -> None:
    problems = group_of('why = "y"\nhas-no-file = { d = "a console" }\nrelations = ["a = d"]')
    assert problems == (
        "Put `relations` before `why`: a group's table gives relations, has-no-marker, "
        "in-another-registry, has-no-file and why, in that order",
    )


def test_a_dotted_field_takes_its_place_from_its_first_line() -> None:
    assert (
        group_of(
            'relations = ["a = b", "a = c"]\n'
            'has-no-marker.b = "./b.json"\n'
            'has-no-marker.c = "./c.json"\n'
            'why = "y"'
        )
        == ()
    )


def test_a_group_s_table_can_say_why_its_sites_are_coupled() -> None:
    group = registry(TEXT + 'why = "nginx rejects a larger body before the app sees it"\n')
    assert group.groups["upload-limit"].why == "nginx rejects a larger body before the app sees it"
    assert group.groups["upload-limit"].problems == ()
    assert registry(TEXT).groups["upload-limit"].why is None


def test_a_why_that_is_not_text_is_reported() -> None:
    group = registry(TEXT + "why = 3\n").groups["upload-limit"]
    assert group.problems == ("Write `why` as a string: why the sites must change together",)


def test_rewording_why_leaves_the_definition_as_reviewed() -> None:
    before = registry(TEXT + 'why = "a"\n').groups["upload-limit"].definition
    assert registry(TEXT + 'why = "b"\n').groups["upload-limit"].definition == before
    assert registry(TEXT).groups["upload-limit"].definition == before


def test_a_change_to_what_a_table_states_changes_its_definition() -> None:
    before = registry(TEXT).groups["upload-limit"].definition
    reworded = registry(TEXT.replace('"proxy >= app"', '"proxy  >=  app"'))
    changed = registry(TEXT.replace('"proxy >= app"', '"proxy > app"'))
    moved = registry(TEXT.replace("./limits.json", "./config/limits.json"))
    assert reworded.groups["upload-limit"].definition == before
    assert changed.groups["upload-limit"].definition != before
    assert moved.groups["upload-limit"].definition != before


def test_adding_a_site_with_no_file_changes_the_definition_but_rewording_where_does_not() -> None:
    def definition(no_file: str) -> str:
        text = f'version = 1\n["COUPLED:o:"]\nrelations = ["a = b"]\n{no_file}\n'
        return registry(text).groups["o"].definition

    assert definition("") != definition('has-no-file = { google = "console" }')
    assert definition('has-no-file = { google = "console" }') == definition(
        'has-no-file = { google = "Google Cloud console" }'
    )


def test_the_reviewed_section_is_written_below_the_groups_and_read_back() -> None:
    reviewed = {
        "upload-limit": Reviewed(
            "abc",
            (
                ReviewedSite("COUPLED:upload-limit: proxy", "m", None, None),
                ReviewedSite("COUPLED:upload-limit: app", None, None, None),
            ),
        )
    }
    text = with_reviewed(TEXT, reviewed)
    assert text.startswith(TEXT)
    assert REVIEWED_HEADER in text
    assert '"COUPLED:upload-limit: proxy" = { unit = "m" }' in text
    assert registry(text).reviewed == {
        "upload-limit": Reviewed(
            "abc",
            (
                ReviewedSite("COUPLED:upload-limit: app", None, None, None),
                ReviewedSite("COUPLED:upload-limit: proxy", "m", None, None),
            ),
        )
    }


def test_writing_the_reviewed_section_again_replaces_it() -> None:
    once = with_reviewed(TEXT, {"x": Reviewed("a", ())})
    twice = with_reviewed(once, {"y": Reviewed("b", ())})
    assert '"COUPLED:x:"' not in twice
    assert twice.count(REVIEWED_HEADER) == 1


def test_a_broken_reviewed_section_is_reported() -> None:
    assert registry(TEXT + '\n[reviewed."COUPLED:x:"]\nsite = 3\n').problems


def test_a_group_s_entry_is_its_table_as_written() -> None:
    text = with_reviewed(TEXT, {"upload-limit": Reviewed("a", ())})
    entry = entry_text(text, "upload-limit")
    assert entry is not None
    assert entry.startswith('["COUPLED:upload-limit:"]')
    assert entry.endswith("regex = 'MAX=(\\d+)' }")
    assert entry_text(text, "other") is None


def test_a_group_s_entry_is_found_however_toml_lets_its_header_be_written() -> None:
    for header in (
        "['COUPLED:upload-limit:']",
        '[ "COUPLED:upload-limit:" ]',
        '  ["COUPLED:upload-limit:"]',
        '["COUPLED:upload-limit:"]  # proxy and app',
        '["COUPLED:upload\\u002dlimit:"]',
    ):
        text = f'version = 1\n\n{header}\nrelations = ["proxy = app"]\n'
        assert entry_text(text, "upload-limit") == f'{header}\nrelations = ["proxy = app"]'


def test_a_group_s_entry_ends_at_the_next_table_however_it_is_written() -> None:
    text = (
        "version = 1\n\n"
        '["COUPLED:a:"]\nrelations = [\n    "x = y",\n]\n\n'
        "  [ 'COUPLED:b:' ]  # next\n"
        'relations = ["p = q"]\n'
    )
    assert entry_text(text, "a") == '["COUPLED:a:"]\nrelations = [\n    "x = y",\n]'


def test_a_group_s_entry_is_not_a_table_nested_under_it_or_an_array_of_tables() -> None:
    text = 'version = 1\n\n[reviewed."COUPLED:a:"]\ndefinition = "x"\n\n[["COUPLED:b:"]]\n'
    assert entry_text(text, "a") is None
    assert entry_text(text, "b") is None


def test_writing_the_reviewed_section_replaces_one_however_its_headers_are_written() -> None:
    once = TEXT + "\n[ reviewed . 'COUPLED:x:' ]\ndefinition = 'a'\n"
    twice = with_reviewed(once, {"y": Reviewed("b", ())})
    assert "COUPLED:x:" not in twice
    assert registry(twice).reviewed == {"y": Reviewed("b", ())}


def test_a_file_in_another_repository_can_t_be_only_sometimes_there() -> None:
    table = 'relations = ["a = b"]\nhas-no-marker = { b = "//github.com/o/n/f?" }'
    assert group_of(table) == (
        "Drop the `?` from `b` in `has-no-marker`: only a file in this repository can be "
        "only sometimes there",
    )


def test_a_file_named_in_in_another_registry_is_sent_to_its_repository_or_its_own_entry() -> None:
    table = 'relations = ["a = b"]\nin-another-registry = { b = "//github.com/o/n/f.json" }'
    assert group_of(table) == (
        "Write `b` in `in-another-registry` as the repository alone, "
        '`b = "//<git-host>/<owner>/<name>"`, where `b` is a site of the group too; if that '
        "repository keeps no such group, give `b` its file in `has-no-marker`",
    )
