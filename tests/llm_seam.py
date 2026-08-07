"""The one mocked seam for Phase 3, and the contract it pins.

`docs/specs/phase-3.md` fixes the provider (Gemini Flash), the variable
(`GEMINI_API_KEY`), and two properties of how it is read — **server-side only** and
**at request time**, so an absent key is feature-off rather than a boot refusal
(ADR-0016). It does not fix how a test replaces the model, and ADR-0004 requires that
every test does: the suite must never reach a live API.

So this module fixes it, in one place, the way `conftest.py` fixed the request shapes.

## The contract

| what                | where                                              |
| ------------------- | -------------------------------------------------- |
| the key             | ``os.environ["GEMINI_API_KEY"]``, read per request |
| the client          | ``app.state.llm``                                  |
| how it is called    | called with the prompt — ``llm(prompt)``, ``.complete(prompt)`` or ``.generate(prompt)`` |
| what it returns     | the model's **raw text**, nothing parsed           |
| how it fails        | it raises; the caller decides degrade or refuse    |

Raw text and not a parsed object, because parsing and schema validation are the
deterministic half of ADR-0004 — the half that has to be under test. A fake that
handed back an already-valid `FilterObject` would mock away
`test_search_is_not_an_oracle_over_notes`'s entire subject: what the code does when
the model says something it is not allowed to say.

Three call spellings are accepted because which one the implementation picks carries
no product meaning, and a test that goes red over a method name is testing a method
name.

## Why the socket is nailed shut

`no_live_api_calls` is autouse in both Phase 3 test modules. An implementation that
builds a real client instead of reading `app.state.llm` would otherwise quietly make
a network call with the fake key below — slow, flaky, and on a bad day billable. With
sockets refused, "the suite never calls the live API" is a property of the suite
rather than a hope. `TestClient` speaks ASGI in-process and opens none.
"""

from __future__ import annotations

import json
import socket
from typing import Any

import pytest

#: Distinctive on purpose: `test_llm_key_absent_from_frontend_bundle` searches the
#: built bundle and every response body for this literal.
FAKE_GEMINI_KEY = "gemini-test-key-3f81ac-not-a-real-credential"

SEARCH_PATH = "/api/search"
AUDIT_PATH = "/api/admin/audit"


class FakeModelError(RuntimeError):
    """What a timed-out or erroring provider looks like from the caller's side."""


class FakeModel:
    """A model that always says the same thing, or always fails the same way.

    Deterministic by construction: the reply does not depend on the prompt, so no
    test can pass because the prompt happened to contain a keyword.
    """

    def __init__(self, reply: Any = None, error: Exception | None = None) -> None:
        self._reply = reply
        self._error = error
        #: Every prompt this model was asked, so a test could assert it was asked at
        #: all. Nothing asserts on the prompt's *text* — that is the live smoke's job.
        self.prompts: list[str] = []

    def __call__(self, prompt: str = "", *_args: Any, **_kwargs: Any) -> str:
        self.prompts.append(prompt)
        if self._error is not None:
            raise self._error
        if isinstance(self._reply, str):
            return self._reply
        return json.dumps(self._reply)

    # The same seam under the names an implementation is likely to reach for.
    complete = __call__
    generate = __call__
    generate_content = __call__


def enable_ai(monkeypatch, app, *, reply: Any = None, error: Exception | None = None) -> FakeModel:
    """Turn the feature on with a key, and put a fake model behind it.

    Both halves matter. The key is what ADR-0016 makes the feature switch, and the
    fake is what keeps the request off the network — an implementation honouring one
    and not the other is exactly what these tests exist to catch.
    """
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_GEMINI_KEY)
    model = FakeModel(reply=reply, error=error)
    app.state.llm = model
    return model


def disable_ai(monkeypatch, app) -> None:
    """No key, no client — the state ADR-0016 calls feature-off."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app.state.llm = None


def search(client, query: str):
    """`POST /api/search` with the spec's body shape."""
    return client.post(SEARCH_PATH, json={"query": query})


def ids_in(response) -> set[int]:
    """The ids of the items a search answered with.

    Membership is the whole subject of ADR-0015: a `user` learns the Dell XPS has
    battery notes by seeing it *match*, whatever the serialiser did to the fields.
    """
    body = response.json()
    assert isinstance(body, dict) and "items" in body, (
        "`POST /api/search` answers `{\"mode\": …, \"items\": […]}` "
        f"(docs/specs/phase-3.md); got {body!r}"
    )
    return {item["id"] for item in body["items"]}


def mode_of(response) -> str:
    """Which path answered — asserted by tests, not just the rows (ADR-0016)."""
    body = response.json()
    assert isinstance(body, dict) and "mode" in body, (
        "every search response is labelled `semantic` or `keyword`: a fallback that "
        f"lies about being the primary is the bug (ADR-0016); got {body!r}"
    )
    return body["mode"]


def findings_of(response) -> list[dict[str, Any]]:
    """The auditor's findings, whether or not they arrived in an envelope.

    Tolerant of a bare list versus `{"findings": […]}` because the spec fixes the
    shape of a *finding* and not of the response around it.
    """
    body = response.json()
    if isinstance(body, dict):
        assert "findings" in body, (
            "the audit response must carry the findings under `findings`, or be the "
            f"list itself; got {sorted(body)}"
        )
        return body["findings"]
    return body


@pytest.fixture(autouse=True)
def no_live_api_calls(monkeypatch):
    """Refuse every outbound connection for the duration of a Phase 3 test."""

    def refuse(*_args: Any, **_kwargs: Any):
        raise AssertionError(
            "a Phase 3 test opened a network connection. The LLM is one seam "
            "(`app.state.llm`, see tests/llm_seam.py) and every test mocks it "
            "(ADR-0004) — the suite must never reach the live API."
        )

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
