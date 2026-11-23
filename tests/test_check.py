"""The checks of a repository's groups, given its files as text and its registry."""

from coupled_tags_lint.core.check import Content, FileRead, Missing, Problem, check, file_sites
from coupled_tags_lint.core.registry import Registry, parse

REGISTRY = ".coupled-tags.toml"


def problems(
    files: dict[str, str],
    groups: str | None,
    others: dict[str, FileRead],
    messages: bool,
) -> list[Problem]:
    sites = [site for path, text in files.items() for site in file_sites(path, text.splitlines())]
    registry = None if groups is None else parse("version = 1\n" + groups)
    return check(sites, registry, others, REGISTRY, messages)


def messages_of(found: list[Problem]) -> list[str]:
    return [f"{problem.where} {problem.message}" for problem in found]


UPLOAD = """
["COUPLED:upload-limit:"]
relations = ["nginx >= app"]
"""

UPLOAD_FILES = {
    "nginx.conf": "client_max_body_size 10m;  # COUPLED:upload-limit: nginx",
    "app.py": "MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app",
}


def test_a_group_whose_relations_hold_has_no_problems() -> None:
    assert problems(UPLOAD_FILES, UPLOAD, {}, False) == []


def test_a_relation_that_does_not_hold_is_reported_at_its_first_site() -> None:
    found = problems(
        {**UPLOAD_FILES, "app.py": "MAX_UPLOAD_MB = 12  # COUPLED:upload-limit: app"},
        UPLOAD,
        {},
        False,
    )
    assert messages_of(found) == [
        "nginx.conf:1 `nginx >= app` doesn't hold with app.py:1: 10m >= 12"
    ]


def test_a_repository_with_markers_and_no_registry_is_reported() -> None:
    [problem] = problems(UPLOAD_FILES, None, {}, False)
    assert problem.where == REGISTRY
    assert "There's no registry" in problem.message


def test_a_key_with_no_table_is_reported_at_its_first_site() -> None:
    [problem] = problems(UPLOAD_FILES, "", {}, False)
    assert problem.where == "nginx.conf:1"
    assert '["COUPLED:upload-limit:"]' in problem.message


def test_a_label_no_marker_has_is_reported() -> None:
    found = problems(UPLOAD_FILES, UPLOAD.replace("app", "application"), {}, False)
    assert any("No site is labelled `application`" in m for m in messages_of(found))


def test_two_sites_with_one_label_are_reported() -> None:
    found = problems(
        {**UPLOAD_FILES, "other.py": "LIMIT = 8  # COUPLED:upload-limit: app"}, UPLOAD, {}, False
    )
    assert any(
        p.where == "other.py:1" and "labelled `app`, at app.py:1" in p.message for p in found
    )


def test_a_site_nothing_relates_is_reported() -> None:
    found = problems(
        {**UPLOAD_FILES, "php.ini": "upload_max_filesize = 8M ; COUPLED:upload-limit: php"},
        UPLOAD,
        {},
        False,
    )
    assert any(p.where == "php.ini:1" and "Nothing relates" in p.message for p in found)


def test_a_bare_op_relates_every_site_and_file() -> None:
    files = {
        "Dockerfile": "# COUPLED:node-version: docker\nFROM node:24.22.1-slim",
        "ci.yml": 'node-version: "24"  # COUPLED:node-version: ci',
    }
    groups = '["COUPLED:node-version:"]\nrelations = ["="]\nfiles = ["./.nvmrc"]\n'
    assert problems(files, groups, {".nvmrc": Content("24.22\n")}, False) == []
    found = problems(files, groups, {".nvmrc": Content("22\n")}, False)
    assert messages_of(found) == ["./.nvmrc `=` doesn't hold with Dockerfile:1: 22 = 24.22.1"]


def test_a_file_s_value_is_read_at_its_pointer() -> None:
    groups = '["COUPLED:upload-limit:"]\nrelations = ["nginx = ./limits.json#/upload_mb"]\n'
    files = {"nginx.conf": UPLOAD_FILES["nginx.conf"]}
    assert problems(files, groups, {"limits.json": Content('{"upload_mb": 10}')}, False) == []
    found = problems(files, groups, {"limits.json": Content('{"upload_mb": 5}')}, False)
    assert "doesn't hold with ./limits.json#/upload_mb: 10m = 5" in messages_of(found)[0]


def test_a_missing_file_is_reported_unless_it_is_optional() -> None:
    groups = '["COUPLED:v:"]\nrelations = ["="]\nfiles = ["./.nvmrc", "./.env?"]\n'
    files = {"a.txt": "X = 1  # COUPLED:v: a"}
    found = problems(files, groups, {".nvmrc": Missing(), ".env": Missing()}, False)
    assert [p.where for p in found] == ["./.nvmrc"]


