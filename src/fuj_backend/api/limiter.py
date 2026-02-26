"""Slowapi rate limiter singleton.

Imported by both route files (as a decorator) and app.py (to register on
app.state). All three must share the same instance.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Key function: rate-limit by client IP address.
# For a local single-client deploy this effectively gives per-process limits.
limiter = Limiter(key_func=get_remote_address)
