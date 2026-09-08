import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { randomUUID } from 'node:crypto';
import type { Config } from './config';
import type { FeedbackRow, TriageState } from './types';

/** 원자적 클레임: pending이거나, stale하게 claimed된 채로 남은 경우에만 claimed로.
 * findActionable과 동일한 predicate를 써야 한다 — 그렇지 않으면 findActionable이 골라준
 * stale-claimed 행을 이 update가 매치하지 못해 재클레임이 죽은 코드가 된다.
 * 성공 시 lease 토큰(uuid)을 반환한다(외부 리뷰 #4): 이후 writeback은 이 lease를 조건으로
 * 걸어, 리클레임당한 구(舊) 워커가 신(新) 워커의 결과를 덮어쓰지 못하게 한다. */
export async function claimQuery(client: SupabaseClient, id: string, reclaimMs: number): Promise<string | null> {
  const lease = randomUUID();
  const staleBefore = new Date(Date.now() - reclaimMs).toISOString();
  const { data, error } = await client
    .from('feedback')
    .update({ triage_state: 'claimed', triaged_at: new Date().toISOString(), triage_lease: lease })
    .eq('id', id)
    .or(`triage_state.eq.pending,and(triage_state.eq.claimed,triaged_at.lt.${staleBefore})`)
    .select('id');
  if (error) throw error;
  return (data?.length ?? 0) > 0 ? lease : null;
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

/** lease 조건부 writeback. 0행 매치(=그사이 다른 폴러가 리클레임)면 조용히 덮어쓰는 대신
 * throw — 호출부가 로그로 남기고, 행의 최종 상태는 리클레임한 쪽이 소유한다. */
export async function writebackQuery(client: SupabaseClient, id: string, lease: string, patch: { triage_state: TriageState; triage_issue_url?: string }): Promise<void> {
  const { data, error } = await client.from('feedback')
    .update({ ...patch, triaged_at: new Date().toISOString() })
    .eq('id', id).eq('triage_lease', lease)
    .select('id');
  if (error) throw error;
  if ((data?.length ?? 0) === 0) throw new Error(`writeback lost lease for feedback ${id} — row was reclaimed`);
}

export function makeDb(cfg: Config) {
  const client = createClient(cfg.supabaseUrl, cfg.supabaseServiceKey, { auth: { persistSession: false } });
  return {
    findActionable: (k: number, reclaimMs: number) => findActionableQuery(client, k, reclaimMs),
    claim: (id: string) => claimQuery(client, id, cfg.reclaimMs),
    writeback: (id: string, lease: string, patch: { triage_state: TriageState; triage_issue_url?: string }) => writebackQuery(client, id, lease, patch),
  };
}
