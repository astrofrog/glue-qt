"""
Qt-specific bindings for the path slicer tool.

The drawing mode and the crosshair mode are matplotlib-only and live
in glue-core; this module subclasses them to set the Qt-specific
viewer class and tool IDs, and wires a dropdown onto the slice tool's
toolbar button: each tool instance keeps its own list of
:class:`PathSlicedData` (so the per-viewer "give me another path on
this cube" case works), and the dropdown lets the user choose between
creating a new path or refreshing one of the existing ones. Hovering
a menu entry highlights the corresponding path on the source viewer
so the user can see which one they're about to replace.
"""

from matplotlib.lines import Line2D
import numpy as np

from qtpy import QtCore, QtWidgets

from glue.config import viewer_tool
from glue.core import Data
from glue.plugins.tools.path_slicer.matplotlib_mode import (
    BasePathSlicerCrosshairMode, BasePathSlicerMode)
from glue.plugins.tools.path_slicer.path_sliced_data import PathSlicedData
from glue.plugins.tools.path_slicer.path_sliced_data_links import (
    link_path_sliced_pair_paths, link_path_sliced_to_parent)

from glue_qt.viewers.image import ImageViewer


__all__ = ['PathSlicerMode', 'PathSlicerCrosshairMode']


# RGBA colours for the on-viewer path overlay; the "active" path is
# drawn opaque, the others a faded version.
_PATH_COLOR = '#669dff'
_PATH_ALPHA_ACTIVE = 1.0
_PATH_ALPHA_INACTIVE = 0.3


