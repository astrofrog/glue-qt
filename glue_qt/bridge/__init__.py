"""
Glue-Qt Bridge

A socket-based bridge for external control of glue-qt (e.g., from Claude Code).

Server-side (in glue):
    from glue_qt.bridge import start_bridge_server, stop_bridge_server

Client-side (from external process):
    python -m glue_qt.bridge.client "print('hello')"
"""

from glue_qt.bridge.server import (
    GlueBridgeServer,
    start_bridge_server,
    stop_bridge_server,
    start_glue_with_bridge,
    DEFAULT_PORT,
)

__all__ = [
    'GlueBridgeServer',
    'start_bridge_server',
    'stop_bridge_server',
    'start_glue_with_bridge',
    'DEFAULT_PORT',
]
