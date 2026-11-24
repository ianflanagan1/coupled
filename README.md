# coupled

Checks the COUPLED groups in a repository: values or code in several places that must change together but can't share a single source of truth. Each place carries a marker, `COUPLED:<key>: <label>`, and the repository's registry, `coupled-registry.toml`, describes each group: how its sites relate, and the files in it that can't hold a marker. The lint checks that markers and registry agree, that the relations between values hold, and that no group has changed since it was last reviewed. It also gives Claude Code two hooks that show Claude a group before it edits one of its sites. The convention, and the Claude Code skill that goes with it, are in [coupled-tags](https://github.com/ianflanagan1/coupled-tags).

```
$ coupled
⚠️ 1 problem in COUPLED groups.
nginx.conf:1 `proxy >= app` doesn't hold with app.py:1: 10m >= 12
```

Runs on macOS and Linux. Built on [cli-kit](https://github.com/ianflanagan1/cli-kit).

## Markers and the registry

```nginx
client_max_body_size 10m;  # COUPLED:upload-limit: proxy
```
```python
MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app
```
```toml
# coupled-registry.toml
version = 1

["COUPLED:upload-limit:"]
relations = ["proxy >= app", "proxy = ./limits.json#/upload_mb"]
```

A marker's key names its group; its label names this site within the group. A key and a label are lowercase letters and digits, in words joined by single hyphens, and the space between them is part of the form: what to search for to find a group is `COUPLED:<key>:`, which finds each of its sites and its table in the registry, as the table is named the same way. Prose goes before `COUPLED:`, or after the label and a `.`: `COUPLED:upload-limit: proxy. Larger bodies get a 413.`

A marker describes the code before its comment on its line, or for a marker on a comment line, the first line of code after it, past any other comment lines but not a blank line. The lint tells comments from code by the file's own comment syntax, which it knows by the file's extension or name, such as `%` in Erlang and `(* *)` in OCaml; a file of a kind it doesn't know takes the common ones, `#`, `//`, `;`, `--`, `/* */`, `<!-- -->` and `{# #}`. `COUPLED:<key>:END`, in a comment after the last line of a block, closes the nearest marker of its key above it, so that it describes every line down to the END. Blocks of different keys can nest but not overlap.

A file whose `COUPLED:` text is all examples, such as the coupled-tags skill copied into a repository's `.claude/skills/`, says so with `COUPLED:IGNORE-FILE` on a line of its own, alone or alone in a comment, such as `<!-- COUPLED:IGNORE-FILE -->`. The lint and the hooks then skip the whole file, wherever it is, with no setting. Written inside a line, as here, it's only a mention. Use it for a file that travels between repositories; for paths of one repository's own, such as test fixtures, use `exclude`.

Each group has a table in the registry, named `["COUPLED:<key>:"]`:

- `relations`: each `<ref> <op> <ref> [<arith> <number>]`, the first ref's value by op the second's through the formula; or a bare op, `=`, `same-as` or `same-shape`, alone, when every site and file of the group is the same. A ref is a site, by its label, or a file that can't hold a marker: `./<path>[?][#<pointer>]` in this repository or `//<git-host>/<owner>/<name>/<path>[?][#<pointer>]` in another, with a JSON Pointer to the value in it, and `?` when it's only sometimes there, such as an untracked `.env`.
- `files`: files in a group whose relation is a bare op, which no relation names.
- `select`: a regex for a site, by its label, picking its value out of its line when the lint can't, with the value in its one capture group: `select = { url = ':(\d+)$' }`.
- `why`: why the sites must change together, which the lint shows when a relation fails and the hooks show beside the group: `why = "nginx rejects a larger body before the app sees it"`. Rewording it needs no review.

Ops are of two kinds, and a group uses one. Value ops, `=`, `!=`, `<`, `<=`, `>`, `>=`, compare single values, and the lint checks them. Structural ops, `same-as` (duplicated code), `same-shape` (types and schemas with the same fields), `subset-of` and `superset-of`, relate code or structure, which the lint records but doesn't compare.

A group may be all files, such as `.nvmrc` and `.tool-versions`, and need no marker. A group in two repositories names the other's files with `//`; each repository's registry describes its own side.

## What it reports

- **markers:** a key or label not in lowercase words joined by hyphens, a marker with no label, prose straight after a label with no `.` between, a tag in the old bracket form, and a marker with no line of code after it
- **block ends:** an END with no marker of its key above it to close, a block holding another of its own key, blocks that overlap, and an END after a marker of a group using value ops
- **the registry:** none when there are markers, one that isn't TOML or has no `version = 1`, a table not named `["COUPLED:<key>:"]`, a field it doesn't know, and a relation, file or selector it can't read
- **groups:** a key with no table, a label no marker has or two markers share, a group with fewer than two sites and files, one mixing value and structural ops, a bare op beside other relations, two relations between the same sites, a site relating to itself, a formula or selector in a group of structural ops, a formula multiplying or dividing by 0, and a site or file nothing relates
- **files:** a file in this repository that isn't there, unless it's marked optional, and one that holds a marker of the group, which should be named by its label
- **values**, in groups using value ops: a site or file whose value it can't read, and a relation that doesn't hold, with the values it compared, and a reminder to change the values rather than the relation unless what must hold has changed
- **the reviewed section:** a group that differs from what it records, with each site's current value in a group using value ops (see [The reviewed section](#the-reviewed-section)), and a key given to `--update` that has no group
- **the message:** a marker without the message after its label when the [settings](#settings) turn it on, or with one when they don't
- **unreadable files:** a file holding `COUPLED:` that isn't UTF-8

The lint reads a site's value from the line its marker describes: the one quoted or backticked literal on it, else an image's version (`FROM node:24.22.1-alpine`), else the right-hand side of an assignment, else a directive's value (`client_max_body_size 10m;`), or what its selector picks out. A file gives its value at its pointer, or if it's one line, that line. Versions match on the parts both give, so `24` and `24.22.1` are `=`; numbers compare numerically, ignoring a unit suffix such as `m` in `10m`; anything else compares as text, by `=` and `!=` only.

The lint doesn't read other repositories, since which revision to compare against, and how to reach it, depend on how the two are released. It names them in its status line as not checked.

## The reviewed section

Relations between values are checked on every run, but structural ops can't be, and a group can lose a site without any relation failing. So `--update <key>` writes, below the groups in the registry, each group it names as it was last reviewed:

- a fingerprint of its table
- each of its sites, by its marker (`"COUPLED:upload-limit: proxy"`)
- in a group using value ops, the unit on each value, since numbers are compared without their units
- in a group using structural ops, a fingerprint of each site's block, and of each file in this repository the group names

The lint fails when the code differs: a table changed, a site added or removed, a unit changed, or a structural block or named file edited. It names the group's other sites. Read them, change them together so the group holds, then rerun with `--update <key>` to record it, naming each group you've reviewed, so recording is never a blanket step; commit the registry with the change, so its diff shows the group was touched. Values themselves aren't recorded: changing one is checked by its relations. Neither is where a site is, so moving a marked line to another file isn't a change.

A block's fingerprint ignores indentation, blank lines, and the markers and ENDs of blocks nested inside it, so reindenting a block or rewording a marker inside it isn't a change. Sites under an excluded path aren't recorded.

It does **not** look at diffs. Diff-aware enforcement in the style of Google's `LINT.IfChange` is out of scope; the reviewed section gives the same effect from the code alone.

## Usage

```sh
coupled            # check the current directory
coupled -l         # also list every key and its sites
coupled -x docs/   # exclude a path prefix, besides the settings file's (repeatable)
coupled --fix      # write or drop the message after each label, as the settings say, then check
coupled --update upload-limit   # record a group you've reviewed, then check (repeatable)
```

In a git work tree it scans tracked files plus untracked files that aren't ignored. Elsewhere it uses `grep --recursive`, skipping `.git`, `node_modules` and `vendor`. It ends with one status line: `➖` and exit status 0 when clean, `⚠️` and the problems, one per line, with exit status 1 when it finds any. A usage error exits with 2.

## Settings

A repository sets the paths to exclude on every run, where its registry is, and whether markers carry a message, in `.config/coupled.toml`, committed with its code:

```toml
#:schema https://raw.githubusercontent.com/ianflanagan1/coupled/main/schema/coupled.v1.json
version = 1
exclude = ["docs", "tests/fixtures"]
registry-file = ".config/coupled.toml"
tag-relations = true
tag-pointer = true
```

- `version`: the version of the file's format, which is 1.
- `exclude`: path prefixes, relative to the directory scanned, whose markers aren't checked, such as examples and test fixtures. None by default.
- `registry-file`: the registry's path, relative to the directory scanned and inside it, so not absolute and with no `..`. `coupled-registry.toml` by default. The lint doesn't move a registry: when you change this, move the file too.
- `tag-relations` and `tag-pointer`: what follows each marker's label, each `false` by default. `tag-relations` gives the site's own relations as seen from it, so any reader, a person in an editor among them, sees what must hold without opening the registry. `tag-pointer` says what to search for and which file describes the group, for a reader who doesn't know the convention, such as an AI agent without the coupled-tags skill or its hooks; a reader who knows it can do without. With both on, the relations come first. A site no relation names gets no relations. `--fix` writes the message from the registry, or drops it when both are off, and the lint reports one that differs from what `--fix` would write, so it's never stale:

  ```python
  MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app. Must be <= proxy.
  MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app. Change only with every "COUPLED:upload-limit:" site, per coupled-registry.toml.
  MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app. Must be <= proxy. Change only with every "COUPLED:upload-limit:" site, per coupled-registry.toml.
  ```

The file is optional. The lint reads the copy on disk in the directory it scans, so a branch that adds fixtures can exclude them in the same change. A file that isn't valid TOML, has no `version` or one the lint doesn't read, holds a setting it doesn't know, or names a registry outside the repository stops the run with `⚠️` and exit status 1, before anything is changed. It's read with [repo-settings](https://github.com/ianflanagan1/repo-settings), and its schema is in `schema/`.

## The Claude Code hooks

`coupled-hook` is a Claude Code hook, for two events:

- **the gate**, as `PreToolUse` on `Write|Edit|MultiEdit`: the first call in a session that changes a marked line, the line a marker describes, or a line of a marked block, is denied, with each touched group's sites and table as the reason. Claude reads them, changes the group together, and retries.
- **the context hook**, as `PostToolUse` on `Read`: when Claude reads a file holding markers, the hook adds each group's sites and table to Claude's context.

A group either hook shows isn't shown again in the session, so the gate rarely fires on a file Claude has read. Files the repository's settings exclude, files holding `COUPLED:IGNORE-FILE`, and the registry, are left alone. Neither sees edits or reads made through Bash, which is why markers name their key in a form a search finds. If the hook fails, it tells the user and lets the call go ahead. A read of a file with no markers costs about 45 ms.

```json
{
  "hooks": {
    "PreToolUse": [{ "matcher": "Write|Edit|MultiEdit", "hooks": [{ "type": "command", "command": "\"$HOME/projects/cli/coupled/.venv/bin/coupled-hook\"" }] }],
    "PostToolUse": [{ "matcher": "Read", "hooks": [{ "type": "command", "command": "\"$HOME/projects/cli/coupled/.venv/bin/coupled-hook\"" }] }]
  }
}
```

## Adding it to a project

This repository is a Nix flake that packages the lint as the `coupled` command, with the Python, `tomlkit`, `git` and `grep` it uses pinned, so it behaves the same on macOS, Linux and CI. Add a release of it to a project's devbox:

```sh
devbox add github:ianflanagan1/coupled/v0.2.0#coupled
```

Then run `coupled` in the project's check, as a step of its Taskfile `check` task, so CI runs it too, and commit the registry.

To move to a new release, change the tag in `devbox.json` and run `devbox update`. Without devbox, `nix run github:ianflanagan1/coupled` runs it once.

## Reviewing changes to the registry

Every change to what's coupled reaches the registry. A site added, removed or relabelled, a group's table edited, a structural block changed, or a file holding sites excluded in the settings or marked `COUPLED:IGNORE-FILE`, fails the lint until `--update` records it there. So agents can edit coupled code and pass the build, while a person still reviews each change to the coupling itself, by requiring review of the registry before merging, and letting every other change merge once CI passes.

The lint can't do this on its own: anything that passes the build, an agent can write, `--update` included. The review is enforced where changes merge. On GitHub:

1. Give the registry an owner in `.github/CODEOWNERS`, along with the files that could switch the check off:

   ```
   /coupled-registry.toml @<owner>
   /.config/coupled.toml  @<owner>
   /Taskfile.yml               @<owner>
   /devbox.json                @<owner>
   /.github/workflows/         @<owner>
   /.github/CODEOWNERS         @<owner>
   ```

   The settings can move the registry and exclude paths, the Taskfile and workflows run the lint, `devbox.json` pins its version, and `CODEOWNERS` holds the rule. Write the registry's path as `registry-file` gives it; [examples/demo](examples/demo) makes the two a COUPLED group, so they can't drift apart.

2. Protect the default branch with a ruleset: require a pull request with 0 approvals and review from code owners, and require the CI check that runs the lint. A pull request touching none of the owned files then merges once CI passes, by auto-merge if it's on; one touching any of them waits for an owner's approval.

3. Let agents push under their own account or GitHub App, with write access to contents and pull requests but no admin rights and no place on the ruleset's bypass list. No one can approve their own pull request, so an agent pushing as you would leave your approval impossible.

GitHub reads `CODEOWNERS` from the pull request's base branch, so a pull request that removes an owner still needs that owner's review. A pull request that drops the lint from CI has to change a workflow, the Taskfile or `devbox.json`, so it needs review too.

## Installing it for yourself

```sh
cd ~/projects/cli/coupled
devbox run -- task setup   # uv sync, then link coupled into ~/.local/bin
```

`task setup` also puts `coupled-hook` in `.venv/bin`, where the hooks above run it from.

## Development

```sh
devbox run -- task test        # pytest
devbox run -- task lint        # ruff check and format
devbox run -- task check       # lint, test, then build the flake and lint this repository's markers
devbox run -- task copy-demo   # copy examples/demo into a new git repository, and print its path
```

`examples/demo` is a small project using every form of marker and relation, in several comment syntaxes. Try the lint and the hooks on the copy `task copy-demo` makes: in place, the demo is inside this repository, whose settings exclude it.

`src/coupled/core/` finds markers, parses the registry and its relations, reads values and blocks, checks groups, writes the message after a label, compares groups with the reviewed section, and decides what the hooks show, as pure functions. `orchestrators/lint.py` gathers the files holding markers, the registry, the files it names and the settings through its ports, and writes the fixed markers and the reviewed section; `orchestrators/hook.py` gathers a group's sites and table for the hooks. `adapters/` holds git grep, the file system, the settings file, the session's shown groups, the command line and the hook's JSON; `__main__.py` wires them.

To release, raise `version` in `pyproject.toml`, commit, then run `github release . patch|minor|major`. Projects move to it by changing their tag.
