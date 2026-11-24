"""The message after a marker's label, and writing or dropping it as --fix does."""

from coupled.core.registry import Registry, parse
from coupled.core.rewrite import message, relations_of, wanted, with_messages
from coupled.core.settings import TagMessage

REGISTRY = "coupled-registry.toml"
POINTER = 'Change only with every "COUPLED:upload-limit:" site, per coupled-registry.toml.'
UPLOAD = {("upload-limit", "app"): POINTER, ("upload-limit", "proxy"): POINTER}


def registry(groups: str) -> Registry:
    parsed = parse("version = 1\n" + groups)
    assert isinstance(parsed, Registry)
    return parsed


def test_the_pointer_names_what_to_search_for_and_where_the_group_is_described() -> None:
    assert message("upload-limit", REGISTRY, None, True) == POINTER


def test_the_relations_can_be_given_alone() -> None:
    assert message("upload-limit", REGISTRY, ">= app", False) == "Must be >= app."


def test_the_relations_come_before_the_pointer() -> None:
    assert message("upload-limit", REGISTRY, ">= app", True) == f"Must be >= app. {POINTER}"


def test_with_neither_relations_nor_pointer_there_is_no_message() -> None:
    assert message("upload-limit", REGISTRY, None, False) is None


def test_a_site_s_relations_are_each_seen_from_it() -> None:
    group = registry(
        '["COUPLED:t:"]\nrelations = ["proxy >= app + 5", "proxy = ./limits.json#/t"]\n'
    ).groups["t"]
    assert relations_of(group, "proxy") == ">= app + 5, = ./limits.json#/t"
    assert relations_of(group, "app") == "<= proxy - 5"
    assert relations_of(group, "other") is None


def test_a_bare_op_is_seen_as_the_same_as_every_other_site() -> None:
    group = registry('["COUPLED:v:"]\nrelations = ["="]\n').groups["v"]
    assert relations_of(group, "ci") == "= every other site and file"


def test_structural_ops_flip_from_the_other_side() -> None:
    group = registry('["COUPLED:f:"]\nrelations = ["ini subset-of phpstan"]\n').groups["f"]
    assert relations_of(group, "phpstan") == "superset-of ini"


def test_each_setting_wants_its_own_part_of_the_message() -> None:
    found = registry('["COUPLED:upload-limit:"]\nrelations = ["proxy >= app"]\n')
    markers = [("upload-limit", "proxy")]
    for pointer, relations, wanted_message in (
        (False, False, None),
        (True, False, POINTER),
        (False, True, "Must be >= app."),
        (True, True, f"Must be >= app. {POINTER}"),
    ):
        tag_message = TagMessage(pointer=pointer, relations=relations)
        wanted_messages = {} if wanted_message is None else {markers[0]: wanted_message}
        assert wanted(markers, found, tag_message, REGISTRY) == wanted_messages


def test_a_site_with_no_relations_wants_only_the_pointer() -> None:
    both = TagMessage(pointer=True, relations=True)
    assert wanted([("x", "a")], None, both, REGISTRY) == {
        ("x", "a"): 'Change only with every "COUPLED:x:" site, per coupled-registry.toml.'
    }
    relations_only = TagMessage(pointer=False, relations=True)
    assert wanted([("x", "a")], None, relations_only, REGISTRY) == {}


def test_a_wanted_message_is_written_after_the_label() -> None:
    lines = ["MAX = 8  # COUPLED:upload-limit: app"]
    assert with_messages(lines, UPLOAD) == [f"{lines[0]}. {POINTER}"]


def test_a_message_already_written_is_left_as_it_is() -> None:
    lines = [f"MAX = 8  # COUPLED:upload-limit: app. {POINTER}"]
    assert with_messages(lines, UPLOAD) == lines


def test_a_message_that_differs_is_rewritten() -> None:
    relations = f"Must be <= proxy. {POINTER}"
    lines = [f"MAX = 8  # COUPLED:upload-limit: app. {POINTER}"]
    assert with_messages(lines, {("upload-limit", "app"): relations}) == [
        f"MAX = 8  # COUPLED:upload-limit: app. {relations}"
    ]
    assert with_messages([f"MAX = 8  # COUPLED:upload-limit: app. {relations}"], UPLOAD) == [
        f"MAX = 8  # COUPLED:upload-limit: app. {POINTER}"
    ]


def test_a_relations_only_message_is_rewritten_and_dropped() -> None:
    lines = ["MAX = 8  # COUPLED:upload-limit: app. Must be <= proxy. Larger is refused."]
    assert with_messages(lines, UPLOAD) == [
        f"MAX = 8  # COUPLED:upload-limit: app. {POINTER} Larger is refused."
    ]
    assert with_messages(lines, {}) == ["MAX = 8  # COUPLED:upload-limit: app. Larger is refused."]


def test_prose_starting_must_be_is_not_taken_for_a_message() -> None:
    lines = ["MAX = 8  # COUPLED:upload-limit: app. Must be in MB."]
    assert with_messages(lines, {}) == lines


def test_the_message_goes_before_prose_after_the_label() -> None:
    lines = ["# COUPLED:upload-limit: proxy. Larger bodies get a 413."]
    assert with_messages(lines, UPLOAD) == [
        f"# COUPLED:upload-limit: proxy. {POINTER} Larger bodies get a 413."
    ]


def test_the_message_goes_before_a_block_comment_s_closer() -> None:
    lines = ["<!-- COUPLED:upload-limit: app -->"]
    assert with_messages(lines, UPLOAD) == [f"<!-- COUPLED:upload-limit: app. {POINTER} -->"]


def test_a_message_not_wanted_is_dropped_and_prose_after_it_kept() -> None:
    lines = [
        f"MAX = 8  # COUPLED:upload-limit: app. {POINTER}",
        f"# COUPLED:upload-limit: proxy. {POINTER} Larger bodies get a 413.",
    ]
    assert with_messages(lines, {}) == [
        "MAX = 8  # COUPLED:upload-limit: app",
        "# COUPLED:upload-limit: proxy. Larger bodies get a 413.",
    ]


def test_each_of_two_markers_on_a_line_gets_its_own_message() -> None:
    a = 'Change only with every "COUPLED:a:" site, per coupled-registry.toml.'
    b = 'Change only with every "COUPLED:b:" site, per coupled-registry.toml.'
    lines = ["X = 1  # COUPLED:a: x. COUPLED:b: y"]
    assert with_messages(lines, {("a", "x"): a, ("b", "y"): b}) == [
        f"X = 1  # COUPLED:a: x. {a} COUPLED:b: y. {b}"
    ]


def test_markers_without_a_label_are_left_alone() -> None:
    lines = ["X = 1  # COUPLED:a:"]
    assert with_messages(lines, UPLOAD) == lines
