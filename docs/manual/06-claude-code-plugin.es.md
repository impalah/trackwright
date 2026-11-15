# Plugin de Claude Code y skills de productor

[English](06-claude-code-plugin.md) · **Español**

Las herramientas de la [referencia de herramientas](04-tools.es.md) son piezas sueltas. El plugin de Trackwright para Claude Code añade **skills**: instrucciones que enseñan al modelo a encadenar esas herramientas en un trabajo de productor, hacer las preguntas adecuadas y detenerse donde hace falta tu criterio. Pides con tus palabras («corta los silencios de más de 3 segundos») y la skill hace el resto contigo.

## Instalación

1. **Lado de Cubase, una vez:** `uv tool install trackwright` y `trackwright setup`. Instala el script y crea la configuración; cuando ofrezca registrar el servidor MCP en Claude Code, responde **no** (lo hace el plugin). Reinicia Cubase.
2. **Permisos** en `~/.config/trackwright/config.toml`:
   ```toml
   [writes]
   enabled = true

   [analysis]
   enabled = true
   ```
   `[writes]` permite a las skills cambiar el proyecto; `[analysis]`, leer el audio que exportes (ver el [capítulo de configuración](03-configuration.es.md)).
3. **En Claude Code:**
   ```text
   /plugin marketplace add impalah/trackwright
   /plugin install trackwright@trackwright
   ```
   En la extensión de Claude Code para VS Code, lo mismo desde `/plugins`.

El plugin arranca su propio servidor con `uvx trackwright==<versión> serve`, así que sus skills siempre se ejecutan contra la versión del servidor para la que se escribieron.

**Si antes registraste el servidor a mano** (`claude mcp add` o `trackwright setup`), quita ese registro: con los dos, Claude Code muestra cada herramienta dos veces, lo que confunde al modelo.

```sh
claude mcp remove trackwright --scope user
```

## Cómo trabajan las skills contigo

Todas las skills siguen las mismas normas, además de la seguridad propia del servidor (dry run, política de escritura, verificación por relectura):

- **Pregunta antes de cambiar nada.** Enseña el plan (los cortes, el plugin y sus valores) y espera tu sí.
- **Los diálogos los haces tú.** La API de Cubase no puede leer audio, así que las skills miden una **exportación**: la skill pone el rango y abre «Exportar mezcla de audio», y tú eliges el formato y pulsas Exportar. Cubase Elements solo exporta Stereo Out, así que la skill pone antes la pista en solo y lo deshace justo después.
- **Nunca guarda el proyecto** si no se lo pides.
- **Todo se puede deshacer** con Edición > Deshacer en Cubase, y la skill te dice cuántas veces.

Todas las skills tienen las mismas secciones y fases, y registran lo que crean para que al repetirlas actualicen lo suyo y nunca lo tuyo: ver [el contrato de las skills](07-skill-contract.es.md).

Cuando te pida exportar, elige: Stereo Out, Archivo Wave, **32 bit float**, la frecuencia de muestreo del proyecto, el nombre que te sugiera y la exportación en tiempo real desactivada.

## `podcast-session-audit`

Hace inventario de la sesión antes de trabajar en ella, y guarda en el perfil del episodio lo que confirmas.

- **Pídela así:** "revisa este episodio", "comprueba el proyecto antes de mezclar", "prepara el perfil del episodio".
- **Qué mira:** cada pista (tipo, salida, fader, mute, solo, plugins) y dónde empiezan y acaban los eventos de cada pista de audio, la extensión del episodio, y lo que Trackwright ya sabe (los perfiles de programa y de episodio, las pistas que crearon otras skills). No mide audio ni necesita exportar.
- **Qué señala:** un solo olvidado, una pista silenciada que tiene audio, una pista sin salida, un fader en silencio, una pista vacía, un render y la pista a la que sustituye; como preguntas, porque tú decides qué es intencionado.
- **Qué pregunta:** a qué programa pertenece el episodio, el rol de cada pista (voz, música, efectos, referencia, otro; nunca lo adivina por el nombre), y los rangos que ninguna skill debe tocar (tú das los tiempos; los marcadores no se pueden leer).
- **Qué no puede ver** (lo dice siempre): la automatización, la ganancia de los clips y los fundidos, los marcadores, un evento que empieza exactamente en 0 s, los presets de los plugins, los envíos y los side-chains.
- **Qué escribe:** solo `Trackwright/profile.toml`, después de enseñártelo; nada cambia en el proyecto de Cubase.

