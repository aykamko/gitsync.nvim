import neovim
import os
import subprocess
import time
# import msgpack

from gitsync import util

CACHE_DIR = '/tmp/gitsync.nvim'


@neovim.plugin
class GitSyncPlugin:
    def __init__(self, vim):
        self.vim = vim
        self.remote_url = None
        self.cache_tag = None
        self.last_poll = 0
        self.poll_master = None
        self.poll_seconds = None
        self.callback = None

    def poll_ref(self, ref, remote):
        fetch = False
        cache_entry = '%s/%s_%s' % (CACHE_DIR, self.cache_tag, util.strhash(ref))
        if not os.path.exists(cache_entry):
            fetch = True
        else:
            lastmodtime = os.stat(cache_entry).st_mtime
            fetch = (time.time() - lastmodtime) >= self.poll_seconds

        util.touch(cache_entry)
        if fetch:
            util.bash('git fetch %s %s' % (remote, ref))
        return fetch

    def notify_desynced(self, local, remote):
        for b in self.vim.buffers:
            old = b.vars.get('gitsync_desynced')
            diff = util.bash('git diff %s..%s -- %s' % (local, remote, b.name))
            # b.vars['gitsync_desynced'] = len(diff) > 0
            new = b.vars['gitsync_desynced'] = True
            if self.callback and (old is None or old != new):
                self.vim.command('call %s()' % self.callback)

    @neovim.function('sync_status')
    def sync_status(self):
        return self.vim.current.buffer.vars.get('gitsync_desynced', False)

    @neovim.command('GitsyncInitPython')
    def init_python(self):
        self.poll_master = self.vim.vars.get('gitsync_poll_master', True)
        self.poll_seconds = 60 * self.vim.vars.get('gitsync_poll_min', 5)
        self.callback = self.vim.vars.get('gitsync_callback')
        self.remote_url = util.bash('git config --get remote.origin.url')
        self.cache_tag = util.strhash(self.remote_url)
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

    # @neovim.autocmd('CursorHold,CursorHoldI,CursorMoved,CursorMovedI')
    @neovim.command('GitsyncSync')
    def sync(self):
        if not all((self.remote_url, self.cache_tag)):
            return

        now = time.time()
        if (now - self.last_poll) < self.poll_seconds:
            return
        self.last_poll = now

        branch = None
        try:
            branch = util.bash('git symbolic-ref --short HEAD')
            ref = util.bash(['git', 'config', '--get', 'branch.%s.merge' % branch])
            remote = util.bash(['git', 'config', '--get', 'branch.%s.remote' % branch])

            self.poll_ref(ref, remote)
            self.notify_desynced(branch, ref)
        except subprocess.CalledProcessError:
            pass  # TODO

        if self.poll_master and branch and branch != 'master':
            try:
                master_ref = util.bash('git config --get branch.master.merge')
                master_remote = util.bash('git config --get branch.master.remote')
                self.poll_ref(master_ref, master_remote)
            except subprocess.CalledProcessError:
                pass  # TODO
