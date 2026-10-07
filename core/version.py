"""
TimeTrack — versión.

Fuente única de la verdad. La leen:
  · main.py           → metadatos de FastAPI y /docs
  · core/instance.py  → decide quién releva a quién entre dos instancias
  · api/routes.py     → GET /api/instance

Al publicar una release hay que subir SOLO este número: si la versión que
anuncia el ejecutable es más baja que la que ya corre, el nuevo .exe cederá el
paso al viejo y el usuario creerá que la actualización no se ha aplicado.
"""

__version__ = "0.16.1"


def version_tuple(raw) -> tuple[int, int, int]:
    """
    'v0.16.0' → (0, 16, 0). Para comparar con < y >.

    Lo que no se pueda interpretar cuenta como la versión más antigua posible:
    un instance.json corrupto o de un formato futuro no debe impedir que una
    instancia legítima arranque.
    """
    if not isinstance(raw, str):
        return (0, 0, 0)

    parts = raw.strip().lstrip("vV").split(".")[:3]
    out: list[int] = []
    for part in parts:
        # Solo los dígitos INICIALES: "0rc1" → 0, no 1. Si se concatenaran todos,
        # una release candidate (0.16.0rc1) contaría como más nueva que la final.
        digits = ""
        for ch in part:
            if not ch.isdigit():
                break
            digits += ch
        out.append(int(digits) if digits else 0)
    while len(out) < 3:
        out.append(0)

    return (out[0], out[1], out[2])
