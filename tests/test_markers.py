from coupled.core.markers import End, Found, Malformed, Marker, find_markers


def found(*lines: str) -> list[Found]:
    return [placed.found for placed in find_markers(list(lines))]


def test_a_marker_names_its_key_and_its_site_s_label() -> None:
    assert found("MAX = 8  # COUPLED:upload-limit: app") == [
        Marker("upload-limit", "app", None, ())
    ]


def test_a_label_can_be_several_words_joined_by_hyphens() -> None:
    assert found("# COUPLED:node-version: ci-matrix") == [
        Marker("node-version", "ci-matrix", None, ())
    ]


def test_prose_can_follow_a_label_after_a_full_stop() -> None:
    assert found("# COUPLED:upload-limit: proxy. Larger bodies get a 413.") == [
        Marker("upload-limit", "proxy", None, ())
    ]


def test_prose_can_come_before_a_marker() -> None:
    assert found("# Pinned for the build. COUPLED:node-version: docker") == [
        Marker("node-version", "docker", None, ())
    ]


def test_a_marker_in_a_block_comment_ends_before_its_closer() -> None:
    assert found("<!-- COUPLED:x: readme -->") == [Marker("x", "readme", None, ())]
    assert found("/* COUPLED:x: css */") == [Marker("x", "css", None, ())]


def test_a_marker_without_a_label_asks_for_one() -> None:
    [marker] = found("X = 1  # COUPLED:x:")
    assert isinstance(marker, Marker) and marker.label is None
    assert "Label this site" in marker.problems[0]


def test_prose_straight_after_a_label_asks_for_a_full_stop_between() -> None:
    [marker] = found("# COUPLED:upload-limit: proxy answers with a 413")
    assert isinstance(marker, Marker) and marker.label == "proxy"
    assert "`COUPLED:upload-limit: proxy. <prose>`" in marker.problems[0]


def test_a_label_written_against_the_key_is_malformed() -> None:
    [marker] = found("# COUPLED:x:app")
    assert isinstance(marker, Malformed)
    assert "space" in marker.problem


def test_a_key_with_uppercase_letters_is_malformed() -> None:
    assert isinstance(found("# COUPLED:Upload_Limit: app")[0], Malformed)


def test_a_tag_in_the_old_bracket_form_asks_for_a_marker_and_a_registry_table() -> None:
    [marker] = found("# COUPLED:x:[= Y]")
    assert isinstance(marker, Malformed)
    assert "registry" in marker.problem


def test_mentions_and_quoted_search_text_are_not_markers() -> None:
    assert found("Search for `COUPLED:<key>:` to find them.") == []
    assert found('Change only with every "COUPLED:upload-limit:" site.') == []
    assert found('["COUPLED:upload-limit:"]') == []


def test_a_file_with_the_ignore_directive_on_a_line_of_its_own_has_no_markers() -> None:
    assert found("COUPLED:IGNORE-FILE", "MAX = 8  # COUPLED:upload-limit: app") == []


def test_the_ignore_directive_can_be_in_a_comment() -> None:
    assert found("<!-- COUPLED:IGNORE-FILE -->", "COUPLED:x: readme") == []
    assert found("  # COUPLED:IGNORE-FILE", "X = 1  # COUPLED:x: app") == []
    assert found("/* COUPLED:IGNORE-FILE */", "/* COUPLED:x: css */") == []


def test_the_ignore_directive_mentioned_in_a_line_is_neither_a_marker_nor_ignores_the_file() -> (
    None
):
    assert found("Write `COUPLED:IGNORE-FILE` on a line.", "# COUPLED:x: app") == [
        Marker("x", "app", None, ())
    ]
    assert found('DIRECTIVE = "COUPLED:IGNORE-FILE"') == []


def test_two_markers_can_share_a_comment() -> None:
    assert found("X = 1  # COUPLED:a: x. COUPLED:b: y") == [
        Marker("a", "x", None, ()),
        Marker("b", "y", None, ()),
    ]