@viewer_tool
class PathSlicerMode(BasePathSlicerMode):
    """
    Path slicer tool with a dropdown that lets the user pick between
    creating a new :class:`PathSlicedData` and refreshing one of the
    existing ones traced on this viewer.

    The list of paths is scoped to this tool instance, which itself is
    scoped to a single source viewer. Drawing the same cube in a
    different viewer gets a fresh list (so the user's other viewer
    isn't disturbed).
    """

    tool_id = 'slice'
    slice_viewer_cls = ImageViewer

    def __init__(self, viewer, **kwargs):
        super().__init__(viewer, **kwargs)
        # Each "trace" -- a single Enter on the path tool -- creates one
        # PathSlicedData per Data layer in the source viewer. A trace is
        # therefore a list of PathSlicedData; the menu lists traces, and
        # selecting "Update trace N" refreshes every PathSlicedData in
        # that trace.
        self._traces = []  # list[list[PathSlicedData]]
        # One slice viewer per trace; parallel to ``self._traces``. Each
        # "Create new" Enter opens a fresh viewer so the user can
        # compare slices side by side. ``self._slice_viewer`` (set on
        # the base class) shadows the most recent for callers that
        # only know the singular attribute (e.g. the crosshair tool's
        # introspection).
        self._slice_viewers = []
        # None means "create new on next Enter"; otherwise one of
        # ``self._traces``.
        self._target_trace = None
        # Path overlays on the source viewer's axes, one Line2D per
        # trace, indexed by trace identity.
        self._overlays = {}  # dict[id(trace_list), Line2D]
        # The menu is a child of the toolbar button. The button isn't
        # created until after Tool.__init__ returns (the toolbar's
        # add_tool builds the action and its widget), so defer wiring.
        QtCore.QTimer.singleShot(0, self._install_dropdown)

    # ------------------------------------------------------------------
    # Dropdown
    # ------------------------------------------------------------------

    def _install_dropdown(self):
        toolbar = self.viewer.toolbar
        action = toolbar.actions.get(self.tool_id)
        if action is None:
            return
        button = toolbar.widgetForAction(action)
        if button is None:
            return
        self._menu = _TargetMenu(self, parent=button)
        button.setMenu(self._menu)
        # MenuButtonPopup gives the button a small arrow next to the
        # icon: clicking the icon still activates the tool with the
        # current target; clicking the arrow shows the menu.
        button.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)

    def _menu_entries(self):
        """The (label, target) pairs the menu shows. ``target`` is
        ``None`` for "create new" or a trace list."""
        entries = [('Create new path', None)]
        for i, trace in enumerate(self._traces, start=1):
            entries.append((f'Update path {i}', trace))
        return entries

    def _set_target(self, target):
        """Set the next-trace target. ``None`` means create new."""
        self._target_trace = target
        self._refresh_overlays()

    # ------------------------------------------------------------------
    # Overlay drawing
    # ------------------------------------------------------------------

    def _refresh_overlays(self):
        # Remove any artists for traces that no longer exist.
        current_keys = {id(trace) for trace in self._traces}
        for key in list(self._overlays):
            if key not in current_keys:
                self._overlays.pop(key).remove()

        # Add/update an artist per trace. The on-screen geometry uses
        # the first PathSlicedData's (x, y), which is in its parent
        # cube's pixel frame -- valid for the source viewer's
        # reference_data layer.
        for trace in self._traces:
            key = id(trace)
            x, y = trace[0].x, trace[0].y
            alpha = (_PATH_ALPHA_ACTIVE if trace is self._target_trace
                     else _PATH_ALPHA_INACTIVE)
            if key in self._overlays:
                line = self._overlays[key]
                line.set_data(x, y)
                line.set_alpha(alpha)
            else:
                line = Line2D(x, y, color=_PATH_COLOR, alpha=alpha, lw=2,
                              zorder=100)
                self.viewer.axes.add_line(line)
                self._overlays[key] = line
        self.viewer.figure.canvas.draw_idle()

    def _hover_preview(self, target):
        """Temporarily highlight ``target`` as the user hovers over its
        menu entry, without committing the selection."""
        for trace, line in zip(self._traces,
                               [self._overlays.get(id(t)) for t in self._traces]):
            if line is None:
                continue
            line.set_alpha(_PATH_ALPHA_ACTIVE if trace is target
                           else _PATH_ALPHA_INACTIVE)
        self.viewer.figure.canvas.draw_idle()

    # ------------------------------------------------------------------
    # The trace -> PathSlicedData side
    # ------------------------------------------------------------------

    def _open_or_update(self, vx, vy):
        # Don't route through path_slicer.common.open_or_update_slice_viewer
        # here: that helper assumes one PathSlicedData per cube and uses
        # ``find_existing_path_slice`` to locate it. With multiple paths
        # per cube the helper would pick a sibling at random and
        # overwrite its vertices.
        if self._target_trace is None:
            new_paths = self._create_trace(vx, vy)
            slice_viewer = self._open_slice_viewer_for(new_paths)
            self._slice_viewers.append(slice_viewer)
            # Shadow the latest viewer on the base-class attribute so
            # the crosshair tool's introspection still finds something.
            self._slice_viewer = slice_viewer
            # The just-created trace becomes the target for the next
            # Enter, so consecutive Enters tweak the same path until
            # the user picks something else from the dropdown.
            self._target_trace = self._traces[-1]
        else:
            self._update_trace(self._target_trace, vx, vy)
            # set_xy broadcasts NumericalDataChangedMessage; the
            # corresponding slice viewer's layer refreshes in place,
            # no extra wiring needed here.
        self._refresh_overlays()

    def _open_slice_viewer_for(self, paths):
        slice_viewer = self.viewer.session.application.new_data_viewer(
            self.slice_viewer_cls)
        for path in paths:
            slice_viewer.add_data(path)
        slice_viewer.state.aspect = 'auto'
        if hasattr(slice_viewer.state, 'color_mode'):
            slice_viewer.state.color_mode = self.viewer.state.color_mode
        slice_viewer.state.reset_limits()
        return slice_viewer

    def _create_trace(self, vx, vy):
        dc = self.viewer.session.data_collection
        x_att = self.viewer.state.x_att
        y_att = self.viewer.state.y_att
        new_trace = []
        for layer_state in self.viewer.state.layers:
            data = layer_state.layer
            if not isinstance(data, Data):
                continue
            n_existing = sum(
                1 for trace in self._traces for ps in trace
                if ps.original_data is data)
            label = f'{data.label} [slice {n_existing + 1}]'
            path = PathSlicedData(data, x_att, np.asarray(vx, dtype=float),
                                  y_att, np.asarray(vy, dtype=float),
                                  label=label)
            path.parent_viewer = self.viewer
            dc.append(path)
            link_path_sliced_to_parent(dc, path)
            new_trace.append(path)
        # Pairwise-link the new trace's PathSlicedData against each
        # other and against every PathSlicedData in every existing
        # trace, so the slice viewer can render them all together.
        for trace in self._traces:
            for slice_a in new_trace:
                for slice_b in trace:
                    link_path_sliced_pair_paths(dc, slice_a, slice_b)
        for i, slice_a in enumerate(new_trace):
            for slice_b in new_trace[i + 1:]:
                link_path_sliced_pair_paths(dc, slice_a, slice_b)
        self._traces.append(new_trace)
        return new_trace

    @staticmethod
    def _update_trace(trace, vx, vy):
        vx_arr = np.asarray(vx, dtype=float)
        vy_arr = np.asarray(vy, dtype=float)
        for path in trace:
            path.set_xy(vx_arr, vy_arr)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        for line in self._overlays.values():
            line.remove()
        self._overlays.clear()
        for slice_viewer in self._slice_viewers:
            slice_viewer.close()
        self._slice_viewers.clear()
        self._slice_viewer = None
        # Skip BasePathSlicerMode.close (which would close the same
        # ``_slice_viewer`` we already handled); jump to PathMode.close.
        return super(BasePathSlicerMode, self).close()


class _TargetMenu(QtWidgets.QMenu):
    """Dynamic popup menu that rebuilds itself with the tool's current
    traces every time it's about to show. Hovering an entry previews
    the corresponding path on the source viewer's overlay."""

    def __init__(self, tool, parent=None):
        super().__init__(parent)
        self._tool = tool
        self.aboutToShow.connect(self._rebuild)
        self.aboutToHide.connect(self._restore_overlays)

    def _rebuild(self):
        self.clear()
        for label, target in self._tool._menu_entries():
            action = self.addAction(label)
            if target is self._tool._target_trace:
                # Mark the current selection (works with the platform's
                # default check style; on most themes a tick appears).
                action.setCheckable(True)
                action.setChecked(True)
            action.triggered.connect(
                lambda _checked=False, t=target: self._tool._set_target(t))
            # Hover preview: highlight the corresponding path while the
            # cursor is over the entry. ``target`` is None for the
            # "Create new path" entry; in that case fade all overlays.
            action.hovered.connect(
                lambda t=target: self._tool._hover_preview(t))

    def _restore_overlays(self):
        # When the menu closes, snap back to the committed target's
        # highlight state (the triggered handler already updated
        # ``_target_trace`` if the user clicked something).
        self._tool._refresh_overlays()


@viewer_tool
class PathSlicerCrosshairMode(BasePathSlicerCrosshairMode):
    tool_id = 'path:crosshair'


def setup():
    ImageViewer.tools.append('slice')
    ImageViewer.tools.append('path:crosshair')
