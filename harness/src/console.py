"""Text-encoding policy for everything the harness prints or logs.

This experiment writes Urdu and Roman Urdu through every layer it has, on a
Windows box whose console encoding is cp1252. That combination fails in two
different ways, and only one of them is loud:

* `stdout` defaults to `errors="strict"`, so printing a single non-cp1252
  character raises `UnicodeEncodeError` -- observed on the Day 3 checkpoint,
  from a U+2011 non-breaking hyphen in an *English* summary.
* `stderr` defaults to `errors="backslashreplace"`, so the same text prints as
  `'\\u067e\\u0686...'` and nothing raises at all. A corpus author gets a
  correct diagnosis about a cell they cannot read.

`logging`'s `FileHandler` is a third case: it inherits the locale encoding and
raises, so the §13 run log dies on the first Urdu payload unless told
otherwise.

The rule is therefore: every stream and every file this harness writes is
UTF-8, explicitly, at the point it is opened. Call `use_utf8_console()` first
thing in any entry point that prints, and build log handlers with
`utf8_file_handler`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def use_utf8_console() -> None:
    """Make `stdout`/`stderr` UTF-8, whatever the console's locale encoding is.

    `errors="replace"` rather than `strict`: a terminal font that cannot draw
    Urdu should show replacement characters, not kill a running experiment.
    Redirecting the same output to a file still yields correct UTF-8.

    Safe to call more than once, and a no-op on streams that cannot be
    reconfigured (pytest's captured streams, pipe wrappers, already-detached
    streams).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def utf8_file_handler(
    path: str | Path,
    level: int = logging.INFO,
    fmt: str = "%(asctime)s %(levelname)s %(name)s: %(message)s",
) -> logging.FileHandler:
    """A log file handler that will not die on a non-ASCII payload (SPEC §13).

    `logging.FileHandler` opens with the locale encoding unless `encoding` is
    passed, which on this box means the first Urdu injected_text written to the
    run log raises inside logging itself.
    """
    handler = logging.FileHandler(Path(path), encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt))
    return handler
