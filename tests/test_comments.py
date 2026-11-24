"""Which comment syntax a file is written in, and finding comments in its lines."""

from coupled.core.comments import is_comment_line, strip_comment, syntax_of


def test_code_is_kept_up_to_its_comment_in_each_language() -> None:
    for path, line, code in (
        ("app.py", "MAX = a % b  # note", "MAX = a % b  "),
        ("deploy.sh", "run --no-cache  # note", "run --no-cache  "),
        ("Dockerfile", "RUN apt-get install --no-install-recommends x", None),
        ("main.go", "max := 8  // note", "max := 8  "),
        ("app.ts", "const re = /a#b/;  /* note */", "const re = /a#b/;  "),
        ("query.sql", "LIMIT 8  -- note", "LIMIT 8  "),
        ("Main.hs", "limit = 8  -- note", "limit = 8  "),
        ("main.ml", "let limit = 8  (* note *)", "let limit = 8  "),
        ("server.erl", "-define(LIMIT, 8).  % note", "-define(LIMIT, 8).  "),
        ("paper.tex", "\\def\\limit{8}  % note", "\\def\\limit{8}  "),
        ("php.ini", "memory_limit = 8M  ; note", "memory_limit = 8M  "),
        ("core.clj", "(def limit 8)  ; note", "(def limit 8)  "),
        ("Module.vb", "Const Limit = 8  ' note", "Const Limit = 8  "),
        (
            "solver.f90",
            "integer, parameter :: limit = 8  ! note",
            "integer, parameter :: limit = 8  ",
        ),
        ("page.html", "<p>8</p>  <!-- note -->", "<p>8</p>  "),
        ("page.j2", "{{ limit }}  {# note #}", "{{ limit }}  "),
    ):
        expected = line if code is None else code
        assert strip_comment(line, syntax_of(path)) == expected, path


def test_a_token_that_opens_a_comment_elsewhere_is_code_in_a_language_without_it() -> None:
    assert strip_comment("x = a % b", syntax_of("app.py")) == "x = a % b"
    assert strip_comment("void (*callback)(int);", syntax_of("app.c")) == "void (*callback)(int);"
    assert strip_comment("ls --all", syntax_of("deploy.sh")) == "ls --all"
    assert not is_comment_line("#define LIMIT 8", syntax_of("limits.h"))
    assert not is_comment_line("# Limits", syntax_of("README.md"))


def test_a_line_holding_only_a_comment_is_a_comment_line() -> None:
    for path, line in (
        ("app.py", "    # note"),
        ("main.go", "// note"),
        ("main.go", " * note, inside a docblock"),
        ("Main.hs", "{- note -}"),
        ("main.ml", "(* note *)"),
        ("server.erl", "% note"),
        ("README.md", "<!-- note -->"),
    ):
        assert is_comment_line(line, syntax_of(path)), (path, line)


def test_files_are_known_by_their_name_where_it_has_no_extension() -> None:
    hash_only = syntax_of("deploy.sh")
    for path in ("Dockerfile", "docker/Dockerfile.prod", "Makefile", ".env", ".env.local"):
        assert syntax_of(path) == hash_only, path


def test_a_file_s_extension_is_matched_whatever_its_case() -> None:
    assert syntax_of("APP.PY") == syntax_of("app.py")


def test_a_file_of_an_unknown_kind_takes_every_common_comment() -> None:
    syntax = syntax_of("config.unknown")
    for line in (
        "# note",
        "// note",
        "; note",
        "-- note",
        "/* note */",
        "<!-- note -->",
        "{# note #}",
    ):
        assert is_comment_line(line, syntax), line
    assert not is_comment_line("% note", syntax)
