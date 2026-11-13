# E11 — Panel de estado en la superficie MIDI Remote

**Objetivo.** Hoy la pestaña MIDI Remote de Cubase muestra para «Trackwright – Bridge» un rectángulo vacío: el único elemento del script es `makeLabelField(0, 0, 4, 1)`, que se puso solo para que Cubase mostrara la superficie. La idea es aprovechar ese espacio como **panel de estado informativo**: si Trackwright está conectado, qué versión del script hay, qué pista está seleccionada y cuál fue la última operación.

Es una ayuda visual y de depuración. **No cambia el funcionamiento:** las herramientas MCP no dependen del panel.

## Observación de partida (captura del usuario, 2026-11-12)

En la pestaña MIDI Remote, Cubase muestra:
- **Título «Trackwright - Bridge»:** viene de `makeDeviceDriver('Trackwright', 'Bridge', …)`.
- **«Página de mapeado: Bridge»:** viene de `makePage('Bridge')`.
- **En el centro:** un recuadro redondeado casi cuadrado, con una pequeña barra blanca dentro y una línea horizontal a cada lado.

**Pregunta abierta:** no se sabe si ese dibujo es el campo de texto `makeLabelField(0, 0, 4, 1)` escalado (la barra blanca) con decoración de Cubase, o un marcador genérico que Cubase pinta cuando la superficie no tiene controles. Un campo de 4×1 debería verse ancho y bajo, y no es lo que aparece. Lo resuelve el primer experimento del alcance (punto 2): añadir elementos fáciles de reconocer y ver qué cambia.

## TW-1101 Panel de estado en la superficie

- **Estado:** hecha (script 1.1.0)
- **Prioridad:** baja (mejora de experiencia de uso)

### Qué dice la API (typings locales v1)

La superficie se **dibuja a partir de los elementos que declara el script**. No hay forma de poner imágenes, iconos ni colores: en los typings no aparece ninguna API de imagen.

| Necesidad | Mecanismo | Seguridad |
|---|---|---|
| Texto fijo («Trackwright 1.0.0») | `page.setLabelFieldText(campo, texto)`. Lo usan los scripts de fábrica (Korg nanoKONTROL); se fija al cargar el script | Documentado |
| Nombre de la pista seleccionada | `page.setLabelFieldHostObject(campo, mTrackSelection.mMixerChannel)`. Muestra el título del objeto y lo sigue | Documentado; comportamiento sin verificar |
| Textos que cambian en tiempo de ejecución (conectado, última operación) | `setDisplayValue(activeDevice, texto)` (API 1.3) sobre el valor de un elemento o de una variable, con un campo asociado a ese elemento mediante `campo.relateTo(elemento)` | **Sin evidencia**: no consta que un campo de texto muestre el `displayValue` de un elemento |
| Actividad (petición en curso) | `makeLamp(…)` y `lamp.mSurfaceValue.setProcessValue(activeDevice, 1 o 0)` | Sin verificar si la lámpara se ilumina en pantalla al cambiar el valor desde el script |

### Alcance propuesto

1. **Diseño** de la superficie, en una cuadrícula de unas 8×3 unidades:
   - **Fila 1:** texto fijo «Trackwright» y la versión del script.
   - **Fila 2:** nombre de la pista seleccionada (`setLabelFieldHostObject`).
   - **Fila 3:** estado dinámico («conectado», la última operación con su resultado y hora) y una lámpara de actividad.
2. **Prueba de concepto en Cubase**, antes de comprometer el diseño. Verificar, una por una, las cuatro mecánicas de la tabla y capturar en el registro lo que se ve.
3. **Implementación** de las que funcionen.
   - El panel se actualiza en `mOnSysex` y `mOnIdle` sin coste apreciable: como mucho una actualización por ciclo de idle.
   - Debe ser **pasivo**: ningún elemento del panel se asocia a comandos ni a valores de Cubase que el usuario pudiera cambiar por accidente al hacer clic en la superficie.
