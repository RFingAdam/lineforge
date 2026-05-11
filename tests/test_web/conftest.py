"""Shared pytest config — force the stub chat handler so tests don't try
to call Anthropic. Tests that exercise the real agent should set
``ATLC3_GUI_CHAT_STUB=0`` themselves and ensure ANTHROPIC_API_KEY is in env.
"""

from __future__ import annotations

import os

os.environ.setdefault("ATLC3_GUI_CHAT_STUB", "1")
