import numpy as np

from matplotlib.lines import Line2D

from glue.core import Data
from glue.config import viewer_tool
from glue.viewers.matplotlib.toolbar_mode import PathMode, ToolbarModeBase
from glue.plugins.tools.pv_slicer.path_sliced_data import PathSlicedData
from glue.plugins.tools.pv_slicer.path_sliced_data_links import (
    link_path_sliced_to_parent, link_path_sliced_pair_paths)

from glue_qt.viewers.image import ImageViewer


__all__ = ['PathSlicerMode', 'PathSlicerCrosshairMode']


@viewer_tool
class PathSlicerMode(PathMode):
    """
    Draw a path on the image viewer; on Enter, materialise a
    :class:`~glue.plugins.tools.pv_slicer.path_sliced_data.PathSlicedData`
    for each cube currently in the viewer and open a PV viewer that
    displays them. Re-pressing the tool reuses the existing PV viewer
    and updates the path in place.
    """

    icon = 'glue_slice'
    tool_id = 'slice'
    action_text = 'Slice Extraction'
    tool_tip = ('Extract a slice from an arbitrary path\n'
                '  ENTER accepts the path\n'
                '  ESCAPE clears the path')
    status_tip = ('Draw a path then press ENTER to extract slice, '
                  'or press ESC to cancel')
    shortcut = 'P'

    def __init__(self, viewer, **kwargs):
        super().__init__(viewer, **kwargs)
        self._roi_callback = self._extract_callback
        self._pv_viewer = None
        self.viewer.state.add_callback('reference_data',
                                       self._on_reference_data_change)
        self._on_reference_data_change()

    def _on_reference_data_change(self, *args):
        # State callbacks can fire after Tool.close() has cleared
        # self.viewer (the state outlives the tool); just bail.
        if self.viewer is None:
            return
        if self.viewer.state.reference_data is not None:
            self.enabled = self.viewer.state.reference_data.ndim == 3

    def _clear_path(self):
        self.viewer.hide_crosshairs()
        self.clear()

    def _extract_callback(self, mode):
        vx, vy = mode.roi().to_polygon()
        self._build_or_update_pvs(vx, vy)

    def _build_or_update_pvs(self, vx, vy):
        viewer_is_new = self._pv_viewer is None
        if viewer_is_new:
            self._pv_viewer = self.viewer.session.application.new_data_viewer(
                ImageViewer)

        dc = self.viewer.session.data_collection
        x_att = self.viewer.state.x_att
        y_att = self.viewer.state.y_att

        updated_pvs = []
        for layer_state in self.viewer.state.layers:
            data = layer_state.layer
            if not isinstance(data, Data):
                # Subsets come along automatically when their parent
                # Data is added; nothing to do here.
                continue

            existing = self._find_existing_pv(dc, data)
            if existing is None:
                pv = PathSlicedData(data, x_att, vx, y_att, vy,
                                    label=data.label + ' [slice]')
                pv.parent_viewer = self.viewer
                dc.append(pv)
                link_path_sliced_to_parent(dc, pv)
            else:
                pv = existing
                pv.cid_x = x_att
                pv.cid_y = y_att
                pv.sliced_dims = (x_att.axis, y_att.axis)
                pv.set_xy(vx, vy)
            updated_pvs.append((pv, layer_state))

        # Link the path axes of every PV pair so the PV viewer's
        # generic FRB calls can translate between them.
        for i, (pv_a, _) in enumerate(updated_pvs):
            for pv_b, _ in updated_pvs[i + 1:]:
                if not self._path_link_exists(dc, pv_a, pv_b):
                    link_path_sliced_pair_paths(dc, pv_a, pv_b)

        if viewer_is_new:
            for pv, layer_state in updated_pvs:
                self._pv_viewer.add_data(pv)
                # Best-effort: copy visual state (color, attribute, etc.)
                # so the PV layer reads as the same series as the cube
                # layer. Some properties' choices aren't yet populated
                # at this point (the layer's just been added) -- in that
                # case fall through and let the user customise.
                pvstate = layer_state.as_dict()
                pvstate.pop('layer', None)
                for new_layer_state in self._pv_viewer.state.layers[::-1]:
                    if new_layer_state.layer is pv:
                        try:
                            new_layer_state.update_from_dict(pvstate)
                        except ValueError:
                            pass
                        break
            self._pv_viewer.state.aspect = 'auto'
            self._pv_viewer.state.color_mode = self.viewer.state.color_mode
            self._pv_viewer.state.reset_limits()

    @staticmethod
    def _find_existing_pv(dc, parent_data):
        for d in dc:
            if isinstance(d, PathSlicedData) and d.original_data is parent_data:
                return d
        return None

    @staticmethod
    def _path_link_exists(dc, pv_a, pv_b):
        cid_a = pv_a.pixel_component_ids[-1]
        cid_b = pv_b.pixel_component_ids[-1]
        for link in dc.external_links:
            ends = list(getattr(link, '_from', []))
            to = getattr(link, '_to', None)
            if to is not None:
                ends.append(to)
            if cid_a in ends and cid_b in ends:
                return True
        return False

    def close(self):
        if self._pv_viewer is not None:
            self._pv_viewer.close()
            self._pv_viewer = None
        return super().close()


