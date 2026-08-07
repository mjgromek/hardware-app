"""Phase 3 Slice A — semantic search, announced degradation, and the oracle it must not be.

`POST /api/search` takes `{"query": "<natural language>"}` behind a session and answers
`{"mode": "semantic" | "keyword", "items": [...]}`. The model's only job is to emit a
filter object over public columns; SQLite is queried through that object and never
through the model's prose (ADR-0004).

**Every test here mocks the model** — `tests/llm_seam.py` holds the seam and the
contract, and an autouse fixture refuses outbound sockets so the claim is enforced
rather than asserted in a docstring.

Three things these tests are careful about:

*Mode is asserted, not inferred.* A keyword fallback that returns plausible rows while
labelling itself `semantic` is the specific bug ADR-0016 exists to prevent, and rows
alone cannot see it.

*Result sets, not field values.* ADR-0012 already nulls `notes` for a `user`, and
`test_field_visibility.py` pins that. The leak Slice A can still open is **membership**:
if the filter can express a predicate over `notes`, a `user` learns the Dell XPS has
battery notes by watching it match, fields nulled or not (ADR-0015).

*Expectations are derived from the inventory, not hardcoded.* Which ids are flagged or
in Repair is ingestion's business (ADR-0002) and is asserted in its own tests; a search
test that hardcoded them would go red when the seed changed, in a file that has nothing
to say about the seed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ANONYMOUS_REFUSAL, HARDWARE_PATH, items_by_id
from tests.llm_seam import (  # noqa: F401 — `no_live_api_calls` is autouse here
    FAKE_GEMINI_KEY,
    FakeModelError,
    SEARCH_PATH,
    disable_ai,
    enable_ai,
    ids_in,
    mode_of,
    no_live_api_calls,
    search,
)

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"

#: Seed id 5. `Available`, and the only thing that connects it to a battery problem is
#: its `notes` — which is what makes it the oracle's test case (CONTEXT.md).
DELL_XPS = 5

#: A query no public column can answer. The Dell XPS must not come back from it.
NOTES_QUERY = "which laptops have battery swelling problems"

#: A query the public columns *can* answer, used as the control: without it, an
#: implementation that returns nothing for everything would pass the oracle test.
BRAND_QUERY = "Dell"

#: Seed id 6, the Logitech MX Master 3 — matched by no phone, tablet or laptop term,
#: which is what makes it the ride-along detector for `name_matches_any`.
MOUSE = 6


def test_search_requires_a_session(anonymous_client: TestClient) -> None:
    """Nobody signed out gets to ask the inventory anything (ADR-0006).

    Search is a data route and reads the same rows `GET /api/hardware` does, so it
    inherits the same rule. The one deliberate exception stays `GET /`, because the
    login page has to be reachable by someone who is not logged in.
    """
    response = search(anonymous_client, BRAND_QUERY)

    assert response.status_code in ANONYMOUS_REFUSAL, (
        "`POST /api/search` is a data route: no session, no answer (ADR-0006). Got "
        f"{response.status_code}: {response.text}"
    )
    assert "items" not in response.text, (
        "a refused search must not carry inventory in its body — the status code is "
        f"not the guard, the absent payload is; got {response.text}"
    )


def test_semantic_query_maps_to_filter_schema(
    monkeypatch, app, admin_client: TestClient
) -> None:
    """The model's filter object is what selects the rows — deterministically.

    The fake emits `{"brand": "Apple", "status": "Available"}` whatever the prompt is,
    so the expected result set is computable from the inventory alone: exactly the
    Apple-branded items that are Available. Asserted as set equality rather than
    "contains", because a filter that is parsed and then ignored returns a superset and
    would satisfy any weaker assertion — that is the failure mode where the AI layer
    looks like it works and is really returning the whole catalogue.

    `Appel` (seed id 9) is excluded by the same equality: `brand` is case-insensitive
    equality, not fuzzy matching, and the typo is the auditor's to find (ADR-0002).
    """
    inventory = items_by_id(admin_client)
    expected = {
        item_id
        for item_id, item in inventory.items()
        if (item.get("brand") or "").lower() == "apple" and item["status"] == "Available"
    }
    assert expected and expected != set(inventory), (
        "setup: the seed must contain some but not all Apple/Available items, or this "
        f"test cannot tell a filter from a passthrough; got {sorted(expected)} of "
        f"{sorted(inventory)}"
    )

    enable_ai(monkeypatch, app, reply={"brand": "Apple", "status": "Available"})

    response = search(admin_client, "apple gear we could hand out today")

    assert response.status_code == 200, response.text
    assert mode_of(response) == "semantic", (
        "the model answered, so the response must say so: `semantic` is a claim about "
        f"which path ran (ADR-0016); got {response.json()}"
    )
    assert ids_in(response) == expected, (
        "the rows must come from the filter object the model emitted — brand and "
        "status, applied to SQLite (ADR-0004). Expected exactly "
        f"{sorted(expected)}, got {sorted(ids_in(response))}"
    )


def test_semantic_search_falls_back_on_api_error(
    monkeypatch, app, admin_client: TestClient
) -> None:
    """When the provider fails, search degrades to keyword — and says it did.

    Two claims, and the second is the one ADR-0016 was written for: `mode` must read
    `keyword`. A fallback that answers `semantic` makes the README's "graceful
    fallback" unverifiable, and makes a reviewer unable to tell whether the AI ever
    ran at all.

    The rows are asserted too, weakly — the feature degrades, it never breaks
    (CONTEXT.md), so a `500` or an empty answer to a query with an obvious keyword
    match is a failure of the fallback rather than of the model.
    """
    enable_ai(monkeypatch, app, error=FakeModelError("504 deadline exceeded"))

    response = search(admin_client, BRAND_QUERY)

    assert response.status_code == 200, (
        "a failed model call must degrade, not break: the employee still gets their "
        f"inventory. Got {response.status_code}: {response.text}"
    )
    assert mode_of(response) == "keyword", (
        "the provider errored, so this is the degraded path and the response has to "
        f"admit it (ADR-0016); got {response.json()['mode']!r}"
    )
    assert DELL_XPS in ids_in(response), (
        f"the keyword fallback searches `name` and `brand`, and {BRAND_QUERY!r} is the "
        f"Dell XPS's brand — it must still be found; got {sorted(ids_in(response))}"
    )


def test_semantic_search_never_returns_unrentable_items(
    monkeypatch, app, user_client: TestClient, admin_client: TestClient
) -> None:
    """`rentable_only` excludes Repair *and* flagged items — one rule, not two.

    ADR-0003 makes `needs_review` block rental with the same `409` as `Repair`, so a
    filter that honoured only the status would offer an employee a laptop the rent
    route is about to refuse them. The exclusion set is read off the inventory rather
    than hardcoded, and asserted non-empty first: on a catalogue where nothing is
    flagged this test proves nothing, and it should say so rather than pass.
    """
    inventory = items_by_id(admin_client)
    unrentable = {
        item_id
        for item_id, item in inventory.items()
        if item["status"] == "Repair" or item["needs_review"]
    }
    assert unrentable, (
        "setup: the seed must contain at least one Repair or flagged item, or "
        "`rentable_only` has nothing to exclude"
    )

    enable_ai(monkeypatch, app, reply={"rentable_only": True})

    response = search(user_client, "something I can take out this afternoon")

    assert response.status_code == 200, response.text
    returned = ids_in(response)
    assert not returned & unrentable, (
        "`rentable_only` must exclude flagged items through the same rule as Repair "
        "(ADR-0003) — offering an item the rent route will refuse is worse than "
        f"offering nothing. Unrentable: {sorted(unrentable)}, returned: "
        f"{sorted(returned)}"
    )
    assert returned, (
        "and something must come back: an empty answer satisfies the exclusion "
        "trivially and would hide a filter that excludes everything"
    )


@pytest.mark.parametrize("path", ["semantic", "keyword"])
def test_search_is_not_an_oracle_over_notes(
    monkeypatch, app, user_client: TestClient, path: str
) -> None:
    """A `user` cannot learn the Dell XPS has battery notes by watching it match.

    ADR-0015's leak is **membership**, not field values: `visible_to` nulls `notes` for
    a `user` already, and the item appearing in the result set for "battery swelling
    problems" tells them what the nulled field says regardless.

    Both paths, because the fallback is where the rule usually rots — a keyword search
    that grew a `LIKE` over `notes` leaks exactly what the schema forbade.

    On the semantic path the fake emits `{"name_contains": "XPS", "notes_contains":
    "swelling"}` — one legal field and one that does not exist. The spec allows no
    partial salvage: a half-valid filter is a wrong filter, so keeping `name_contains`
    and dropping the rest would answer the forbidden question through the permitted
    field. The whole object is refused or the leak is open.

    The control runs first on both paths. Without it, an endpoint that answered every
    query with `[]` would be the best-scoring implementation in this file.
    """
    disable_ai(monkeypatch, app)
    control = search(user_client, BRAND_QUERY)
    assert control.status_code == 200 and DELL_XPS in ids_in(control), (
        "setup: search must be able to return the Dell XPS at all, or 'it did not "
        f"come back' means nothing. Got {control.status_code}: {control.text}"
    )

    if path == "semantic":
        enable_ai(
            monkeypatch,
            app,
            reply={"name_contains": "XPS", "notes_contains": "swelling"},
        )

    response = search(user_client, NOTES_QUERY)

    assert response.status_code == 200, (
        "a query the schema cannot express is answered, not errored — the model "
        f"saying something illegal is an expected event. Got {response.status_code}: "
        f"{response.text}"
    )
    assert DELL_XPS not in ids_in(response), (
        f"the {path} path made search an oracle over `notes`: a `user` asked which "
        "items have battery problems and item 5 came back, which tells them what "
        "their nulled `notes` field says (ADR-0015). The filter schema has no "
        "`notes`/`history`/`review_reason` predicate for anyone, and the keyword "
        f"fallback searches `name` and `brand` only. Got {sorted(ids_in(response))}"
    )


def test_category_query_maps_to_concrete_product_terms(
    monkeypatch, app, admin_client: TestClient
) -> None:
    """"Something to test a mobile app on" finds the phones and the tablet.

    No item's name contains "mobile" and the schema has no category column, so the
    model's contribution is *vocabulary*: `name_matches_any` carries the concrete
    product terms it infers — and SQLite still decides which rows exist (ADR-0004).
    The mock emits the terms, so what this pins is the plumbing: OR within the list,
    case-insensitive, against `name` and `brand`, and nothing else sneaking in.

    Expected ids are derived with a plain Python containment check — independent of
    the SQL that implements the predicate — and the mouse is asserted absent by id,
    because "the terms matched something" must not decay into "everything matched".
    """
    terms = ["iPhone", "Galaxy", "iPad"]
    inventory = items_by_id(admin_client)
    expected = {
        item_id
        for item_id, item in inventory.items()
        if any(
            term.lower() in (item["name"] or "").lower()
            or term.lower() in (item["brand"] or "").lower()
            for term in terms
        )
    }
    assert expected and MOUSE not in expected and expected != set(inventory), (
        "setup: the seed must contain some but not all term-matched items, and the "
        f"mouse must not be one of them; got {sorted(expected)} of {sorted(inventory)}"
    )

    enable_ai(monkeypatch, app, reply={"name_matches_any": terms})

    response = search(admin_client, "something to test a mobile app on")

    assert response.status_code == 200, response.text
    assert mode_of(response) == "semantic", (
        f"the model answered, so the label says so (ADR-0016); got {response.json()}"
    )
    assert ids_in(response) == expected, (
        "`name_matches_any` is OR-within-the-list, case-insensitive, over `name` and "
        f"`brand` only. Expected exactly {sorted(expected)}, got "
        f"{sorted(ids_in(response))}"
    )
    assert MOUSE not in ids_in(response), (
        "the mouse matches no term and must not ride along — a predicate that "
        "degenerates into the whole catalogue is a passthrough wearing a filter's name"
    )


def test_category_terms_match_name_and_brand_case_insensitively(
    monkeypatch, app, admin_client: TestClient
) -> None:
    """"laptop" finds the MacBooks and the XPS, and never the mouse.

    The model turns the category word into concrete product terms
    (`["MacBook", "XPS", "ThinkPad", "Latitude"]`); terms that match nothing in this
    inventory are simply inert, and lowercase "macbook" must still find "MacBook" —
    the model's casing is not part of the contract.
    """
    terms = ["macbook", "XPS", "ThinkPad", "Latitude"]
    inventory = items_by_id(admin_client)
    expected = {
        item_id
        for item_id, item in inventory.items()
        if any(
            term.lower() in (item["name"] or "").lower()
            or term.lower() in (item["brand"] or "").lower()
            for term in terms
        )
    }
    assert expected and MOUSE not in expected, (
        f"setup: the laptop terms must match something and never the mouse; got "
        f"{sorted(expected)}"
    )

    enable_ai(monkeypatch, app, reply={"name_matches_any": terms})

    response = search(admin_client, "laptop")

    assert response.status_code == 200, response.text
    assert mode_of(response) == "semantic", response.text
    assert ids_in(response) == expected, (
        f"expected exactly the laptop-term matches {sorted(expected)}; got "
        f"{sorted(ids_in(response))}"
    )


def test_llm_key_absent_from_frontend_bundle(
    monkeypatch, app, user_client: TestClient
) -> None:
    """`GEMINI_API_KEY` is server-side only — not in the bundle, not in a response.

    The provider is called from FastAPI or it is called from the browser; there is no
    third option, and the second one publishes the key to every employee with a
    devtools tab. The bundle is checked for the literal key *and* for the string
    `gemini` at all, because a `VITE_GEMINI_*` reference in the source is a key in the
    bundle at the next `npm run build` — the failure would ship one commit later, in a
    commit that changed no test.

    Response bodies are checked separately: a search that echoes its configuration
    back for debugging leaks the same secret through a different door.
    """
    enable_ai(monkeypatch, app, reply={"brand": "Dell"})

    for source in sorted(FRONTEND.glob("dist/**/*")) + sorted(FRONTEND.glob("src/**/*")):
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8", errors="ignore").lower()
        assert FAKE_GEMINI_KEY.lower() not in text, (
            f"{source} carries the API key. Secrets are server-side only"
        )
        assert "gemini" not in text, (
            f"{source} mentions the provider. Nothing in the frontend may name the "
            "LLM key — a `VITE_GEMINI_*` reference is a published credential at the "
            "next build, and the call belongs behind FastAPI"
        )

    responses = [
        user_client.get("/"),
        user_client.get(HARDWARE_PATH),
        user_client.post(SEARCH_PATH, json={"query": BRAND_QUERY}),
    ]
    for response in responses:
        assert FAKE_GEMINI_KEY.lower() not in response.text.lower(), (
            f"{response.request.method} {response.request.url.path} echoed the API "
            "key back to the browser"
        )
