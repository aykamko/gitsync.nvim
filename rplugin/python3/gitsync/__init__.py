import neovim
import os
import subprocess
import time

from gitsync import util

CACHE_DIR = '/tmp/gitsync.nvim'


class BranchFile:
    POLL_SECONDS = 5 * 60  # default 5 minutes

    def __init__(self, filepath, branch):
        self.filepath = filepath
        self.branch = branch

        self.upstream_ref = self.git(['rev-parse', '--abbrev-ref',  '%s@{u}' % branch])
        self.remote, self.upstream_branch = self.upstream_ref.split('/', maxsplit=1)
        self.remote_url = self.git(['config', '--get', 'remote.%s.url' % self.remote])
        self.cache_entry = '%s/%s::%s' % \
            (CACHE_DIR, util.strhash(self.remote_url), util.strhash(self.upstream_branch))

    def git(self, cmd, **kwargs):
        return util.git(self.filepath, cmd, **kwargs)

    def poll_upstream(self):
        """
        TODO
        """
        fetch = False
        if not os.path.exists(self.cache_entry):
            fetch = True
        else:
            lastmodtime = os.stat(self.cache_entry).st_mtime
            fetch = (time.time() - lastmodtime) >= BranchFile.POLL_SECONDS
        if fetch:
            self.git(['fetch', self.remote, self.upstream_branch])
            util.touch(self.cache_entry)

        compare = '%s..%s' % (self.branch, self.upstream_ref)
        behind_count = int(self.git(['rev-list', '--count', compare]))
        # only check diff if we're behind upstream
        if behind_count < 1:
            return False

        if bool(self.git(['diff', '--quiet', compare, '--', self.filepath], exitcode=True)):
            return behind_count


class GitsyncBuffer(neovim.api.Buffer):
    def __init__(self, neovim_buf):
        super().__init__(neovim_buf._session, neovim_buf.code_data)

        self.active_branch = self.git('symbolic-ref --short HEAD')

        self.watched_branchfiles = {}
        try:
            self.watched_branchfiles[self.active_branch] = \
                BranchFile(self.path, self.active_branch)
        except subprocess.CalledProcessError:
            pass  # no tracked upstream for current branch

        # don't watch master unless file exists in master
        if self.active_branch != 'master' and \
                self.git(['cat-file', '-e', 'master:%s' % self.path], exitcode=True):
            try:
                self.watched_branchfiles['master'] = BranchFile(self.path, 'master')
            except subprocess.CalledProcessError:
                pass  # no tracked upstream for master

        self.last_poll = 0
        self._desynced_branches = {}

    @property
    def path(self):
        """
        More correctly named shim for self.name, since this buffer's name is that path of the file.
        """
        return self.name

    @property
    def desynced_branches(self):
        return sorted(self._desynced_branches.items())

    def git(self, cmd, **kwargs):
        return util.git(self.path, cmd, **kwargs)

    def poll_upstream(self):
        changed = False
        for branchfile in self.watched_branchfiles.values():
            behind_count = branchfile.poll_upstream()

            if behind_count > 0:
                if branchfile.branch not in self._desynced_branches:
                    changed = True
                self._desynced_branches[branchfile.branch] = behind_count
            elif branchfile.branch in self._desynced_branches:
                changed = True
                del self._desynced_branches[branchfile.branch]

        return changed

    def diff(self, vim, args, fugitive_cmd):
        if not len(args):
            branch = 'master'
        elif args[0] == 'current':
            branch = self.active_branch
        else:
            branch = args[0]
        upstream_ref = self.git(['rev-parse', '--abbrev-ref', '%s@{u}' % branch])
        vim.command('%s %s' % (fugitive_cmd, upstream_ref))


@neovim.plugin
class GitSyncPlugin:
    def __init__(self, vim):
        self.vim = vim
        self.active_bufs = {}
        self.last_poll = 0
        self.callback = None
        self.airline = False
        self.initialized = False

    @neovim.command('GitsyncInitPython')
    def init_python(self):
        self.poll_seconds = 60 * self.vim.vars.get('gitsync_poll_min', 5)
        BranchFile.POLL_SECONDS = self.poll_seconds
        self.airline = self.vim.vars.get('gitsync_airline', False)
        self.callback = self.vim.vars.get('gitsync_callback', None)

        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        self.initialized = True
        self.vim.vars['gitsync_initialized'] = 1

    @neovim.autocmd('BufRead')
    def add_buffer(self):
        try:
            curbuf = self.vim.current.buffer
            gbuf = self.active_bufs[gbuf.number] = GitsyncBuffer(curbuf)
            self.sync(True)
        except subprocess.CalledProcessError:
            # if we get an exception, then the buffer isn't backed by a git repo
            pass

    # TODO
    # @neovim.autocmd('BufDelete')
    # def remove_buffer(self):
    #     util.pdb()
    #     delbuf_num = int(self.vim.eval("bufnr('<afile>')"))
    #     del self.active_bufs[delbuf_num]

    @neovim.command('GitsyncSync')
    def manual_sync(self):
        self.sync(True)

    @neovim.autocmd('CursorHold,CursorHoldI,CursorMoved,CursorMovedI')
    def sync(self, force=False):
        if not self.initialized:
            return
        if not force and (time.time() - self.last_poll) < self.poll_seconds:
            return

        # util.pdb()
        changed = False
        for b in self.active_bufs.values():
            if b.poll_upstream():
                changed = True
        self.poll_seconds = time.time()

        if changed:
            if self.callback:
                self.vim.command('call %s()' % self.callback)
            if self.airline:
                self.vim.command('call airline#extensions#gitsync#apply()')

    @neovim.function('GitsyncStatus', sync=True)
    def status(self, args=None):
        desynced = self.desynced()
        if not len(desynced):
            return ''
        return ', '.join(('%s(%d)' % (b, c) for (b, c) in desynced)) + ' ↻'

    @neovim.function('GitsyncDesynced', sync=True)
    def desynced(self, args=None):
        gbuf = self.active_bufs.get(self.vim.current.buffer.number, None)
        if not gbuf:
            return []
        return gbuf.desynced_branches

    # Fugitive wrappers
    @neovim.command('Sdiff', nargs='?', sync=True)
    def g_diff(self, args):
        self.diff(args, 'Gdiff')

    @neovim.command('Svdiff', nargs='?', sync=True)
    def gv_diff(self, args):
        self.diff(args, 'Gvdiff')

    @neovim.command('Ssdiff', nargs='?', sync=True)
    def gs_diff(self, args):
        self.diff(args, 'Gsdiff')

    def diff(self, args, fugitive_cmd):
        gbuf = self.active_bufs[self.vim.current.buffer.number]
        gbuf.diff(self.vim, args, fugitive_cmd)
