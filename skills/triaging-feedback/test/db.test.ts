import { describe, it, expect, vi } from 'vitest';
import { claimQuery, findActionableQuery, writebackQuery } from '../src/db';

describe('claimQuery', () => {
  it('claims when pending, OR when stale-claimed (reclaim clause present, row returned)', async () => {
    const chain = { update: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(), or: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: [{ id: 'a' }], error: null }) };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    expect(await claimQuery(client, 'a', 30 * 60_000)).toBe(true);
    expect(chain.update).toHaveBeenCalledWith(expect.objectContaining({ triage_state: 'claimed' }));
    expect(chain.eq).toHaveBeenCalledWith('id', 'a');
    const orArg = chain.or.mock.calls[0][0] as string;
    expect(orArg).toContain('triage_state.eq.pending');
    expect(orArg).toContain('triaged_at.lt.');
  });
  it('returns false when nothing was claimable (0 rows)', async () => {
    const chain = { update: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(), or: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: [], error: null }) };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    expect(await claimQuery(client, 'a', 30 * 60_000)).toBe(false);
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
  it('updates the patch fields plus a fresh triaged_at, scoped by id', async () => {
    const chain = { update: vi.fn().mockReturnThis(), eq: vi.fn().mockResolvedValue({ data: null, error: null }) };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    await writebackQuery(client, 'f1', { triage_state: 'ticketed', triage_issue_url: 'https://example.com/issues/1' });
    expect(chain.update).toHaveBeenCalledWith(expect.objectContaining({
      triage_state: 'ticketed',
      triage_issue_url: 'https://example.com/issues/1',
      triaged_at: expect.any(String),
    }));
    expect(chain.eq).toHaveBeenCalledWith('id', 'f1');
  });
});
