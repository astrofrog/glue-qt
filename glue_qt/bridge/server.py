"""
Glue-Qt Bridge Server

A socket server that allows external control of a running glue-qt instance.
Commands are Python code executed in the glue context.

Security: Requires user approval via popup dialog for each new connection.
"""

import json
import sys
import traceback
from io import StringIO

from qtpy.QtCore import QObject, Signal, Slot
from qtpy.QtNetwork import QTcpServer, QHostAddress
from qtpy.QtWidgets import QMessageBox

DEFAULT_PORT = 9876


class GlueBridgeServer(QObject):
    """Socket server for remote control of glue-qt."""

    command_received = Signal(str)
    connection_approved = Signal(object)

    def __init__(self, app, port=DEFAULT_PORT, parent=None):
        super().__init__(parent)
        self.app = app
        self.port = port
        self.server = QTcpServer(self)
        self.approved_connections = []
        self.pending_connections = []

        # Build the namespace for command execution
        self.namespace = {
            'app': app,
            'application': app,
            'dc': app.data_collection,
            'data_collection': app.data_collection,
            'session': app.session,
            'hub': app.session.hub,
        }

        # Add common imports to namespace
        exec("""
import numpy as np
from glue.core import Data, DataCollection
from glue.core.roi import RectangularROI, CircularROI, PolygonalROI
from glue.core.subset import SubsetState
""", self.namespace)

        self.server.newConnection.connect(self._on_new_connection)

    def start(self):
        """Start the server."""
        if self.server.listen(QHostAddress.SpecialAddress.LocalHost, self.port):
            print(f"Glue bridge server listening on localhost:{self.port}")
            return True
        else:
            print(f"Failed to start server: {self.server.errorString()}")
            return False

    def stop(self):
        """Stop the server."""
        self.server.close()
        for conn in self.approved_connections + self.pending_connections:
            conn.close()
        self.approved_connections.clear()
        self.pending_connections.clear()

    def is_running(self):
        """Check if server is running."""
        return self.server.isListening()

    @Slot()
    def _on_new_connection(self):
        """Handle new client connection - requires user approval."""
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            self.pending_connections.append(connection)

            # Show approval dialog
            approved = self._request_approval(connection)

            if approved:
                self.pending_connections.remove(connection)
                self.approved_connections.append(connection)
                connection.readyRead.connect(lambda c=connection: self._on_ready_read(c))
                connection.disconnected.connect(lambda c=connection: self._on_disconnected(c))

                # Send approval confirmation
                response = {'success': True, 'message': 'Connection approved'}
                connection.write((json.dumps(response) + '\n').encode('utf-8'))
                connection.flush()
            else:
                self.pending_connections.remove(connection)
                # Send rejection and close
                response = {'success': False, 'error': 'Connection rejected by user'}
                connection.write((json.dumps(response) + '\n').encode('utf-8'))
                connection.flush()
                connection.close()

    def _request_approval(self, connection):
        """Show dialog to approve/reject connection."""
        peer_address = connection.peerAddress().toString()
        peer_port = connection.peerPort()

        msg = QMessageBox(self.app)
        msg.setWindowTitle("Bridge Connection Request")
        msg.setText("An external process wants to control glue.")
        msg.setInformativeText(
            f"Connection from: {peer_address}:{peer_port}\n\n"
            "This will allow the process to execute Python code in glue's context. "
            "Only approve if you initiated this connection (e.g., from Claude Code)."
        )
        msg.setIcon(QMessageBox.Question)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)

        result = msg.exec_()
        return result == QMessageBox.Yes

    def _on_disconnected(self, connection):
        """Handle client disconnection."""
        if connection in self.approved_connections:
            self.approved_connections.remove(connection)

    def _on_ready_read(self, connection):
        """Handle incoming data from client."""
        while connection.canReadLine():
            line = connection.readLine().data().decode('utf-8').strip()
            if line:
                try:
                    request = json.loads(line)
                    response = self._execute_command(request)
                except json.JSONDecodeError as e:
                    response = {'error': f'Invalid JSON: {e}', 'success': False}

                # Send response
                response_json = json.dumps(response) + '\n'
                connection.write(response_json.encode('utf-8'))
                connection.flush()

    def _execute_command(self, request):
        """Execute a command in the glue context."""
        cmd_type = request.get('type', 'exec')
        code = request.get('code', '')

        # Capture stdout
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured_out = StringIO()
        captured_err = StringIO()

        try:
            sys.stdout = captured_out
            sys.stderr = captured_err

            if cmd_type == 'eval':
                # Evaluate expression and return result
                result = eval(code, self.namespace)
                return {
                    'success': True,
                    'result': repr(result),
                    'stdout': captured_out.getvalue(),
                    'stderr': captured_err.getvalue(),
                }
            else:
                # Execute statements
                exec(code, self.namespace)
                return {
                    'success': True,
                    'result': None,
                    'stdout': captured_out.getvalue(),
                    'stderr': captured_err.getvalue(),
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc(),
                'stdout': captured_out.getvalue(),
                'stderr': captured_err.getvalue(),
            }
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


def start_bridge_server(app, port=DEFAULT_PORT):
    """
    Start the bridge server on an existing GlueApplication.

    Parameters
    ----------
    app : GlueApplication
        The running glue application
    port : int
        Port for the bridge server (default: 9876)

    Returns
    -------
    server : GlueBridgeServer
        The bridge server instance
    """
    server = GlueBridgeServer(app, port=port)
    if server.start():
        app._bridge_server = server
        return server
    return None


def stop_bridge_server(app):
    """
    Stop the bridge server on an existing GlueApplication.

    Parameters
    ----------
    app : GlueApplication
        The running glue application
    """
    if hasattr(app, '_bridge_server') and app._bridge_server is not None:
        app._bridge_server.stop()
        app._bridge_server = None


def start_glue_with_bridge(data_files=None, port=DEFAULT_PORT):
    """
    Start glue-qt with the bridge server enabled.

    Parameters
    ----------
    data_files : list, optional
        List of data files to load on startup
    port : int
        Port for the bridge server (default: 9876)

    Returns
    -------
    app : GlueApplication
        The glue application instance
    server : GlueBridgeServer
        The bridge server instance
    """
    from glue_qt.app import GlueApplication
    from glue.core import DataCollection

    # Create application
    dc = DataCollection()
    app = GlueApplication(data_collection=dc)

    # Load any initial data files
    if data_files:
        for f in data_files:
            app.load_data(f)

    # Create and start bridge server
    server = start_bridge_server(app, port=port)

    # Start the application
    app.start()

    return app, server


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Start glue-qt with bridge server')
    parser.add_argument('files', nargs='*', help='Data files to load')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Bridge server port')
    args = parser.parse_args()

    start_glue_with_bridge(data_files=args.files, port=args.port)