def test_an_end_closes_the_nearest_marker_of_its_key_above_it() -> None:
    placed = find_markers(["# COUPLED:x: a", "def f():", "    pass", "# COUPLED:x:END"])
    assert placed[0].close == 3
    assert placed[1].found == End("x", ())


def test_an_end_with_no_marker_above_it_is_reported() -> None:
    [end] = found("# COUPLED:x:END")
    assert isinstance(end, End)
    assert "Open this block" in end.problems[0]


def test_blocks_of_one_key_cannot_nest() -> None:
    ends = [
        item
        for item in found(
            "# COUPLED:x: a", "# COUPLED:x: b", "f()", "# COUPLED:x:END", "# COUPLED:x:END"
        )
        if isinstance(item, End)
    ]
    assert any("can't nest" in problem for problem in ends[1].problems)


def test_blocks_can_nest_but_not_overlap() -> None:
    ends = [
        item
        for item in found(
            "# COUPLED:a: x", "f()", "# COUPLED:b: y", "g()", "# COUPLED:a:END", "# COUPLED:b:END"
        )
        if isinstance(item, End)
    ]
    assert any("not overlap" in problem for problem in ends[0].problems)


def test_the_stop_is_the_column_after_the_label() -> None:
    line = "X = 1  # COUPLED:x: app. More."
    [placed] = find_markers([line])
    assert line[placed.stop :] == ". More."


def test_a_marker_in_a_haskell_or_ocaml_block_comment_ends_before_its_closer() -> None:
    assert found("{- COUPLED:x: haskell -}") == [Marker("x", "haskell", None, ())]
    assert found("(* COUPLED:x: ocaml *)") == [Marker("x", "ocaml", None, ())]


def test_a_regex_after_the_label_picks_the_site_s_value() -> None:
    assert found('- "8080:8080"  # COUPLED:port: compose /"(\\d+):/') == [
        Marker("port", "compose", '"(\\d+):', ())
    ]


def test_a_slash_in_a_regex_is_written_escaped() -> None:
    [marker] = found("# COUPLED:x: owners /^\\/(\\S+)/")
    assert isinstance(marker, Marker) and marker.regex == "^\\/(\\S+)"


def test_prose_can_follow_a_regex_after_a_full_stop() -> None:
    assert found("# COUPLED:x: app /(\\d+)/. In MB.") == [Marker("x", "app", "(\\d+)", ())]


def test_a_marker_in_a_block_comment_ends_its_regex_before_the_closer() -> None:
    assert found('<!-- COUPLED:x: form /max="(\\d+)"/ -->') == [
        Marker("x", "form", 'max="(\\d+)"', ())
    ]


def test_the_stop_is_the_column_after_a_regex() -> None:
    line = "X = 1  # COUPLED:x: app /(\\d+)/. More."
    [placed] = find_markers([line])
    assert line[placed.stop :] == ". More."


def test_a_regex_with_no_closing_slash_asks_for_one() -> None:
    [marker] = found("# COUPLED:x: app /(\\d+)")
    assert isinstance(marker, Marker) and marker.regex is None
    assert "Close the regex" in marker.problems[0]


def test_an_empty_regex_asks_for_one() -> None:
    [marker] = found("# COUPLED:x: app //")
    assert isinstance(marker, Marker) and marker.regex is None
    assert "between the slashes" in marker.problems[0]


def test_a_regex_that_does_not_compile_is_reported() -> None:
    [marker] = found("# COUPLED:x: app /(\\d+/")
    assert isinstance(marker, Marker) and marker.regex is None
    assert "Fix the regex" in marker.problems[0]


def test_prose_straight_after_a_regex_asks_for_a_full_stop_between() -> None:
    [marker] = found("# COUPLED:x: app /(\\d+)/ in MB")
    assert isinstance(marker, Marker) and marker.regex == "(\\d+)"
    assert "`COUPLED:x: app /(\\d+)/. <prose>`" in marker.problems[0]
