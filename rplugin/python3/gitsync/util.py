import subprocess
import os
import base64
from remote_pdb import RemotePdb


def touch(fname, mode=0o666, dir_fd=None, **kwargs):
    """
    Implements the `touch` Unix utility, which set the modification and access time of a file to
    the current time of day. If the file doesn't exist, it is created with default permissions.

    Source: http://stackoverflow.com/a/1160227
    """
    flags = os.O_CREAT | os.O_APPEND
    with os.fdopen(os.open(fname, flags=flags, mode=mode, dir_fd=dir_fd)) as f:
        os.utime(f.fileno() if os.utime in os.supports_fd else fname,
                 dir_fd=None if os.supports_fd else dir_fd, **kwargs)


def bash(cmd, strip=True):
    cmdstr = cmd.split() if (type(cmd) == str) else cmd
    out = subprocess.check_output(cmdstr, universal_newlines=True)
    if strip:
        out = out.strip()
    return out


def strhash(string, encoding='utf8'):
    if type(string) == bytes:
        h = base64.urlsafe_b64encode(string)
    else:
        h = base64.urlsafe_b64encode(string.encode(encoding))
    return h.decode(encoding)


def pdb(host='127.0.0.1', port=4444):
    RemotePdb(host, port).set_trace()


def debug(vim, msg):
    msg = str(msg)
    vim.command('echomsg "' + msg.replace('"', '""') + '"')
