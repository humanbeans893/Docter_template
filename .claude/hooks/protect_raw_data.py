#!/usr/bin/env python3
"""PreToolUse hook: block file modifications under projects/<study>/data/raw/.

Raw data is immutable (AGENTS.md > Data). Exit code 2 blocks the tool
call and feeds the stderr message back to the agent. Bash-level writes (shell
redirects) are not intercepted here — that stays covered by convention and the
permission deny rules in .claude/settings.json.
"""

import json
import re
import sys

RAW_PATTERN = re.compile(r"(^|/)projects/[^/]+/data/raw(/|$)")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # malformed input: never block unrelated tool calls
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if path and RAW_PATTERN.search(str(path).replace("\\", "/")):
        print(
            f"BLOCKED: '{path}' is inside a data/raw/ directory. Raw data is "
            "immutable (AGENTS.md > Data). Write derived outputs to "
            "data/interim/ or data/processed/ from a script instead.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
