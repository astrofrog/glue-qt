from .pv_slicer import *  # noqa


def setup():
    from glue_qt.viewers.image import ImageViewer
    from glue_qt.plugins.tools.pv_slicer import (  # noqa: F401
        PathSlicerMode, PathSlicerCrosshairMode)
    ImageViewer.tools.append('slice')
    ImageViewer.tools.append('pv:crosshair')
