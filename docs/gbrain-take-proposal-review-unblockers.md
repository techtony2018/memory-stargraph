# GBrain Take Proposal Review Unblockers

This note records the GBrain-side patch needed to unblock Memory Stargraph SG-0092 Take Review. It is intentionally sanitized: no private hostnames, tokens, service paths, or deployment targets belong in this tracked file.

## Current State

- Memory Stargraph V1.0.122 has a bounded Take Review UI/proxy shell, but the active GBrain remote tool surface lacks `take_proposals_*` review operations.
- The local `gbrain` CLI is configured as a thin client. During the SG-0093/SG-0094 run, `gbrain get notes/memory-starmap-todo-list` and `gbrain remote doctor` failed at OAuth discovery with a network reachability error, so GBrain backlog statuses could not be transitioned from this environment.
- Local GBrain source inspection found the table already exists in `src/schema.sql` as `take_proposals`, with `status IN ('pending','accepted','rejected','superseded')`.
- Existing generated MCP operations expose `takes_list` and `takes_search`, but no proposal-review tools.

## Required Hosted Tools

Add these generated operations in GBrain `src/core/operations.ts` so both stdio and HTTP MCP expose them through the existing contract-first surface:

| operation | scope | mutating | remote | behavior |
| --- | --- | --- | --- | --- |
| `take_proposals_list` | `read` | no | yes | List pending proposals, source-scoped by `sourceScopeOpts(ctx)` and holder-filtered by `ctx.takesHoldersAllowList` when set. |
| `take_proposals_accept` | `write` | yes | yes | Promote one pending proposal into the page takes fence and DB index, then mark proposal `accepted` with `acted_at`, `acted_by`, and `promoted_row_num`. |
| `take_proposals_reject` | `write` | yes | yes | Mark one pending proposal `rejected` with `acted_at` and `acted_by`. |
| `take_proposals_defer` | `read` | no | yes | Return the selected pending proposal as deferred without changing DB state. This preserves the current schema because `deferred` is not an allowed status. The UI can hide it for the current review session. |
| `take_proposals_bulk` | `write` | yes | yes | Apply a bounded array of accept/reject/defer actions and return per-item results. |

## Security Contract

- All list/action queries must call `sourceScopeOpts(ctx)`.
- If `sourceIds` is present, it wins over scalar `sourceId`.
- Holder allow-list filtering must apply to proposals the same way it applies to `takes_list`: when `ctx.takesHoldersAllowList` is present, only proposals whose `holder` is in that list are visible or actionable.
- `accept` must only promote a proposal that is visible under the same source and holder filters.
- `accept` must lock the page with existing `withPageLock`, update the markdown takes fence via `upsertTakeRow`, write the page file, then call `engine.addTakesBatch`.
- If `sync.repo_path` is unavailable or the page markdown file cannot be updated, `accept` should fail before mutating `take_proposals`.

## GBrain Patch

Apply this in the GBrain repo, not in Memory Stargraph. The current local GBrain checkout observed during this run was dirty on an unrelated branch, so this patch is documented here for a future clean GBrain PR.

### `src/core/operations.ts`

Add imports near the existing operation imports:

```ts
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { withPageLock } from './page-lock.ts';
import { upsertTakeRow } from './takes-fence.ts';
```

Add helper types/functions near the existing `takes_list` and `takes_search` operations:

```ts
type TakeProposalAction = 'accept' | 'reject' | 'defer';

interface TakeProposalRow {
  id: number;
  source_id: string;
  page_slug: string;
  status: 'pending' | 'accepted' | 'rejected' | 'superseded';
  claim_text: string;
  kind: string;
  holder: string;
  weight: number;
  domain: string | null;
  proposed_at: string;
  proposal_run_id: string;
  prompt_version: string;
  wave_version: string;
  model_id: string;
  acted_at: string | null;
  acted_by: string | null;
  promoted_row_num: number | null;
}

function actorForProposalAction(ctx: OperationContext): string {
  const clientId = ctx.auth?.client_id ? String(ctx.auth.client_id).slice(0, 8) : 'local';
  return ctx.remote ? `mcp:${clientId}` : 'local';
}

function proposalScopeWhere(scope: { sourceId?: string; sourceIds?: string[] }): {
  sql: string;
  params: unknown[];
} {
  if (scope.sourceIds && scope.sourceIds.length > 0) {
    return { sql: 'tp.source_id = ANY($1::text[])', params: [scope.sourceIds] };
  }
  return { sql: 'tp.source_id = $1::text', params: [scope.sourceId ?? 'default'] };
}
```

Add operations after `takes_search`:

