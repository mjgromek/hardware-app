"""Phase 3 Slice B — the Inventory Auditor proposes, and never disposes.

`GET /api/admin/audit` runs the model over the catalogue and returns findings shaped
`{"item_id", "kind", "evidence", "explanation"}`, where `kind` is the closed enum
`status_contradiction | unidentifiable | probable_misspelling` (ADR-0014). Computed per
run, persisted nowhere.

Three properties carry the weight here, and they are why the route is not simply "the
search endpoint with a different prompt":

*Admin-only.* Every finding quotes `notes` or `history`, and derived content inherits
its source's restriction — ADR-0012 is not weakened by putting a model between the
column and the reader (ADR-0014).

*It refuses rather than degrades.* Search falls back to keyword; the auditor answers
`503`. A keyword auditor cannot find seed id 10 — the row with an empty brand, no
purchase date and no notes to regex — so a degraded audit wearing the AI's name
reports fewer findings and looks like a clean catalogue (ADR-0016).

*It writes nothing.* `needs_review` is a rentability guard (ADR-0003); an auditor that
sets it is an LLM deciding what may be rented. The verb that acts on a finding is
Slice C's, it takes a human's reason, and it is out of this file's scope.

The model is mocked in every test (`tests/llm_seam.py`, ADR-0004) — these pin the
plumbing around the judgment, not the judgment. Whether the real prompt actually
notices `"Appel"` is the live smoke's job, and it is not part of this suite.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from tests.conftest import ANONYMOUS_REFUSAL, audit_rows, items_by_id, rental_rows
from tests.llm_seam import (  # noqa: F401 — `no_live_api_calls` is autouse here
    AUDIT_PATH,
    disable_ai,
    enable_ai,
    findings_of,
    no_live_api_calls,
)

#: ADR-0014's closed vocabulary. Exactly the three classes ADR-0002 deferred.
FINDING_KINDS = {"status_contradiction", "unidentifiable", "probable_misspelling"}

#: Seed id 5: `Available`, notes say the battery is swelling.
DELL_XPS = 5
#: Seed id 11: `Available`, history says liquid damage.
MACBOOK_AIR = 11
#: Seed id 10: empty brand, null purchase date, no prose at all — the finding with no
#: keyword signature, and so the only one that distinguishes the layer from a regex.
UNKNOWN_DEVICE = 10


def _finding(item_id: int, kind: str, evidence: str, explanation: str) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "kind": kind,
        "evidence": evidence,
        "explanation": explanation,
    }


CONTRADICTIONS = [
    _finding(
        DELL_XPS,
        "status_contradiction",
        "Battery swelling, do not issue without service.",
        "Marked Available while its own notes say it must not be issued.",
    ),
    _finding(
        MACBOOK_AIR,
        "status_contradiction",
        "Returned by user with liquid damage. Keyboard sticky.",
        "Marked Available after a liquid-damage return that was never serviced.",
    ),
]

UNIDENTIFIABLE = _finding(
    UNKNOWN_DEVICE,
    "unidentifiable",
    "name 'Unknown Device', brand '', purchaseDate null",
    "Nothing in this row identifies a physical device, so it cannot be audited or "
    "issued.",
)


def _by_item(findings: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Findings keyed by item, so nothing depends on the order the model listed them."""
    return {finding["item_id"]: finding for finding in findings}


def _row_counts(app) -> dict[str, int]:
    """Every table and how many rows it holds — the whole database, coarsely.

    Coarse on purpose: "the auditor writes nothing" is a claim about *anywhere*, and a
    check that named `hardware` and `audit_events` would miss the findings table
    somebody added to cache a run.
    """
    engine = app.state.engine
    with engine.connect() as connection:
        return {
            name: connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
            for name in inspect(engine).get_table_names()
        }


def test_auditor_is_admin_only(
    monkeypatch, app, admin_client: TestClient, user_client: TestClient,
    anonymous_client: TestClient,
) -> None:
    """A `user` gets `403`, a stranger gets `401`, and an admin gets the findings.

    Not a general admin-route reflex: every finding quotes `notes` or `history`, which
    ADR-0012 restricts, and a summary of a restricted field is a restricted field
    (ADR-0014). Routing that prose through a model does not launder it.

    The admin's `200` is the control. Without it a route that refused everybody — or
    that does not exist — would satisfy both refusals.
    """
    enable_ai(monkeypatch, app, reply={"findings": CONTRADICTIONS})

    refused = user_client.get(AUDIT_PATH)
    assert refused.status_code == 403, (
        "an employee must be refused the audit: its findings quote the maintenance "
        f"prose ADR-0012 keeps admin-only. Got {refused.status_code}: {refused.text}"
    )
    assert "swelling" not in refused.text.lower(), (
        f"and the refusal must not carry the evidence with it; got {refused.text}"
    )

    anonymous = anonymous_client.get(AUDIT_PATH)
    assert anonymous.status_code in ANONYMOUS_REFUSAL, (
        f"nobody signed out reads the audit; got {anonymous.status_code}"
    )

    allowed = admin_client.get(AUDIT_PATH)
    assert allowed.status_code == 200, (
        "control: an admin must be able to run the audit, or the two refusals above "
        f"are satisfied by a route that answers nobody. Got {allowed.status_code}: "
        f"{allowed.text}"
    )


