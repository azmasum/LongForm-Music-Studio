# PyInstaller spec for the LFMS portable build.
# Build from the repo root:  pyinstaller installer\lfms.spec --noconfirm
import os

block_cipher = None
ROOT = os.path.abspath(SPECPATH + os.sep + "..")

a = Analysis(
    [os.path.join(ROOT, "installer", "entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[
        # stubs the excluded scipy.special._ellip_harm_2 (see file)
        os.path.join(ROOT, "installer", "rthook_scipy_ellip.py"),
    ],
    excludes=[
        "pytest",
        "setuptools",
        "tkinter",
        "matplotlib",
        "IPython",
        "jedi",
        # scipy subpackages LFMS never needs AND nothing eagerly imports
        # (verified via sys.modules after importing scipy.signal).
        # Do NOT exclude integrate/interpolate/optimize/stats/ndimage/
        # spatial/sparse.* here — scipy.signal imports them eagerly and
        # the frozen app dies with circular ImportErrors.
        "scipy.io",
        "scipy.misc",
        "scipy.cluster",
        "scipy.odr",
        # excluded because modulegraph's bytecode scan crashes on them;
        # installer/rthook_scipy_ellip.py stubs both back at runtime
        "scipy.special._ellip_harm_2",
        "scipy.stats",
    ],
    noarchive=False,
)
# ship libsndfile DLLs that soundfile needs at runtime
import soundfile as _sf

_sf_dir = os.path.dirname(_sf.__file__)
for _name in ("_soundfile_data",):
    _p = os.path.join(_sf_dir, _name)
    if os.path.isdir(_p):
        a.datas += Tree(_p, prefix=os.path.join("_soundfile_data"))

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LongFormMusicStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="LongFormMusicStudio",
)
