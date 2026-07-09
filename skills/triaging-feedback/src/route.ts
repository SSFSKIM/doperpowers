import type { FeedbackCategory } from './types';

/** 카테고리 우선 라우팅. idea/question은 절대 workspace_write로 가지 않는다. */
export function preRoute(category: FeedbackCategory): 'diagnose' | 'ticket' {
  if (category === 'idea' || category === 'question') return 'ticket';
  return 'diagnose'; // bug, other
}
