import md5
import os
import subprocess
import neovim
import json
# import msgpack


def escape(expr):
    return expr.replace("'", "''")


def debug(vim, msg):
    vim.command('echomsg string(\'' + escape(json.dumps(msg)) + '\')')


@neovim.plugin
class GitSyncPlugin:
    def __init__(self, vim):
        self.vim = vim
        self.remote_url = None

    def poll_cache(self):
        if not os.exists


    @neovim.command('GitsyncInitPython')
    def init_python(self):
        self.remote_url = subprocess.check_output('git config --get remote.origin.url')
        debug(self.vim, self.remote_url)