def test_auditor_refuses_without_api_key(
    monkeypatch, app, admin_client: TestClient
) -> None:
    """No key, no audit — `503` with a readable reason, and no quiet keyword pass.

    ADR-0016 splits the two features deliberately. Search degrades because an employee
    still needs to find a laptop; the auditor refuses because a degraded audit is
    indistinguishable from a clean catalogue, and the row it would silently stop
    finding is exactly id 10. A missing key is still feature-off and not a boot
    refusal — the app is up, this route is the only thing that says no.
    """
    disable_ai(monkeypatch, app)

    response = admin_client.get(AUDIT_PATH)

    assert response.status_code == 503, (
        "the auditor refuses loudly when it cannot run — it never falls back to "
        f"keyword (ADR-0016). Got {response.status_code}: {response.text}"
    )
    body = response.json()
    reason = body.get("detail") if isinstance(body, dict) else None
    assert isinstance(reason, str) and len(reason.strip()) > 10, (
        "the refusal must carry a reason an admin can act on — 'the AI layer is not "
        f"configured', not an empty 503. Got {body!r}"
    )
    assert "finding" not in response.text.lower(), (
        "a refusal must not ship findings of any kind: half an audit under the "
        f"auditor's name is what ADR-0016 refuses. Got {response.text}"
    )


def test_auditor_flags_unidentifiable_item(
    monkeypatch, app, admin_client: TestClient
) -> None:
    """Seed id 10 comes back as `unidentifiable`, with its evidence intact.

    **The finding with no keyword signature.** Ids 5 and 11 contain the words a regex
    could match; id 10 is an empty brand, a null date and the name "Unknown Device",
    and calling that unidentifiable is a judgment rather than a search. It is why
    ADR-0016 refuses to let the auditor degrade, and why ADR-0014's vocabulary is
    closed — "unidentifiable" is a claim a test can pin, where "this laptop seems old"
    is not.

    The model is mocked, so what this asserts is the plumbing: a finding the model made
    reaches an admin whole — every field of the shape, with the evidence still attached
    to the item it was about.
    """
    enable_ai(monkeypatch, app, reply={"findings": [UNIDENTIFIABLE]})

    response = admin_client.get(AUDIT_PATH)

    assert response.status_code == 200, response.text
    findings = _by_item(findings_of(response))
    assert UNKNOWN_DEVICE in findings, (
        "the model reported item 10 and the audit dropped it. This is the finding "
        "that proves the layer is not a regex (ADR-0016); got "
        f"{sorted(findings)}"
    )

    finding = findings[UNKNOWN_DEVICE]
    assert finding["kind"] == "unidentifiable", (
        "`kind` comes from ADR-0014's closed enum and must survive the round trip "
        f"unrenamed; got {finding['kind']!r}"
    )
    assert finding["evidence"].strip(), (
        "a finding without its evidence is an assertion an admin cannot check — the "
        f"quote is what makes it reviewable (ADR-0014); got {finding!r}"
    )
    assert finding["explanation"].strip(), (
        f"and the explanation is what makes it readable; got {finding!r}"
    )


def test_auditor_flags_status_notes_contradiction(
    monkeypatch, app, admin_client: TestClient
) -> None:
    """Ids 5 and 11 come back as `status_contradiction`, each quoting its own row.

    Both, not either: the Dell XPS's problem is in `notes` and the MacBook Air's is in
    `history`, and an auditor reading one column finds one of them. CONTEXT.md left
    both contradictions in the database on purpose — they are what this route exists
    to find.

    The evidence is asserted against the row it belongs to, so a serialiser that pairs
    the right findings with the wrong items fails here rather than looking correct in
    aggregate.
    """
    enable_ai(monkeypatch, app, reply={"findings": CONTRADICTIONS})

    response = admin_client.get(AUDIT_PATH)

    assert response.status_code == 200, response.text
    findings = _by_item(findings_of(response))
    for expected in CONTRADICTIONS:
        item_id = expected["item_id"]
        assert item_id in findings, (
            f"item {item_id} is one of the two semantic contradictions the seed keeps "
            f"on purpose (CONTEXT.md); got findings for {sorted(findings)}"
        )
        assert findings[item_id]["kind"] == "status_contradiction", (
            f"item {item_id} is Available while its own prose says otherwise; got "
            f"{findings[item_id]['kind']!r}"
        )
        assert findings[item_id]["evidence"] == expected["evidence"], (
            "the evidence must stay attached to the row it was quoted from; item "
            f"{item_id} came back with {findings[item_id]['evidence']!r}"
        )


