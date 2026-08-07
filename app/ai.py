"""The AI layer — a filter schema the model must speak, and an auditor that proposes.

The LLM emits a schema-validated filter object and SQLite returns the rows, so the
model cannot hallucinate inventory (ADR-0004). No restricted-field predicates for
anyone (ADR-0015), a closed finding vocabulary that writes nothing (ADR-0014), and a
client resolved at request time so an absent key is feature-off (ADR-0016).
"""

from __future__ import annotations

import hashlib
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
    "ResponseCache",
    "audit_catalogue",
    "catalogue_fingerprint",
    "keyword_search",
    "normalise_query",
    "resolve_client",
    "semantic_filter",
    "select_items",
]

#: ADR-0014's closed vocabulary — exactly the three classes ADR-0002 deferred.
FINDING_KINDS = ("status_contradiction", "unidentifiable", "probable_misspelling")

#: Measured: the live provider spends ~7.5s thinking before one small JSON object,
#: so the spec's 5s meant the semantic path could never answer. 12s is latency with
#: headroom — a slower true answer with an honest label beats a fast fallback.
REQUEST_TIMEOUT_SECONDS = 12.0

#: An audit reads the whole catalogue; 5 seconds is a search budget, not an audit
#: budget. The first live run timed out on the borrowed number.
AUDIT_TIMEOUT_SECONDS = 30.0

GEMINI_KEY_VAR = "GEMINI_API_KEY"
GEMINI_MODEL_VAR = "GEMINI_MODEL"
#: The alias, not a pin: `gemini-2.5-flash` answered 404 "no longer available to new
#: users" on the deployment's key. Anyone needing a pin sets `GEMINI_MODEL`.
GEMINI_DEFAULT_MODEL = "gemini-flash-latest"


class ResponseCache:
    """The model's replies, remembered — never the rows.

    Keys chosen so staleness is structurally impossible: search filters by
    normalised query (the SQL still runs fresh per request), audit findings by
    catalogue fingerprint (a changed catalogue misses the cache — the amendment in
    ADR-0014). In-memory, so findings still die with the process.
    """

    def __init__(self) -> None:
        self.search_filters: dict[str, FilterObject | None] = {}
        self.audit_findings: dict[str, list[dict[str, Any]]] = {}


def normalise_query(query_text: str) -> str:
    """Casing and whitespace differences are the same question."""
    return " ".join(query_text.lower().split())


def catalogue_fingerprint(items: tuple, quarantine: tuple) -> str:
    """One hash naming the exact catalogue state an audit describes.

    Built over the same payload the audit prompt carries, so "the fingerprint
    matched" and "the model would have been shown the same thing" are one fact.
    """
    payload = {"items": _catalogue_payload(items), "quarantine": list(quarantine)}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class ModelUnavailable(RuntimeError):
    """The model cannot be reached — no key, or the provider failed.

    One exception for both causes on purpose: the *caller* decides what unavailability
    means (search degrades, the auditor refuses — ADR-0016), so the distinction that
    matters is theirs, not this module's.
    """


class FilterObject(BaseModel):
    """Everything the model is allowed to say about a search (ADR-0004, ADR-0015).

    `extra="forbid"` is load-bearing: a reply carrying `notes_contains` is rejected
    wholesale — partial salvage would answer the forbidden question through the
    permitted field.
    """

    model_config = ConfigDict(extra="forbid")

    status: Status | None = None
    needs_review: bool | None = None
    brand: str | None = None
    name_contains: str | None = None
    #: "laptop" has no column, so the model names concrete product terms and SQLite
    #: still decides which rows exist. Matched over `name`/`brand` only — this
    #: widens what the model may *say*, not what it may see.
    name_matches_any: list[str] | None = None
    purchased_before: date | None = None
    purchased_after: date | None = None
    rentable_only: bool | None = None


def parse_filter(raw: str) -> FilterObject | None:
    """The model's raw text, as a filter — or ``None``, never a partial. An illegal
    reply is an expected event: the caller falls back, not 500s."""
    payload = _json_body(raw)
    if not isinstance(payload, dict):
        return None
    try:
        return FilterObject.model_validate(payload)
    except ValidationError:
        return None


def select_items(session: Session, filters: FilterObject) -> tuple[HardwareItem, ...]:
    """The filter object, applied — in SQL, over public columns only (ADR-0015).
    `rentable_only` means Available *and* unflagged, so the search never offers an
    item the rent route is about to refuse."""
    query = select(hardware)
    if filters.status is not None:
        query = query.where(hardware.c.status == filters.status.value)
    if filters.needs_review is not None:
        query = query.where(hardware.c.needs_review == filters.needs_review)
    if filters.brand is not None:
        query = query.where(hardware.c.brand.ilike(filters.brand))
    if filters.name_contains is not None:
        query = query.where(hardware.c.name.ilike(f"%{filters.name_contains}%"))
    if filters.name_matches_any:
        terms = [term for term in filters.name_matches_any if term.strip()]
        if terms:
            query = query.where(
                or_(
                    *(
                        clause
                        for term in terms
                        for clause in (
                            hardware.c.name.ilike(f"%{term}%"),
                            hardware.c.brand.ilike(f"%{term}%"),
                        )
                    )
                )
            )
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
    """The degraded path: query words against `name` and `brand`, nothing else — a
    fallback that grew a LIKE over `notes` would leak what the schema forbids (ADR-0015)."""
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
    """Run the model over the catalogue and keep only findings the enum admits
    (ADR-0014). A finding an admin cannot check against a row is not a finding."""
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
    state: Any,
    environ: Mapping[str, str] | None = None,
    *,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> Callable[[str], str] | None:
    """The model behind this request, or ``None`` for feature-off (ADR-0016).
    Request-time so rotating the key changes the next request, not the next boot; a
    test's fake on `app.state.llm` wins before any network object is built."""
    env = os.environ if environ is None else environ
    key = env.get(GEMINI_KEY_VAR)
    if not key:
        return None
    fake = getattr(state, "llm", None)
    if fake is not None:
        return fake
    return _gemini_client(key, env.get(GEMINI_MODEL_VAR, GEMINI_DEFAULT_MODEL), timeout)


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
            serial_number=row["serial_number"],
            category=row["category"],
            date_added=row["date_added"],
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
        "for something rentable/borrowable today, set rentable_only. When the "
        "question names a *category* of device rather than a product — laptop, "
        "phone, headphones, tablet, mouse, monitor — populate name_matches_any with "
        "concrete product and model terms that category implies, e.g. \"laptop\" -> "
        '["MacBook", "XPS", "ThinkPad", "Latitude"], "headphones" -> ["WH-1000", '
        '"AirPods", "headset"]. Prefer terms over guessing a status. If the question '
        "cannot be expressed with these fields, reply with an empty JSON object.\n\n"
        f"Question: {query_text}"
    )


def _catalogue_payload(items: tuple[HardwareItem, ...]) -> list[dict[str, Any]]:
    """What the audit shows the model — and what its cache key is built over."""
    return [
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


def _audit_prompt(items: tuple[HardwareItem, ...], quarantine: tuple) -> str:
    catalogue = _catalogue_payload(items)
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


def _gemini_client(key: str, model: str, timeout: float) -> Callable[[str], str]:
    """A real Gemini call, built only when no fake is on the seam."""

    def call(prompt: str) -> str:
        # stdlib on purpose: the first deploy used httpx, a test-extra — locally
        # green, live the auditor's 503 read "No module named 'httpx'".
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
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read())
            return body["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as error:
            raise ModelUnavailable(f"Gemini request failed: {error}") from error

    return call
