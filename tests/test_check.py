"""The checks of a repository's groups, given its files as text and its registry."""

from coupled.core.check import Content, FileRead, Missing, Problem, check, file_sites
from coupled.core.registry import Registry, parse
from coupled.core.settings import MarkerMessage

REGISTRY = "coupled-registry.toml"
OFF = MarkerMessage(pointer=False, relations=False)
POINTER = MarkerMessage(pointer=True, relations=False)


def problems(
    files: dict[str, str],
    groups: str | None,
    others: dict[str, FileRead],
    message: MarkerMessage,
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


def test_a_group_mixing_kinds_of_op_is_reported() -> None:
    groups = '["COUPLED:upload-limit:"]\nrelations = ["proxy >= app", "app same-as proxy"]\n'
    found = problems(UPLOAD_FILES, groups, {}, OFF)
    assert any(
        "Use ops of one kind in a group, not >= and same-as" in m for m in messages_of(found)
    )


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


STATUS = """
["COUPLED:status:"]
relations = ["web subset-of app"]
"""

STATUS_FILES = {
    "app.py": (
        "# COUPLED:status: app\nclass Status(StrEnum):\n"
        '    PENDING = "pending"\n    STORED = "stored"\n# COUPLED:status:END'
    ),
    "web.ts": '// COUPLED:status: web\nexport type Status = "pending" | "stored";',
}


def test_a_set_relation_that_holds_has_no_problems() -> None:
    assert problems(STATUS_FILES, STATUS, {}, OFF) == []


def test_a_set_relation_that_does_not_hold_names_what_only_one_site_holds() -> None:
    web = '// COUPLED:status: web\nexport type Status = "pending" | "archived";'
    found = problems({**STATUS_FILES, "web.ts": web}, STATUS, {}, OFF)
    assert messages_of(found) == [
        "web.ts:1 `web subset-of app` doesn't hold with app.py:1: `archived` is only here. "
        "Change the members so it holds; change the relation only if what must hold has changed"
    ]


def test_a_bare_same_set_compares_every_site_and_file() -> None:
    groups = '["COUPLED:status:"]\nrelations = ["same-set"]\nfiles = ["./statuses.json#/all"]\n'
    same: dict[str, FileRead] = {"statuses.json": Content('{"all": ["stored", "pending"]}')}
    assert problems(STATUS_FILES, groups, same, OFF) == []
    fewer: dict[str, FileRead] = {"statuses.json": Content('{"all": ["pending"]}')}
    found = problems(STATUS_FILES, groups, fewer, OFF)
    assert messages_of(found)[0].startswith(
        "./statuses.json#/all `same-set` doesn't hold with app.py:1: `stored` is only there."
    )


def test_a_selector_picks_each_of_a_site_s_members() -> None:
    files = {
        "model.py": (
            "# COUPLED:columns: model\nclass Upload:\n    id: str\n    size_bytes: int\n"
            "# COUPLED:columns:END"
        ),
        "table.sql": (
            "-- COUPLED:columns: table\nCREATE TABLE uploads (\n    id TEXT,\n"
            "    size_bytes INTEGER\n);\n-- COUPLED:columns:END"
        ),
    }
    groups = (
        '["COUPLED:columns:"]\nrelations = ["model same-set table"]\n'
        "select = { model = '^(\\w+): ', table = '^([a-z_]+) ' }\n"
    )
    assert problems(files, groups, {}, OFF) == []
    files["table.sql"] = files["table.sql"].replace("size_bytes", "bytes")
    assert (
        "`size_bytes` is only here; `bytes` is only there"
        in messages_of(problems(files, groups, {}, OFF))[0]
    )


def test_a_site_whose_members_cannot_be_read_asks_for_a_selector() -> None:
    web = "// COUPLED:status: web\nexport type Status = Pending | Stored;"
    found = problems({**STATUS_FILES, "web.ts": web}, STATUS, {}, OFF)
    assert [p.where for p in found] == ["web.ts:1"]
    assert "select = { web = '<regex>' }" in found[0].message


STEPS = """
["COUPLED:setup:"]
relations = ["same-text"]
"""

STEPS_FILES = {
    "ci.yml": (
        "# COUPLED:setup: ci\n- uses: actions/checkout@v4\n- run: npm ci\n# COUPLED:setup:END"
    ),
    "release.yml": (
        "      # COUPLED:setup: release\n      - uses: actions/checkout@v4\n\n"
        "      - run: npm ci\n      # COUPLED:setup:END"
    ),
}


def test_blocks_with_the_same_text_however_they_are_indented_have_no_problems() -> None:
    assert problems(STEPS_FILES, STEPS, {}, OFF) == []


def test_text_that_differs_is_reported_with_the_first_line_that_does() -> None:
    release = STEPS_FILES["release.yml"].replace("npm ci", "npm install")
    found = problems({**STEPS_FILES, "release.yml": release}, STEPS, {}, OFF)
    assert messages_of(found) == [
        "release.yml:1 `same-text` doesn't hold with ci.yml:1: `- run: npm install` here is "
        "`- run: npm ci` there. Change the text so it holds; change the relation only if what "
        "must hold has changed"
    ]


def test_a_site_s_text_is_compared_with_a_file_s() -> None:
    groups = '["COUPLED:setup:"]\nrelations = ["ci same-text ./steps.txt"]\n'
    files = {"ci.yml": STEPS_FILES["ci.yml"]}
    steps: dict[str, FileRead] = {
        "steps.txt": Content("- uses: actions/checkout@v4\n- run: npm ci\n")
    }
    assert problems(files, groups, steps, OFF) == []
    steps = {"steps.txt": Content("- uses: actions/checkout@v4\n")}
    found = problems(files, groups, steps, OFF)
    assert "doesn't hold with ./steps.txt: `- run: npm ci` is only here" in messages_of(found)[0]


def test_the_markers_of_sites_inside_a_block_are_not_part_of_its_text() -> None:
    files = {
        "ci.yml": (
            "# COUPLED:setup: ci\n- uses: actions/setup-node@v4\n"
            '  node-version: "24"  # COUPLED:node: ci\n# COUPLED:setup:END'
        ),
        "release.yml": (
            "# COUPLED:setup: release\n- uses: actions/setup-node@v4\n"
            '  node-version: "24"  # COUPLED:node: release. Pinned.\n# COUPLED:setup:END'
        ),
    }
    groups = STEPS + '["COUPLED:node:"]\nrelations = ["="]\n'
    assert problems(files, groups, {}, OFF) == []


VAT_FILES = {
    "a.py": "# COUPLED:vat: invoice\ndef vat(n):\n    return n / 5\n# COUPLED:vat:END",
    "b.py": "# COUPLED:vat: cart\ndef vat(n):\n    return n // 5\n# COUPLED:vat:END",
}
VAT_WHY = 'why = "an invoice and a cart must charge the same VAT"\n'


def test_a_judged_group_s_relations_are_not_compared() -> None:
    groups = '["COUPLED:vat:"]\nrelations = ["same-as"]\n' + VAT_WHY
    assert problems(VAT_FILES, groups, {}, OFF) == []


def test_a_judged_group_that_does_not_say_why_is_reported() -> None:
    [problem] = problems(VAT_FILES, '["COUPLED:vat:"]\nrelations = ["same-as"]\n', {}, OFF)
    assert problem.where == 'coupled-registry.toml ["COUPLED:vat:"]'
    assert problem.message.startswith("Say why these sites are coupled, as `why = ")


def test_prose_can_be_the_description_of_code_in_a_judged_group() -> None:
    files = {
        **VAT_FILES,
        "README.md": "<!-- COUPLED:vat: docs -->\nVAT is a fifth of the net price.",
    }
    groups = (
        '["COUPLED:vat:"]\nrelations = ["invoice same-as cart", "docs description-of invoice"]\n'
        + VAT_WHY
    )
    assert problems(files, groups, {}, OFF) == []


def test_a_formula_with_an_op_that_does_not_compare_values_is_reported() -> None:
    groups = '["COUPLED:status:"]\nrelations = ["web subset-of app + 1"]\n'
    found = problems(STATUS_FILES, groups, {}, OFF)
    assert any("Use a formula only with = != < <= > >=" in m for m in messages_of(found))


def test_a_selector_in_a_text_or_judged_group_is_reported() -> None:
    found = problems(STEPS_FILES, STEPS + "select = { ci = 'npm' }\n", {}, OFF)
    assert any("Use `select` only with" in m for m in messages_of(found))


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
