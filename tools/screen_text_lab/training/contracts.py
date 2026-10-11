"""Small, framework-independent contracts for isolated OCR experiments."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def class_tokens(characters: list[str], head: str = "ctc") -> list[str]:
    if any(not isinstance(character, str) or len(character) != 1 or character.isspace()
           for character in characters):
        raise ValueError("Dictionary entries must be individual non-whitespace Unicode characters")
    if len(set(characters)) != len(characters) or " " in characters:
        raise ValueError("Dictionary must have unique entries without implicit space")
    special = {"ctc": ["blank"], "nrtr": ["blank", "<unk>", "<s>", "</s>"]}
    if head not in special:
        raise ValueError("Unknown head")
    if any(item in special[head] for item in characters):
        raise ValueError("Dictionary collides with special tokens")
    return special[head] + characters + [" "]


def class_mapping(old: list[str], new: list[str], head: str = "ctc") -> list[int]:
    """Map every old class including implicit space to its new class ID."""
    old_tokens, new_tokens = class_tokens(old, head), class_tokens(new, head)
    lookup = {token: index for index, token in enumerate(new_tokens)}
    if not set(old_tokens).issubset(lookup):
        raise ValueError("Dictionary expansion may not drop existing characters")
    return [lookup[token] for token in old_tokens]


def shape_audit(expected: dict, actual: dict) -> dict:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatches = [{"key": key, "expected": list(expected[key]), "actual": list(actual[key])}
                  for key in sorted(set(expected) & set(actual))
                  if list(expected[key]) != list(actual[key])]
    return {"ok": not (missing or extra or mismatches), "expected_count": len(expected),
            "actual_count": len(actual), "missing": missing, "extra": extra,
            "shape_mismatches": mismatches}


def required_ctc_steps(text: str) -> int:
    return len(text) + sum(first == second for first, second in zip(text, text[1:]))


def nrtr_accepts(text: str, max_text_length: int) -> bool:
    """Mirror the pinned official NRTR length boundary, not its OOV filtering."""
    return bool(text) and len(text) < max_text_length - 1
