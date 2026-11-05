import { execFileSync } from 'node:child_process';

export function defaultExec(cmd, args, opts = {}) {
  return execFileSync(cmd, args, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'], ...opts });
}

/** What a failed command printed, so a finding says why. */
export const failureOutput = (e) => [e.stdout, e.stderr].filter(Boolean).join('\n').trim() || e.message;
