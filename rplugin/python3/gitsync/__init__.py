import neovim
import os
import subprocess
import time

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

    def update_desynced(self, name, local, remote, buf):
        # don't update if we're even with or ahead of remote
        if int(util.bash('git rev-list --count %s..%s' % (local, remote))) == 0:
            return

        for b in self.vim.buffers:
            bufset = self.buf_desynced[buf]
            desynced = bool(util.bash_exitcode('git diff --quiet %s..%s -- %s' %
                                               (local, remote, b.name)))

            if desynced:
                trigger = name not in bufset
                bufset.add(name)
            elif name in bufset:
                trigger = True
                bufset.remove(name)

            if self.callback and trigger:
                self.vim.command('call %s()' % self.callback)

    @neovim.function('GitsyncDesynced', sync=True)
    def sync_status(self, _):
        return sorted(self.buf_desynced[self.vim.current.buffer.number])

    @neovim.command('GitsyncInitPython')
    def init_python(self):
        self.poll_seconds = 60 * self.vim.vars.get('gitsync_poll_min', 5)
        self.callback = self.vim.vars.get('gitsync_callback')
        try:
            self.remote_url = util.bash('git config --get remote.origin.url')
            self.cache_tag = util.strhash(self.remote_url)
        except subprocess.CalledProcessError:
            return

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
            remote_ref = util.bash('git rev-parse --abbrev-ref @{u}')
            repo, remote_branch = remote_ref.split('/', maxsplit=1)
            local_ref = util.bash('git symbolic-ref --short HEAD')

            self.poll_remote(remote_branch, repo)
            self.update_desynced('current', local_ref, remote_ref, buf)
        except subprocess.CalledProcessError:
            pass

        # also poll against master if we're not already on it
        if local_ref == 'master':
            return
        try:
            remote_ref = util.bash('git rev-parse --abbrev-ref master@{u}')
            master_repo, remote_branch = remote_ref.split('/', maxsplit=1)
            if master_repo != repo:  # doesn't make sense to diff against two different remotes
                return
            local_ref = util.bash('git merge-base HEAD master')

            self.poll_remote(remote_branch, repo)
            self.update_desynced('master', local_ref, remote_ref, buf)
        except subprocess.CalledProcessError:
            pass

    # Fugitive wrappers
    @neovim.command('GSGdiff', nargs='?', sync=True)
    def g_diff(self, args):
        self.diff(args, 'Gdiff')

    @neovim.command('GSGvdiff', nargs='?', sync=True)
    def gv_diff(self, args):
        self.diff(args, 'Gvdiff')

    @neovim.command('GSGsdiff', nargs='?', sync=True)
    def gs_diff(self, args):
        self.diff(args, 'Gsdiff')

    def diff(self, args, fugitive_cmd):
        if not len(args):
            branch = 'master'
        elif args[0] == 'current':
            branch = util.bash('git symbolic-ref --short HEAD')
        else:
            branch = args[0]
        remote_ref = util.bash('git rev-parse --abbrev-ref %s@{u}' % branch)
        self.vim.command('%s %s' % (fugitive_cmd, remote_ref))
