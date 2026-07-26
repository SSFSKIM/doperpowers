"""Documents on disk: one JSON file per document under ``data/<tenant>/``.

Single-threaded by construction. The service handles one request at a time in
one process and nothing else writes ``data/`` (see the README's Concurrency
section), so the read-then-write sequences in this module have no concurrent
writer to interleave with and deliberately carry no locking, no ``O_EXCL`` and
no temp-file-plus-rename.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Document names appear in file paths, so they are deliberately narrow.
NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")

Row = Dict[str, object]


class BadDocumentName(ValueError):
    """Raised when a caller supplies a name we refuse to put on disk."""


@dataclass(frozen=True)
class Document:
    name: str
    revision: int
    rows: List[Row]


def check_name(name: object) -> str:
    """Return ``name`` if it is a legal document name, else raise."""
    if not isinstance(name, str) or NAME_PATTERN.fullmatch(name) is None:
        raise BadDocumentName(
            "document name must match /%s/" % NAME_PATTERN.pattern
        )
    return name


def _document_path(tenant: str, name: str) -> str:
    return os.path.join(ROOT, tenant, check_name(name) + ".json")


def list_tenants() -> List[str]:
    """Every tenant that has at least one document on this node."""
    if not os.path.isdir(ROOT):
        return []
    return sorted(
        entry
        for entry in os.listdir(ROOT)
        if os.path.isdir(os.path.join(ROOT, entry))
    )


def list_documents(tenant: str) -> List[str]:
    """Names of one tenant's documents, alphabetically."""
    directory = os.path.join(ROOT, tenant)
    if not os.path.isdir(directory):
        return []
    return sorted(
        entry[: -len(".json")]
        for entry in os.listdir(directory)
        if entry.endswith(".json")
    )


def load_document(tenant: str, name: str) -> Optional[Document]:
    """Read one document, or None when the tenant does not have it."""
    path = _document_path(tenant, name)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return None
    return Document(
        name=name,
        revision=int(payload["revision"]),
        rows=list(payload["rows"]),
    )


def save_document(tenant: str, name: str, rows: List[Row]) -> int:
    """Replace a document's rows and return its new revision number."""
    path = _document_path(tenant, name)
    previous = load_document(tenant, name)
    revision = 1 if previous is None else previous.revision + 1

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"revision": revision, "rows": rows}, handle)
    return revision
