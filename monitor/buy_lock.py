"""
Cross-bot duplicate buy prevention via atomic file locks.

Both harry and jaemin bots share /tmp/day-trader-locks/.
Before buying, each bot tries to create a lock file atomically.
os.O_EXCL guarantees only one process wins the race.
"""

import logging
import os
from datetime import datetime

import pytz

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")
LOCK_DIR = "/tmp/day-trader-locks"


def claim_stock_for_buy(stock_code: str) -> bool:
    os.makedirs(LOCK_DIR, exist_ok=True)
    today = datetime.now(KST).strftime("%Y-%m-%d")
    lock_file = os.path.join(LOCK_DIR, f"{today}_{stock_code}")
    try:
        # O_EXCL: fail if file exists — atomic on Linux/macOS
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()}".encode())
        os.close(fd)
        logger.info("buy_lock: %s claimed for today", stock_code)
        return True
    except FileExistsError:
        logger.info(
            "buy_lock: %s already claimed by another bot — skipping", stock_code
        )
        return False
    except Exception as e:
        # Lock mechanism failure should NOT block trading
        logger.warning(
            "buy_lock: failed to create lock for %s: %s — allowing buy", stock_code, e
        )
        return True


def cleanup_old_locks():
    today = datetime.now(KST).strftime("%Y-%m-%d")
    if not os.path.exists(LOCK_DIR):
        return
    removed = 0
    for fname in os.listdir(LOCK_DIR):
        if not fname.startswith(today):
            try:
                os.remove(os.path.join(LOCK_DIR, fname))
                removed += 1
            except Exception:
                pass
    if removed:
        logger.info("buy_lock: cleaned up %d old lock files", removed)
