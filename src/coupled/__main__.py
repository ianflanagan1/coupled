"""The entrypoints: the coupled command, and the coupled-hook Claude Code hook.

Each imports only what it wires, as the hook runs on every file Claude reads."""

import sys


def main() -> None:
    from coupled.adapters.driven.files import LocalFiles
    from coupled.adapters.driven.search import GrepSearch
    from coupled.adapters.driven.settings import LocalSettings
    from coupled.adapters.driving.cli import run
    from coupled.orchestrators.lint import Lint

    sys.exit(run(Lint(GrepSearch(), LocalFiles(), LocalSettings()), sys.argv[1:]))


def hook() -> None:
    from coupled.adapters.driven.files import LocalFiles
    from coupled.adapters.driven.search import GrepSearch
    from coupled.adapters.driven.session import SessionMarks
    from coupled.adapters.driven.settings import LocalSettings
    from coupled.adapters.driving.hook import run
    from coupled.orchestrators.hook import Hook

    wired = Hook(GrepSearch(), LocalFiles(), LocalSettings(), SessionMarks())
    sys.exit(run(wired, sys.stdin.read()))


if __name__ == "__main__":
    main()
