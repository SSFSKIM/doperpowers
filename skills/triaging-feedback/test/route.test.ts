import { describe, it, expect } from 'vitest';
import { preRoute } from '../src/route';

describe('preRoute', () => {
  it('idea → ticket', () => expect(preRoute('idea')).toBe('ticket'));
  it('question → ticket', () => expect(preRoute('question')).toBe('ticket'));
  it('bug → diagnose', () => expect(preRoute('bug')).toBe('diagnose'));
  it('other → diagnose (worker infers)', () => expect(preRoute('other')).toBe('diagnose'));
});