```ts
const take_proposals_list: Operation = {
  name: 'take_proposals_list',
  description: 'List pending take proposals for human review.',
  scope: 'read',
  params: {
    status: { type: 'string', description: 'Proposal status filter. Default pending.' },
    page_slug: { type: 'string', description: 'Optional page slug filter.' },
    holder: { type: 'string', description: 'Optional holder filter.' },
    limit: { type: 'number', description: 'Max rows, default 50, cap 200.' },
    offset: { type: 'number', description: 'Skip first N rows.' },
  },
  handler: async (ctx, p) => {
    const scope = sourceScopeOpts(ctx);
    const scoped = proposalScopeWhere(scope);
    const limit = clampSearchLimit(p.limit as number | undefined, 50, 200);
    const offset = Math.max(0, Math.floor((p.offset as number | undefined) ?? 0));
    const status = String(p.status || 'pending');
    const rows = await ctx.engine.executeRaw<TakeProposalRow>(
      `SELECT tp.*
         FROM take_proposals tp
        WHERE ${scoped.sql}
          AND tp.status = $${scoped.params.length + 1}
          AND ($${scoped.params.length + 2}::text IS NULL OR tp.page_slug = $${scoped.params.length + 2}::text)
          AND ($${scoped.params.length + 3}::text IS NULL OR tp.holder = $${scoped.params.length + 3}::text)
          AND ($${scoped.params.length + 4}::text[] IS NULL OR tp.holder = ANY($${scoped.params.length + 4}::text[]))
        ORDER BY tp.proposed_at DESC, tp.id DESC
        LIMIT $${scoped.params.length + 5} OFFSET $${scoped.params.length + 6}`,
      [
        ...scoped.params,
        status,
        p.page_slug || null,
        p.holder || null,
        ctx.takesHoldersAllowList ?? null,
        limit,
        offset,
      ],
    );
    return rows;
  },
};

async function getVisiblePendingProposal(
  ctx: OperationContext,
  id: number,
): Promise<TakeProposalRow> {
  const scope = sourceScopeOpts(ctx);
  const scoped = proposalScopeWhere(scope);
  const rows = await ctx.engine.executeRaw<TakeProposalRow>(
    `SELECT tp.*
       FROM take_proposals tp
      WHERE ${scoped.sql}
        AND tp.id = $${scoped.params.length + 1}
        AND tp.status = 'pending'
        AND ($${scoped.params.length + 2}::text[] IS NULL OR tp.holder = ANY($${scoped.params.length + 2}::text[]))
      LIMIT 1`,
    [...scoped.params, id, ctx.takesHoldersAllowList ?? null],
  );
  if (!rows[0]) {
    throw new OperationError('proposal_not_found', `No visible pending take proposal found for id=${id}`);
  }
  return rows[0];
}

async function acceptTakeProposal(ctx: OperationContext, id: number): Promise<Record<string, unknown>> {
  const proposal = await getVisiblePendingProposal(ctx, id);
  const page = await ctx.engine.getPage(proposal.page_slug, sourceScopeOpts(ctx));
  if (!page) throw new OperationError('page_not_found', `Page not found for proposal: ${proposal.page_slug}`);

  const repoPath = await ctx.engine.getConfig('sync.repo_path');
  if (!repoPath) throw new OperationError('repo_path_required', 'sync.repo_path is required to accept take proposals');
  const filePath = join(repoPath, `${proposal.page_slug}.md`);
  if (!existsSync(filePath)) throw new OperationError('page_file_missing', `Page file not found: ${proposal.page_slug}.md`);

  let promotedRowNum = 0;
  await withPageLock(proposal.page_slug, async () => {
    const body = readFileSync(filePath, 'utf-8');
    const updated = upsertTakeRow(body, {
      claim: proposal.claim_text,
      kind: proposal.kind,
      holder: proposal.holder,
      weight: proposal.weight,
      source: `take_proposal:${proposal.id}`,
      active: true,
    });
    mkdirSync(dirname(filePath), { recursive: true });
    writeFileSync(filePath, updated.body, 'utf-8');
    promotedRowNum = updated.rowNum;
    await ctx.engine.addTakesBatch([{
      page_id: page.id,
      row_num: promotedRowNum,
      claim: proposal.claim_text,
      kind: proposal.kind,
      holder: proposal.holder,
      weight: proposal.weight,
      source: `take_proposal:${proposal.id}`,
      active: true,
      superseded_by: null,
    }]);
    await ctx.engine.executeRaw(
      `UPDATE take_proposals
          SET status = 'accepted',
              acted_at = now(),
              acted_by = $2,
              promoted_row_num = $3
        WHERE id = $1 AND status = 'pending'`,
      [id, actorForProposalAction(ctx), promotedRowNum],
    );
  });
  return { ok: true, action: 'accept', id, page_slug: proposal.page_slug, promoted_row_num: promotedRowNum };
}

async function rejectTakeProposal(ctx: OperationContext, id: number): Promise<Record<string, unknown>> {
  const proposal = await getVisiblePendingProposal(ctx, id);
  await ctx.engine.executeRaw(
    `UPDATE take_proposals
        SET status = 'rejected',
            acted_at = now(),
            acted_by = $2
      WHERE id = $1 AND status = 'pending'`,
    [id, actorForProposalAction(ctx)],
  );
  return { ok: true, action: 'reject', id, page_slug: proposal.page_slug };
}

const take_proposals_accept: Operation = {
  name: 'take_proposals_accept',
  description: 'Accept one visible pending take proposal and promote it into the canonical takes fence.',
  scope: 'write',
  mutating: true,
  params: { id: { type: 'number', required: true } },
  handler: async (ctx, p) => acceptTakeProposal(ctx, Number(p.id)),
};

const take_proposals_reject: Operation = {
  name: 'take_proposals_reject',
  description: 'Reject one visible pending take proposal.',
  scope: 'write',
  mutating: true,
  params: { id: { type: 'number', required: true } },
  handler: async (ctx, p) => rejectTakeProposal(ctx, Number(p.id)),
};

const take_proposals_defer: Operation = {
  name: 'take_proposals_defer',
  description: 'Defer one visible pending take proposal for the current review session without changing DB state.',
  scope: 'read',
  params: { id: { type: 'number', required: true } },
  handler: async (ctx, p) => ({ ok: true, action: 'defer', proposal: await getVisiblePendingProposal(ctx, Number(p.id)) }),
};

const take_proposals_bulk: Operation = {
  name: 'take_proposals_bulk',
  description: 'Apply a bounded batch of take proposal review actions.',
  scope: 'write',
  mutating: true,
  params: {
    actions: {
      type: 'array',
      required: true,
      items: { type: 'object' },
      description: 'Array of {id:number, action:"accept"|"reject"|"defer"}, max 50.',
    },
  },
  handler: async (ctx, p) => {
    const actions = Array.isArray(p.actions) ? p.actions.slice(0, 50) : [];
    const results = [];
    for (const raw of actions) {
      const item = raw as { id?: unknown; action?: unknown };
      const id = Number(item.id);
      const action = String(item.action || '') as TakeProposalAction;
      try {
        if (!Number.isFinite(id)) throw new OperationError('invalid_id', 'action id must be a number');
        if (action === 'accept') results.push(await acceptTakeProposal(ctx, id));
        else if (action === 'reject') results.push(await rejectTakeProposal(ctx, id));
        else if (action === 'defer') results.push({ ok: true, action, proposal: await getVisiblePendingProposal(ctx, id) });
        else throw new OperationError('invalid_action', `Unsupported proposal action: ${String(item.action)}`);
      } catch (err) {
        results.push({ ok: false, id, action, error: err instanceof Error ? err.message : String(err) });
      }
    }
    return { ok: true, results };
  },
};
```

