"""Load only the parts of the pinned MediaCrawler tree this adapter calls.

Upstream package __init__ files import each platform's full crawler (database,
cache, CSV/Excel and word-cloud stores), and tools.utils imports the slider-CAPTCHA
solver (OpenCV/NumPy). The adapter uses the API clients, field enums and helpers
only, and never solves CAPTCHAs, so those imports are skipped here. Vendor files
stay byte-for-byte unchanged; with the full requirements installed nothing is skipped.
"""
import importlib.util
import sys
import types
from pathlib import Path

PLATFORMS = ('xhs', 'bilibili', 'weibo', 'zhihu', 'douyin', 'kuaishou', 'tieba')


def _package(name, path):
    if name in sys.modules:return
    module = types.ModuleType(name)
    module.__path__ = [str(path)];module.__package__ = name
    module.__file__ = str(Path(path) / '__init__.py')
    sys.modules[name] = module
    parent, _, child = name.rpartition('.')
    if parent in sys.modules:setattr(sys.modules[parent], child, module)


def prepare(root):
    # Relative paths in a not-yet-configured runtime.json are relative to the skill folder.
    root = Path(root)
    if not root.is_absolute():root = Path(__file__).resolve().parents[1] / root
    root = root.resolve()
    if str(root) not in sys.path:sys.path.insert(0, str(root))
    # Platform packages without their crawler-importing __init__.
    _package('media_platform', root / 'media_platform')
    for platform in PLATFORMS:_package('media_platform.' + platform, root / 'media_platform' / platform)
    # Slider CAPTCHA solving needs OpenCV; manual login never calls it.
    if 'tools.slider_util' not in sys.modules and importlib.util.find_spec('cv2') is None:
        import tools
        stub = types.ModuleType('tools.slider_util');stub.__all__ = []
        stub.__doc__ = 'Skipped: slider CAPTCHA solving is not used; users verify manually.'
        sys.modules['tools.slider_util'] = stub;tools.slider_util = stub
    return root
