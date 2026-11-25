import unittest
from decimal import Decimal

from coupled.core.comments import syntax_of
from coupled.core.markers import find_markers
from coupled.core.relations import Arith, Formula, SetOp, ValueOp
from coupled.core.values import (
    Fails,
    Holds,
    Incomparable,
    Members,
    Text,
    Unreadable,
    Value,
    block_lines,
    compare,
    compare_member,
    compare_members,
    compare_text,
    described_line,
    json_at,
    read_file_members,
    read_file_text,
    read_file_value,
    read_members,
    read_value,
    text_of,
    unit_of,
    value_line,
)

PYTHON = syntax_of("a.py")


def block(path: str, *lines: str) -> list[str]:
    """The block of the first marker in lines, of the file at path."""
    placed = find_markers(list(lines))
    return block_lines(list(lines), placed[0], placed, syntax_of(path))


class ValueLines(unittest.TestCase):
    def test_a_trailing_marker_describes_the_code_before_its_comment(self) -> None:
        for path, line, code in (
            ("app.py", "MAX_UPLOAD_MB = 8  # COUPLED:x: a", "MAX_UPLOAD_MB = 8"),
            (
                "nginx.conf",
                "client_max_body_size 10m;  # COUPLED:x: a",
                "client_max_body_size 10m;",
            ),
            ("map.js", "mapId: 'a#b',  // COUPLED:x: a", "mapId: 'a#b',"),
            (
                "php.ini",
                "xdebug.output_dir = /tmp/profiles  ; COUPLED:x: a",
                "xdebug.output_dir = /tmp/profiles",
            ),
            ("README.md", "- Map ID: `dog-cafe-map`. COUPLED:x: a", "- Map ID: `dog-cafe-map`."),
            ("Dockerfile", "RUN npm ci --omit=dev  # COUPLED:x: a", "RUN npm ci --omit=dev"),
        ):
            self.assertEqual(code, value_line([line], 0, syntax_of(path)), line)

    def test_a_marker_on_a_comment_line_describes_the_next_line_of_code(self) -> None:
        lines = [
            "# Base image. COUPLED:x: base. Pinned for the build.",
            "# COUPLED:y: image",
            "# Another comment.",
            "FROM node:24-slim  # pinned",
        ]
        self.assertEqual("FROM node:24-slim", value_line(lines, 0, syntax_of("Dockerfile")))

    def test_a_marker_with_a_blank_line_before_its_code_describes_nothing(self) -> None:
        self.assertIsNone(value_line(["# COUPLED:x: a", "", "X = 1"], 0, PYTHON))
        self.assertEqual([], block("a.py", "# COUPLED:x: a", "", "def f():"))

    def test_a_marker_with_no_code_after_it_describes_nothing(self) -> None:
        self.assertIsNone(value_line(["# COUPLED:x: a", "# end"], 0, PYTHON))


class DescribedLines(unittest.TestCase):
    def test_a_trailing_marker_describes_its_own_line(self) -> None:
        self.assertEqual(0, described_line(["X = 1  # COUPLED:x: a", "Y = 2"], 0, PYTHON))

    def test_a_marker_on_its_own_line_describes_the_next_line_past_comments(self) -> None:
        self.assertEqual(2, described_line(["# COUPLED:x: a", "# More words.", "X = 1"], 0, PYTHON))

    def test_a_marker_on_its_own_line_of_markdown_describes_the_next_line(self) -> None:
        self.assertEqual(
            1, described_line(["COUPLED:x: a", "- rule: A unit is"], 0, syntax_of("README.md"))
        )

    def test_a_marker_with_a_blank_line_before_its_code_describes_no_line(self) -> None:
        self.assertIsNone(
            described_line(["COUPLED:x: a", "", "- rule: A unit is"], 0, syntax_of("README.md"))
        )


