# ADR-0001: Code licence: MIT, with AGPL-3.0 dependencies noted

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The code should be easy to reuse, and it should match the companion repos (`bogota-pop`, `bogota-pop-viewer`), which are MIT. The main analysis dependency, cityseer, is licensed AGPL-3.0 (cityseer 5.8.0, `pyproject.toml`).

## Decision

The code in this repo is MIT licensed. The README states that running the pipeline installs AGPL-3.0 software (cityseer).

## Alternatives considered

- **AGPL-3.0 for the whole repo**, to match cityseer. Rejected: MIT code can be combined with AGPL code, and keeping MIT lets parts that don't touch cityseer (ingest, tiling) be reused freely.

## Consequences

Anyone who distributes a program built from this repo together with cityseer, or runs it as a network service, must meet AGPL-3.0 terms for that combined work. Published data outputs are not affected; their licence is ADR-0002.
