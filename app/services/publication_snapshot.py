from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from typing import Any


def canonical_snapshot_bytes(
    snapshot: dict[str, Any],
) -> bytes:
    """
    Serialize a preview deterministically.

    Identical ATI previews always produce the same
    SHA-256 digest regardless of dictionary key order.
    """

    if not isinstance(snapshot, dict):
        raise TypeError(
            "ATI preview snapshot must be a dictionary"
        )

    content = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    return content.encode("utf-8")


def snapshot_hash(
    snapshot: dict[str, Any],
) -> str:
    return hashlib.sha256(
        canonical_snapshot_bytes(snapshot)
    ).hexdigest()


def freeze_snapshot(
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """
    Return an independent JSON-safe copy and its hash.
    """

    frozen = json.loads(
        canonical_snapshot_bytes(snapshot)
        .decode("utf-8")
    )

    return frozen, snapshot_hash(frozen)


def verify_snapshot(
    snapshot: dict[str, Any] | None,
    expected_hash: str | None,
) -> dict[str, Any]:
    """
    Validate and return an independent snapshot copy.

    Legacy approvals without a stored snapshot and
    modified snapshots are rejected.
    """

    if snapshot is None:
        raise RuntimeError(
            "Публикация заблокирована: "
            "в approval отсутствует сохранённый "
            "снимок ATI. Создайте заявку повторно."
        )

    if not expected_hash:
        raise RuntimeError(
            "Публикация заблокирована: "
            "у снимка ATI отсутствует "
            "контрольный отпечаток."
        )

    actual_hash = snapshot_hash(snapshot)

    if not hmac.compare_digest(
        actual_hash,
        str(expected_hash),
    ):
        raise RuntimeError(
            "Публикация заблокирована: "
            "сохранённый снимок ATI был изменён "
            "или повреждён."
        )

    return deepcopy(snapshot)
