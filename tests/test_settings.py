from coupled.core.settings import (
    REGISTRY_FILE,
    Invalid,
    Read,
    Settings,
    TagMessage,
    Version,
    settings,
)

WHERE = ".config/coupled.toml"
OFF = TagMessage(pointer=False, relations=False)


NOT_A_REGISTRY = Invalid(
    f"registry-file in {WHERE} must be the path of a file inside the repository.", ()
)


def read(table: dict[str, object]) -> Read:
    return Read(Version.V1, table, WHERE)


def test_a_repository_with_no_settings_file_excludes_nothing() -> None:
    assert settings(None) == Settings([], REGISTRY_FILE, OFF)


def test_a_file_that_sets_nothing_excludes_nothing() -> None:
    assert settings(read({})) == Settings([], REGISTRY_FILE, OFF)


def test_the_paths_under_exclude_are_the_excludes() -> None:
    found = settings(read({"exclude": ["README.md", "tests"]}))
    assert found == Settings(["README.md", "tests"], REGISTRY_FILE, OFF)


def test_a_trailing_slash_on_an_excluded_path_is_dropped() -> None:
    assert settings(read({"exclude": ["docs/"]})) == Settings(["docs"], REGISTRY_FILE, OFF)


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


def test_a_file_that_names_no_registry_uses_the_registry_at_the_root() -> None:
    found = settings(read({"exclude": ["docs"]}))
    assert found == Settings(["docs"], "coupled-registry.toml", OFF)


def test_the_path_under_registry_is_the_registry() -> None:
    found = settings(read({"registry-file": ".config/coupled-registry.toml"}))
    assert found == Settings([], ".config/coupled-registry.toml", OFF)


def test_a_registry_that_is_not_text_is_invalid() -> None:
    assert settings(read({"registry-file": 3})) == NOT_A_REGISTRY


def test_an_empty_registry_is_invalid() -> None:
    assert settings(read({"registry-file": ""})) == NOT_A_REGISTRY


def test_a_registry_given_by_an_absolute_path_is_invalid() -> None:
    assert settings(read({"registry-file": "/tmp/coupled.toml"})) == NOT_A_REGISTRY


def test_a_registry_outside_the_repository_is_invalid() -> None:
    assert settings(read({"registry-file": "../coupled.toml"})) == NOT_A_REGISTRY
    assert settings(read({"registry-file": "config/../../coupled.toml"})) == NOT_A_REGISTRY


def test_a_registry_that_names_a_directory_is_invalid() -> None:
    assert settings(read({"registry-file": "config/"})) == NOT_A_REGISTRY


def test_markers_show_relations_and_markers_point_to_registry_are_each_turned_on_on_their_own() -> (
    None
):
    for pointer in (False, True):
        for relations in (False, True):
            found = settings(
                read({"markers-point-to-registry": pointer, "markers-show-relations": relations})
            )
            wanted = TagMessage(pointer=pointer, relations=relations)
            assert found == Settings([], REGISTRY_FILE, wanted)


def test_a_marker_message_setting_that_is_not_true_or_false_is_invalid() -> None:
    for name in ("markers-point-to-registry", "markers-show-relations"):
        for written in ("yes", 1):
            found = settings(read({name: written}))
            assert found == Invalid(f"{name} in {WHERE} must be true or false.", ())
