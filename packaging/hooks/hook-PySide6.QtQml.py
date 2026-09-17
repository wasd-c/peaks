"""Collect only the QML modules used by Peaks.

PyInstaller's stock PySide6 hook walks every QML module shipped in the
PySide6 wheel. That includes optional QtWebEngine, QtQuick3D, multimedia,
and mobile-style modules that are not reachable from Peaks' QML imports.
Keeping the filter here (rather than deleting files after ``COLLECT``) lets
PyInstaller still validate and resolve the native plugins that are included.
"""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()
binaries += qml_binaries
datas += qml_datas


def _is_required_qml_file(source: str) -> bool:
    """Keep non-QML hook data and only the QML modules imported by Main.qml."""

    qml_root_value = pyside6_library_info.location.get("QmlImportsPath")
    if not qml_root_value:
        qml_root_value = pyside6_library_info.location.get("Qml2ImportsPath")
    if not qml_root_value:
        return False

    try:
        relative = Path(source).resolve().relative_to(Path(qml_root_value).resolve())
    except ValueError:
        # ``add_qt6_dependencies`` also returns translations and native Qt
        # plugins. They are not QML module files and must remain intact.
        return True

    parts = relative.parts
    if not parts:
        return False

    # QtQml is an auto-import dependency of QtQuick. Keep its models and
    # worker-script submodules together because the qml plugin references
    # them at runtime.
    if parts[0] == "QtQml":
        return True
    if parts[0] != "QtQuick":
        return False
    if len(parts) <= 2:
        return True

    # Basic is the default QtQuick.Controls style. ``impl`` and
    # ``Basic/impl`` are implementation imports of that style. The other
    # style trees (Imagine, Material, Universal, iOS, macOS, FluentWinUI3)
    # are optional and account for most of the otherwise unnecessary QML
    # payload.
    if parts[1] == "Controls":
        return len(parts) == 3 or parts[2] in {"Basic", "impl"}
    return parts[1] in {"Effects", "Layouts", "Templates", "Window"}


binaries = [item for item in binaries if _is_required_qml_file(item[0])]
datas = [item for item in datas if _is_required_qml_file(item[0])]
