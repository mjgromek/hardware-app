"""Phase 4 — clearing `needs_review` records what changed, not that somebody looked.

Amends ADR-0017's symmetry: `clear-review`'s mandatory reason must begin with
`fixed:` — "fixed: battery replaced, safe to issue" — validated server-side, `422`
otherwise. ADR-0010 accepted that a mandatory reason can be typed as "ok"; this is
the narrower claim that a *release* must at least assert a change of state, because
"somebody inspected this and it is fit to issue" is exactly the claim a later
incident interrogates, and "checked" records nothing an incident can use.

The check lives after authorization on purpose: a `user`'s refusal stays `403`
whatever their reason says (`test_non_admin_cannot_clear_review_flag` pins that with
a non-conforming reason), and only an authorized admin's prose is worth validating.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import audit_rows, clear_review_path, items_by_id

ACCEPTED = (200, 201, 204)

#: Seed id 6, flagged at import for its 2027 purchase date.
FLAGGED_ITEM = 6

RESOLUTION = "fixed: purchase date corrected in the asset register, safe to issue"


def _flag_of(client: TestClient, item_id: int) -> bool:
    return items_by_id(client)[item_id]["needs_review"]


def test_clear_reason_must_begin_with_fixed(admin_client: TestClient, app) -> None:
    """A reason that does not state a fix is refused — `422`, flag intact, no event.

    "Bench-tested by IT" says somebody looked; the amendment requires what *changed*.
    The refused attempts must leave no trace: a `422` that has already written the
    audit row files a mandatory reason against a release that never happened.
    """
    for reason in (
        "Bench-tested by IT; purchase date was a data-entry error",
        "checked, seems fine",
        "fixed",  # the word alone is not the prefix
    ):
        response = admin_client.post(clear_review_path(FLAGGED_ITEM), json={"reason": reason})
        assert response.status_code == 422, (
            f"a clear reason of {reason!r} must be refused as unprocessable — the "
            "release note must begin with 'fixed:' (ADR-0017 as amended). Got "
            f"{response.status_code}: {response.text}"
        )

    assert _flag_of(admin_client, FLAGGED_ITEM) is True, (
        "no refused attempt may have cleared the flag"
    )
    assert not audit_rows(app), (
        f"and none may have written an audit event; got {audit_rows(app)}"
    )


def test_bare_fixed_prefix_records_nothing_and_is_refused(admin_client: TestClient) -> None:
    """`fixed:` followed by nothing (or spaces) is the empty reason wearing a prefix."""
    for reason in ("fixed:", "fixed:   "):
        response = admin_client.post(clear_review_path(FLAGGED_ITEM), json={"reason": reason})
        assert response.status_code == 422, (
            f"{reason!r} asserts a fix and describes none; got "
            f"{response.status_code}: {response.text}"
        )
    assert _flag_of(admin_client, FLAGGED_ITEM) is True


def test_fixed_reason_clears_and_is_recorded_verbatim(
    admin_client: TestClient, user_client: TestClient, app
) -> None:
    """The conforming reason releases the item and lands in the audit row as typed.

    End to end on purpose: the flag drops, the item becomes rentable (ADR-0003's
    guard released through its own mechanism), and the audit event carries the
    admin's words — the record an incident reads later.
    """
    response = admin_client.post(clear_review_path(FLAGGED_ITEM), json={"reason": RESOLUTION})
    assert response.status_code in ACCEPTED, (
        f"a 'fixed:' reason must clear the flag; got {response.status_code}: "
        f"{response.text}"
    )
    assert _flag_of(admin_client, FLAGGED_ITEM) is False

    events = audit_rows(app, action="clear_review_flag")
    assert len(events) == 1 and events[0]["reason"] == RESOLUTION, (
        f"the resolution is recorded verbatim, once; got {audit_rows(app)}"
    )

    rentable = user_client.post(f"/api/hardware/{FLAGGED_ITEM}/rent")
    assert rentable.status_code in ACCEPTED, (
        "a cleared item is rentable — a flag that clears but still blocks is "
        f"decoration (ADR-0003); got {rentable.status_code}: {rentable.text}"
    )


def test_case_of_the_prefix_does_not_matter(admin_client: TestClient) -> None:
    """`FIXED: replaced the battery` is the same claim — refusing it teaches admins
    to game casing, not to write better release notes."""
    response = admin_client.post(
        clear_review_path(FLAGGED_ITEM), json={"reason": "FIXED: replaced the battery"}
    )
    assert response.status_code in ACCEPTED, (
        f"the prefix is case-insensitive; got {response.status_code}: {response.text}"
    )
