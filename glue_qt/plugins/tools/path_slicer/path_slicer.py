"""
Qt-specific bindings for the path slicer tool. The drawing mode and
the crosshair mode are matplotlib-only and live in glue-core; this
module just subclasses them to set the Qt-specific PV viewer class
and tool IDs, and to register with ``@viewer_tool``.
"""

from glue.config import viewer_tool
from glue.plugins.tools.path_slicer.matplotlib_mode import (
    BasePathSlicerMode, BasePathSlicerCrosshairMode)

from glue_qt.viewers.image import ImageViewer


__all__ = ['PathSlicerMode', 'PathSlicerCrosshairMode']


@viewer_tool
class PathSlicerMode(BasePathSlicerMode):
    tool_id = 'slice'
    pv_viewer_cls = ImageViewer


@viewer_tool
class PathSlicerCrosshairMode(BasePathSlicerCrosshairMode):
    tool_id = 'path:crosshair'
