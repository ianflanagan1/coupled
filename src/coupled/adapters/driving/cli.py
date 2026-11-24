"""The coupled command line."""

import os
import re

from cli_kit import cli, outcome
from cli_kit.outcome import Done, NothingToDo, Precondition

from coupled.core.markers import NAME_PATTERN
from coupled.core.settings import REGISTRY_FILE, Invalid
from coupled.orchestrators.lint import Lint, Report

_PROG = "coupled"

_DESCRIPTION = f"""\
Check the COUPLED:<key>: <label> markers in a repository against its registry.

The registry, {REGISTRY_FILE} at <dir> by default, holds a table for each group,
["COUPLED:<key>:"], whose relations relate its sites, by their labels, and the
files that can't hold a marker. Reports malformed markers, a marker whose key
has no table, labels that no marker or more than one has, files that aren't
there, and sites and files nothing relates. In groups whose ops compare values
(= != < <= > >=), sets of names (same-set subset-of superset-of) or text
(same-text), it reports sites that can't be read and relations that don't hold.
Files in other repositories aren't checked, and the status line lists their
repositories.

It also compares the groups with the registry's reviewed section, which records
each group's table, the unit on each value, and a fingerprint of each block that
an op it can't compare relates (same-as same-shape description-of described-by).
A table changed, a site added or removed, a unit changed or such a block edited
is reported until the group is reviewed and recorded with --update <key>, which
names each group it records.

<dir>/.config/coupled.toml, if it's there, sets beside version = 1 the
path prefixes to exclude on every run, as exclude = ["docs", "tests"], the
registry, as registry-file = ".config/coupled-registry.toml", and what
follows each marker's label: markers-show-relations = true for the site's
own relations, and markers-point-to-registry = true for what to search for
and which file describes its group. Both are off by default. --fix writes
the message.

Exit status: 0 clean, 1 problems found, 2 usage error."""


def run(lint: Lint, argv: list[str]) -> int:
    parser = cli.ArgumentParser(prog=_PROG, description=_DESCRIPTION)
    parser.add_argument("-l", action="store_true", help="list every key and its sites")
    parser.add_argument(
        "-x",
        action="append",
        default=[],
        metavar="<path>",
        help="exclude a path prefix (relative to <dir>), besides the settings file's; repeatable",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="write or drop the message after each marker's label, as the settings say, then check",
    )
    parser.add_argument(
        "--update",
        action="append",
        default=[],
        metavar="<key>",
        help="record the group of <key> as it is now in the registry's reviewed section, "
        "once you've reviewed it, then check; repeatable",
    )
    parser.add_argument(
        "dir", nargs="?", default=".", metavar="<dir>", help="directory to scan (default: .)"
    )
    args = parser.parse_args(argv)

    if not os.path.isdir(args.dir):
        parser.error(f"{args.dir} isn't a directory")
    for key in args.update:
        if re.fullmatch(NAME_PATTERN, key) is None:
            parser.error(f"--update takes a group's key, such as upload-limit, not {key}")
    excludes = [path.rstrip("/") for path in args.x]
    return cli.finish(
        _PROG, lambda: _show(lint.run(args.dir, excludes, args.update, args.fix), args.l)
    )


def _show(report: Report | Invalid, list_keys: bool) -> Done | NothingToDo:
    if isinstance(report, Invalid):
        raise Precondition(report.message, *report.details)
    if list_keys:
        for key, wheres in report.keys:
            print(f"{key} ({len(wheres)})" + "".join("\n    " + where for where in wheres))
    changes = []
    if report.fixed:
        changes.append(f"Fixed markers in {', '.join(report.fixed)}.")
    if report.updated:
        changes.append(f"Updated {report.registry_file}.")
    if report.problems:
        for change in changes:
            outcome.changed(change)
        raise Precondition(
            f"{_count(len(report.problems), 'problem')} in COUPLED groups.",
            *(f"{problem.where} {problem.message}" for problem in report.problems),
        )
    if report.keys:
        summary = f"No problems in {_count(len(report.keys), 'COUPLED key')}."
    else:
        summary = "No COUPLED markers."
    if report.unchecked:
        summary += f" Not checked, as they're other repositories: {', '.join(report.unchecked)}."
    if changes:
        return Done(" ".join(changes), summary)
    return NothingToDo(summary)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"
