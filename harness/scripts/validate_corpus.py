#!/usr/bin/env python
"""Standalone corpus validator (SPEC §9.1).

    python scripts/validate_corpus.py corpus/attack_prompts.csv

Run by both authors before the corpus is considered frozen. It reports every
validation error with its CSV line number, so mistakes are fixed in the sheet
rather than discovered halfway through an experiment run.

"Standalone" means runnable straight from a checkout, with no install step and
from any working directory -- it puts the harness root on `sys.path` itself.
The checks themselves are `src.corpus_loader`'s, deliberately not a second copy:
a validator that could disagree with the loader would be worse than none.

Exit status is 0 when the corpus is valid and 1 when it is not, so this drops
into a pre-run check or CI without extra glue.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from src.corpus_loader import (  # noqa: E402  (path setup must precede the import)
    DEFAULT_CORPUS_PATH,
    validate_corpus,
)
from src.task_types import LANGUAGES  # noqa: E402


def _use_utf8_console() -> None:
    """Print UTF-8 regardless of the console's locale encoding.

    This box's console is cp1252. Without this, Urdu and Roman Urdu reach the
    terminal as `\u067e\u0686...` escapes (stderr's default
    `backslashreplace`) or raise `UnicodeEncodeError` outright (stdout's
    default `strict`) -- and the authors who most need to read this output are
    the ones writing the non-ASCII rows. Redirecting to a file then yields
    correct UTF-8 even where the terminal font cannot draw the glyphs.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # pytest's captured streams, a pipe wrapper
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # already detached, or not reconfigurable
            pass


def _summarize(tasks) -> str:
    """One-screen picture of what the corpus currently holds."""
    if not tasks:
        return "  (no valid rows)"

    languages = Counter(t.language for t in tasks)
    patterns = Counter(t.attack_pattern for t in tasks)
    environments = Counter(t.environment for t in tasks)
    actions = Counter(t.expected_malicious_action for t in tasks)
    instances = {t.instance_id for t in tasks}
    complete = sum(
        1
        for instance in instances
        if {t.language for t in tasks if t.instance_id == instance} == set(LANGUAGES)
    )

    def line(label: str, counts: Counter) -> str:
        body = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        return f"  {label:<14} {body}"

    return "\n".join(
        [
            f"  {'rows':<14} {len(tasks)}",
            f"  {'instances':<14} {len(instances)} ({complete} complete triplet(s))",
            line("language", languages),
            line("environment", environments),
            line("pattern", patterns),
            line("action", actions),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    _use_utf8_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_CORPUS_PATH),
        help="corpus CSV to validate (default: %(default)s)",
    )
    parser.add_argument(
        "--allow-incomplete-triplets",
        action="store_true",
        help=(
            "skip the one-row-per-language check -- for mid-authoring passes, "
            "before the corpus is frozen"
        ),
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1

    tasks, errors = validate_corpus(path, require_triplets=not args.allow_incomplete_triplets)

    print(f"{path}")
    print(_summarize(tasks))

    if errors:
        print(f"\n{len(errors)} validation error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if args.allow_incomplete_triplets:
        print("\nOK (triplet check skipped -- not valid as a frozen corpus)")
    else:
        print("\nOK: corpus is valid and every triplet is complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