def test_a_group_of_files_alone_needs_no_marker() -> None:
    groups = '["COUPLED:v:"]\nrelations = ["./.nvmrc = ./.tool-version"]\n'
    others: dict[str, FileRead] = {".nvmrc": Content("24\n"), ".tool-version": Content("24\n")}
    assert problems({}, groups, others, False) == []


def test_a_group_with_one_member_is_reported() -> None:
    groups = '["COUPLED:v:"]\nrelations = ["="]\n'
    [problem] = problems({"a.txt": "X = 1  # COUPLED:v: a"}, groups, {}, False)
    assert "needs at least two sites or files, and has 1" in problem.message


def test_a_group_mixing_value_and_structural_ops_is_reported() -> None:
    groups = '["COUPLED:upload-limit:"]\nrelations = ["nginx >= app", "app same-as nginx"]\n'
    found = problems(UPLOAD_FILES, groups, {}, False)
    assert any("either value ops or structural ops" in m for m in messages_of(found))


def test_relating_two_sites_twice_is_reported() -> None:
    groups = '["COUPLED:upload-limit:"]\nrelations = ["nginx >= app", "app <= nginx"]\n'
    found = problems(UPLOAD_FILES, groups, {}, False)
    assert any("in only one relation" in m for m in messages_of(found))


def test_a_selector_picks_a_site_s_value() -> None:
    files = {
        "a.env": "APP_URL=http://localhost:8080  # COUPLED:port: url",
        "b.env": "HTTP_PORT=8080  # COUPLED:port: port",
    }
    groups = '["COUPLED:port:"]\nrelations = ["url = port"]\nselect = { url = \':(\\d+)$\' }\n'
    assert problems(files, groups, {}, False) == []


def test_an_unreadable_value_asks_for_a_selector() -> None:
    files = {**UPLOAD_FILES, "app.py": "f('a', 'b')  # COUPLED:upload-limit: app"}
    found = problems(files, UPLOAD, {}, False)
    assert any("select = { app = '<regex>' }" in m for m in messages_of(found))


def test_an_end_after_a_marker_of_a_value_group_is_reported() -> None:
    files = {
        **UPLOAD_FILES,
        "app.py": "# COUPLED:upload-limit: app\nMAX = 8\n# COUPLED:upload-limit:END",
    }
    found = problems(files, UPLOAD, {}, False)
    assert any("Drop the END" in m for m in messages_of(found))


def test_a_structural_group_s_relations_are_not_compared() -> None:
    files = {
        "a.py": "# COUPLED:vat: invoice\ndef vat(n):\n    return n / 5\n# COUPLED:vat:END",
        "b.py": "# COUPLED:vat: cart\ndef vat(n):\n    return n // 5\n# COUPLED:vat:END",
    }
    assert problems(files, '["COUPLED:vat:"]\nrelations = ["same-as"]\n', {}, False) == []


def test_a_marker_with_a_blank_line_before_its_code_is_reported() -> None:
    files = {**UPLOAD_FILES, "app.py": "# COUPLED:upload-limit: app\n\nMAX = 8"}
    found = problems(files, UPLOAD, {}, False)
    assert any(p.where == "app.py:1" and "no blank line" in p.message for p in found)


def test_with_messages_on_a_marker_without_its_message_is_reported() -> None:
    found = problems(UPLOAD_FILES, UPLOAD, {}, True)
    assert len(found) == 2
    assert all("--fix writes it" in p.message for p in found)
    written = {
        path: text
        + '. Change only with every "COUPLED:upload-limit:" site, per .coupled-tags.toml.'
        for path, text in UPLOAD_FILES.items()
    }
    assert problems(written, UPLOAD, {}, True) == []


def test_with_messages_off_a_marker_with_a_message_is_reported() -> None:
    written = {
        **UPLOAD_FILES,
        "app.py": UPLOAD_FILES["app.py"]
        + '. Change only with every "COUPLED:upload-limit:" site, per .coupled-tags.toml.',
    }
    [problem] = problems(written, UPLOAD, {}, False)
    assert problem.where == "app.py:1" and "--fix drops it" in problem.message


def test_a_registry_that_cannot_be_read_is_reported() -> None:
    sites = file_sites("a.py", ["X = 1  # COUPLED:x: a"])
    [problem] = check(sites, parse("nope ="), {}, REGISTRY, False)
    assert "Can't read the registry" in problem.message


def test_markers_alone_are_checked_even_without_a_registry() -> None:
    sites = file_sites("a.py", ["# COUPLED:x:[= Y]"])
    assert any("registry" in p.message for p in check(sites, None, {}, REGISTRY, False))
    assert isinstance(parse("version = 1\n"), Registry)