## `podcast-silence-trim`

Encuentra los silencios más largos que una duración y los quita, cerrando los huecos para que el episodio sea más corto.

- **Pídelo así:** «quita los silencios de más de 3 segundos», «corta las pausas de más de 2 s entre el minuto 5 y el 20».
- **Qué pregunta:** la duración mínima (2 s si no lo dices), el rango (todo el proyecto por defecto) y qué analizar.
- **Por qué analiza por defecto toda la mezcla:** el corte quita el tramo de **todas las pistas**, así que un tramo solo es seguro de cortar si está en silencio en todas. Si nombras una pista y otras tienen sonido ahí (otra voz, una música de fondo), te explica las opciones: toda la mezcla, solo esa pista sabiendo que los cortes afectan a las demás, o borrar solo en esa pista sin cerrar los huecos.
- **Qué te enseña:** cada corte propuesto (inicio, fin, duración) y el tiempo total que se quitaría. Tú eliges todos, algunos o ninguno.
- **Cómo corta:** del último al primero, para que las posiciones anteriores no se muevan; cada corte se verifica con los bordes de los eventos de una pista.
- **Márgenes:** se conservan 0,25 s de cada silencio en los dos extremos para no comerse palabras (un silencio de 3 s se convierte en un corte de 2,5 s). Pide cortes más ajustados o más holgados si quieres.

## `noise-gate`

Añade y ajusta una puerta de ruido en una pista, para que el ruido de fondo entre frases desaparezca y la voz suave se conserve.

- **Pídelo así:** «pon una noise gate en la pista Voz», «quita el ruido de sala en las pausas de la pista del invitado».
- **Qué puerta:** no da ninguna por supuesta. Busca puertas entre tus plugins (`Gate` de Cubase o de terceros), descarta las que no actúan por nivel de audio (las que se abren con MIDI, los reductores de ruido espectrales) y te deja elegir si hay varias. Una vez cargado, comprueba que el plugin tiene de verdad un umbral en dB.
- **Cómo elige el umbral:** mide el **ruido de fondo** y la **voz más baja** sobre una exportación y pone el umbral en medio. La puerta oye la pista antes de su fader y su panorama, y la exportación sale después de ellos, así que traduce el valor (una pista mono centrada se exporta 3 dB más baja). Si el ruido y la voz suave están a menos de 12 dB, te avisa de que una puerta no puede separarlos bien.
- **Qué propone:** umbral, rango (cuánto atenúa; unos −30 dB suenan naturales en voz, −∞ lo quita todo), hold y release (para no cortar los finales de palabra). Tú los apruebas o los cambias.
- **Cómo comprueba el resultado:** opcionalmente, una segunda exportación con la puerta activa: las pausas deben bajar más o menos lo que indica el rango, y la voz suave debe mantener su nivel. Después, escucha: ninguna medida sustituye a tus oídos.
- **Quitarla:** el interruptor Bypass del plugin, o quítalo del slot de inserción en Cubase (Trackwright no puede quitar plugins).

Medido con una señal de prueba (ruido a −55 dBFS, voz a −16 y −36 dBFS): el ruido de las pausas bajó 30 dB y las frases fuerte y suave mantuvieron exactamente su nivel (ver el registro de verificación).

## Otros clientes MCP

Las skills usan solo los campos del estándar abierto [Agent Skills](https://agentskills.io), así que los mismos archivos podrían funcionar en otros clientes que lean ese formato. **No** se ha probado todavía; por ahora el plugin es para Claude Code (terminal y extensión de VS Code).
