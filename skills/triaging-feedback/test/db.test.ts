import { describe, it, expect, vi } from 'vitest';
import { claimQuery } from '../src/db';

describe('claimQuery', () => {
  it('claims only when triage_state is pending (row returned)', async () => {
    const chain = { update: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: [{ id: 'a' }], error: null }) };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    expect(await claimQuery(client, 'a')).toBe(true);
    expect(chain.update).toHaveBeenCalledWith(expect.objectContaining({ triage_state: 'claimed' }));
    // guarded on id AND pending
    expect(chain.eq).toHaveBeenCalledWith('id', 'a');
    expect(chain.eq).toHaveBeenCalledWith('triage_state', 'pending');
  });
  it('returns false when nothing was claimable (0 rows)', async () => {
    const chain = { update: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: [], error: null }) };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    expect(await claimQuery(client, 'a')).toBe(false);
  });
});
