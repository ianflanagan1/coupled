"""The registry's reviewed section: a record of each group as it was last reviewed, so that a
change the lint can't check by value fails until someone has reviewed the group and recorded it
again with --update.

It records each group's table by a fingerprint, and each of its sites by its marker, with the
unit on its value in a group of value ops, or a fingerprint of its block in a group of
structural ops, beside a fingerprint of each file in this repository the group names. So a table
changed, a site added or removed, a unit changed or a structural block edited all fail.
"""

import hashlib
from dataclasses import dataclass
from typing import assert_never, final

from coupled_tags_lint.core.check import (
    Content,
    FileRead,
    Missing,
    Problem,
    Site,
    is_value_group,
    labelled,
)
from coupled_tags_lint.core.markers import marker_text
from coupled_tags_lint.core.registry import Registry, Reviewed, ReviewedSite, table_name
from coupled_tags_lint.core.values import Value, json_at, read_value, unit_of

# How to update the reviewed section, as compare's messages end.
UPDATE = "rerun with --update"


@final
@dataclass(frozen=True)
class CurrentSite:
    """A site as it is now, at where (`path:line`, or a file's ref)."""

    where: str
    site: ReviewedSite


@final
@dataclass(frozen=True)
class CurrentGroup:
    definition: str
    sites: tuple[CurrentSite, ...]


def current(
    sites: list[Site], registry: Registry, files: dict[str, FileRead]
) -> dict[str, CurrentGroup]:
    """Each group in the registry as it is now, given each file in this repository that its
    groups refer to."""
    groups: dict[str, CurrentGroup] = {}
    for key, group in registry.groups.items():
        value_group = is_value_group(group)
        records: list[CurrentSite] = []
        for site, label in labelled(sites, key):
            unit = None
            block = None
            if not value_group:
                block = fingerprint(site.block)
            elif site.code is not None:
                reading = read_value(site.code, group.selector(label))
                if isinstance(reading, Value):
                    unit = unit_of(reading.text)
            records.append(
                CurrentSite(site.where, ReviewedSite(marker_text(key, label), unit, block))
            )
        if not value_group:
            for ref in group.file_refs():
                if ref.repo is not None:
                    continue
                file = files.get(ref.path)
                match file:
                    case Content(text):
                        reached = text if ref.pointer is None else json_at(text, ref.pointer)
                        block = fingerprint((reached or text).splitlines())
                        name = ref.unmarked().text()
                        records.append(CurrentSite(ref.text(), ReviewedSite(name, None, block)))
                    case Missing() | None:
                        pass  # Reported by check, unless it's optional.
                    case _:
                        assert_never(file)
        groups[key] = CurrentGroup(group.definition, tuple(records))
    return groups


def fingerprint(lines: list[str] | tuple[str, ...]) -> str:
    """A short hash of lines, ignoring indentation and blank lines."""
    text = "\n".join(line.strip() for line in lines if line.strip())
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def reviewed(now: dict[str, CurrentGroup]) -> dict[str, Reviewed]:
    """The reviewed section recording the groups as they are now."""
    return {
        key: Reviewed(group.definition, tuple(site.site for site in group.sites))
        for key, group in now.items()
    }


def compare(
    old: dict[str, Reviewed], now: dict[str, CurrentGroup], registry_file: str
) -> list[Problem]:
    """The differences between the reviewed section and the groups as they are now, each saying
    what to do."""
    problems: list[Problem] = []
    for key in sorted(set(old) | set(now)):
        table = f"{registry_file} {table_name(key)}"
        if key not in now:
            problems.append(
                Problem(
                    registry_file,
                    f"The reviewed section records COUPLED:{key}:, which has no table now. If "
                    f"removing it was intended, {UPDATE}",
                )
            )
            continue
        group = now[key]
        if key not in old:
            problems.append(
                Problem(
                    table,
                    f"COUPLED:{key}: hasn't been reviewed. Check that its group holds, then "
                    f"{UPDATE} to record it",
                )
            )
            continue
        if group.definition != old[key].definition:
            problems.append(
                Problem(
                    table,
                    f"The table of COUPLED:{key}: has changed since it was last reviewed. If "
                    f"every site and file holds as it's now written, {UPDATE}",
                )
            )
        problems += _compare_sites(key, old[key].sites, group.sites)
    return problems


def _compare_sites(
    key: str, then: tuple[ReviewedSite, ...], now: tuple[CurrentSite, ...]
) -> list[Problem]:
    problems: list[Problem] = []
    before = {site.name: site for site in then}
    names = [site.site.name for site in now]
    wheres = [site.where for site in now]
    for site in then:
        if site.name not in names:
            problems.append(
                Problem(
                    site.name,
                    f"This site of COUPLED:{key}: was reviewed, but it's gone. If removing it "
                    f"was intended, {UPDATE}",
                )
            )
    for site in now:
        old = before.get(site.site.name)
        if old is None:
            problems.append(
                Problem(
                    site.where,
                    f"This site of COUPLED:{key}: hasn't been reviewed. Check that its group "
                    f"holds, then {UPDATE}",
                )
            )
            continue
        if site.site.unit != old.unit:
            problems.append(
                Problem(
                    site.where,
                    f"Its unit has changed from {_unit(old.unit)} to {_unit(site.site.unit)} "
                    "since it was last reviewed. The lint compares numbers without their units, "
                    f"so convert this value, or the formulas of COUPLED:{key}:, to the old unit; "
                    f"or if the group holds in the new one, {UPDATE}",
                )
            )
        if site.site.block != old.block:
            others = [where for where in wheres if where != site.where]
            problems.append(
                Problem(
                    site.where,
                    f"It has changed since it was last reviewed. Read every site of "
                    f"COUPLED:{key}: ({', '.join(others) or 'none other here'}, and its table "
                    f"in the registry), change them together so the group holds, then {UPDATE}",
                )
            )
    return problems


def _unit(unit: str | None) -> str:
    return "none" if unit is None else f"`{unit}`"


def excluded(path: str, excludes: list[str]) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in excludes)
