"""PyInstaller runtime hooks: stub excluded-but-eagerly-imported modules.

Two scipy modules are excluded from the bundle because modulegraph's
bytecode scan crashes on them, yet they are imported eagerly by packages
LFMS really needs:

- ``scipy.special._ellip_harm_2`` — required by ``scipy.special`` itself;
  we stub the two names ``_ellip_harm.py`` imports.
- ``scipy.stats`` — only consumer inside ``scipy.signal`` is one
  ``scoreatpercentile`` call in ``_peak_finding.py``; we reimplement it
  via ``numpy.percentile`` and stub everything else.

Calling any stubbed routine raises NotImplementedError instead of
crashing at startup.
"""
import sys
import types


def _unavailable(*_args, **_kwargs):
    raise NotImplementedError(
        "this scipy submodule is not bundled in this build"
    )


def _install_ellip_stub() -> None:
    name = "scipy.special._ellip_harm_2"
    if name in sys.modules:
        return
    try:
        __import__(name)
        return
    except Exception:  # noqa: BLE001 - any failure means we need the stub
        pass
    stub = types.ModuleType(name)
    stub._ellipsoid = _unavailable
    stub._ellipsoid_norm = _unavailable
    sys.modules[name] = stub


def _install_stats_stub() -> None:
    name = "scipy.stats"
    if name in sys.modules:
        return
    try:
        __import__(name)
        return
    except Exception:  # noqa: BLE001 - any failure means we need the stub
        pass

    def scoreatpercentile(data, per, limit=(), interpolation_method="fraction",
                          axis=None, out=None, overwrite_input=False):
        import numpy as np

        del limit, interpolation_method, out, overwrite_input
        return np.percentile(data, per, axis=axis)

    stub = types.ModuleType(name)
    stub.scoreatpercentile = scoreatpercentile
    stub.__getattr__ = lambda attr: _unavailable
    sys.modules[name] = stub


_install_ellip_stub()
_install_stats_stub()
