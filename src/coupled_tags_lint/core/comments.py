"""The comment syntaxes markers are written in: which one a file uses, and its code outside them.

A file's syntax comes from its name: its extension, or the whole name where it has none, such
as `Dockerfile`. A file of a kind not listed here takes every common comment, which can read
code as a comment, such as a shell command's `--flag`, so a language whose tokens clash with
other languages' code, such as `%` or `(*`, is found only by its own files. The tokens follow
each language's own documentation, cross-checked against PLDB's comment features
(https://pldb.io/features/hasLineComments.html).
"""

import re
from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True)
class Syntax:
    """A language's comments: the openers of comments that end with their line, and each block
    comment's opener with its closer."""

    line: tuple[str, ...]
    block: tuple[tuple[str, str], ...]


_C_BLOCK = ("/*", "*/")
_HTML_BLOCK = ("<!--", "-->")

_HASH = Syntax(("#",), ())
_C = Syntax(("//",), (_C_BLOCK,))
_CSS = Syntax((), (_C_BLOCK,))
_HASH_AND_C = Syntax(("#", "//"), (_C_BLOCK,))
_NIX = Syntax(("#",), (_C_BLOCK,))
_POWERSHELL = Syntax(("#",), (("<#", "#>"),))
_SQL = Syntax(("--",), (_C_BLOCK,))
_DASHES = Syntax(("--",), ())
_HASKELL = Syntax(("--",), (("{-", "-}"),))
_OCAML = Syntax((), (("(*", "*)"),))
_PASCAL = Syntax(("//",), (("(*", "*)"),))
_PERCENT = Syntax(("%",), ())
_SEMICOLON = Syntax((";",), ())
_INI = Syntax((";", "#"), ())
_APOSTROPHE = Syntax(("'",), ())
_BANG = Syntax(("!",), ())
_MARKUP = Syntax((), (_HTML_BLOCK,))
_TEMPLATE = Syntax((), (("{#", "#}"), _HTML_BLOCK))
_NONE = Syntax((), ())
_UNKNOWN = Syntax(("#", "//", ";", "--"), (_C_BLOCK, _HTML_BLOCK, ("{#", "#}")))


def _each(syntax: Syntax, names: str) -> dict[str, Syntax]:
    return dict.fromkeys(names.split(), syntax)


# Each file extension, lowercase and without its `.`, with its syntax.
_EXTENSIONS = (
    _each(
        _HASH,
        "py pyi pyw sh bash zsh fish ksh rb rake gemspec pl pm r yml yaml toml conf ex exs jl "
        "cmake nim cr graphql gql tcl awk mk dockerfile coffee properties",
    )
    | _each(
        _C,
        "c h cc cpp cxx hh hpp hxx mm cs java js mjs cjs jsx ts mts cts tsx go rs kt kts swift "
        "scala sc dart groovy gradle proto zig jsonc json5 scss sass less styl sol",
    )
    | _each(_CSS, "css")
    | _each(_HASH_AND_C, "php phtml tf hcl")
    | _each(_NIX, "nix")
    | _each(_POWERSHELL, "ps1 psm1 psd1")
    | _each(_SQL, "sql")
    | _each(_DASHES, "lua adb ads")
    | _each(_HASKELL, "hs elm purs")
    | _each(_OCAML, "ml mli")
    | _each(_PASCAL, "fs fsi fsx pas dpr")
    | _each(_PERCENT, "erl hrl tex sty ltx bib")
    | _each(_SEMICOLON, "lisp lsp el clj cljs cljc edn scm ss rkt asm")
    | _each(_INI, "ini cfg npmrc gitconfig")
    | _each(_APOSTROPHE, "vb vbs bas")
    | _each(_BANG, "f90 f95 f03 f08")
    | _each(
        _MARKUP,
        "md markdown html htm xhtml xml svg xsd xsl xslt plist csproj fsproj vbproj props targets",
    )
    | _each(_TEMPLATE, "j2 jinja jinja2 twig njk")
    | _each(_NONE, "json")
)

# Each file name with no extension to go by, lowercase, with its syntax.
_NAMES = _each(
    _HASH,
    "dockerfile containerfile makefile gnumakefile justfile vagrantfile gemfile rakefile "
    "brewfile procfile .env .gitignore .dockerignore .gitattributes .bashrc .zshrc .profile",
) | _each(_INI, ".editorconfig .gitconfig")

# The starts of file names whose rest varies, such as `Dockerfile.prod`, with their syntax.
_PREFIXES = _each(_HASH, "dockerfile. containerfile. .env.")

# Every block comment's closer, in any syntax: a marker's label ends before one.
CLOSERS = tuple(
    sorted(
        {
            closer
            for syntax in (*_EXTENSIONS.values(), *_NAMES.values(), _UNKNOWN)
            for _, closer in syntax.block
        }
    )
)


def syntax_of(path: str) -> Syntax:
    """The comment syntax of the file at path, by its name."""
    name = path.rsplit("/", 1)[-1].lower()
    if name in _NAMES:
        return _NAMES[name]
    for prefix, syntax in _PREFIXES.items():
        if name.startswith(prefix):
            return syntax
    stem, dot, extension = name[1:].rpartition(".")
    if dot and stem:
        return _EXTENSIONS.get(extension, _UNKNOWN)
    return _UNKNOWN


def strip_comment(text: str, syntax: Syntax) -> str:
    """text up to the comment in it."""
    match = _opener(syntax).search(text)
    return text if match is None else text[: match.start()]


def is_comment_line(line: str, syntax: Syntax) -> bool:
    """Whether line holds only a comment."""
    return _comment_line(syntax).match(line) is not None


def _openers(syntax: Syntax) -> str:
    """A pattern for any of syntax's comment openers, the longest first."""
    openers = sorted({*syntax.line, *(opener for opener, _ in syntax.block)}, key=len, reverse=True)
    return "|".join(re.escape(opener) for opener in openers) or "(?!)"


def _docblock(syntax: Syntax) -> str:
    """A pattern for the `*` starting a docblock's line, where syntax has `/* */` comments."""
    return r"|^\s*\*" if _C_BLOCK in syntax.block else ""


def _opener(syntax: Syntax) -> re.Pattern[str]:
    """A comment's opener: anywhere after whitespace, or `*` starting a docblock line."""
    return re.compile(rf"(?:^|(?<=\s))(?:{_openers(syntax)}){_docblock(syntax)}")


def _comment_line(syntax: Syntax) -> re.Pattern[str]:
    return re.compile(rf"^\s*(?:{_openers(syntax)}){_docblock(syntax)}")