4. **Si los textos dinámicos no funcionan:** quedarse con el texto fijo y la pista seleccionada, y documentar la limitación.

### Preparación del experimento (hecha, 2026-11-13)

- **Panel en el script principal, desactivado** (`PANEL_ENABLED = false`): el script publicado no cambia. Un test comprueba que sigue teniendo un único campo de 4×1 y `capabilities.panel.enabled = false`.
- **Versión de prueba:** `experiments/tw1101/build.py` genera `1.0.1+tw1101` con el panel activado.
- **Instalación:** `trackwright script install --file <script>` (con ensayo previo) instala la versión de prueba, y `script install --apply` vuelve a la publicada.
- **Arnés de Node.js:** emula los campos, `relateTo`, las lámparas y `setLabelFieldText` / `setLabelFieldHostObject`. Los tests comprueban la disposición, el texto con cada petición, el parpadeo y que todas las operaciones siguen respondiendo. **Esto solo demuestra que el script llama a la API como se pretende; lo que dibuja Cubase solo se sabe en Cubase.**
- **Protocolo:** pasos E1 a E6 en [`experiments/tw1101/README.md`](../../experiments/tw1101/README.md).

### Resultados del experimento (2026-11-13)

Detalle en [`docs/verificacion.md`](../verificacion.md#2026-11-13--experimento-tw-1101-panel-de-estado-script-101tw1101).

| Mecanismo | Resultado |
|---|---|
| Texto fijo (`setLabelFieldText`) | ✅ funciona |
| Pista seleccionada (`setLabelFieldHostObject`) | ✅ funciona y se actualiza sola |
| Lámpara (`setProcessValue`) | ✅ parpadea según lo que fija el script |
| Texto dinámico (`relateTo` + `setDisplayValue`) | ❌ siempre «-» |

La **pregunta abierta** queda resuelta: el dibujo inicial era el campo de texto de 4×1 vacío.

### Decisión e implementación (script 1.1.0)

Se adopta lo verificado (opción elegida por el usuario):
- **Fila 0:** «Trackwright <versión>» (`setLabelFieldText`) y, a la derecha, una **lámpara de actividad**. Se enciende al llegar una petición y se apaga cuando la cola queda vacía, tras un mínimo de 3 ciclos de idle (unos 0,3 s), para que se vea.
- **Fila 1:** la pista seleccionada (`setLabelFieldHostObject`).
- **Descartados:** la fila de estado (`relateTo` + `setDisplayValue`, que no se muestra) y el parpadeo continuo.

Tests en `tests/script/test_panel.py`: disposición, uso exclusivo de mecanismos verificados, encendido y apagado de la lámpara, una sola conmutación con varias peticiones en cola y operaciones sin bloqueo. El generador del experimento se retiró, y su protocolo queda en `experiments/tw1101/README.md`.

### Riesgos

- **Mapping Assistant:** los elementos visibles aparecen en el asistente de asignación de Cubase, y el usuario podría asignarles funciones. Usar campos de texto y lámparas, que no se asignan, y nunca knobs ni botones.
- **Un error en la superficie impide que el script cargue.** Cada llamada a la API de la superficie va dentro de `try/catch`, y un fallo se registra en `status.lastError` sin afectar al resto.
- **Compatibilidad:** `setDisplayValue` es de la API 1.3 (Cubase 15.0.20 o posterior). Comprobar su existencia antes de usarlo.

### Criterios de aceptación

- El script sigue cargando y todas las operaciones existentes pasan los tests del arnés de Node.js. El arnés se amplía para emular los elementos nuevos.
- Prueba en Cubase real anotada en `docs/verificacion.md`: qué se ve en cada estado (puente parado, conectado y operación en curso), con la descripción del usuario.
- Ninguna operación de Trackwright se ralentiza: se comparan las latencias de `ping` y `da.channels` antes y después.
- El manual de instalación (paso 6) describe lo que el usuario debe ver en el panel.

### Fuera de alcance

- Imágenes, logotipos o colores: la API no lo permite.
- Controles interactivos en el panel, como botones que lancen acciones.
