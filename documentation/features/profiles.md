# Feature: Profiles

Un perfil es un espacio de trabajo independiente: tiene sus propias apps trackeadas y sus propias sesiones. Útil para separar contextos (trabajo / personal / gaming).

---

## Conceptos clave

- Siempre existe al menos un perfil: **Default** (no se puede eliminar).
- Solo un perfil está **activo** en cada momento. El tracker registra sesiones en el perfil activo.
- Las apps y sesiones de distintos perfiles son completamente independientes.

---

## Cambiar de perfil

En Settings → Profiles, o en el panel lateral (nombre del perfil activo visible en el sidebar).

Al activar un perfil:
- `PUT /api/profiles/{id}/activate` actualiza `is_active=1` en BD
- El tracker recarga `_exe_map` con las apps del nuevo perfil en el próximo ciclo
- El dashboard y Manage Apps muestran solo las apps del perfil activo

---

## Crear y eliminar perfiles

**Crear**: Settings → Profiles → `+ New profile`. Solo se pide el nombre.

**Eliminar**: botón `✕` en la lista de perfiles. No se puede eliminar Default. Eliminar un perfil borra en cascada todas sus apps y sesiones (`ON DELETE CASCADE` en SQLite).

---

## Migrar datos entre perfiles

Settings → Profiles → sección **Migrate profile**.

Seleccionar origen → destino → Migrate. Mueve todas las apps y sesiones del perfil origen al destino:
- Si el destino ya tiene una app con el mismo exe, las sesiones del origen se redirigen a esa app y la entrada del origen se elimina.
- Si no hay colisión, la app entera (con sus sesiones) se mueve al destino.
- El perfil origen queda vacío (pero sigue existiendo).

Esta operación **no se puede deshacer**.

---

## Exportar un perfil

Settings → Profiles → sección **Export profile** → Download JSON.

Descarga un JSON con:
```json
{
  "profile": { "id": 1, "name": "Default", ... },
  "apps": [ { "id": ..., "exe_name": ..., "display_name": ..., ... } ],
  "sessions": [ { "id": ..., "app_id": ..., "started_at": ..., ... } ]
}
```

Útil para hacer copias de seguridad o trasladar datos entre instalaciones. No hay importación automática (se puede hacer restaurando la BD directamente).

---

## Archivos relevantes

| Fichero | Rol |
|---|---|
| `ui/static/shared.js` | `loadProfilesSettings`, `newProfile`, `activateProfile`, `deleteProfile`, `confirmMigrate`, `doExportProfile` |
| `api/routes.py` | `/profiles` CRUD, `/profiles/migrate`, `/profiles/{id}/export` |
| `core/database.py` | `create_profile`, `set_active_profile`, `delete_profile`, `migrate_profile` |
