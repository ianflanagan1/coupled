"""The checks of a repository's groups, given its files as text and its registry."""

from coupled.core.check import Content, FileRead, Missing, Problem, check, file_sites
from coupled.core.registry import Registry, parse
from coupled.core.settings import TagMessage

REGISTRY = "coupled-registry.toml"
OFF = TagMessage(pointer=False, relations=False)
POINTER = TagMessage(pointer=True, relations=False)


def problems(
    files: dict[str, str],
    groups: str | None,
    others: dict[str, FileRead],
    message: TagMessage,
) -> list[Problem]:
    sites = [site for path, text in files.items() for site in file_sites(path, text.splitlines())]
    registry = None if groups is None else parse("version = 1\n" + groups)
    return check(sites, registry, others, REGISTRY, message)


def messages_of(found: list[Problem]) -> list[str]:
    return [f"{problem.where} {problem.message}" for problem in found]


UPLOAD = """
["COUPLED:upload-limit:"]
relations = ["proxy >= app"]
"""

UPLOAD_FILES = {
    "nginx.conf": "client_max_body_size 10m;  # COUPLED:upload-limit: proxy",
    "app.py": "MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app",
}


def test_a_group_whose_relations_hold_has_no_problems() -> None:
    assert problems(UPLOAD_FILES, UPLOAD, {}, OFF) == []


def test_a_relation_that_does_not_hold_is_reported_at_its_first_site() -> None:
    found = problems(
        {**UPLOAD_FILES, "app.py": "MAX_UPLOAD_MB = 12  # COUPLED:upload-limit: app"},
        UPLOAD,
        {},
        OFF,
    )
    assert messages_of(found) == [
        "nginx.conf:1 `proxy >= app` doesn't hold with app.py:1: 10m >= 12. Change the values "
        "so it holds; change the relation only if what must hold has changed"
    ]


def test_a_relation_that_does_not_hold_says_why_its_sites_are_coupled() -> None:
    found = problems(
        {**UPLOAD_FILES, "app.py": "MAX_UPLOAD_MB = 12  # COUPLED:upload-limit: app"},
        UPLOAD + 'why = "nginx rejects a larger body before the app sees it"\n',
        {},
        OFF,
    )
    assert messages_of(found) == [
        "nginx.conf:1 `proxy >= app` doesn't hold with app.py:1: 10m >= 12. They're coupled "
        "because nginx rejects a larger body before the app sees it. Change the values so it "
        "holds; change the relation only if what must hold has changed"
    ]


def test_a_repository_with_markers_and_no_registry_is_reported() -> None:
    [problem] = problems(UPLOAD_FILES, None, {}, OFF)
    assert problem.where == REGISTRY
    assert "There's no registry" in problem.message


def test_a_key_with_no_table_is_reported_at_its_first_site() -> None:
    [problem] = problems(UPLOAD_FILES, "", {}, OFF)
    assert problem.where == "nginx.conf:1"
    assert '["COUPLED:upload-limit:"]' in problem.message


def test_a_label_no_marker_has_is_reported() -> None:
    found = problems(UPLOAD_FILES, UPLOAD.replace("app", "application"), {}, OFF)
    assert any("No site is labelled `application`" in m for m in messages_of(found))


def test_two_sites_with_one_label_are_reported() -> None:
    found = problems(
        {**UPLOAD_FILES, "other.py": "LIMIT = 8  # COUPLED:upload-limit: app"},
        UPLOAD,
        {},
        OFF,
    )
    assert any(
        p.where == "other.py:1" and "labelled `app`, at app.py:1" in p.message for p in found
    )


def test_a_site_nothing_relates_is_reported() -> None:
    found = problems(
        {**UPLOAD_FILES, "php.ini": "upload_max_filesize = 8M ; COUPLED:upload-limit: php"},
        UPLOAD,
        {},
        OFF,
    )
    assert any(p.where == "php.ini:1" and "Nothing relates" in p.message for p in found)


def test_a_bare_op_relates_every_site_and_file() -> None:
    files = {
        "Dockerfile": "# COUPLED:node-version: docker\nFROM node:24.22.1-slim",
        "ci.yml": 'node-version: "24"  # COUPLED:node-version: ci',
    }
    groups = '["COUPLED:node-version:"]\nrelations = ["="]\nfiles = ["./.nvmrc"]\n'
    assert problems(files, groups, {".nvmrc": Content("24.22\n")}, OFF) == []
    found = problems(files, groups, {".nvmrc": Content("22\n")}, OFF)
    assert messages_of(found)[0].startswith(
        "./.nvmrc `=` doesn't hold with Dockerfile:1: 22 = 24.22.1. Change the values"
    )


def test_a_file_s_value_is_read_at_its_pointer() -> None:
    groups = '["COUPLED:upload-limit:"]\nrelations = ["proxy = ./limits.json#/upload_mb"]\n'
    files = {"nginx.conf": UPLOAD_FILES["nginx.conf"]}
    assert problems(files, groups, {"limits.json": Content('{"upload_mb": 10}')}, OFF) == []
    found = problems(files, groups, {"limits.json": Content('{"upload_mb": 5}')}, OFF)
    assert "doesn't hold with ./limits.json#/upload_mb: 10m = 5" in messages_of(found)[0]


