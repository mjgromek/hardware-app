# ADR-0001 — Single-origin deployment

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** `brainstorm.md` §11 (platform choice); whole-project grilling, Q2

## Context

§11 settled the *platform*: Railway over Vercel, because Vercel's ephemeral
filesystem resets a file-based SQLite database on every cold start, and Railway
offers a persistent volume alongside the FastAPI process.

It did not settle the *topology*. "Single repo" is not "single origin", and the
difference is load-bearing: it decides whether the frontend and API share a host,
which in turn decides the CORS story, the cookie policy available to the auth
layer, and how many deploy pipelines exist.

Left undecided, this blocks the auth mechanism decision — a same-site cookie is
trivial on one origin and requires `SameSite=None; Secure` plus CSRF handling
across two.

## Decision

One Railway service. FastAPI serves the built Vue bundle as static files from
`dist/`, and SQLite lives on the attached persistent volume. API and UI share a
single origin.

## Consequences

- **There is no CORS configuration**, because there is no cross-origin request to
  configure.

- **This deletes `test_cors_rejects_unknown_origin` from the §11 test list.** No
  cross-origin path exists for the application to reject, so the test would assert
  a condition the architecture already makes unreachable. A test that cannot
  meaningfully fail is worse than an absent one — it reads as cargo cult to anyone
  reviewing the suite. It is replaced by an authorization test that exercises a
  path that genuinely exists.

- Cookie-based auth becomes same-site by construction, removing CSRF handling and
  the `SameSite=None` cookie configuration from scope.

- One deploy pipeline, one URL, one environment-variable set. The LLM API key has
  exactly one place to live, server-side, which is what §10 "Guardrails" requires.

- The frontend build step must be wired into the deploy, so a broken Vue build now
  fails the API deploy as well. The two are no longer independently shippable.

- **Trade-off accepted:** static assets are served by the Python process rather
  than a CDN, and the frontend cannot scale or roll back independently of the API.
  At this size neither cost is real, but both would be at production scale, and
  this is the reasoning that would have to be revisited first.
