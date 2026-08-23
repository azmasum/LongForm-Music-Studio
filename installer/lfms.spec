# PyInstaller spec for the LFMS portable build.
# Build from the repo root:  pyinstaller installer\lfms.spec --noconfirm
import os
import sys

block_cipher = None
ROOT = os.path.abspath(SPECPATH + os.sep + "..")

# Embed a real Windows version resource (Explorer properties, Inno Setup's
# GetVersionNumbersString) from the single source of truth in lfms.core.
sys.path.insert(0, ROOT)
from PyInstaller.utils.win32.versioninfo import (  # noqa: E402
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

from lfms.core.version import APP_NAME, ORGANIZATION, VERSION  # noqa: E402

_parts = [int(x) for x in VERSION.split(".")] + [0] * (4 - len(VERSION.split(".")))
_filevers = tuple(_parts[:4])
version_resource = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=_filevers,
        prodvers=_filevers,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", ORGANIZATION),
                        StringStruct("FileDescription", APP_NAME),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("ProductName", APP_NAME),
                        StringStruct("ProductVersion", VERSION),
                        StringStruct("OriginalFilename", "LongFormMusicStudio.exe"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

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
    version=version_resource,
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