def test_a_missing_file_is_reported_unless_it_is_optional() -> None:
    groups = '["COUPLED:v:"]\nrelations = ["="]\nfiles = ["./.nvmrc", "./.env?"]\n'
    files = {"a.txt": "X = 1  # COUPLED:v: a"}
    found = problems(files, groups, {".nvmrc": Missing(), ".env": Missing()}, OFF)
    assert [p.where for p in found] == ["./.nvmrc"]


def test_a_group_of_files_alone_needs_no_marker() -> None:
    groups = '["COUPLED:v:"]\nrelations = ["./.nvmrc = ./.tool-version"]\n'
    others: dict[str, FileRead] = {".nvmrc": Content("24\n"), ".tool-version": Content("24\n")}
    assert problems({}, groups, others, OFF) == []


def test_a_group_with_one_member_is_reported() -> None:
    groups = '["COUPLED:v:"]\nrelations = ["="]\n'
    [problem] = problems({"a.txt": "X = 1  # COUPLED:v: a"}, groups, {}, OFF)
    assert "needs at least two sites or files, and has 1" in problem.message


def test_a_group_mixing_value_and_structural_ops_is_reported() -> None:
    groups = '["COUPLED:upload-limit:"]\nrelations = ["proxy >= app", "app same-as proxy"]\n'
    found = problems(UPLOAD_FILES, groups, {}, OFF)
    assert any("either value ops or structural ops" in m for m in messages_of(found))


def test_relating_two_sites_twice_is_reported() -> None:
    groups = '["COUPLED:upload-limit:"]\nrelations = ["proxy >= app", "app <= proxy"]\n'
    found = problems(UPLOAD_FILES, groups, {}, OFF)
    assert any("in only one relation" in m for m in messages_of(found))


def test_a_selector_picks_a_site_s_value() -> None:
    files = {
        "a.env": "APP_URL=http://localhost:8080  # COUPLED:port: url",
        "b.env": "HTTP_PORT=8080  # COUPLED:port: port",
    }
    groups = '["COUPLED:port:"]\nrelations = ["url = port"]\nselect = { url = \':(\\d+)$\' }\n'
    assert problems(files, groups, {}, OFF) == []


def test_an_unreadable_value_asks_for_a_selector() -> None:
    files = {**UPLOAD_FILES, "app.py": "f('a', 'b')  # COUPLED:upload-limit: app"}
    found = problems(files, UPLOAD, {}, OFF)
    assert any("select = { app = '<regex>' }" in m for m in messages_of(found))


def test_an_end_after_a_marker_of_a_value_group_is_reported() -> None:
    files = {
        **UPLOAD_FILES,
        "app.py": "# COUPLED:upload-limit: app\nMAX = 8\n# COUPLED:upload-limit:END",
    }
    found = problems(files, UPLOAD, {}, OFF)
    assert any("Drop the END" in m for m in messages_of(found))


def test_a_structural_group_s_relations_are_not_compared() -> None:
    files = {
        "a.py": "# COUPLED:vat: invoice\ndef vat(n):\n    return n / 5\n# COUPLED:vat:END",
        "b.py": "# COUPLED:vat: cart\ndef vat(n):\n    return n // 5\n# COUPLED:vat:END",
    }
    assert problems(files, '["COUPLED:vat:"]\nrelations = ["same-as"]\n', {}, OFF) == []


def test_a_marker_with_a_blank_line_before_its_code_is_reported() -> None:
    files = {**UPLOAD_FILES, "app.py": "# COUPLED:upload-limit: app\n\nMAX = 8"}
    found = problems(files, UPLOAD, {}, OFF)
    assert any(p.where == "app.py:1" and "no blank line" in p.message for p in found)


def test_with_messages_on_a_marker_without_its_message_is_reported() -> None:
    found = problems(UPLOAD_FILES, UPLOAD, {}, POINTER)
    assert len(found) == 2
    assert all("--fix does it" in p.message for p in found)
    written = {
        path: text
        + '. Change only with every "COUPLED:upload-limit:" site, per coupled-registry.toml.'
        for path, text in UPLOAD_FILES.items()
    }
    assert problems(written, UPLOAD, {}, POINTER) == []


def test_with_messages_off_a_marker_with_a_message_is_reported() -> None:
    written = {
        **UPLOAD_FILES,
        "app.py": UPLOAD_FILES["app.py"]
        + '. Change only with every "COUPLED:upload-limit:" site, per coupled-registry.toml.',
    }
    [problem] = problems(written, UPLOAD, {}, OFF)
    assert problem.where == "app.py:1" and "--fix does it" in problem.message


def test_a_registry_that_cannot_be_read_is_reported() -> None:
    sites = file_sites("a.py", ["X = 1  # COUPLED:x: a"])
    [problem] = check(sites, parse("nope ="), {}, REGISTRY, OFF)
    assert "Can't read the registry" in problem.message


def test_markers_alone_are_checked_even_without_a_registry() -> None:
    sites = file_sites("a.py", ["# COUPLED:x:[= Y]"])
    assert any("registry" in p.message for p in check(sites, None, {}, REGISTRY, OFF))
    assert isinstance(parse("version = 1\n"), Registry)
