"""
Glue-Qt Bridge

A socket-based bridge for external control of glue-qt (e.g., from Claude Code).
"""

from glue_qt.bridge.server import (
    GlueBridgeServer,
    start_bridge_server,
    stop_bridge_server,
    start_glue_with_bridge,
    DEFAULT_PORT,
)
from glue_qt.bridge.client import (
    BridgeConnection,
    send_command,
    glue_exec,
    glue_eval,
    get_connection,
)

__all__ = [
    'GlueBridgeServer',
    'start_bridge_server',
    'stop_bridge_server',
    'start_glue_with_bridge',
    'BridgeConnection',
    'send_command',
    'glue_exec',
    'glue_eval',
    'get_connection',
    'DEFAULT_PORT',
]
