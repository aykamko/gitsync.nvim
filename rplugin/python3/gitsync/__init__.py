import neovim
import os
import subprocess
import time
# import msgpack

from collections import defaultdict
from gitsync import util

CACHE_DIR = '/tmp/gitsync.nvim'


@neovim.plugin
class GitSyncPlugin:
    def __init__(self, vim):
        self.vim = vim
        self.remote_url = None
        self.cache_tag = None
        self.last_poll = 0
        self.poll_seconds = None
        self.callback = None
        self.buf_desynced = defaultdict(set)

    def poll_remote(self, branch, repo):
        fetch = False
        cache_entry = '%s/%s_%s' % (CACHE_DIR, self.cache_tag, util.strhash(branch))
        if not os.path.exists(cache_entry):
            fetch = True
        else:
            lastmodtime = os.stat(cache_entry).st_mtime
            fetch = (time.time() - lastmodtime) >= self.poll_seconds

        if fetch:
            util.touch(cache_entry)
            util.bash('git fetch %s %s' % (repo, branch))

        return fetch

    def update_desynced(self, local, remote, buf):
        for b in self.vim.buffers:
            if int(util.bash('git rev-list --count %s..%s' % (local, remote))) == 0:
                continue

            bufset = self.buf_desynced[buf]
            try:
                desynced = len(util.bash('git diff %s..%s -- %s' % (local, remote, b.name))) > 0

                if desynced and local not in bufset:
                    bufset.add(local)
                    trigger = True
                elif not desynced and local in bufset:
                    bufset.remove(local)
                    trigger = True

                if self.callback and trigger:
                    self.vim.command('call %s()' % self.callback)
            except subprocess.CalledProcessError:
                pass

    @neovim.function('GitsyncDesynced', sync=True)
    def sync_status(self, _):
        return sorted(self.buf_desynced[self.vim.current.buffer.number])

    @neovim.command('GitsyncInitPython')
    def init_python(self):
        self.poll_seconds = 60 * self.vim.vars.get('gitsync_poll_min', 5)
        self.callback = self.vim.vars.get('gitsync_callback')
        self.remote_url = util.bash('git config --get remote.origin.url')
        self.cache_tag = util.strhash(self.remote_url)
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

        self.sync()

    @neovim.autocmd('BufRead')
    def _reset_timer(self):
        self.last_poll = 0

    @neovim.autocmd('CursorHold,CursorHoldI,CursorMoved,CursorMovedI')
    def sync(self):
        if not all((self.remote_url, self.cache_tag)):
            return

        now = time.time()
        if (now - self.last_poll) < self.poll_seconds:
            return
        self.last_poll = now

        buf = self.vim.current.buffer.number

        local_ref = None
        try:
            remote_ref = util.bash('git rev-parse --symbolic-full-name --abbrev-ref @{u}')
            repo, remote_branch = remote_ref.split('/', maxsplit=1)
            local_ref = util.bash('git symbolic-ref --short HEAD')

            self.poll_remote(remote_branch, repo)
            self.update_desynced(local_ref, remote_ref, buf)
        except subprocess.CalledProcessError:
            pass  # TODO

        if local_ref is None or local_ref != 'master':
            try:
                remote_ref = util.bash(
                    'git rev-parse --symbolic-full-name --abbrev-ref master@{u}'
                )
                repo, remote_branch = remote_ref.split('/', maxsplit=1)
                local_ref = 'master'

                self.poll_remote(remote_branch, repo)
                self.update_desynced(local_ref, remote_ref, buf)
            except subprocess.CalledProcessError:
                pass  # TODO
