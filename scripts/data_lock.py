"""Shared predictions.json locking + read-modify-write helpers.

Every writer (panel_adjudicate, monte_carlo, miro_worker, app.py endpoints)
must use these: with locked_data():  ... modify d ... save happens on exit.
Prevents the stale-snapshot clobber that wiped Marty marks.
"""
import json
import logging
import os
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s pid=%(process)d %(name)s %(message)s")
logging.getLogger("filelock").setLevel(logging.DEBUG)
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

BASE = Path(r'C:/Users/schof/veracity2')
DATA_FILE = BASE / 'data' / 'predictions.json'
LOCK_FILE = BASE / 'data' / 'predictions.json.lock'
_LOCK = FileLock(str(LOCK_FILE), timeout=300)


@contextmanager
def locked_data():
    """Acquire the shared lock, load fresh data, yield dict, save on exit."""
    with _LOCK:
        data = json.load(open(DATA_FILE, encoding='utf-8'))
        try:
            yield data
        finally:
            json.dump(data, open(DATA_FILE, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)


@contextmanager
def locked_read():
    """Read-only access under the lock."""
    with _LOCK:
        yield json.load(open(DATA_FILE, encoding='utf-8'))
