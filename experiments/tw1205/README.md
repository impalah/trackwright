# Experimento TW-1205: presets de los plugins

**Fecha:** 2026-11-13.
**Entorno:** Cubase Elements 15.0.30, script 1.5.5 y Compressor en el slot 1 de POC-TEST.
**Método:**
- se guardaron los 15 parámetros del Compressor (sin medidores);
- se comparó tras cada comando;
- al final se restauraron escribiéndolos uno a uno (diferencia final: **ninguna**) y se cerró el editor.

## Abrir el editor

El slot tiene el parámetro **«Edición»** (tag 4101): escribir 1 abre el editor del plugin y 0 lo cierra. La relectura da «Activ.» / «Desact.» ✅.

## `Preset / Next` y `Previous`

| Caso | Resultado |
|---|---|
| Editor abierto por la API y **sin preset cargado** (estado original) | `canPerform = true`, **sin cambios** |
| El usuario enfoca la ventana y elige un preset por error | Threshold −13,9 dB, Ratio 5,2:1… |
| **Next** con la ventana enfocada | ✅ Cambian 5 parámetros (Threshold −33,0 dB, Ratio 2,44:1, Attack 3,8 ms, Release 437 ms, Analysis 100 %) |
| **Previous** | ✅ Vuelve exactamente a los valores anteriores |
| Next con el editor **cerrado** | Sin cambios |
| Next con el editor **abierto por la API, sin clic**, con un preset cargado | ✅ Cambia; Previous lo deshace exactamente |

## Validación de la herramienta y causa real (2026-11-13)

- **Primer intento con la herramienta:** sin cambios, también con un preset recién elegido y con 1 s de espera tras abrir el editor.
- **Causa:** los comandos actúan sobre la ventana de plugin con el **foco de teclado**. El caso que funcionó (editor reabierto por la API) venía de un clic previo del usuario en esa ventana.
- **Confirmación:**
  1. editor abierto por la API y un clic del usuario: Next cambia 8 parámetros y Previous los devuelve exactos;
  2. cerrado y reabierto por la API, sin clic nuevo: Next sigue funcionando.
- **Diseño final:** si no cambia nada, `awaiting_user`, con el editor abierto y la petición de un clic. La siguiente llamada funciona.
- **Nombre del preset:** no está en la API (la única mención a «preset» es el downmix de la sala de control) ni en el plugin o el slot. Solo se puede comprobar que cambió.
- **Restauración:** el Compressor quedó con los 15 valores originales (diferencia: ninguna) y con el editor cerrado.

## Conclusiones

- Los comandos actúan sobre el **editor de plugin con el foco de teclado**: hace falta un clic del usuario la primera vez. Con el editor cerrado no hacen nada.
- **Sin un preset cargado no hacen nada:** el usuario tiene que haber elegido antes un preset en la ventana del plugin. Es la explicación más probable del primer intento.
- El cambio se verifica comparando los parámetros del plugin antes y después.
- El preset **no se puede elegir por nombre** ni se puede leer su nombre: solo avanzar o retroceder.
- Con varios editores abiertos, no se sabe a cuál se aplica. La herramienta debe trabajar con uno solo.