class ReadingValues(unittest.TestCase):
    def test_the_value_of_common_lines_is_read(self) -> None:
        for code, value in (
            ("private const string FOLDER = 'user';", "user"),
            ('SESSIONS = "claude-sessions"', "claude-sessions"),
            ("- API key: `AIza123`.", "AIza123"),
            ("FROM php:8.5-fpm-bookworm AS builder", "8.5"),
            ("FROM --platform=linux/amd64 node:24.22.1-alpine", "24.22.1"),
            ("image: docker.io/library/node:24.22.1-alpine", "24.22.1"),
            ("HTTP_PORT=8080", "8080"),
            ("IMAGE_NAMESPACE: ianflanagan1", "ianflanagan1"),
            ("xdebug.output_dir = /tmp/profiles", "/tmp/profiles"),
            ("dir=$HOME/.local/state/x", "$HOME/.local/state/x"),
            ("server.keepAliveTimeout = 65_000;", "65_000"),
            ("client_max_body_size 10m;", "10m"),
            ("location ^~ /media/ {", "/media/"),
        ):
            self.assertEqual(Value(value), read_value(code, None), code)

    def test_a_line_with_several_quoted_values_is_unreadable(self) -> None:
        self.assertIsInstance(read_value("f('a', 'b')", None), Unreadable)

    def test_a_line_with_no_single_value_is_unreadable(self) -> None:
        for code in (
            "RUN mkdir /tmp/profiles \\",
            "LINTED: bin src config",
            "type listing struct {",
        ):
            self.assertIsInstance(read_value(code, None), Unreadable, code)

    def test_a_regex_picks_its_capture_group(self) -> None:
        self.assertEqual(Value("8080"), read_value("APP_URL=http://localhost:8080", r":(\d+)$"))

    def test_a_regex_without_a_group_picks_its_whole_match(self) -> None:
        self.assertEqual(
            Value("/tmp/profiles"), read_value("RUN mkdir /tmp/profiles \\", r"/tmp/\w+")
        )

    def test_a_regex_that_does_not_match_is_unreadable(self) -> None:
        self.assertIsInstance(read_value("X = 1", r"port (\d+)"), Unreadable)


class FileValues(unittest.TestCase):
    def test_a_regex_picks_a_value_out_of_a_file_matching_at_each_line(self) -> None:
        content = "NAME=x\nUPLOAD_MB=8\n"
        self.assertEqual(Value("8"), read_file_value(content, None, r"^UPLOAD_MB=(\d+)$"))

    def test_a_regex_that_matches_nothing_in_a_file_is_unreadable(self) -> None:
        self.assertIsInstance(read_file_value("NAME=x\n", None, r"^UPLOAD_MB=(\d+)"), Unreadable)

    def test_a_one_line_file_is_its_value(self) -> None:
        self.assertEqual(Value("24"), read_file_value("24\n", None, None))

    def test_a_longer_file_without_a_pointer_has_no_value(self) -> None:
        self.assertIsNone(read_file_value("{\n}\n", None, None))

    def test_a_pointer_reads_a_value_in_json(self) -> None:
        content = '{"engines": {"node": ">=24"}, "list": [1, 2.5], "a/b": {"~c": "d"}}'
        self.assertEqual(Value(">=24"), read_file_value(content, "/engines/node", None))
        self.assertEqual(Value("2.5"), read_file_value(content, "/list/1", None))
        self.assertEqual(Value("d"), read_file_value(content, "/a~1b/~0c", None))

    def test_a_pointer_to_nothing_or_to_an_object_is_unreadable(self) -> None:
        self.assertIsInstance(read_file_value('{"a": 1}', "/b", None), Unreadable)
        self.assertIsInstance(read_file_value('{"a": {}}', "/a", None), Unreadable)
        self.assertIsInstance(read_file_value('{"a": true}', "/a", None), Unreadable)

    def test_a_pointer_reaches_through_a_list_by_index(self) -> None:
        content = '{"runtimes": [{"name": "node"}, {"name": "python", "version": "3.13"}]}'
        self.assertEqual(Value("node"), read_file_value(content, "/runtimes/0/name", None))
        self.assertEqual(Value("3.13"), read_file_value(content, "/runtimes/1/version", None))

    def test_a_list_index_that_is_not_plain_decimal_digits_reaches_nothing(self) -> None:
        content = '{"list": ["a", "b", "c"]}'
        for index in ("3", "-", "-1", "01", "00", "+1", " 1", "1 ", "1.0", "²", "١", ""):
            self.assertIsInstance(
                read_file_value(content, f"/list/{index}", None), Unreadable, index
            )

    def test_a_pointer_into_a_file_that_is_not_json_is_unreadable(self) -> None:
        self.assertIsInstance(read_file_value("a = 1", "/a", None), Unreadable)