@viewer_tool
class PathSlicerCrosshairMode(ToolbarModeBase):
    """
    Tool for the PV viewer that, while the mouse is dragged, projects
    the current cursor position back to the parent cube viewer and
    moves the cube's slice index accordingly.
    """

    icon = 'glue_path'
    tool_id = 'pv:crosshair'
    action_text = 'Show position on original path'
    tool_tip = 'Click and drag to show position of cursor on original slice.'
    status_tip = tool_tip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._move_callback = self._on_move
        self._press_callback = self._on_press
        self._release_callback = self._on_release
        self._active = False
        self._line = None
        self._crosshair = None
        self.data = None
        self.viewer.state.add_callback('reference_data',
                                       self._on_reference_data_change)
        self._on_reference_data_change()

    def _on_reference_data_change(self, *args):
        if self.viewer is None:
            return
        ref = self.viewer.state.reference_data
        self.enabled = isinstance(ref, PathSlicedData) \
            and getattr(ref, 'parent_viewer', None) is not None
        self.data = ref if self.enabled else None

    def activate(self):
        # Draw the path on the parent viewer, plus an empty crosshair
        # marker that the move callback will reposition.
        self._line = Line2D(self.data.x, self.data.y, zorder=1000,
                            color='#669dff', alpha=0.6, lw=2)
        self.data.parent_viewer.axes.add_line(self._line)
        self._crosshair = self.data.parent_viewer.axes.plot(
            [], [], '+', ms=12, mfc='none', mec='#669dff', mew=1,
            zorder=100)[0]
        self.data.parent_viewer.figure.canvas.draw_idle()
        super().activate()

    def deactivate(self):
        if self._line is not None:
            self._line.remove()
            self._line = None
        if self._crosshair is not None:
            self._crosshair.remove()
            self._crosshair = None
        if self.data is not None:
            self.data.parent_viewer.figure.canvas.draw_idle()
        super().deactivate()

    def _on_press(self, mode):
        self._active = True

    def _on_release(self, mode):
        self._active = False

    def _on_move(self, mode):
        if not self._active or self.data is None:
            return

        xdata, ydata = self._event_xdata, self._event_ydata
        if xdata is None or ydata is None:
            return

        # The PV viewer's x-axis is the path index; clip and round to
        # land on a valid sample of the parent's path.
        ind = int(round(np.clip(xdata, 0, self.data.shape[-1] - 1)))
        x = self.data.x[ind]
        y = self.data.y[ind]
        self._crosshair.set_xdata([x])
        self._crosshair.set_ydata([y])

        # The PV's y-axis is the parent cube's non-sliced axis -- move
        # the parent viewer's slice index to that integer pixel. This
        # writes to ImageViewerState.slices, which is backend-agnostic
        # (so the same approach works for the matplotlib and bqplot
        # image viewers in glue-jupyter).
        parent_viewer = self.data.parent_viewer
        state = parent_viewer.state
        slc = list(state.slices)
        for i in range(state.reference_data.ndim):
            if i != state.x_att.axis and i != state.y_att.axis:
                slc[i] = int(ydata)
        state.slices = tuple(slc)
        parent_viewer.figure.canvas.draw_idle()
