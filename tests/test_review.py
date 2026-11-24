"""Comparing a repository's groups with the registry's reviewed section."""

from coupled.core.check import Content, FileRead, Site, file_sites
from coupled.core.registry import Registry, parse
from coupled.core.review import compare, current, reviewed

REGISTRY = "coupled-registry.toml"

VALUES = """version = 1
["COUPLED:upload-limit:"]
relations = ["proxy >= app"]
"""

JUDGED = """version = 1
["COUPLED:vat:"]
relations = ["invoice same-as cart"]
"""


def sites(files: dict[str, str]) -> list[Site]:
    return [site for path, text in files.items() for site in file_sites(path, text.splitlines())]


def registry(text: str) -> Registry:
    parsed = parse(text)
    assert isinstance(parsed, Registry)
    return parsed


def differences(
    before: dict[str, str], after: dict[str, str], text: str, after_text: str
) -> list[str]:
    """The problems after a change from before to after, recorded as reviewed before it."""
    others: dict[str, FileRead] = {}
    old = reviewed({}, current(sites(before), registry(text), others), ["upload-limit", "vat"])
    now = current(sites(after), registry(after_text), others)
    return [f"{p.where} {p.message}" for p in compare(old, now, REGISTRY)]


UPLOAD = {
    "nginx.conf": "client_max_body_size 10m;  # COUPLED:upload-limit: proxy",
    "app.py": "MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app",
}

VAT = {
    "a.py": "# COUPLED:vat: invoice\ndef vat(n):\n    return n / 5\n# COUPLED:vat:END",
    "b.py": "# COUPLED:vat: cart\ndef vat(n):\n    return n / 5\n# COUPLED:vat:END",
}


def test_a_group_as_it_was_reviewed_has_no_differences() -> None:
    assert differences(UPLOAD, UPLOAD, VALUES, VALUES) == []


def test_a_value_changed_within_its_unit_is_left_to_the_relations() -> None:
    after = {**UPLOAD, "nginx.conf": "client_max_body_size 20m;  # COUPLED:upload-limit: proxy"}
    assert differences(UPLOAD, after, VALUES, VALUES) == []


def test_a_unit_changed_is_reported() -> None:
    after = {**UPLOAD, "nginx.conf": "client_max_body_size 10k;  # COUPLED:upload-limit: proxy"}
    [problem] = differences(UPLOAD, after, VALUES, VALUES)
    assert problem.startswith("nginx.conf:1 Its unit has changed from `m` to `k`")


def test_a_changed_table_is_reported() -> None:
    changed = VALUES.replace(">=", ">")
    [problem] = differences(UPLOAD, UPLOAD, VALUES, changed)
    assert "The table of COUPLED:upload-limit: has changed" in problem


def test_a_site_added_or_removed_is_reported() -> None:
    added = {**UPLOAD, "php.ini": "upload_max_filesize = 8M ; COUPLED:upload-limit: php"}
    [problem] = differences(UPLOAD, added, VALUES, VALUES)
    assert problem.startswith("php.ini:1 This site of COUPLED:upload-limit: hasn't been reviewed")
    [problem] = differences(added, UPLOAD, VALUES, VALUES)
    assert problem.startswith("COUPLED:upload-limit: php This site")


def test_moving_a_site_to_another_file_is_not_a_difference() -> None:
    moved = {"server.conf": UPLOAD["nginx.conf"], "app.py": UPLOAD["app.py"]}
    assert differences(UPLOAD, moved, VALUES, VALUES) == []


def test_an_edited_block_of_a_judged_group_is_reported_with_the_other_sites() -> None:
    after = {**VAT, "a.py": VAT["a.py"].replace("n / 5", "n / 6")}
    [problem] = differences(VAT, after, JUDGED, JUDGED)
    assert problem.startswith("a.py:1 It has changed since it was last reviewed")
    assert "b.py:1" in problem


def test_reindenting_a_block_of_a_judged_group_is_not_a_difference() -> None:
    after = {**VAT, "a.py": VAT["a.py"].replace("    return", "        return")}
    assert differences(VAT, after, JUDGED, JUDGED) == []


def test_an_edited_block_of_a_set_or_text_group_is_left_to_the_relations() -> None:
    after = {**VAT, "a.py": VAT["a.py"].replace("n / 5", "n / 6")}
    for op in ("same-set", "same-text"):
        compared = JUDGED.replace("same-as", op)
        assert differences(VAT, after, compared, compared) == []


def test_a_file_a_set_or_text_group_names_is_not_recorded() -> None:
    for op in ("same-set", "same-text"):
        text = JUDGED.replace('"invoice same-as cart"', f'"invoice {op} ./vat.txt"')
        now = current(sites({"a.py": VAT["a.py"]}), registry(text), {"vat.txt": Content("5")})
        assert [site.site.name for site in now["vat"].sites] == ["COUPLED:vat: invoice"]


def test_an_edited_file_a_judged_group_names_is_reported() -> None:
    text = JUDGED.replace('"invoice same-as cart"', '"invoice same-shape ./schema.json"')
    group = {"a.py": VAT["a.py"]}
    first = current(sites(group), registry(text), {"schema.json": Content("{}")})
    old = reviewed({}, first, ["vat"])
    now = current(sites(group), registry(text), {"schema.json": Content('{"a": 1}')})
    [problem] = compare(old, now, REGISTRY)
    assert problem.where == "./schema.json"


def test_a_group_never_reviewed_is_reported_at_its_table() -> None:
    now = current(sites(UPLOAD), registry(VALUES), {})
    [problem] = compare({}, now, REGISTRY)
    assert problem.where == 'coupled-registry.toml ["COUPLED:upload-limit:"]'
    assert "hasn't been reviewed" in problem.message


def test_a_reviewed_group_whose_table_is_gone_is_reported() -> None:
    old = reviewed({}, current(sites(UPLOAD), registry(VALUES), {}), ["upload-limit"])
    [problem] = compare(old, {}, REGISTRY)
    assert "which has no table now" in problem.message


def test_recording_one_group_keeps_what_the_others_recorded() -> None:
    both = registry(VALUES + JUDGED.replace("version = 1\n", ""))
    now = current(sites({**UPLOAD, **VAT}), both, {})
    first = reviewed({}, now, ["vat"])
    assert list(first) == ["vat"]
    assert sorted(reviewed(first, now, ["upload-limit"])) == ["upload-limit", "vat"]


def test_a_message_about_a_value_group_gives_each_site_s_value_now() -> None:
    now = current(sites(UPLOAD), registry(VALUES), {})
    [problem] = compare({}, now, REGISTRY)
    assert "nginx.conf:1 `10m`" in problem.message and "app.py:1 `8`" in problem.message
    assert problem.message.endswith("rerun with --update upload-limit to record it")