class Comparing(unittest.TestCase):
    def test_equal_strings_hold_and_different_ones_fail(self) -> None:
        self.assertEqual(Holds(), compare(ValueOp.EQ, "/cache/", "/cache/", None))
        self.assertIsInstance(compare(ValueOp.EQ, "/cache/", "/caches/", None), Fails)
        self.assertEqual(Holds(), compare(ValueOp.NE, "staging", "prod", None))

    def test_versions_compare_on_the_components_both_give(self) -> None:
        self.assertEqual(Holds(), compare(ValueOp.EQ, "24", "24.22.1", None))
        self.assertEqual(Holds(), compare(ValueOp.EQ, "v3.12", "3.12.4", None))
        self.assertIsInstance(compare(ValueOp.EQ, "24.1", "24.2", None), Fails)
        self.assertEqual(Holds(), compare(ValueOp.LT, "8.5", "8.10", None))

    def test_numbers_compare_numerically_ignoring_a_unit_suffix(self) -> None:
        self.assertEqual(Holds(), compare(ValueOp.GE, "10m", "8", None))
        self.assertEqual(Holds(), compare(ValueOp.EQ, "65_000", "65000", None))
        self.assertIsInstance(compare(ValueOp.LT, "9", "8", None), Fails)

    def test_ordering_strings_is_incomparable(self) -> None:
        self.assertIsInstance(compare(ValueOp.LT, "a", "b", None), Incomparable)

    def test_a_formula_applies_to_the_other_value(self) -> None:
        self.assertEqual(
            Holds(), compare(ValueOp.GT, "65_000", "60", Formula(Arith.MUL, Decimal(1000)))
        )
        self.assertEqual(
            Holds(), compare(ValueOp.LT, "60", "65_000", Formula(Arith.DIV, Decimal(1000)))
        )
        self.assertEqual(Holds(), compare(ValueOp.GE, "65s", "60", Formula(Arith.ADD, Decimal(5))))
        self.assertEqual(Holds(), compare(ValueOp.EQ, "55", "60", Formula(Arith.SUB, Decimal(5))))

    def test_a_failing_formula_shows_its_working(self) -> None:
        verdict = compare(ValueOp.GT, "59000", "60", Formula(Arith.MUL, Decimal(1000)))
        self.assertEqual(Fails("59000 > 60 * 1000 (= 60000)"), verdict)

    def test_a_formula_on_a_value_that_is_not_a_number_is_incomparable(self) -> None:
        self.assertIsInstance(
            compare(ValueOp.EQ, "a", "60", Formula(Arith.ADD, Decimal(1))), Incomparable
        )

    def test_dividing_by_zero_is_incomparable(self) -> None:
        self.assertIsInstance(
            compare(ValueOp.EQ, "1", "60", Formula(Arith.DIV, Decimal(0))), Incomparable
        )


