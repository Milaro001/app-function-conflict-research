"""Nonblocking exclusive file lock for one dedicated browser profile."""
import os

def acquire_profile_lock(file):
    if os.name=='nt':
        import msvcrt
        file.seek(0,2)
        if file.tell()==0:file.write('0');file.flush()
        file.seek(0)
        try:msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as exc:raise BlockingIOError('Profile already in use') from exc
    else:
        import fcntl
        fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
    # Closing the descriptor releases the lock on either backend.
