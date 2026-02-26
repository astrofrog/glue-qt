# Glue-Qt Bridge

A socket-based bridge for external programmatic control of glue-qt. This allows AI assistants (like Claude Code) or scripts to control a running glue instance.

## Quick Start

### 1. Start the bridge in glue

**Option A: From the menu (recommended)**
1. Start glue normally: `glue`
2. Go to **Plugins → Claude Code Bridge...**
3. Enter port (default: 9876) and click OK

**Option B: Start glue with bridge enabled**
```bash
python -m glue_qt.bridge.server
```

### 2. Send commands

```bash
python -m glue_qt.bridge.client "print('Hello from glue!')"
python -m glue_qt.bridge.client --eval "len(dc)"
```

## Protocol

The bridge uses a simple JSON-over-TCP protocol on localhost.

### Connection

1. Connect to `localhost:9876` (or configured port)
2. Wait for approval response (user sees a popup in glue)
3. If approved: `{"success": true, "message": "Connection approved"}`
4. If rejected: `{"success": false, "error": "Connection rejected by user"}`

### Sending Commands

Send a JSON object followed by newline:

```json
{"type": "exec", "code": "print('hello')"}
```

Or to evaluate an expression and get its value:

```json
{"type": "eval", "code": "len(dc)"}
```

### Response Format

```json
{
  "success": true,
  "result": "5",
  "stdout": "any printed output\n",
  "stderr": ""
}
```

On error:
```json
{
  "success": false,
  "error": "NameError: name 'foo' is not defined",
  "traceback": "...",
  "stdout": "",
  "stderr": ""
}
```

## Available Variables

Commands execute in a namespace with these pre-defined variables:

| Variable | Description |
|----------|-------------|
| `app` / `application` | The GlueApplication instance |
| `dc` / `data_collection` | The DataCollection containing all datasets |
| `session` | The Session object |
| `hub` | The message Hub |
| `np` | NumPy (pre-imported) |
| `Data` | glue.core.Data class |
| `DataCollection` | glue.core.DataCollection class |

## Example Commands

### Load data
```python
app.load_data('/path/to/file.fits')
```

### Create a dataset programmatically
```python
import numpy as np
from glue.core import Data
data = Data(x=np.random.random(100), y=np.random.random(100), label='my_data')
dc.append(data)
```

### Create a scatter plot
```python
from glue_qt.viewers.scatter import ScatterViewer
viewer = app.new_data_viewer(ScatterViewer, data=dc[0])
viewer.state.x_att = dc[0].id['x']
viewer.state.y_att = dc[0].id['y']
```

### Create a histogram
```python
from glue_qt.viewers.histogram import HistogramViewer
viewer = app.new_data_viewer(HistogramViewer, data=dc[0])
viewer.state.x_att = dc[0].id['x']
```

### Create an image viewer
```python
from glue_qt.viewers.image import ImageViewer
viewer = app.new_data_viewer(ImageViewer, data=dc[0])
```

### Make a selection (subset)
```python
from glue.core.subset import InequalitySubsetState
import operator
subset_state = InequalitySubsetState(dc[0].id['x'], 0.5, operator=operator.gt)
dc.new_subset_group('x > 0.5', subset_state)
```

### Change colormap
```python
from matplotlib import cm
viewer = app.viewers[0][0]  # First viewer
viewer.state.layers[0].cmap = cm.viridis
```

### Close all viewers
```python
for tab in app.viewers:
    for viewer in tab[:]:
        viewer.close()
```

### Remove all data
```python
while len(dc) > 0:
    dc.remove(dc[0])
```

## Python Client Example

```python
import json
import socket

def send_to_glue(code, cmd_type='exec', port=9876):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect(('localhost', port))

        # Wait for approval
        approval = sock.recv(4096).decode().strip()
        response = json.loads(approval)
        if not response.get('success'):
            raise ConnectionRefusedError(response.get('error'))

        # Send command
        request = json.dumps({'type': cmd_type, 'code': code}) + '\n'
        sock.sendall(request.encode())

        # Get response
        result = sock.recv(4096).decode().strip()
        return json.loads(result)

# Usage
result = send_to_glue("print(len(dc))")
print(result['stdout'])
```

## Security

- The server only listens on localhost (127.0.0.1)
- Each new connection requires user approval via popup dialog
- Once approved, a connection stays approved for the session
- Commands execute with full Python capabilities in glue's context

## For AI Assistants

If you're an AI assistant wanting to control glue:

1. Check if bridge is running: try connecting to localhost:9876
2. If connection refused, ask user to start the bridge via Plugins menu
3. Wait for user to approve the connection (they'll see a popup)
4. Send Python commands as JSON with `{"type": "exec", "code": "..."}`
5. Parse the JSON response to check success and get results
6. Use the variables `dc`, `app`, `session` to interact with glue
7. Import viewers from `glue_qt.viewers.*` to create visualizations
