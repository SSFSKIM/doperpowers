import { describe, it, expect, vi } from 'vitest';
import { claimQuery, findActionableQuery, writebackQuery } from '../src/db';

describe('claimQuery', () => {
  it('claims when pending OR stale-claimed, returning a lease token and stamping it on the row', async () => {
    const chain = { update: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(), or: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: [{ id: 'a' }], error: null }) };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    const lease = await claimQuery(client, 'a', 30 * 60_000);
    expect(typeof lease).toBe('string');
    const patch = chain.update.mock.calls[0][0];
    expect(patch.triage_state).toBe('claimed');
    expect(patch.triage_lease).toBe(lease); // lease가 행에 새겨져야 writeback 조건이 성립
    expect(chain.eq).toHaveBeenCalledWith('id', 'a');
    const orArg = chain.or.mock.calls[0][0] as string;
    expect(orArg).toContain('triage_state.eq.pending');
    expect(orArg).toContain('triaged_at.lt.');
  });
  it('returns null when nothing was claimable (0 rows)', async () => {
    const chain = { update: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(), or: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: [], error: null }) };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    expect(await claimQuery(client, 'a', 30 * 60_000)).toBeNull();
  });
});

describe('findActionableQuery', () => {
  it('selects pending-or-stale-claimed rows, ordered oldest-first, limited to k', async () => {
    const chain = {
      select: vi.fn().mockReturnThis(),
      or: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockResolvedValue({ data: [], error: null }),
    };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    await findActionableQuery(client, 3, 30 * 60_000);
    const orArg = chain.or.mock.calls[0][0] as string;
    expect(orArg).toContain('triage_state.eq.pending');
    expect(orArg).toContain('triaged_at.lt.');
    expect(chain.order).toHaveBeenCalledWith('created_at', { ascending: true });
    expect(chain.limit).toHaveBeenCalledWith(3);
  });
});

describe('writebackQuery', () => {
  function chainWith(rows: unknown[]) {
    return { update: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: rows, error: null }) };
  }
  it('updates the patch fields plus a fresh triaged_at, scoped by id AND lease', async () => {
    const chain = chainWith([{ id: 'f1' }]);
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    await writebackQuery(client, 'f1', 'lease-1', { triage_state: 'ticketed', triage_issue_url: 'https://example.com/issues/1' });
    expect(chain.update).toHaveBeenCalledWith(expect.objectContaining({
      triage_state: 'ticketed',
      triage_issue_url: 'https://example.com/issues/1',
      triaged_at: expect.any(String),
    }));
    expect(chain.eq).toHaveBeenCalledWith('id', 'f1');
    expect(chain.eq).toHaveBeenCalledWith('triage_lease', 'lease-1');
  });
  it('throws when the lease was lost (0 rows matched) — the reclaimer owns the row now', async () => {
    const chain = chainWith([]);
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    await expect(writebackQuery(client, 'f1', 'stale-lease', { triage_state: 'ticketed' })).rejects.toThrow(/lease/);
  });
});
