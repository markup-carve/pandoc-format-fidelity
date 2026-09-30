import { execFileSync } from 'node:child_process';
import { realpathSync } from 'node:fs';

export function checkoutRevision(root) {
    try {
        const git = (...args) => execFileSync('git', ['-C', root, ...args], {
            encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
        }).trim();
        if (realpathSync(git('rev-parse', '--show-toplevel')) !== realpathSync(root)) return null;
        if (git('status', '--porcelain', '--untracked-files=no')) return null;
        return git('rev-parse', 'HEAD');
    } catch {
        return null;
    }
}
