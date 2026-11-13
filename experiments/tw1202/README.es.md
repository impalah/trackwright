# Experimento TW-1202: guardar el proyecto

[English](README.md) · **Español**

**Fecha:** 2026-11-13.
**Entorno:** Cubase Elements 15.0.30, script 1.5.3 y proyecto de pruebas `X0001`, con autorización expresa del usuario para guardarlo.
**Verificación:** nombres, tamaños y fechas de los `.cpr` de la carpeta del proyecto (deducida con `lsof`). No se abrió ningún archivo.

| Paso | Antes | Después |
|---|---|---|
| `File / Save` (13:58:16) | `X0001.cpr`, 227 194 bytes, 2026-11-12 20:54:01 | `X0001.cpr`, 228 091 bytes, **13:58:17**. Sin `.bak` (el Cubase del usuario no hace copia al guardar) |
| `File / Save New Version` (13:58:26) | — | **`X0001-01.cpr`** nuevo, 228 094 bytes, 13:58:27. `X0001.cpr` sin cambios |

- **`canPerform`** de los dos comandos: `true`. Actúan sin que el script deje de responder (clase *direct* en un proyecto ya guardado).
- **Tras `Save New Version`,** Cubase trabaja sobre el archivo nuevo: los siguientes `Save` irán a `X0001-01.cpr`.
- **No probado:** `Save` en un proyecto **nunca guardado**. Previsiblemente abre «Guardar como» (diálogo).

## Diseño de `cubase_save_project`

- **Modos:** `save` y `new_version`.
- **Permiso propio** (`[writes] save = true`, desactivado por defecto) además de las escrituras, y `dry_run` por defecto.
- **Verificación:** algún `.cpr` de la carpeta del proyecto con fecha posterior a la orden. Con `new_version`, uno nuevo.
- **Si no aparece en unos segundos:** `awaiting_user`, porque puede haber un diálogo, como en un proyecto sin guardar.
- **Fuera de alcance:** `Close`, `Revert` y `Quit`. No se ofrecen.
