from decimal import Decimal

from coupled_tags_lint.core.registry import (
    REVIEWED_HEADER,
    Registry,
    Reviewed,
    ReviewedSite,
    Unparseable,
    entry_text,
    parse,
    with_reviewed,
)
from coupled_tags_lint.core.relations import (
    Arith,
    Bare,
    Equation,
    FileRef,
    Formula,
    Label,
    StructuralOp,
    ValueOp,
    parse_relation,
)

TEXT = """version = 1

["COUPLED:upload-limit:"]
relations = ["nginx >= app", "nginx = ./limits.json#/upload_mb * 1024"]
files = ["./.env?"]
select = { app = 'MAX = (\\d+)' }
"""


def registry(text: str) -> Registry:
    parsed = parse(text)
    assert isinstance(parsed, Registry), parsed
    return parsed


def test_a_relation_relates_two_sites_by_their_labels() -> None:
    assert parse_relation("nginx >= app") == Equation(
        Label("nginx"), ValueOp.GE, Label("app"), None
    )


def test_a_relation_can_put_the_second_value_through_a_formula() -> None:
    assert parse_relation("timeout > idle * 1000") == Equation(
        Label("timeout"), ValueOp.GT, Label("idle"), Formula(Arith.MUL, Decimal(1000))
    )


def test_a_relation_can_name_a_file_with_a_pointer_in_this_or_another_repository() -> None:
    assert parse_relation("app = ./package.json#/engines/node") == Equation(
        Label("app"), ValueOp.EQ, FileRef(None, "package.json", False, "/engines/node"), None
    )
    relation = parse_relation("go same-shape //github.com/o/n/schema.json")
    assert relation == Equation(
        Label("go"),
        StructuralOp.SAME_SHAPE,
        FileRef("github.com/o/n", "schema.json", False, None),
        None,
    )


def test_a_bare_op_alone_says_every_site_is_the_same() -> None:
    assert parse_relation("=") == Bare(ValueOp.EQ)
    assert parse_relation("same-as") == Bare(StructuralOp.SAME_AS)


def test_an_op_that_cannot_stand_alone_says_how_to_write_it() -> None:
    assert isinstance(parse_relation("<"), str)


def test_a_relation_with_an_unknown_op_or_a_bad_ref_says_how_to_write_it() -> None:
    assert isinstance(parse_relation("a ~ b"), str)
    assert isinstance(parse_relation("A = b"), str)
    assert isinstance(parse_relation("a = b +"), str)


def test_a_group_s_table_gives_its_relations_files_and_selectors() -> None:
    group = registry(TEXT).groups["upload-limit"]
    assert group.problems == ()
    assert group.relations[0] == Equation(Label("nginx"), ValueOp.GE, Label("app"), None)
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


def test_a_change_to_what_a_table_states_changes_its_definition() -> None:
    before = registry(TEXT).groups["upload-limit"].definition
    reworded = registry(TEXT.replace('"nginx >= app"', '"nginx  >=  app"'))
    changed = registry(TEXT.replace('"nginx >= app"', '"nginx > app"'))
    assert reworded.groups["upload-limit"].definition == before
    assert changed.groups["upload-limit"].definition != before


def test_the_reviewed_section_is_written_below_the_groups_and_read_back() -> None:
    reviewed = {
        "upload-limit": Reviewed(
            "abc",
            (
                ReviewedSite("COUPLED:upload-limit: nginx", "m", None),
                ReviewedSite("COUPLED:upload-limit: app", None, None),
            ),
        )
    }
    text = with_reviewed(TEXT, reviewed)
    assert text.startswith(TEXT)
    assert REVIEWED_HEADER in text
    assert '"COUPLED:upload-limit: nginx" = { unit = "m" }' in text
    assert registry(text).reviewed == {
        "upload-limit": Reviewed(
            "abc",
            (
                ReviewedSite("COUPLED:upload-limit: app", None, None),
                ReviewedSite("COUPLED:upload-limit: nginx", "m", None),
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
