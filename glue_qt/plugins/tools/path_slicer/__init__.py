from .path_slicer import *  # noqa: F401, F403


def setup():
    from glue_qt.viewers.image import ImageViewer
    from glue_qt.plugins.tools.path_slicer.path_slicer import (  # noqa: F401
        PathSlicerMode, PathSlicerCrosshairMode)
    ImageViewer.tools.append('slice')
    ImageViewer.tools.append('path:crosshair')
