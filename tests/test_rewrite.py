"""Writing and dropping the message after a marker's label, as --fix does."""

from coupled_tags_lint.core.rewrite import message, with_messages

REGISTRY = ".coupled-tags.toml"
MESSAGE = message("upload-limit", REGISTRY)


def test_the_message_names_what_to_search_for_and_where_the_group_is_described() -> None:
    assert MESSAGE == (
        'Change only with every "COUPLED:upload-limit:" site, per .coupled-tags.toml.'
    )


def test_turned_on_the_message_is_written_after_the_label() -> None:
    lines = ["MAX = 8  # COUPLED:upload-limit: app"]
    assert with_messages(lines, REGISTRY, True) == [f"{lines[0]}. {MESSAGE}"]


def test_a_message_already_written_is_left_as_it_is() -> None:
    lines = [f"MAX = 8  # COUPLED:upload-limit: app. {MESSAGE}"]
    assert with_messages(lines, REGISTRY, True) == lines


def test_the_message_goes_before_prose_after_the_label() -> None:
    lines = ["# COUPLED:upload-limit: nginx. Larger bodies get a 413."]
    assert with_messages(lines, REGISTRY, True) == [
        f"# COUPLED:upload-limit: nginx. {MESSAGE} Larger bodies get a 413."
    ]


def test_the_message_goes_before_a_block_comment_s_closer() -> None:
    lines = ["<!-- COUPLED:upload-limit: docs -->"]
    assert with_messages(lines, REGISTRY, True) == [
        f"<!-- COUPLED:upload-limit: docs. {MESSAGE} -->"
    ]


def test_a_message_naming_another_registry_is_rewritten() -> None:
    lines = [f"MAX = 8  # COUPLED:upload-limit: app. {MESSAGE}"]
    assert with_messages(lines, ".config/coupled.toml", True) == [
        "MAX = 8  # COUPLED:upload-limit: app. " + message("upload-limit", ".config/coupled.toml")
    ]


def test_turned_off_the_message_is_dropped_and_prose_after_it_kept() -> None:
    lines = [
        f"MAX = 8  # COUPLED:upload-limit: app. {MESSAGE}",
        f"# COUPLED:upload-limit: nginx. {MESSAGE} Larger bodies get a 413.",
    ]
    assert with_messages(lines, REGISTRY, False) == [
        "MAX = 8  # COUPLED:upload-limit: app",
        "# COUPLED:upload-limit: nginx. Larger bodies get a 413.",
    ]


def test_each_of_two_markers_on_a_line_gets_its_own_message() -> None:
    lines = ["X = 1  # COUPLED:a: x. COUPLED:b: y"]
    assert with_messages(lines, REGISTRY, True) == [
        f"X = 1  # COUPLED:a: x. {message('a', REGISTRY)} COUPLED:b: y. {message('b', REGISTRY)}"
    ]


def test_markers_without_a_label_are_left_alone() -> None:
    lines = ["X = 1  # COUPLED:a:"]
    assert with_messages(lines, REGISTRY, True) == lines
