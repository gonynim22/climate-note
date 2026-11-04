# build.spec - PyInstaller 빌드 설정
# 실행: pyinstaller build.spec

from pathlib import Path
import sys

_SPEC_DIR = Path(SPECPATH) if "SPECPATH" in globals() else Path.cwd()
sys.path.insert(0, str(_SPEC_DIR))
sys.path.insert(0, str(_SPEC_DIR / "src"))  # 앱 모듈(B안)

from app_info import APP_DISPLAY_NAME, APP_VERSION
from build_app import make_windows_version_info

block_cipher = None

dist_name = f"{APP_DISPLAY_NAME}_{APP_VERSION}"
version_info = make_windows_version_info()

# 화면 글자 따기(걷어낼 수 있는 선택형 미니앱): 폴더가 있을 때만 모델·onnxruntime·numpy를 넣는다.
# html은 폴더와 무관하게 넣는다. src/ui_text.py(v4.5)와 screen_text/layout.py가 html.escape를 쓴다.
# 걷어낸 빌드에서 html을 빼면 빌드는 성공하고 EXE만 시작하지 못했다(2026-10-31 실측).
_SCREEN_TEXT = (_SPEC_DIR / "screen_text").is_dir()
_SCREEN_TEXT_DATAS = [
    ('screen_text/models', 'screen_text/models'),
    ('screen_text/icon.svg', 'screen_text'),
    ('screen_text/licenses', 'screen_text/licenses'),
] if _SCREEN_TEXT else []
_SCREEN_TEXT_IMPORTS = ['onnxruntime', 'numpy'] if _SCREEN_TEXT else []

a = Analysis(
    ['main.py'],
    pathex=[str(_SPEC_DIR), str(_SPEC_DIR / "src")],
    binaries=[],
    datas=[
        ('icon', 'icon'),
        ('fonts', 'fonts'),
        ('resources', 'resources'),
        ('licenses', 'licenses'),
        ('LICENSE', '.'),
    ] + _SCREEN_TEXT_DATAS,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtXml',
        'PySide6.QtNetwork',
        'qfluentwidgets',
        'cryptography',
        'cryptography.fernet',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.primitives.hashes',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.backends.openssl',
        'pythoncom',
        'win32job',
        'win32api',
        'xml.etree.ElementTree',
        'defusedxml',
        'defusedxml.ElementTree',
    ] + _SCREEN_TEXT_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 불필요한 모듈 제외 (경량화)
        'matplotlib',
        'pandas',
        'PIL',
        'scipy',
        'tkinter',
        'wx',
        'PyQt5',
        'PyQt6',
        'xmlrpc',
        'unittest',
        'pydoc',
        'doctest',
        'asyncio',
        'concurrent',
        'multiprocessing',
        'ctypes.test',
        'lib2to3',
        'distutils',
        'pkg_resources',
        'setuptools',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'sphinx',
        'sqlalchemy',
        'arrow',
        'pendulum',
        'loguru',
        # PySide6 불필요 서브모듈 제외 (대폭 경량화)
        # 주의: QtXml, QtSvg, QtSvgWidgets, QtNetwork는 qfluentwidgets가 사용하므로 제외 금지
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DExtras',
        'PySide6.Qt3DAnimation',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtPositioning',
        'PySide6.QtLocation',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtRemoteObjects',
        'PySide6.QtScxml',
        'PySide6.QtStateMachine',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtUiTools',
        'PySide6.QtConcurrent',
        'PySide6.QtDBus',
        'PySide6.QtHttpServer',
    ] + ([] if _SCREEN_TEXT else ['numpy']),
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=dist_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # UPX 압축으로 크기 최소화
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,     # 콘솔 창 숨김 (GUI 앱)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon/icon_fixed_256.ico',
    version=version_info,
)
