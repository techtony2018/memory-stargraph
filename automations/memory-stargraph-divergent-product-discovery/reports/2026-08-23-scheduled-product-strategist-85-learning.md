---
type: Learning
title: Active-Tag Metadata Drift Is A Readiness Risk
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
product: products/memory-stargraph
status: active
source_run: runs/memory-stargraph-divergent-product-discovery-20260823t040212-0700-85
source_report: reports/memory-stargraph-divergent-product-discovery-20260823t040212-0700-85
tags:
  - discovery
  - learning
  - memory-stargraph
  - product-strategy
---

# Active-Tag Metadata Drift Is A Readiness Risk

Active-tag readback is a coordination and readiness surface, not just artifact metadata. If completed historical Run/report pages retain or regain standalone `active` tags, workers can falsely infer unsafe concurrency, stale leases, or unfinished work.

Evidence from `runs/memory-stargraph-divergent-product-discovery-20260823t040212-0700-85`: source-sync was current on V1.0.198, SG-0207/SG-0208 had terminal evidence that global active tags were clear on 2026-08-17, but `gbrain list --tag active -n 50` on 2026-08-23 returned historical completed artifacts. Raw readback of `reports/memory-stargraph-wish-sg0205-20260815t033202-0700-49bc24b` still showed `tags: active` with completed status and `active_change: false`.

Reusable rule: when Product Strategy finds stale active-tag evidence on completed artifacts, do not clear tags directly from the strategy role. Attempt promotion only through the official SG TODO helper. If the helper blocks because TODO archive high-water evidence has gaps, preserve the product candidate and blocker in the Run/report, then request Product Owner/Developer governance rather than manually allocating a TODO ID.
