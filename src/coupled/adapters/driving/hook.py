"""The coupled-hook command: a Claude Code hook, reading the hook's event as JSON on stdin.

Registered as PreToolUse on Write|Edit|MultiEdit, it's the gate: it denies the first call in a
session that changes a line a COUPLED marker covers, giving the group's sites and table as the
reason. Registered as PostToolUse on Read, it adds the groups in the file read to Claude's
context. Anything else passes silently. If it fails, it says so to the user and lets the call
go ahead, rather than blocking every edit.

It doesn't see edits or reads made through Bash.
"""

import json
import os

from coupled.core.hook import Change, Replace, Rewrite
from coupled.orchestrators.hook import Hook

_EDITS = ("Edit", "MultiEdit", "Write")


def run(hook: Hook, event_text: str) -> int:
    try:
        output = _handle(hook, event_text)
    except Exception as error:  # The catch-all for the hook's one invocation.
        output = {
            "systemMessage": (
                f"The coupled hook failed, so it didn't check this call for COUPLED "
                f"groups: {error!r}"
            )
        }
    if output is not None:
        print(json.dumps(output))
    return 0


def _handle(hook: Hook, event_text: str) -> dict[str, object] | None:
    event = json.loads(event_text)
    if not isinstance(event, dict):
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict) or not tool_input.get("file_path"):
        return None
    path = os.path.abspath(str(tool_input["file_path"]))
    session = str(event.get("session_id", ""))
    name, tool = event.get("hook_event_name"), event.get("tool_name")
    if name == "PreToolUse" and tool in _EDITS:
        reason = hook.gate(session, path, _changes(str(tool), tool_input))
        if reason is None:
            return None
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    if name == "PostToolUse" and tool == "Read":
        text = hook.context(session, path)
        if text is None:
            return None
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
    return None


def _changes(tool: str, tool_input: dict[str, object]) -> list[Change]:
    if tool == "Write":
        return [Rewrite(str(tool_input.get("content", "")))]
    edits = tool_input.get("edits") if tool == "MultiEdit" else [tool_input]
    if not isinstance(edits, list):
        return []
    return [
        Replace(str(edit.get("old_string", "")), bool(edit.get("replace_all")))
        for edit in edits
        if isinstance(edit, dict)
    ]