class ReadingMembers(unittest.TestCase):
    def test_a_block_s_members_are_the_quoted_values_on_its_lines(self) -> None:
        block = ("class Status(StrEnum):", 'PENDING = "pending"', "STORED = 'stored'")
        self.assertEqual(Members(("pending", "stored")), read_members(block, None))

    def test_several_members_can_share_a_line(self) -> None:
        block = ('export type Status = "pending" | "stored";',)
        self.assertEqual(Members(("pending", "stored")), read_members(block, None))

    def test_a_member_found_twice_is_one_member(self) -> None:
        self.assertEqual(Members(("a", "b")), read_members(("'a', 'b'", "'a'"), None))

    def test_a_regex_picks_each_member_by_its_capture_group(self) -> None:
        block = ("CREATE TABLE uploads (", "id TEXT PRIMARY KEY,", "size_bytes INTEGER", ");")
        self.assertEqual(Members(("id", "size_bytes")), read_members(block, r"^([a-z_]+) "))

    def test_a_regex_without_a_group_picks_each_whole_match(self) -> None:
        block = ("disable_functions = exec,popen",)
        self.assertEqual(Members(("exec", "popen")), read_members(block, r"(?<=[ ,])\w+"))

    def test_a_block_with_no_quoted_value_is_unreadable(self) -> None:
        self.assertIsInstance(read_members(("id: str", "name: str"), None), Unreadable)

    def test_a_regex_that_matches_nothing_is_unreadable(self) -> None:
        self.assertIsInstance(read_members(("id: str",), r"^(\w+) ="), Unreadable)


class FileMembers(unittest.TestCase):
    def test_a_regex_picks_each_member_out_of_a_file_s_lines(self) -> None:
        content = "- pending\n- stored\nother\n"
        self.assertEqual(
            Members(("pending", "stored")), read_file_members(content, None, r"^- (\w+)")
        )

    def test_a_file_s_members_are_its_lines(self) -> None:
        self.assertEqual(Members(("en", "fr")), read_file_members("en\n\n  fr\n", None, None))

    def test_a_pointer_to_a_list_reads_its_items(self) -> None:
        content = '{"locales": ["en", "fr"], "ports": [80, 443]}'
        self.assertEqual(Members(("en", "fr")), read_file_members(content, "/locales", None))
        self.assertEqual(Members(("80", "443")), read_file_members(content, "/ports", None))

    def test_a_pointer_to_an_object_reads_its_keys(self) -> None:
        content = '{"scripts": {"build": "tsc", "test": "vitest"}}'
        self.assertEqual(Members(("build", "test")), read_file_members(content, "/scripts", None))

    def test_a_pointer_to_one_value_to_nothing_or_into_a_list_of_objects_is_unreadable(
        self,
    ) -> None:
        for content, pointer in (
            ('{"a": 1}', "/a"),
            ('{"a": 1}', "/b"),
            ('{"a": [{"b": 1}]}', "/a"),
            ("a: [1]", "/a"),
        ):
            self.assertIsInstance(read_file_members(content, pointer, None), Unreadable, content)

    def test_an_empty_file_or_list_has_no_members(self) -> None:
        self.assertEqual(Members(()), read_file_members("\n", None, None))
        self.assertEqual(Members(()), read_file_members('{"a": []}', "/a", None))


