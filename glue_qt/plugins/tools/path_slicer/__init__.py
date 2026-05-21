"""
Qt-specific bindings for the path slicer tool. The drawing mode and
the crosshair mode are matplotlib-only and live in glue-core; this
module just subclasses them to set the Qt-specific viewer class and
tool IDs, registers them with ``@viewer_tool``, and wires the IDs
onto :class:`~glue_qt.viewers.image.ImageViewer` via :func:`setup`.
"""

from glue.config import viewer_tool
from glue.plugins.tools.path_slicer.matplotlib_mode import (
    BasePathSlicerMode, BasePathSlicerCrosshairMode)

from glue_qt.viewers.image import ImageViewer


__all__ = ['PathSlicerMode', 'PathSlicerCrosshairMode']


@viewer_tool
class PathSlicerMode(BasePathSlicerMode):
    tool_id = 'slice'
    slice_viewer_cls = ImageViewer


@viewer_tool
class PathSlicerCrosshairMode(BasePathSlicerCrosshairMode):
    tool_id = 'path:crosshair'


def setup():
    ImageViewer.tools.append('slice')
    ImageViewer.tools.append('path:crosshair')
