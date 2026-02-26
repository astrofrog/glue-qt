"""
Claude Code Bridge Plugin

Adds a menu item to enable/disable the bridge server for external control.
"""

from qtpy.QtWidgets import QMessageBox, QInputDialog
from glue_qt.config import menubar_plugin


def toggle_bridge(session, data_collection):
    """Toggle the Claude Code bridge server on/off."""
    from glue_qt.bridge import start_bridge_server, stop_bridge_server, DEFAULT_PORT

    app = session.application

    if hasattr(app, '_bridge_server') and app._bridge_server is not None:
        # Bridge is running - offer to stop it
        msg = QMessageBox(app)
        msg.setWindowTitle("Claude Code Bridge")
        msg.setText("Bridge server is currently running.")
        msg.setInformativeText(f"Listening on port {app._bridge_server.port}.\n\nDo you want to stop it?")
        msg.setIcon(QMessageBox.Question)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)

        if msg.exec_() == QMessageBox.Yes:
            stop_bridge_server(app)
            QMessageBox.information(app, "Claude Code Bridge", "Bridge server stopped.")
    else:
        # Bridge is not running - offer to start it
        port, ok = QInputDialog.getInt(
            app,
            "Claude Code Bridge",
            "Enter port number for bridge server:",
            DEFAULT_PORT,
            1024,
            65535
        )

        if ok:
            server = start_bridge_server(app, port=port)
            if server:
                QMessageBox.information(
                    app,
                    "Claude Code Bridge",
                    f"Bridge server started on port {port}.\n\n"
                    "You will be prompted to approve each new connection."
                )
            else:
                QMessageBox.critical(
                    app,
                    "Claude Code Bridge",
                    f"Failed to start bridge server on port {port}.\n"
                    "The port may already be in use."
                )


def setup():
    """Register the plugin."""
    menubar_plugin.add("Claude Code Bridge...", toggle_bridge)
