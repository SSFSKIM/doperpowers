import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { Config } from './config';
import type { FeedbackRow, TriageState } from './types';

/** 원자적 클레임: pending이거나, stale하게 claimed된 채로 남은 경우에만 claimed로.
 * findActionable과 동일한 predicate를 써야 한다 — 그렇지 않으면 findActionable이 골라준
 * stale-claimed 행을 이 update가 매치하지 못해 재클레임이 죽은 코드가 된다. */
export async function claimQuery(client: SupabaseClient, id: string, reclaimMs: number): Promise<boolean> {
  const staleBefore = new Date(Date.now() - reclaimMs).toISOString();
  const { data, error } = await client
    .from('feedback')
    .update({ triage_state: 'claimed', triaged_at: new Date().toISOString() })
    .eq('id', id)
    .or(`triage_state.eq.pending,and(triage_state.eq.claimed,triaged_at.lt.${staleBefore})`)
    .select('id');
  if (error) throw error;
  return (data?.length ?? 0) > 0;
}

/** claimQuery가 재클레임 대상으로 고르는 것과 동일한 predicate로 착수 가능한 행을 조회. */
export async function findActionableQuery(client: SupabaseClient, k: number, reclaimMs: number): Promise<FeedbackRow[]> {
  const staleBefore = new Date(Date.now() - reclaimMs).toISOString();
  const { data, error } = await client
    .from('feedback')
    .select('id,user_id,role,academy_id,category,body,page_path,host,created_at,triage_state')
    .or(`triage_state.eq.pending,and(triage_state.eq.claimed,triaged_at.lt.${staleBefore})`)
    .order('created_at', { ascending: true })
    .limit(k);
  if (error) throw error;
  return (data ?? []) as FeedbackRow[];
}

export async function writebackQuery(client: SupabaseClient, id: string, patch: { triage_state: TriageState; triage_issue_url?: string }): Promise<void> {
  const { error } = await client.from('feedback')
    .update({ ...patch, triaged_at: new Date().toISOString() }).eq('id', id);
  if (error) throw error;
}

export function makeDb(cfg: Config) {
  const client = createClient(cfg.supabaseUrl, cfg.supabaseServiceKey, { auth: { persistSession: false } });
  return {
    findActionable: (k: number, reclaimMs: number) => findActionableQuery(client, k, reclaimMs),
    claim: (id: string) => claimQuery(client, id, cfg.reclaimMs),
    writeback: (id: string, patch: { triage_state: TriageState; triage_issue_url?: string }) => writebackQuery(client, id, patch),
  };
}