class ComparingMembers(unittest.TestCase):
    def test_the_same_members_in_any_order_are_the_same_set(self) -> None:
        self.assertEqual(
            Holds(), compare_members(SetOp.SAME_SET, Members(("a", "b")), Members(("b", "a")))
        )

    def test_a_set_that_differs_names_what_only_each_side_has(self) -> None:
        self.assertEqual(
            Fails("`a` is only here; `c`, `d` are only there"),
            compare_members(SetOp.SAME_SET, Members(("a", "b")), Members(("b", "c", "d"))),
        )

    def test_a_subset_holds_only_names_the_other_holds(self) -> None:
        self.assertEqual(
            Holds(), compare_members(SetOp.SUBSET_OF, Members(("a",)), Members(("a", "b")))
        )
        self.assertEqual(
            Fails("`c` is only here"),
            compare_members(SetOp.SUBSET_OF, Members(("a", "c")), Members(("a", "b"))),
        )

    def test_a_superset_holds_every_name_the_other_holds(self) -> None:
        self.assertEqual(
            Holds(), compare_members(SetOp.SUPERSET_OF, Members(("a", "b")), Members(("a",)))
        )
        self.assertEqual(
            Fails("`b` is only there"),
            compare_members(SetOp.SUPERSET_OF, Members(("a",)), Members(("a", "b"))),
        )

    def test_a_proper_subset_holds_only_names_the_other_holds_and_not_all_of_them(self) -> None:
        self.assertEqual(
            Holds(), compare_members(SetOp.PROPER_SUBSET_OF, Members(("a",)), Members(("a", "b")))
        )
        self.assertEqual(
            Fails("`c` is only here"),
            compare_members(SetOp.PROPER_SUBSET_OF, Members(("a", "c")), Members(("a", "b"))),
        )
        self.assertEqual(
            Fails("both hold the same names"),
            compare_members(SetOp.PROPER_SUBSET_OF, Members(("a", "b")), Members(("b", "a"))),
        )

    def test_a_proper_superset_holds_every_name_the_other_holds_and_more(self) -> None:
        self.assertEqual(
            Holds(),
            compare_members(SetOp.PROPER_SUPERSET_OF, Members(("a", "b")), Members(("a",))),
        )
        self.assertEqual(
            Fails("`b` is only there"),
            compare_members(SetOp.PROPER_SUPERSET_OF, Members(("a",)), Members(("a", "b"))),
        )
        self.assertEqual(
            Fails("both hold the same names"),
            compare_members(SetOp.PROPER_SUPERSET_OF, Members(("a",)), Members(("a",))),
        )

    def test_disjoint_sets_share_no_name(self) -> None:
        self.assertEqual(
            Holds(), compare_members(SetOp.DISJOINT_FROM, Members(("a",)), Members(("b",)))
        )
        self.assertEqual(
            Fails("`b`, `c` are in both"),
            compare_members(
                SetOp.DISJOINT_FROM, Members(("a", "b", "c")), Members(("c", "b", "d"))
            ),
        )

    def test_a_long_difference_is_cut_short(self) -> None:
        names = tuple(str(n) for n in range(8))
        self.assertEqual(
            Fails("`1`, `2`, `3`, `4`, `5` and 2 more are only here"),
            compare_members(SetOp.SUBSET_OF, Members(names), Members(("0",))),
        )


class ComparingAMember(unittest.TestCase):
    def test_a_value_is_a_member_of_a_set_that_holds_it(self) -> None:
        self.assertEqual(Holds(), compare_member(Value("info"), Members(("debug", "info"))))

    def test_a_value_the_set_does_not_hold_is_named_with_the_set(self) -> None:
        self.assertEqual(
            Fails("`trace` isn't among `debug`, `info`"),
            compare_member(Value("trace"), Members(("debug", "info"))),
        )


class Texts(unittest.TestCase):
    def test_text_is_its_lines_without_indentation_or_blank_lines(self) -> None:
        self.assertEqual(Text(("a:", "- b")), text_of(["a:", "", "    - b  "]))

    def test_a_file_s_text_is_all_of_it(self) -> None:
        self.assertEqual(
            Text(("node_modules", "dist")), read_file_text("node_modules\n\ndist\n", None)
        )

    def test_a_pointer_reads_the_json_there_however_it_is_laid_out(self) -> None:
        self.assertEqual(
            read_file_text('{"x": {"b": 2, "a": 1}}', "/x"),
            read_file_text('{"y": 0, "x": {\n  "a": 1,\n  "b": 2\n}}', "/x"),
        )

    def test_a_pointer_to_nothing_is_unreadable(self) -> None:
        self.assertIsInstance(read_file_text('{"x": 1}', "/y"), Unreadable)
        self.assertIsInstance(read_file_text("x: 1", "/x"), Unreadable)

    def test_the_same_lines_are_the_same_text(self) -> None:
        self.assertEqual(Holds(), compare_text(Text(("a", "b")), Text(("a", "b"))))

    def test_text_that_differs_shows_the_first_line_that_does(self) -> None:
        self.assertEqual(
            Fails("`return n / 5` here is `return n // 5` there"),
            compare_text(
                Text(("def vat(n):", "return n / 5", "x")),
                Text(("def vat(n):", "return n // 5", "y")),
            ),
        )

    def test_text_that_goes_on_past_the_other_shows_its_next_line(self) -> None:
        self.assertEqual(
            Fails("`c` is only here"), compare_text(Text(("a", "b", "c")), Text(("a", "b")))
        )
        self.assertEqual(
            Fails("`b` is only there"), compare_text(Text(("a",)), Text(("a", "b", "c")))
        )

    def test_a_long_line_is_cut_short(self) -> None:
        verdict = compare_text(Text(("x" * 100,)), Text(("y",)))
        self.assertEqual(Fails("`" + "x" * 57 + "...` here is `y` there"), verdict)


