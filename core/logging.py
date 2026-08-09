"""One logger factory for the whole platform.

Deliberately small. The *interesting* logging in this project is not text on stderr — it is the
``logs`` table, which records every model call with its tokens, cost and latency and is what the
dashboard reads. This module exists so that operational messages (startup, failed uploads,
provider failover) land somewhere consistent, not so that it can grow into a framework.
"""
from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger, configuring the root handler exactly once."""
    global _CONFIGURED
    if not _CONFIGURED:
        logging.basicConfig(
            level=os.getenv("LOG_LEVEL", "INFO").upper(),
            format="%(asctime)s %(levelname)-7s %(name)-24s %(message)s",
            datefmt="%H:%M:%S",
            stream=sys.stderr,
        )
        # These two are chatty at INFO and drown out everything we actually wrote.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        _CONFIGURED = True
    return logging.getLogger(name)
