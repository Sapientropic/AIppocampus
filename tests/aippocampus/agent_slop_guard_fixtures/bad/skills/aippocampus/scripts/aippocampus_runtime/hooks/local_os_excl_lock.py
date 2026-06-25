import os


def acquire(path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
