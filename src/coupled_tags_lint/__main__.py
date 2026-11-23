"""The entrypoints: the coupled-tags-lint command, and the coupled-tags-hook Claude Code hook.

Each imports only what it wires, as the hook runs on every file Claude reads."""

import sys


def main() -> None:
    from coupled_tags_lint.adapters.driven.files import LocalFiles
    from coupled_tags_lint.adapters.driven.search import GrepSearch
    from coupled_tags_lint.adapters.driven.settings import LocalSettings
    from coupled_tags_lint.adapters.driving.cli import run
    from coupled_tags_lint.orchestrators.lint import Lint

    sys.exit(run(Lint(GrepSearch(), LocalFiles(), LocalSettings()), sys.argv[1:]))


def hook() -> None:
    from coupled_tags_lint.adapters.driven.files import LocalFiles
    from coupled_tags_lint.adapters.driven.search import GrepSearch
    from coupled_tags_lint.adapters.driven.session import SessionMarks
    from coupled_tags_lint.adapters.driven.settings import LocalSettings
    from coupled_tags_lint.adapters.driving.hook import run
    from coupled_tags_lint.orchestrators.hook import Hook

    wired = Hook(GrepSearch(), LocalFiles(), LocalSettings(), SessionMarks())
    sys.exit(run(wired, sys.stdin.read()))


if __name__ == "__main__":
    main()
