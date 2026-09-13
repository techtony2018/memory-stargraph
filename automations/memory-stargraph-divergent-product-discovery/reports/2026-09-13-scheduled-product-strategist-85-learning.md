---
type: Learning
title: Critical Reranker State Is Approval Packet Input, Not A Strategy TODO
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
product: products/memory-stargraph
status: active
source_run: runs/memory-stargraph-divergent-product-discovery-20260913t040118-0700-85
source_report: reports/memory-stargraph-divergent-product-discovery-20260913t040118-0700-85
tags:
  - discovery
  - learning
  - memory-stargraph
  - product-strategy
---

# Critical Reranker State Is Approval Packet Input, Not A Strategy TODO

When Memory Stargraph readiness exposes an approval-gated operational fix, Product Strategy should separate product evidence from execution authority. A Critical state can be real and user-relevant without authorizing Strategy to mutate configuration or create a duplicate SG TODO.

Evidence from `runs/memory-stargraph-divergent-product-discovery-20260913t040118-0700-85`: customer readiness on V1.0.217 reports GBrain reranker `critical` because the known ZeroEntropy default stopped working on 2026-09-04 and `configured_override=false`. Completed SG-0222 already created the bounded readiness surface and human-approved remediation/verification path, explicitly forbidding automatic GBrain upgrade or reranker configuration mutation. The same run also hit HTTP 502 from normal `/api/entity-save`; direct `gbrain import --no-embed` recovered artifact persistence, but Product Owner clarified that this is degraded recovery rather than proof that the normal write path is healthy.

Reusable rule: if a current readiness check is Critical but the remaining action is explicit Product Owner/operator approval, record it as approval-packet input and delivery evidence. If normal artifact persistence fails and a fallback succeeds, label the fallback as degraded recovery. Do not create a Strategy-promoted SG TODO, do not run the operator command, and do not mark either issue resolved until authorized post-approval or write-path verification exists.
