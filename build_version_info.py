"""
Genera el fichero de recurso de versión de Windows para PyInstaller, a partir
de core/version.py — así el número que ve Windows en Propiedades del .exe
(Detalles → Versión del archivo / del producto) nunca se desincroniza del que
devuelve /api/instance y se ve en Ajustes: una sola fuente de la verdad.
"""

from core.version import __version__, version_tuple

_TEMPLATE = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers},
    prodvers={filevers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'InfectedBit'),
        StringStruct(u'FileDescription', u'TimeTrack'),
        StringStruct(u'FileVersion', u'{version}'),
        StringStruct(u'InternalName', u'TimeTrack'),
        StringStruct(u'OriginalFilename', u'TimeTrack.exe'),
        StringStruct(u'ProductName', u'TimeTrack'),
        StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def write(path: str = "build_version_info.txt") -> str:
    major, minor, patch = version_tuple(__version__)
    filevers = (major, minor, patch, 0)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_TEMPLATE.format(filevers=filevers, version=__version__))
    return path