Finally, add the five operations to the exported `operations` array near the other takes operations so `buildToolDefs` exposes them automatically.

### Tests To Add

Add a PGLite dispatch test similar to `test/takes-mcp-allowlist.serial.test.ts`:

```ts
test('take_proposals_list source-scopes and holder-filters pending proposals', async () => {
  const result = await dispatchToolCall(engine, 'take_proposals_list', {}, {
    remote: true,
    sourceId: 'default',
    takesHoldersAllowList: ['world'],
  });
  const rows = JSON.parse(result.content[0].text);
  expect(rows.every((row: { source_id: string; holder: string; status: string }) =>
    row.source_id === 'default' && row.holder === 'world' && row.status === 'pending'
  )).toBe(true);
});

test('take_proposals_reject cannot act on hidden holders', async () => {
  const result = await dispatchToolCall(engine, 'take_proposals_reject', { id: privateProposalId }, {
    remote: true,
    takesHoldersAllowList: ['world'],
  });
  expect(result.isError).toBe(true);
  expect(result.content[0].text).toContain('No visible pending take proposal');
});

test('take_proposals_accept promotes visible proposal and records acted fields', async () => {
  const result = await dispatchToolCall(engine, 'take_proposals_accept', { id: worldProposalId }, {
    remote: true,
    takesHoldersAllowList: ['world'],
  });
  expect(result.isError).toBeFalsy();
  const accepted = JSON.parse(result.content[0].text);
  expect(accepted.promoted_row_num).toBeGreaterThan(0);
});
```

The accept test needs a temporary `sync.repo_path` and markdown page file so it verifies the fence write, not only DB state.

## Thin Client Patch/Docs

After the hosted operations ship, verify the thin client exposes them through remote MCP:

```bash
gbrain remote doctor
gbrain call take_proposals_list '{"limit":5}'
gbrain call take_proposals_defer '{"id":1}'
```

If `gbrain call` cannot route these operations, patch the thin-client operation allow-list/routing table to include:

```text
take_proposals_list
take_proposals_accept
take_proposals_reject
take_proposals_defer
take_proposals_bulk
```

The existing `gbrain sources` failure message confirms not every CLI command is routable from thin clients; prefer MCP `gbrain call <operation>` for this review surface unless dedicated CLI verbs are added later.

## Memory Stargraph Follow-Up

Once GBrain exposes the tools:

1. Redeploy GBrain remote MCP.
2. Verify `tools/list` includes all five `take_proposals_*` operations.
3. Re-run Memory Stargraph Take Review against the dashboard-managed service.
4. Mark SG-0093 and SG-0094 completed only after local, `.85`, and `.102` Memory Stargraph deployments verify the expected `ui_version` and the Take Review API reaches live GBrain.
