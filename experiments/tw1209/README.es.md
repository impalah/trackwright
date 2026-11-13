# Experimento TW-1209: propiedades del proyecto

[English](README.md) · **Español**

**Fecha:** 2026-11-13.
**Entorno:** Cubase Elements 15.0.30, script 1.4.0 y proyecto de pruebas.
**Alcance:** todo en solo lectura, salvo mover el cursor en el paso 2, que luego se restauró. No hizo falta instalar un script de experimento.

## 1. Carpeta del proyecto con `lsof` (con permiso del usuario)

- **Cubase no mantiene abierto el `.cpr`** (0 coincidencias): lo lee al abrir y lo cierra.
- **Sí quedan abiertos los archivos de audio** del proyecto, en `<carpeta del proyecto>/Audio/`. De ahí sale la carpeta: `/ruta/a/proyectos/TEST`.
- **Límites:**
  - no da el nombre exacto del `.cpr`;
  - en un proyecto sin audio no se ve nada;
  - con varios proyectos abiertos aparecerían varias carpetas.
- No se listó el contenido de la carpeta.

## 2. Compás deducido normalizando posiciones (cursor movido y restaurado)

| Posición pedida | Cubase la deja en | Conclusión |
|---|---|---|
| `1. 5. 1. 0` | `2. 1. 1. 0` | 4 tiempos por compás |
| `1. 4. 1. 0` | `1. 4. 1. 0` | El tiempo 4 existe |
| `1. 1. 5. 0` | `1. 2. 1. 0` | 4 semicorcheas por tiempo: el tiempo es una negra, denominador 4 |
| `1. 7. 1. 0` | `2. 3. 1. 0` | Coherente con 4/4 |
| `1. 1. 1. 300` | `1. 1. 3. 60` | 120 ticks por semicorchea |
| `1. 1. 1. 500` | `1. 2. 1. 20` | Ídem |

Funciona, pero lo hace innecesario el paso 3.

## 3. Objetos DirectAccess fuera del mezclador

`da.object` acepta cualquier ID. Los hijos de «Device Root» (ID 1) incluyen objetos de estudio y de proyecto, **leídos sin escribir nada**.

### «Transporte» (`type: Transport`, ID 18 en esta sesión; 101 parámetros)

| Tag | Título | Valor leído |
|---|---|---|
| 4027 | `signature` | **«4/4»** |
| 4022 | `cycle` | Desact. |
| 4099 | `metronomeOn` | Desact. |
| 4100 | `precountOn` | Desact. |
| 4020 / 4021 | `punchIn` / `punchOut` | Desact. |
| 4028 / 4029 | `punchInTime` / `punchOutTime` | 2. 1. 1. 0 / 4. 1. 1. 0 |
| 4030 / 4031 / 4051 | `cycleLeftTime` / `cycleRightTime` / `cycleDuration` | 2. 1. 1. 0 / 4. 1. 1. 0 / 2. 0. 0. 0 |
| 4032 / 4033, 4037 / 4038 | `preRoll` / `postRoll`, `usePreRoll` / `usePostRoll` | 0 / Desact. |
| 4023 / 4101 | `time` / `time2` | 1. 1. 1. 0 / 0:00:00.000 (**la segunda pantalla sí da segundos aquí**) |
| 4025 / 4102 | `timeFormat` / `timeFormat2` | Compases+Tiempos / Segundos |
| 4129, 4121, 4106, 4107, 4108 | Modos de grabación | Punch in/out, Mantener historial, Nuevas partes, Mix, Iniciar en cursor |
| 4145 / 4150 | `startPlayModes` / `returnOnStop` | Inicio desde posición / Desact. |
| 4015 / 4016 / 4019 | `start` / `stop` / `record` | Estado del transporte (stop = Activ.) |
| 4098 | `message` | OFFLINE |

### Otros objetos

- **«Metronome»** (`type: Metronome`): `clickLevel` 127, `tickInRecord` Desact. y `tickInPlayback` Desact. Este último es el «clic durante la reproducción».
- **«Sistema de audio»:** su único hijo es la interfaz de audio, sin parámetros. **No se toca** (regla de no controlar interfaces de audio).
- **Sin rastro en ningún objeto** (IDs 0–699) de la frecuencia de muestreo, la resolución, el frame rate, la longitud del proyecto o su nombre.

## 4. Verificación con 3/4 (cambiado por el usuario en la barra de transporte)

- **`signature`** (tag 4027) = **«3/4»**. El valor de proceso es 1966,12 (con 4/4 era 2621,48): una codificación interna, así que se usa el texto mostrado.
- **Normalización del cursor:** `1. 4. 1. 0` → `2. 1. 1. 0` (3 tiempos), `1. 3. 1. 0` se mantiene y `1. 1. 5. 0` → `1. 2. 1. 0` (denominador 4). **Coincide.**
- **Sin verificar:** el comportamiento con cambios de compás a mitad del proyecto, porque no hay pista de compás.

## Conclusiones

1. **TW-1209 se puede implementar sin script nuevo,** con `da.params` sobre los objetos Transport y Metronome. Se localizan **por tipo** entre los hijos de Device Root, porque los IDs cambian entre sesiones.
2. **Compás:** el parámetro `signature` lo da directamente, verificado con 4/4 y 3/4. Queda por ver si sigue al cursor cuando hay cambios de compás.
3. **TW-1210:** los parámetros del Transport (`cycle`, `metronomeOn`, `precountOn`, `punchIn`…) son candidatos a escribirse con `da.param.set` y releerse. **Sin probar:** escribir es parte de TW-1210.
4. **Frecuencia de muestreo, longitud y nombre:** no accesibles por la API. Para la carpeta, `lsof`, con sus límites.
