from unittest.mock import MagicMock

import numpy as np

from glue.core import Data
from glue.core.coordinates import IdentityCoordinates
from glue.plugins.tools.path_slicer.path_sliced_data import PathSlicedData

from glue_qt.app import GlueApplication
from glue_qt.viewers.image import ImageViewer

from .. import PathSlicerMode, PathSlicerCrosshairMode


class TestPathSlicerMode:

    def setup_method(self, method):
        self.cube = Data(label='cube',
                         x=np.arange(1000).reshape((5, 10, 20)),
                         coords=IdentityCoordinates(n_dim=3))
        self.app = GlueApplication()
        self.dc = self.app.data_collection
        self.dc.append(self.cube)
        self.viewer = self.app.new_data_viewer(ImageViewer, data=self.cube)

    def teardown_method(self, method):
        self.viewer.close()
        self.viewer = None
        self.app.close()
        self.app = None

    def test_extract_callback_creates_path_sliced_data(self):
        self.viewer.toolbar.active_tool = 'slice'
        tool = self.viewer.toolbar.active_tool
        assert isinstance(tool, PathSlicerMode)

        # Stub the ROI to feed a known vertex list to _extract_callback.
        roi = MagicMock()
        roi.to_polygon.return_value = ([1, 10, 12], [2, 13, 14])
        mode = MagicMock()
        mode.roi.return_value = roi

        tool._extract_callback(mode)

        # The data collection should now hold the cube and one path slice.
        slices = [d for d in self.dc if isinstance(d, PathSlicedData)]
        assert len(slices) == 1
        assert slices[0].original_data is self.cube
        # parent_viewer is wired up so PathSlicerCrosshairMode can find
        # its way back to the cube viewer.
        assert slices[0].parent_viewer is self.viewer

    def test_re_extracting_updates_existing_slice_in_place(self):
        self.viewer.toolbar.active_tool = 'slice'
        tool = self.viewer.toolbar.active_tool

        roi = MagicMock()
        roi.to_polygon.return_value = ([1, 10, 12], [2, 13, 14])
        mode = MagicMock()
        mode.roi.return_value = roi
        tool._extract_callback(mode)
        first_slice = [d for d in self.dc if isinstance(d, PathSlicedData)][0]
        first_x = first_slice.x.copy()

        # Re-trace -- there must still be a single slice and its x must have
        # been replaced (not appended-to or recreated).
        roi.to_polygon.return_value = ([0, 5, 15], [0, 4, 12])
        tool._extract_callback(mode)
        slices = [d for d in self.dc if isinstance(d, PathSlicedData)]
        assert len(slices) == 1
        assert slices[0] is first_slice
        assert not np.array_equal(first_x, slices[0].x)

    def test_crosshair_disabled_without_path_sliced_reference_data(self):
        # The crosshair tool only makes sense when the viewer's reference
        # data is a PathSlicedData with a known parent_viewer; on a plain
        # cube viewer it should be disabled.
        mode = PathSlicerCrosshairMode(self.viewer)
        assert mode.enabled is False
        assert mode.data is None

    def test_crosshair_enabled_on_slice_viewer(self):
        # Push a PathSlicedData through the slice tool, then verify the
        # crosshair tool reports as enabled when constructed against the
        # slice viewer (which the slice tool opened).
        self.viewer.toolbar.active_tool = 'slice'
        tool = self.viewer.toolbar.active_tool
        roi = MagicMock()
        roi.to_polygon.return_value = ([1, 10, 12], [2, 13, 14])
        mode = MagicMock()
        mode.roi.return_value = roi
        tool._extract_callback(mode)

        slice_viewer = tool._slice_viewer
        assert slice_viewer is not None
        crosshair = PathSlicerCrosshairMode(slice_viewer)
        assert crosshair.enabled is True
        assert isinstance(crosshair.data, PathSlicedData)

    def test_crosshair_action_hidden_on_cube_viewer(self):
        # The crosshair tool only makes sense over a slice viewer; the
        # toolbar must hide the action when the tool reports as disabled
        # at registration time (not just on subsequent changes).
        action = self.viewer.toolbar.actions['path:crosshair']
        assert action.isVisible() is False
        assert self.viewer.toolbar.tools['path:crosshair'].enabled is False