def test_auditor_drops_off_enum_finding_kinds(
    monkeypatch, app, admin_client: TestClient
) -> None:
    """A kind outside the enum is dropped — never stored, never invented into it.

    ADR-0014's whole point: an open vocabulary lets the model assert the untestable
    ("this laptop seems old"), which is the prose ADR-0004 exists to avoid. So a reply
    mixing one legal finding with two invented kinds must come back as one finding —
    and the surviving one proves the drop was selective rather than a parse that failed
    wholesale and returned nothing.
    """
    enable_ai(
        monkeypatch,
        app,
        reply={
            "findings": [
                _finding(1, "looks_old", "purchased 2021-11-23", "Probably due for replacement."),
                UNIDENTIFIABLE,
                _finding(3, "needs_replacement", "Repair since 2021", "Long time in repair."),
            ]
        },
    )

    response = admin_client.get(AUDIT_PATH)

    assert response.status_code == 200, response.text
    findings = findings_of(response)
    kinds = {finding["kind"] for finding in findings}
    assert kinds <= FINDING_KINDS, (
        "the auditor's vocabulary is closed (ADR-0014): a kind the model invented is "
        f"dropped, not passed through and not added to the enum. Got {sorted(kinds)}"
    )
    assert {finding["item_id"] for finding in findings} == {UNKNOWN_DEVICE}, (
        "only the legal finding survives — items 1 and 3 were reported under kinds "
        "that do not exist, and a finding with no kind is not a finding. Got "
        f"{sorted(finding['item_id'] for finding in findings)}"
    )


def test_auditor_writes_nothing(monkeypatch, app, admin_client: TestClient) -> None:
    """Running the audit changes no row in any table, and flags nothing.

    "Proposes, never disposes" (ADR-0014) is the whole safety argument for pointing a
    model at the catalogue: `needs_review` is a rentability guard (ADR-0003), so an
    auditor that set it would be an LLM deciding what may be rented, and
    `review_reason` keeps human authors only. Findings are a computed payload —
    persisted nowhere, recomputed per run, so there is no staleness question and
    nothing for a demo reset to erase.

    The database is compared table by table rather than field by field, because the
    tempting implementation is not "set the flag" but "cache the run", and a check that
    named the columns it expected to be untouched would miss a new table entirely.
    """
    enable_ai(monkeypatch, app, reply={"findings": CONTRADICTIONS + [UNIDENTIFIABLE]})

    before_items = items_by_id(admin_client)
    before_counts = _row_counts(app)
    before_audit = audit_rows(app)
    before_rentals = rental_rows(app)
    assert before_items[DELL_XPS]["needs_review"] is False, (
        "setup: item 5 must start unflagged, or 'the auditor did not flag it' is "
        f"unfalsifiable; got {before_items[DELL_XPS]}"
    )

    response = admin_client.get(AUDIT_PATH)

    assert response.status_code == 200 and findings_of(response), (
        "setup: the audit must actually produce findings, or writing nothing is "
        f"trivially true. Got {response.status_code}: {response.text}"
    )

    after_items = items_by_id(admin_client)
    assert after_items[DELL_XPS]["needs_review"] is False, (
        "the auditor flagged item 5. It proposes and never disposes: `needs_review` "
        "blocks rental (ADR-0003), so setting it from a model's output is the LLM "
        "deciding what may be rented. A human acts on the finding, through the verb "
        "ADR-0017 adds"
    )
    assert after_items[DELL_XPS]["review_reason"] == before_items[DELL_XPS]["review_reason"], (
        "`review_reason` has human authors only — ingestion and the admin — never the "
        f"model (ADR-0014); got {after_items[DELL_XPS]['review_reason']!r}"
    )
    assert after_items == before_items, (
        "no hardware row may change: the audit is a read. Differences: "
        f"{[k for k in after_items if after_items[k] != before_items.get(k)]}"
    )
    assert _row_counts(app) == before_counts, (
        "findings are persisted nowhere and recomputed per run (ADR-0014) — no new "
        f"row, no new table. Before {before_counts}, after {_row_counts(app)}"
    )
    assert audit_rows(app) == before_audit, (
        "`audit_events` records what a human decided (ADR-0010). A machine's opinion "
        "is not an event, and gains an actor only when an admin acts on it"
    )
    assert rental_rows(app) == before_rentals, (
        "and nothing about rentals is the auditor's business"
    )