class Blocks(unittest.TestCase):
    def test_a_block_runs_from_the_line_its_marker_describes_to_its_end(self) -> None:
        self.assertEqual(
            ["private int vat(int net) {", "return net / 5;", "// rounded down", "}"],
            block(
                "Invoice.java",
                "/**",
                " * COUPLED:vat: invoice",
                " */",
                "private int vat(int net) {",
                "    return net / 5;",
                "",
                "    // rounded down",
                "}",
                "// COUPLED:vat:END",
                "private int other() {",
            ),
        )

    def test_a_block_ends_at_its_end_whatever_the_indentation(self) -> None:
        self.assertEqual(
            ["services:", "app:", "image: app", "worker:"],
            block(
                "compose.yaml",
                "# COUPLED:x: a",
                "services:",
                "  app:",
                "    image: app",
                "worker:",
                "# COUPLED:x:END",
            ),
        )

    def test_a_trailing_marker_starts_the_block_on_its_own_line_without_its_comment(self) -> None:
        self.assertEqual(
            ["def f():", "return 1"],
            block("a.py", "def f():  # COUPLED:x: a", "    return 1", "# COUPLED:x:END"),
        )

    def test_a_marker_without_an_end_describes_only_its_line(self) -> None:
        self.assertEqual(
            ["def f():"], block("a.py", "# COUPLED:x: a", "def f():", "    return 1", "")
        )
        self.assertEqual(
            ["disable_functions = exec,popen"],
            block("php.ini", "disable_functions = exec,popen ; COUPLED:x: a", "  other = 1"),
        )

    def test_the_markers_of_blocks_inside_a_block_are_not_part_of_it(self) -> None:
        self.assertEqual(
            ["def f():", "TABLE = {", "}", "x = 1", "return TABLE"],
            block(
                "a.py",
                "# COUPLED:outer: f",
                "def f():",
                "    # COUPLED:inner: table",
                "    TABLE = {",
                "    }",
                "    # COUPLED:inner:END",
                "    x = 1  # COUPLED:other: x",
                "    return TABLE",
                "# COUPLED:outer:END",
            ),
        )

    def test_a_marker_describing_no_line_has_no_block(self) -> None:
        self.assertEqual([], block("a.py", "x = 1", "# COUPLED:x: a"))

    def test_a_marker_whose_end_comes_before_any_code_has_no_block(self) -> None:
        self.assertEqual([], block("a.py", "# COUPLED:x: a", "# COUPLED:x:END", "f()"))


class Units(unittest.TestCase):
    def test_a_number_s_unit_is_its_suffix(self) -> None:
        self.assertEqual("m", unit_of("10m"))
        self.assertEqual("M", unit_of("10M"))
        self.assertEqual("ms", unit_of("65_000 ms"))

    def test_a_number_without_a_suffix_or_a_non_number_has_no_unit(self) -> None:
        for text in ("8", "3.12", "24.22.1", "/cache/", "node"):
            with self.subTest(text=text):
                self.assertIsNone(unit_of(text))


class JsonAt(unittest.TestCase):
    def test_a_pointer_reaches_a_subtree_written_canonically(self) -> None:
        self.assertEqual('{"a": 1, "b": 2}', json_at('{"x": {"b": 2, "a": 1}}', "/x"))

    def test_nothing_at_the_pointer_or_not_json_is_none(self) -> None:
        self.assertIsNone(json_at('{"x": 1}', "/y"))
        self.assertIsNone(json_at("x: 1", "/x"))


if __name__ == "__main__":
    unittest.main()
