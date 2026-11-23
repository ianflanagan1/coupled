from coupled_tags_lint.core.lock import LOCK_FILE
from coupled_tags_lint.core.settings import Invalid, Read, Settings, Version, settings

WHERE = ".config/ianf-coupled-tags.toml"


NOT_A_LOCK = Invalid(f"lock-file in {WHERE} must be the path of a file inside the repository.", ())


def read(table: dict[str, object]) -> Read:
    return Read(Version.V1, table, WHERE)


def test_a_repository_with_no_settings_file_excludes_nothing() -> None:
    assert settings(None) == Settings([], LOCK_FILE)


def test_a_file_that_sets_nothing_excludes_nothing() -> None:
    assert settings(read({})) == Settings([], LOCK_FILE)


def test_the_paths_under_exclude_are_the_excludes() -> None:
    found = settings(read({"exclude": ["README.md", "tests"]}))
    assert found == Settings(["README.md", "tests"], LOCK_FILE)


def test_a_trailing_slash_on_an_excluded_path_is_dropped() -> None:
    assert settings(read({"exclude": ["docs/"]})) == Settings(["docs"], LOCK_FILE)


def test_a_file_that_cannot_be_read_stays_invalid() -> None:
    invalid = Invalid("No version in " + WHERE + ".", ("Add version = 1.",))
    assert settings(invalid) == invalid


def test_a_setting_the_lint_does_not_know_is_invalid() -> None:
    found = settings(read({"exclude": [], "skip": [], "also": 1}))
    assert found == Invalid(f"Unknown settings in {WHERE}: also, skip.", ())


def test_an_exclude_that_is_not_a_list_is_invalid() -> None:
    found = settings(read({"exclude": "tests"}))
    assert found == Invalid(f"exclude in {WHERE} must be a list of paths.", ())


def test_an_excluded_path_that_is_not_text_is_invalid() -> None:
    found = settings(read({"exclude": ["tests", 3]}))
    assert found == Invalid(f"exclude in {WHERE} must be a list of paths.", ())


def test_an_empty_excluded_path_is_invalid() -> None:
    found = settings(read({"exclude": [""]}))
    assert found == Invalid(f"exclude in {WHERE} must be a list of paths.", ())


def test_a_file_that_names_no_lock_uses_the_lock_at_the_root() -> None:
    assert settings(read({"exclude": ["docs"]})) == Settings(["docs"], ".coupled-tags.lock")


def test_the_path_under_lock_is_the_lock_file() -> None:
    found = settings(read({"lock-file": ".config/coupled-tags.lock"}))
    assert found == Settings([], ".config/coupled-tags.lock")


def test_a_lock_that_is_not_text_is_invalid() -> None:
    assert settings(read({"lock-file": 3})) == NOT_A_LOCK


def test_an_empty_lock_is_invalid() -> None:
    assert settings(read({"lock-file": ""})) == NOT_A_LOCK


def test_a_lock_given_by_an_absolute_path_is_invalid() -> None:
    assert settings(read({"lock-file": "/tmp/coupled-tags.lock"})) == NOT_A_LOCK


def test_a_lock_outside_the_repository_is_invalid() -> None:
    assert settings(read({"lock-file": "../coupled-tags.lock"})) == NOT_A_LOCK
    assert settings(read({"lock-file": "locks/../../coupled-tags.lock"})) == NOT_A_LOCK


def test_a_lock_that_names_a_directory_is_invalid() -> None:
    assert settings(read({"lock-file": "locks/"})) == NOT_A_LOCK
