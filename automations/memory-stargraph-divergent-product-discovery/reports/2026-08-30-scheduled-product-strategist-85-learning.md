---
type: Learning
title: Use Search Coverage Fields Before Judging Search Health
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
product: products/memory-stargraph
status: active
source_run: runs/memory-stargraph-divergent-product-discovery-20260830t040141-0700-85
source_report: reports/memory-stargraph-divergent-product-discovery-20260830t040141-0700-85
tags:
  - discovery
  - learning
  - memory-stargraph
  - product-strategy
---

# Use Search Coverage Fields Before Judging Search Health

Memory Stargraph `/api/search` responses can expose matched slugs under `graph.source.coverage.search_slugs` rather than a top-level `results` array. Product Strategy should verify the actual response shape before treating an empty parsed field as evidence of search failure.

Evidence from `runs/memory-stargraph-divergent-product-discovery-20260830t040141-0700-85`: an initial parser looking for top-level `.results` made known current queries appear empty. After inspecting the response shape, corrected probes for SG-0217, SG-0221, Ask Yoda MCP-only retrieval, Memory Stargraph, and people/stacey-soong returned `search_status=complete` with expected slugs and fast elapsed times.

Reusable rule: before proposing or promoting any search-health product gap, cite the concrete API fields used for evidence. If `/api/search` is used, inspect `graph.source.coverage.search_slugs`, `search_status`, `source_status`, and elapsed time. Do not create a TODO from a missing parser field.
