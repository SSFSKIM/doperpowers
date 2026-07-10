import { describe, it, expect } from 'vitest';
import { resolveTrust } from '../src/trust';

const row = (over: any = {}) => ({ id: 'f1', role: 'student', body: '버튼이 안 눌려요', ...over }) as any;

describe('resolveTrust', () => {
  it('trusted role → developer (server-resolved role snapshot, not forgeable)', () => {
    expect(resolveTrust(row({ role: 'admin' }), { trustedRoles: ['admin'] })).toEqual({ level: 'developer', body: '버튼이 안 눌려요' });
  });
  it('untrusted role, no code → user', () => {
    expect(resolveTrust(row(), { trustedRoles: ['admin'] }).level).toBe('user');
  });
  it('devCode prefix → developer, and the code is STRIPPED from the body (never leaks into tickets)', () => {
    const r = resolveTrust(row({ body: '#dev18 라벨 X를 Y로 바꿔줘' }), { trustedRoles: ['admin'], devCode: 'dev18' });
    expect(r.level).toBe('developer');
    expect(r.body).toBe('라벨 X를 Y로 바꿔줘');
    expect(r.body).not.toContain('dev18');
  });
  it('devCode not configured → prefix is just text, user trust', () => {
    const r = resolveTrust(row({ body: '#dev18 뭔가' }), { trustedRoles: ['admin'] });
    expect(r.level).toBe('user');
    expect(r.body).toBe('#dev18 뭔가');
  });
  it('code in the middle of the body does not count', () => {
    expect(resolveTrust(row({ body: '이거 #dev18 인데요' }), { trustedRoles: ['admin'], devCode: 'dev18' }).level).toBe('user');
  });
  it('null role is handled', () => {
    expect(resolveTrust(row({ role: null }), { trustedRoles: ['admin'] }).level).toBe('user');
  });
});
