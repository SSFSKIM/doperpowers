import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { Config } from './config';
import type { FeedbackRow, TriageState } from './types';

/** 원자적 클레임: pending인 경우에만 claimed로. 반환행이 있으면 이 폴러가 소유. */
export async function claimQuery(client: SupabaseClient, id: string): Promise<boolean> {
  const { data, error } = await client
    .from('feedback')
    .update({ triage_state: 'claimed', triaged_at: new Date().toISOString() })
    .eq('id', id)
    .eq('triage_state', 'pending')
    .select('id');
  if (error) throw error;
  return (data?.length ?? 0) > 0;
}

export function makeDb(cfg: Config) {
  const client = createClient(cfg.supabaseUrl, cfg.supabaseServiceKey, { auth: { persistSession: false } });
  return {
    async findActionable(k: number, reclaimMs: number): Promise<FeedbackRow[]> {
      const staleBefore = new Date(Date.now() - reclaimMs).toISOString();
      const { data, error } = await client
        .from('feedback')
        .select('id,user_id,role,academy_id,category,body,page_path,host,created_at,triage_state')
        .or(`triage_state.eq.pending,and(triage_state.eq.claimed,triaged_at.lt.${staleBefore})`)
        .order('created_at', { ascending: true })
        .limit(k);
      if (error) throw error;
      return (data ?? []) as FeedbackRow[];
    },
    claim: (id: string) => claimQuery(client, id),
    async writeback(id: string, patch: { triage_state: TriageState; triage_pr_url?: string; triage_issue_url?: string }) {
      const { error } = await client.from('feedback')
        .update({ ...patch, triaged_at: new Date().toISOString() }).eq('id', id);
      if (error) throw error;
    },
  };
}
