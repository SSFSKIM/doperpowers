export type FeedbackCategory = 'bug' | 'idea' | 'question' | 'other';
export type TriageState = 'pending' | 'claimed' | 'ticketed' | 'skipped' | 'failed';

export interface FeedbackRow {
  id: string; user_id: string; role: string | null; academy_id: string | null;
  category: FeedbackCategory; body: string; page_path: string | null;
  host: string | null; created_at: string; triage_state: TriageState;
}
