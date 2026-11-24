# ADR-0011: Add angular density, farness and Hillier integration

- **Status:** Accepted
- **Date:** 2026-11-23
- **Extends:** ADR-0009

## Context

ADR-0009 chose simplest-path closeness and betweenness. cityseer 5.8's `CityNetwork.centrality_simplest` emits only `cc_harmonic_<d>_ang` and `cc_betweenness_<d>_ang` by default. It can compute more measures from the same routes, if asked for them by expression.

Two of them matter for reading the results. The analysis is unweighted (ADR-0009), so a fine grid of short segments scores high partly because it has more segments; density shows how many segments each one reaches. Space syntax's normalised measures also need density and total depth: normalised integration, and normalised choice (NACH), which divides choice by a function of total depth.

## Decision

The city and pilot runs also compute, at every distance:

- `cc_density_<d>_ang`: segments reachable within the distance (`1` per segment).
- `cc_farness_<d>_ang`: angular total depth (`1 + c/90` per segment, where *c* is the degrees of turning on the simplest route).
- `cc_hillier_<d>_ang`: Hillier's normalised integration, `density² / farness`.

The expressions are cityseer 5.8's own defaults for these names. They are written out in `config/analysis.yaml` (`centrality:`), so a change in cityseer's defaults can't change the results silently. Harmonic closeness and betweenness are unchanged.

## Alternatives considered

- **Compute NACH and other normalisations inside cityseer.** Not yet: NACH is derived from betweenness and farness, so it can be computed from the output when it's needed.
- **Keep only the two measures.** Rejected: density and farness come from the same calculation at little extra cost, and they're needed to read and normalise the other two.

## Consequences

- Five columns per distance instead of two (30 in all).
- Dead segments get no closeness-type values (density, farness, harmonic, Hillier), as before.
