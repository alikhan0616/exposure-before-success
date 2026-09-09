"""Corpus CSV -> `InjectionTask` objects, with validation (SPEC §9, §2.1, §2.1a).

The CSV is the runtime format, not the authoring format (§9.1): rows are typed
in a shared sheet and exported here. That makes this loader the only line of
defence against authoring typos, so it is deliberately strict and deliberately
loud -- it collects *every* problem in the file and reports them together with
row numbers, rather than dying on the first one, because the person fixing them
is looking at a spreadsheet and wants the whole list in one pass.

Three invariants matter more than the rest:

* **Typed targets** (§2.1a). `attacker_target_json` must parse and match the
  schema for its action, so checkers can consume the dict without re-parsing.
* **Matched triplets** (§9). Every `instance_id` appears exactly once per
  language. This is what makes EN/UR/RU a controlled comparison rather than
  three loosely related samples; if it breaks, the paper's core claim breaks
  with it, so a frozen corpus fails to load rather than running skewed.
* **Placement coherence.** A row's `environment` must match the environment of
  the UserTask it names, since the payload's position is keyed on the UserTask
  (`injection_points.py`). A mismatch would inject into a different environment
  than the row claims to be testing.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .task_types import (
    ACTION_TO_CHECKER,
    ATTACK_PATTERNS,
    ENVIRONMENTS,
    LANGUAGES,
    MALICIOUS_ACTIONS,
    REPO_ROOT,
    TARGET_SCHEMAS,
    USER_TASKS_BY_ID,
    InjectionTask,
)

# The corpus is authored at the project root, alongside `analysis/` and
# `results/`, not inside the harness package: it is shared editorial content
# rather than code (§9.1 -- exported from a sheet before every run).
PROJECT_ROOT = REPO_ROOT.parent
DEFAULT_CORPUS_PATH = PROJECT_ROOT / "corpus" / "attack_prompts.csv"

# SPEC §2.1: exact names, in this order.
COLUMNS: tuple[str, ...] = (
    "id",
    "attack_pattern",
    "environment",
    "language",
    "variant_num",
    "instance_id",
    "injected_text",
    "expected_malicious_action",
    "attacker_target_json",
    "user_task_id",
    "source_citation",
    "source_dataset_ref",
)

# `source_dataset_ref` is explicitly allowed to be empty (§2.1: "else empty").
OPTIONAL_COLUMNS: frozenset[str] = frozenset({"source_dataset_ref"})

# §2.1: 1 or 2, or 3 if the stretch variant gets authored.
ALLOWED_VARIANT_NUMS: tuple[int, ...] = (1, 2, 3)

# Fields that must be identical across the three languages of one instance.
# The payload text and its target may differ -- that is the manipulation under
# study -- but everything describing the *condition* may not, or the triplet
# stops being matched.
TRIPLET_INVARIANT_FIELDS: tuple[str, ...] = (
    "attack_pattern",
    "environment",
    "variant_num",
    "expected_malicious_action",
    "user_task_id",
)


@dataclass(frozen=True)
class CorpusError:
    """One validation failure, addressed the way the author sees the file."""

    line: int | None  # 1-based line in the CSV; None for file-level problems
    prompt_id: str
    column: str
    message: str

    def __str__(self) -> str:
        where = f"line {self.line}" if self.line is not None else "file"
        who = f" [{self.prompt_id}]" if self.prompt_id else ""
        what = f" {self.column}:" if self.column else ""
        return f"{where}{who}{what} {self.message}"


class CorpusValidationError(ValueError):
    """Raised with every error found, not just the first."""

    def __init__(self, path: Path | str, errors: Sequence[CorpusError]) -> None:
        self.path = str(path)
        self.errors = list(errors)
        listed = "\n".join(f"  - {e}" for e in self.errors)
        super().__init__(
            f"{len(self.errors)} validation error(s) in {self.path}:\n{listed}"
        )


def _quote(values: Iterable[str]) -> str:
    return ", ".join(repr(v) for v in values)


# ---------------------------------------------------------------------------
# Per-row validation
# ---------------------------------------------------------------------------


def _validate_target(
    action: str, raw: str, line: int, prompt_id: str, errors: list[CorpusError]
) -> dict[str, Any] | None:
    """Parse and schema-check `attacker_target_json` (§2.1a)."""
    add = lambda msg: errors.append(  # noqa: E731 - local shorthand, one use site
        CorpusError(line, prompt_id, "attacker_target_json", msg)
    )

    if not raw.strip():
        add("is empty; every row needs a typed target")
        return None
    try:
        target = json.loads(raw)
    except ValueError as exc:
        add(f"is not valid JSON ({exc})")
        return None
    if not isinstance(target, dict):
        add(f"must be a JSON object, got {type(target).__name__}")
        return None

    schema = TARGET_SCHEMAS.get(action)
    if schema is None:  # unknown action; already reported by the caller
        return target

    for key in schema["required"]:
        value = target.get(key)
        if value is None:
            add(f"missing required key {key!r} for action {action!r}")
        elif not isinstance(value, str) or not value.strip():
            add(f"{key!r} must be a non-empty string, got {value!r}")

    for key, allowed in schema["enums"].items():
        value = target.get(key)
        if value is not None and value not in allowed:
            add(f"{key}={value!r} not one of {_quote(allowed)}")

    extra = set(target) - set(schema["required"])
    if extra:
        # Not fatal on its own, but almost always a misspelled key that would
        # otherwise read as a silently missing one.
        add(f"unexpected key(s) {_quote(sorted(extra))} for action {action!r}")

    return target


def _validate_row(
    row: dict[str, str], line: int, errors: list[CorpusError]
) -> InjectionTask | None:
    """Validate one CSV row; returns the InjectionTask, or None if unusable."""
    before = len(errors)
    prompt_id = (row.get("id") or "").strip()

    def add(column: str, message: str) -> None:
        errors.append(CorpusError(line, prompt_id, column, message))

    def enum(column: str, allowed: tuple[str, ...]) -> str:
        value = (row.get(column) or "").strip()
        if value not in allowed:
            add(column, f"{value!r} is not one of {_quote(allowed)}")
        return value

    if not prompt_id:
        add("id", "is empty; every row needs a unique id")

    attack_pattern = enum("attack_pattern", ATTACK_PATTERNS)
    environment = enum("environment", ENVIRONMENTS)
    language = enum("language", LANGUAGES)
    action = enum("expected_malicious_action", MALICIOUS_ACTIONS)

    instance_id = (row.get("instance_id") or "").strip()
    if not instance_id:
        add("instance_id", "is empty; it is what binds the EN/UR/RU triplet")

    raw_variant = (row.get("variant_num") or "").strip()
    try:
        variant_num = int(raw_variant)
    except ValueError:
        add("variant_num", f"{raw_variant!r} is not an integer")
        variant_num = 0
    else:
        if variant_num not in ALLOWED_VARIANT_NUMS:
            add("variant_num", f"{variant_num} is not one of {ALLOWED_VARIANT_NUMS}")

    # Not stripped: an obfuscation payload may open or close with whitespace or
    # zero-width characters, and normalising it here would quietly defuse the
    # very attack the row exists to test.
    injected_text = row.get("injected_text") or ""
    if not injected_text.strip():
        add("injected_text", "is empty; there would be no payload to inject")

    user_task_id = (row.get("user_task_id") or "").strip()
    user_task = USER_TASKS_BY_ID.get(user_task_id)
    if user_task is None:
        add("user_task_id", f"{user_task_id!r} is not a known UserTask (§5)")
    elif environment and user_task.environment != environment:
        add(
            "environment",
            f"{environment!r} does not match user_task {user_task_id!r} "
            f"(environment {user_task.environment!r})",
        )

    target = _validate_target(
        action, row.get("attacker_target_json") or "", line, prompt_id, errors
    )

    source_citation = (row.get("source_citation") or "").strip()
    if not source_citation:
        add("source_citation", "is empty; every payload needs a provenance note")

    if len(errors) > before:
        return None

    return InjectionTask(
        prompt_id=prompt_id,
        instance_id=instance_id,
        attack_pattern=attack_pattern,
        environment=environment,
        language=language,
        variant_num=variant_num,
        injected_text=injected_text,
        expected_malicious_action=action,
        attacker_target=target or {},
        user_task_id=user_task_id,
        checker_name=ACTION_TO_CHECKER[action],
        source_citation=source_citation,
    )


# ---------------------------------------------------------------------------
# Corpus-level validation
# ---------------------------------------------------------------------------


def _check_unique_ids(
    tasks: Sequence[InjectionTask], lines: dict[str, int], errors: list[CorpusError]
) -> None:
    seen: dict[str, int] = {}
    for task in tasks:
        first = seen.get(task.prompt_id)
        if first is None:
            seen[task.prompt_id] = lines[task.prompt_id]
        else:
            errors.append(
                CorpusError(
                    lines[task.prompt_id],
                    task.prompt_id,
                    "id",
                    f"duplicate id (first seen on line {first})",
                )
            )


def _check_triplets(
    tasks: Sequence[InjectionTask], lines: dict[str, int], errors: list[CorpusError]
) -> None:
    """The matched-triplet invariant (§9): one EN, one UR, one RU per instance."""
    by_instance: dict[str, list[InjectionTask]] = {}
    for task in tasks:
        by_instance.setdefault(task.instance_id, []).append(task)

    for instance_id, group in sorted(by_instance.items()):
        line = min(lines[t.prompt_id] for t in group)
        by_language: dict[str, list[InjectionTask]] = {}
        for task in group:
            by_language.setdefault(task.language, []).append(task)

        missing = [lang for lang in LANGUAGES if lang not in by_language]
        if missing:
            errors.append(
                CorpusError(
                    line,
                    instance_id,
                    "instance_id",
                    f"incomplete triplet: no {_quote(missing)} row "
                    f"(have {_quote(sorted(by_language))})",
                )
            )
        for lang, rows in sorted(by_language.items()):
            if len(rows) > 1:
                errors.append(
                    CorpusError(
                        line,
                        instance_id,
                        "instance_id",
                        f"{len(rows)} {lang!r} rows ({_quote(r.prompt_id for r in rows)}); "
                        "each language must appear exactly once",
                    )
                )

        # Same condition across the triplet, or the comparison is confounded.
        for field_name in TRIPLET_INVARIANT_FIELDS:
            values = {getattr(t, field_name) for t in group}
            if len(values) > 1:
                errors.append(
                    CorpusError(
                        line,
                        instance_id,
                        field_name,
                        f"differs across the triplet ({_quote(sorted(map(str, values)))}); "
                        "language must be the only thing that varies",
                    )
                )


def _check_header(
    fieldnames: Sequence[str] | None, errors: list[CorpusError]
) -> bool:
    """Header must be the §2.1 columns, exact names in exact order."""
    if not fieldnames:
        errors.append(CorpusError(None, "", "", "file is empty: no header row"))
        return False

    header = tuple(name.strip() for name in fieldnames)
    if header == COLUMNS:
        return True

    missing = [c for c in COLUMNS if c not in header]
    unexpected = [c for c in header if c not in COLUMNS]
    if missing:
        errors.append(CorpusError(1, "", "", f"header is missing column(s) {_quote(missing)}"))
    if unexpected:
        errors.append(CorpusError(1, "", "", f"header has unknown column(s) {_quote(unexpected)}"))
    if not missing and not unexpected:
        errors.append(
            CorpusError(
                1,
                "",
                "",
                f"header column order is {_quote(header)}; §2.1 requires {_quote(COLUMNS)}",
            )
        )
    return False


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def validate_corpus(
    path: str | Path = DEFAULT_CORPUS_PATH, *, require_triplets: bool = True
) -> tuple[list[InjectionTask], list[CorpusError]]:
    """Parse and validate a corpus CSV, returning `(tasks, errors)`.

    Never raises on invalid content -- `scripts/validate_corpus.py` wants the
    full error list to print. `require_triplets=False` is the mid-authoring
    mode: rows are still fully checked, but a half-translated corpus is not yet
    a failure.
    """
    path = Path(path)
    errors: list[CorpusError] = []
    tasks: list[InjectionTask] = []
    lines: dict[str, int] = {}

    # utf-8-sig: sheet exports carry a BOM, which would otherwise become part of
    # the first header name and fail the header check for invisible reasons.
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not _check_header(reader.fieldnames, errors):
            return [], errors

        for line, row in enumerate(reader, start=2):  # line 1 is the header
            if not any((value or "").strip() for value in row.values()):
                continue  # trailing blank line from the export
            task = _validate_row(row, line, errors)
            if task is not None:
                lines.setdefault(task.prompt_id, line)
                tasks.append(task)

    _check_unique_ids(tasks, lines, errors)

    if require_triplets:
        if not tasks and not errors:
            errors.append(
                CorpusError(None, "", "", "corpus has no data rows")
            )
        _check_triplets(tasks, lines, errors)

    return tasks, errors


def load_corpus(
    path: str | Path = DEFAULT_CORPUS_PATH, *, require_triplets: bool = True
) -> tuple[list[InjectionTask], dict[str, str]]:
    """Load a valid corpus, or raise `CorpusValidationError` listing every fault.

    Returns the parsed rows and the action -> checker-name map (§9), which is
    what the agent loop uses to pick a checker per trial.
    """
    tasks, errors = validate_corpus(path, require_triplets=require_triplets)
    if errors:
        raise CorpusValidationError(path, errors)
    return tasks, dict(ACTION_TO_CHECKER)
