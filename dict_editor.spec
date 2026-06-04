# -*- mode: python ; coding: utf-8 -*-
#
# Build:  uv run pyinstaller dict_editor.spec
# Output: dist/词典编辑器/词典编辑器.exe
#
from pathlib import Path

# ── Qt DLLs this app never uses ───────────────────────────────────────────────
# Removing them cuts bundle size from ~400 MB to ~120 MB and speeds up startup.
_EXCLUDE_DLLS = {
    # WebEngine (biggest offender: ~200 MB)
    'qt6webenginecore.dll', 'qt6webengine.dll',
    'qt6webenginewidgets.dll', 'qt6webenginequick.dll',
    # QML / Quick
    'qt6qml.dll', 'qt6qmlcompiler.dll', 'qt6qmlcore.dll',
    'qt6qmllocalstorage.dll', 'qt6qmlmodels.dll',
    'qt6qmlnativefunctions.dll', 'qt6qmlworkerscript.dll',
    'qt6qmlxmllistmodel.dll',
    'qt6quick.dll', 'qt6quickcontrols2.dll', 'qt6quickcontrols2impl.dll',
    'qt6quickcontrols2basic.dll', 'qt6quickcontrols2basicstyleimpl.dll',
    'qt6quickcontrols2fusion.dll', 'qt6quickcontrols2fusionstyleimpl.dll',
    'qt6quickcontrols2imagine.dll', 'qt6quickcontrolsimagine.dll',
    'qt6quickcontrols2imaginestyleimpl.dll',
    'qt6quickcontrols2material.dll', 'qt6quickcontrols2materialstyleimpl.dll',
    'qt6quickcontrols2universal.dll', 'qt6quickcontrols2universalstyleimpl.dll',
    'qt6quickdialogs2.dll', 'qt6quickdialogs2quickimpl.dll',
    'qt6quickdialogs2utils.dll',
    'qt6quicklayouts.dll', 'qt6quickparticles.dll',
    'qt6quickshapes.dll', 'qt6quicktemplates2.dll', 'qt6quickwidgets.dll',
    # 3D
    'qt63dcore.dll', 'qt63dextras.dll', 'qt63dinput.dll',
    'qt63dlogic.dll', 'qt63dquick.dll', 'qt63dquickextras.dll',
    'qt63dquickinput.dll', 'qt63dquickscene2d.dll', 'qt63drender.dll',
    'qt63drenderquick.dll',
    'qt6quick3d.dll', 'qt6quick3dassetimporter.dll', 'qt6quick3dassetutils.dll',
    'qt6quick3dhelpers.dll', 'qt6quick3druntimerender.dll', 'qt6quick3dutils.dll',
    # Multimedia / ffmpeg
    'qt6multimedia.dll', 'qt6multimediaquick.dll', 'qt6multimediawidgets.dll',
    'avcodec-61.dll', 'avformat-61.dll', 'avutil-61.dll',
    'swresample-61.dll', 'swscale-8.dll', 'ffmpeg.exe',
    # Other heavy / unused
    'qt6designer.dll', 'qt6designercomponents.dll',
    'qt6pdf.dll', 'qt6pdfquick.dll',
    'qt6shadertools.dll',
    'qt6charts.dll', 'qt6datavisualization.dll',
    'qt6virtualkeyboard.dll',
    'qt6scxml.dll', 'qt6statemachine.dll',
    'qt6location.dll', 'qt6positioning.dll', 'qt6positioningquick.dll',
    'qt6remoteobjects.dll', 'qt6sensors.dll', 'qt6serialport.dll',
    'qt6bluetooth.dll', 'qt6nfc.dll',
    # Software OpenGL fallback (not needed with Fusion widget style)
    'opengl32sw.dll',
}

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.ico', '.')],
    hiddenimports=[
        'mdict_utils',
        'mdict_utils.base',
        'mdict_utils.base.readmdict',
        'mdict_utils.base.writemdict',
        'mdict_utils.base.lzo',
        'markdown',
        'markdown.extensions.extra',
        'markdown.extensions.nl2br',
        'markdown.extensions.sane_lists',
        'markdown.extensions.tables',
        'markdown.extensions.fenced_code',
        'markdown.treeprocessors',
        'markdown.postprocessors',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # PySide6 modules not imported by this app
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic', 'PySide6.Qt3DExtras', 'PySide6.Qt3DAnimation',
        'PySide6.Qt3DQuick', 'PySide6.QtQuick3D',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtDesigner',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtShaderTools',
        'PySide6.QtVirtualKeyboard',
        'PySide6.QtScxml', 'PySide6.QtStateMachine',
        'PySide6.QtLocation', 'PySide6.QtPositioning',
        'PySide6.QtRemoteObjects', 'PySide6.QtSensors',
        'PySide6.QtSerialPort', 'PySide6.QtBluetooth', 'PySide6.QtNfc',
        'PySide6.QtTest', 'PySide6.QtHelp',
        'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
        # stdlib bloat
        'tkinter', '_tkinter', 'unittest', 'pydoc',
        'difflib', 'doctest',
    ],
    noarchive=False,
    optimize=1,
)

# Drop the unwanted Qt DLLs that Analysis still pulls in transitively
a.binaries = [
    (name, src, typ)
    for name, src, typ in a.binaries
    if Path(name).name.lower() not in _EXCLUDE_DLLS
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='词典编辑器',
    contents_directory='data',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX decompresses at load time — slower startup
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,          # same reason: skip UPX on DLLs for faster startup
    name='词典编辑器',
)