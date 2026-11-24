from decimal import Decimal

from coupled.core.registry import (
    REVIEWED_HEADER,
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
    Bare,
    Equation,
    FileRef,
    Formula,
    JudgedOp,
    Kind,
    Label,
    SetOp,
    TextOp,
    ValueOp,
    kind_of,
    parse_relation,
)

TEXT = """version = 1

["COUPLED:upload-limit:"]
relations = ["proxy >= app", "proxy = ./limits.json#/upload_mb * 1024"]
files = ["./.env?"]
select = { app = 'MAX = (\\d+)' }
"""


def registry(text: str) -> Registry:
    parsed = parse(text)
    assert isinstance(parsed, Registry), parsed
    return parsed


def test_a_relation_relates_two_sites_by_their_labels() -> None:
    assert parse_relation("proxy >= app") == Equation(
        Label("proxy"), ValueOp.GE, Label("app"), None
    )


def test_a_relation_can_put_the_second_value_through_a_formula() -> None:
    assert parse_relation("timeout > idle * 1000") == Equation(
        Label("timeout"), ValueOp.GT, Label("idle"), Formula(Arith.MUL, Decimal(1000))
    )


def test_a_relation_can_name_a_file_with_a_pointer_in_this_or_another_repository() -> None:
    assert parse_relation("app = ./package.json#/engines/node") == Equation(
        Label("app"), ValueOp.EQ, FileRef(None, "package.json", False, "/engines/node"), None
    )
    relation = parse_relation("writer same-shape //github.com/o/n/schema.json")
    assert relation == Equation(
        Label("writer"),
        JudgedOp.SAME_SHAPE,
        FileRef("github.com/o/n", "schema.json", False, None),
        None,
    )


def test_a_bare_op_alone_says_every_site_is_the_same() -> None:
    assert parse_relation("=") == Bare(ValueOp.EQ)
    assert parse_relation("same-set") == Bare(SetOp.SAME_SET)
    assert parse_relation("same-text") == Bare(TextOp.SAME_TEXT)
    assert parse_relation("same-as") == Bare(JudgedOp.SAME_AS)
    assert parse_relation("same-shape") == Bare(JudgedOp.SAME_SHAPE)


def test_an_op_that_cannot_stand_alone_says_which_can() -> None:
    for op in ("<", "subset-of", "description-of", "described-by"):
        problem = parse_relation(op)
        assert isinstance(problem, str)
        assert "only = same-set same-text same-as same-shape can stand alone" in problem


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
        assert parse_relation(text) == Equation(Label(left), op, Label(right), None)


def test_each_op_is_of_one_kind() -> None:
    assert {kind_of(op) for op in ValueOp} == {Kind.VALUE}
    assert {kind_of(op) for op in SetOp} == {Kind.SET}
    assert {kind_of(op) for op in TextOp} == {Kind.TEXT}
    assert {kind_of(op) for op in JudgedOp} == {Kind.JUDGED}


def test_a_relation_with_an_unknown_op_or_a_bad_ref_says_how_to_write_it() -> None:
    assert isinstance(parse_relation("a ~ b"), str)
    assert isinstance(parse_relation("A = b"), str)
    assert isinstance(parse_relation("a = b +"), str)


def test_a_group_s_table_gives_its_relations_files_and_selectors() -> None:
    group = registry(TEXT).groups["upload-limit"]
    assert group.problems == ()
    assert group.relations[0] == Equation(Label("proxy"), ValueOp.GE, Label("app"), None)
    assert group.files == (FileRef(None, ".env", True, None),)
    assert group.selector("app") == "MAX = (\\d+)"
    assert [ref.text() for ref in group.file_refs()] == ["./.env?", "./limits.json#/upload_mb"]


def test_a_registry_without_its_version_cannot_be_read() -> None:
    assert isinstance(parse('["COUPLED:x:"]\nrelations = ["="]\n'), Unparseable)


def test_text_that_is_not_toml_cannot_be_read() -> None:
    assert isinstance(parse("version = 1\n[[["), Unparseable)


def test_a_table_not_named_as_a_marker_is_searched_for_is_reported() -> None:
    assert registry('version = 1\n[upload-limit]\nrelations = ["="]\n').problems


def test_a_group_with_no_relations_or_an_unknown_field_is_reported() -> None:
    group = registry('version = 1\n["COUPLED:x:"]\nfiles = ["./a"]\nnote = "y"\n').groups["x"]
    assert any("relations" in problem for problem in group.problems)
    assert any("Drop `note`" in problem for problem in group.problems)


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
    assert reworded.groups["upload-limit"].definition == before
    assert changed.groups["upload-limit"].definition != before


def test_the_reviewed_section_is_written_below_the_groups_and_read_back() -> None:
    reviewed = {
        "upload-limit": Reviewed(
            "abc",
            (
                ReviewedSite("COUPLED:upload-limit: proxy", "m", None),
                ReviewedSite("COUPLED:upload-limit: app", None, None),
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
                ReviewedSite("COUPLED:upload-limit: app", None, None),
                ReviewedSite("COUPLED:upload-limit: proxy", "m", None),
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
    assert entry.endswith("select = { app = 'MAX = (\\d+)' }")
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
        'relations = ["="]\n'
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


def test_a_group_s_table_names_where_each_site_with_no_file_is_set() -> None:
    group = registry(
        'version = 1\n["COUPLED:o:"]\nrelations = ["app = google"]\n'
        'has-no-file = { google = "Google Cloud console > Credentials" }\n'
    ).groups["o"]
    assert group.no_file_sites == (("google", "Google Cloud console > Credentials"),)
    assert group.problems == ()


def test_a_site_with_no_file_not_named_by_a_label_or_not_described_is_reported() -> None:
    group = registry(
        'version = 1\n["COUPLED:o:"]\nrelations = ["app = google"]\n'
        'has-no-file = { Google = "console", google = " " }\n'
    ).groups["o"]
    assert group.problems == (
        "Name each site in `has-no-file` by a label, in lowercase letters and digits joined "
        "by single hyphens: `Google` isn't one",
        'Say where `google` is set, as `has-no-file = { google = "<where>" }`',
    )


def test_adding_a_site_with_no_file_changes_the_definition_but_rewording_where_does_not() -> None:
    def definition(no_file: str) -> str:
        text = f'version = 1\n["COUPLED:o:"]\nrelations = ["="]\n{no_file}\n'
        return registry(text).groups["o"].definition

    assert definition("") != definition('has-no-file = { google = "console" }')
    assert definition('has-no-file = { google = "console" }') == definition(
        'has-no-file = { google = "Google Cloud console" }'
    )
