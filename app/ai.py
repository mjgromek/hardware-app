"""The AI layer — a filter schema the model must speak, and an auditor that proposes.

ADR-0004 fixes the shape: the LLM emits a schema-validated filter object and SQLite
returns the rows, so the model cannot hallucinate inventory and the layer is testable
against a mock. This module owns both halves of that boundary — the schema and the SQL —
for the reason `app.rentals` owns its statements (ADR-0008): splitting "what the filter
means" from "the query it becomes" would leave two shallow modules sharing one rule.

Three decisions from grilling 3 live here:

- **The schema has no `notes`/`history`/`review_reason` predicate — for anyone**
  (ADR-0015). `extra="forbid"` is the enforcement: a model reply carrying
  `notes_contains` is rejected *wholesale*, because keeping the legal half would answer
  the forbidden question through the permitted field. The keyword fallback searches
  `name` and `brand` only, same rule.
- **The auditor's vocabulary is closed** (ADR-0014): a finding whose `kind` the model
  invented is dropped, never stored, never added to the enum. Findings are a computed
  payload — this module writes nothing, anywhere.
- **The client is resolved at request time** (ADR-0016): `app.state.llm` if a test put
  one there, else a real Gemini call built from `GEMINI_API_KEY` read now — so an
  absent key is feature-off, never a boot refusal.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from datetime import date
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain import HardwareItem, Status
from app.storage import hardware

__all__ = [
    "FINDING_KINDS",
    "FilterObject",
    "ModelUnavailable",
    "audit_catalogue",
    "keyword_search",
    "resolve_client",
    "semantic_filter",
    "select_items",
]

#: ADR-0014's closed vocabulary — exactly the three classes ADR-0002 deferred.
FINDING_KINDS = ("status_contradiction", "unidentifiable", "probable_misspelling")

#: Spec: 5 seconds, then the caller degrades (search) or refuses (auditor).
REQUEST_TIMEOUT_SECONDS = 5.0

GEMINI_KEY_VAR = "GEMINI_API_KEY"
GEMINI_MODEL_VAR = "GEMINI_MODEL"
#: The alias, not a pinned version: `gemini-2.5-flash` answered 404 "no longer
#: available to new users" on the deployment's key. The alias tracks whatever
#: Google currently serves; anyone needing a pin sets `GEMINI_MODEL`.
GEMINI_DEFAULT_MODEL = "gemini-flash-latest"


class ModelUnavailable(RuntimeError):
    """The model cannot be reached — no key, or the provider failed.

    One exception for both causes on purpose: the *caller* decides what unavailability
    means (search degrades, the auditor refuses — ADR-0016), so the distinction that
    matters is theirs, not this module's.
    """


class FilterObject(BaseModel):
    """Everything the model is allowed to say about a search (ADR-0004, ADR-0015).

    `extra="forbid"` is load-bearing, not tidiness: it is what rejects a reply carrying
    `notes_contains` *wholesale*. Partial salvage — keep `name_contains`, drop the rest —
    would answer the forbidden question through the permitted field
    (`test_search_is_not_an_oracle_over_notes`).
    """

    model_config = ConfigDict(extra="forbid")

    status: Status | None = None
    needs_review: bool | None = None
    brand: str | None = None
    name_contains: str | None = None
    purchased_before: date | None = None
    purchased_after: date | None = None
    rentable_only: bool | None = None


def parse_filter(raw: str) -> FilterObject | None:
    """The model's raw text, as a filter — or ``None``, never a partial.

    A half-valid filter is a wrong filter (docs/specs/phase-3.md), and the model saying
    something illegal is an expected event, not an error: the caller answers with the
    keyword fallback rather than a `500`.
    """
    payload = _json_body(raw)
    if not isinstance(payload, dict):
        return None
    try:
        return FilterObject.model_validate(payload)
    except ValidationError:
        return None


def select_items(session: Session, filters: FilterObject) -> tuple[HardwareItem, ...]:
    """The filter object, applied — in SQL, over public columns only (ADR-0015).

    `rentable_only` is ADR-0003 through the same rule as the rent guard, not a parallel
    one: rentable means `Available` *and* unflagged, so the search never offers an item
    the rent route is about to refuse.
    """
    query = select(hardware)
    if filters.status is not None:
        query = query.where(hardware.c.status == filters.status.value)
    if filters.needs_review is not None:
        query = query.where(hardware.c.needs_review == filters.needs_review)
    if filters.brand is not None:
        query = query.where(hardware.c.brand.ilike(filters.brand))
    if filters.name_contains is not None:
        query = query.where(hardware.c.name.ilike(f"%{filters.name_contains}%"))
    if filters.purchased_before is not None:
        query = query.where(hardware.c.purchase_date < filters.purchased_before)
    if filters.purchased_after is not None:
        query = query.where(hardware.c.purchase_date > filters.purchased_after)
    if filters.rentable_only:
        query = query.where(
            hardware.c.status == Status.AVAILABLE.value,
            hardware.c.needs_review == False,  # noqa: E712 — SQL, not Python truthiness
        )
    return _items(session, query)


def keyword_search(session: Session, query_text: str) -> tuple[HardwareItem, ...]:
    """The degraded path: query words against `name` and `brand`. Nothing else.

    The same ADR-0015 rule as the schema — a keyword fallback that grew a `LIKE` over
    `notes` would leak exactly what the schema forbade, through the door nobody was
    watching.
    """
    tokens = [token for token in re.findall(r"[A-Za-z0-9]+", query_text) if len(token) > 1]
    if not tokens:
        return ()
    matches = [
        clause
        for token in tokens
        for clause in (
            hardware.c.name.ilike(f"%{token}%"),
            hardware.c.brand.ilike(f"%{token}%"),
        )
    ]
    return _items(session, select(hardware).where(or_(*matches)))


def semantic_filter(client: Callable[[str], str], query_text: str) -> FilterObject | None:
    """Ask the model for a filter. ``None`` means "use the fallback", loudly typed.

    Raises `ModelUnavailable` only for provider failure — an illegal reply is not a
    failure, it is the model being a model (ADR-0015's whole premise).
    """
    try:
        raw = _call(client, _search_prompt(query_text))
    except ModelUnavailable:
        raise
    except Exception as error:  # provider errors are not this module's vocabulary
        raise ModelUnavailable(str(error)) from error
    return parse_filter(raw)


def audit_catalogue(
    client: Callable[[str], str], items: tuple[HardwareItem, ...], quarantine: tuple
) -> list[dict[str, Any]]:
    """Run the model over the catalogue and keep only findings the enum admits.

    Off-enum kinds are dropped — never stored, never invented into the vocabulary
    (ADR-0014). Malformed entries (no item id, blank evidence) go the same way: a
    finding an admin cannot check against a row is not a finding.
    """
    try:
        raw = _call(client, _audit_prompt(items, quarantine))
    except ModelUnavailable:
        raise
    except Exception as error:
        raise ModelUnavailable(str(error)) from error

    payload = _json_body(raw)
    if isinstance(payload, dict):
        payload = payload.get("findings")
    if not isinstance(payload, list):
        return []

    findings = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") not in FINDING_KINDS:
            continue
        if not isinstance(entry.get("item_id"), int):
            continue
        evidence = str(entry.get("evidence") or "").strip()
        explanation = str(entry.get("explanation") or "").strip()
        if not evidence or not explanation:
            continue
        findings.append(
            {
                "item_id": entry["item_id"],
                "kind": entry["kind"],
                "evidence": evidence,
                "explanation": explanation,
            }
        )
    return findings


def resolve_client(
    state: Any, environ: Mapping[str, str] | None = None
) -> Callable[[str], str] | None:
    """The model behind this request, or ``None`` for feature-off (ADR-0016).

    Request-time on purpose: the key is read now, not at boot, so rotating or removing
    it changes the next request rather than requiring a restart. A test's fake on
    `app.state.llm` wins over a real client — that is the seam the suite mocks
    (tests/llm_seam.py), and it is honoured before any network object is built.
    """
    env = os.environ if environ is None else environ
    key = env.get(GEMINI_KEY_VAR)
    if not key:
        return None
    fake = getattr(state, "llm", None)
    if fake is not None:
        return fake
    return _gemini_client(key, env.get(GEMINI_MODEL_VAR, GEMINI_DEFAULT_MODEL))


# --- internals -----------------------------------------------------------------


def _items(session: Session, query) -> tuple[HardwareItem, ...]:
    rows = session.execute(query).mappings().all()
    return tuple(
        HardwareItem(
            id=row["id"],
            name=row["name"],
            brand=row["brand"],
            purchase_date=row["purchase_date"],
            status=Status(row["status"]),
            source_id=row["source_id"],
            needs_review=bool(row["needs_review"]),
            review_reason=row["review_reason"],
            notes=row["notes"],
            history=row["history"],
            assigned_to=row["assigned_to"],
        )
        for row in rows
    )


def _call(client: Callable[..., str], prompt: str) -> str:
    """One prompt in, raw text out — whichever spelling the client offers."""
    for name in ("__call__", "complete", "generate", "generate_content"):
        method = getattr(client, name, None)
        if callable(method):
            return method(prompt)
    raise ModelUnavailable(f"the configured client {client!r} is not callable")


def _json_body(raw: str) -> Any:
    """The JSON in the model's reply, tolerant of markdown code fences."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _search_prompt(query_text: str) -> str:
    schema = FilterObject.model_json_schema()
    return (
        "You translate an employee's natural-language question about a hardware "
        "inventory into a JSON filter object. Reply with ONLY the JSON object, no "
        "prose. Omit fields you are not using. The only legal fields are exactly "
        f"those in this schema:\n{json.dumps(schema)}\n\n"
        f'Statuses are exactly "Available", "In Use", "Repair". If the question asks '
        "for something rentable/borrowable today, set rentable_only. If the question "
        "cannot be expressed with these fields, reply with an empty JSON object.\n\n"
        f"Question: {query_text}"
    )


def _audit_prompt(items: tuple[HardwareItem, ...], quarantine: tuple) -> str:
    catalogue = [
        {
            "item_id": item.id,
            "name": item.name,
            "brand": item.brand,
            "purchase_date": str(item.purchase_date) if item.purchase_date else None,
            "status": item.status.value,
            "needs_review": item.needs_review,
            "notes": item.notes,
            "history": item.history,
        }
        for item in items
    ]
    return (
        "You are auditing a hardware inventory for an internal tool. Report findings "
        "as JSON: {\"findings\": [{\"item_id\": <int>, \"kind\": <kind>, \"evidence\": "
        "<verbatim quote or field values from that row>, \"explanation\": <one "
        "sentence>}]}. Reply with ONLY the JSON.\n\n"
        "The ONLY legal kinds, use no others:\n"
        "- status_contradiction: the status conflicts with the row's own notes or "
        "history (e.g. Available but the prose says it must not be issued)\n"
        "- unidentifiable: nothing in the row identifies a physical device (empty or "
        "meaningless name/brand, no date, no prose) — it needs a physical audit\n"
        "- probable_misspelling: a brand or name is almost certainly a typo of a real "
        "one\n\n"
        "Do not report items whose data is merely incomplete but identifiable. Do not "
        "invent kinds. Do not correct anything — you propose, a human decides.\n\n"
        f"Catalogue:\n{json.dumps(catalogue)}\n\n"
        "Quarantined rows (failed structural validation):\n"
        f"{json.dumps(list(quarantine), default=str)}"
    )


def _gemini_client(key: str, model: str) -> Callable[[str], str]:
    """A real Gemini call, built only when no fake is on the seam.

    Imported lazily so the suite — which nails the socket shut — never constructs it.
    Raises `ModelUnavailable` for every transport or provider failure: the caller's
    vocabulary, not httpx's.
    """

    def call(prompt: str) -> str:
        # stdlib on purpose. The first deploy used httpx here, which is a test-extra
        # rather than a production dependency — locally green, live the auditor's own
        # 503 reason read "No module named 'httpx'". The refusal-with-a-reason design
        # (ADR-0016) is what surfaced it; the fix is to depend on nothing.
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent",
            data=json.dumps(
                {"contents": [{"parts": [{"text": prompt}]}]}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT_SECONDS
            ) as response:
                body = json.loads(response.read())
            return body["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as error:
            raise ModelUnavailable(f"Gemini request failed: {error}") from error

    return call
