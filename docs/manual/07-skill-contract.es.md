# El contrato de las skills

[English](07-skill-contract.md) · **Español**

Todas las skills de Trackwright (TW-1609) tienen la misma forma, para que cada una se pueda leer, revisar y confiar en ella del mismo modo, y para que una skill nunca toque lo que no es suyo. `tests/unit/test_plugin.py` comprueba la forma de cada `SKILL.md` de `plugins/claude-code/skills/`.

## Secciones

Un `SKILL.md` tiene estas secciones (`## …`), en este orden. Puede haber otras antes o entre ellas (por ejemplo, una explicación de lo que hace el trabajo).

| Sección | Qué dice |
|---|---|
| `Requires` | Lo que debe cumplirse antes de empezar: campos de `cubase_status` (`connected`, `writes_enabled`, `analysis_enabled`, `workspace_enabled`, `allowed_tracks`), plugins que deben estar instalados, y qué decir cuando falta alguno. |
| `Inputs` | Lo que la skill necesita del usuario, y lo que toma de los perfiles de programa y de episodio (`cubase_profile`): valores por defecto que propone, roles de pista, rangos protegidos. Solo pregunta lo que falta. |
| `Workflow` | El trabajo, en siete fases (abajo). |
| `Safety` | Lo que la skill no debe hacer nunca. |
| `Outputs` | Lo que recibe el usuario: el informe, los archivos que quedan (exportaciones, renders, informes), cómo deshacer, y que el proyecto no se guarda. |
| `Ownership` | Lo que crea la skill (pistas, plugins, renders, marcadores…), cómo lo registra en `Trackwright/state.json`, y cómo al repetirla encuentra y actualiza lo suyo en lugar de añadir cosas nuevas. Todo lo que no está registrado como de la skill es del usuario. |

## Fases del flujo

Dentro de `Workflow`, un paso por fase (`### N. Fase`), en este orden:

1. **Inspect:** leer el proyecto (pistas, inserciones, solos, lo que `state.json` dice que la skill creó antes).
2. **Analyze:** exportar con el usuario y medir; nombrar la exportación de la que salen los números (`source`), y exportar de nuevo cuando `source.project_saved_after` dice que el proyecto se guardó después.
3. **Propose:** un plan breve con los números de los que sale.
4. **Preview:** lo que el usuario puede oír antes del cambio (o justo después): un archivo de preescucha, un rango en ciclo con Bypass, o un dry run. Cuando no hay preescucha, el paso dice por qué y qué la sustituye.
5. **Approve:** un sí explícito del usuario. Nada cambia antes.
6. **Apply:** cada escritura con dry run primero, nunca repetida tras un timeout; registrar lo creado (`cubase_workspace`, acción `record`).
7. **Verify:** comprobar el resultado (releer, bordes, una exportación y un análisis nuevos) y pedir al usuario que escuche.

## La propiedad en `state.json`

`cubase_workspace` con `action: "record"` guarda un elemento por cada cosa que creó una skill: `kind` (`track`, `plugin`, `render`, `preview`, `marker`, `automation`, `report`), `key` (un uid de pista, `<uid de pista>/slot:N`, una ruta dentro del espacio de trabajo…), `skill`, `run_id` y `details` libres. `action: "forget"` lo quita cuando esa cosa ya no existe. `cubase_import_audio` registra por sí solo la pista de un render. Las reglas:

- una skill solo actualiza o sustituye elementos registrados a su nombre;
- un plugin o una pista sin registrar es del usuario: solo se cambia cuando el usuario pide ese en concreto, y nunca se registra como de la skill;
- registrar necesita `[workspace] enabled` y el espacio de trabajo creado (`cubase_workspace`, acción `init`); sin ello la skill funciona pero no puede reconocer lo suyo en otra ejecución, y lo dice.

## Reglas comunes

- Hablar al usuario en su idioma; mantenerle informado, porque está delante de Cubase.
- Dry run primero; aplicar solo lo que el usuario aprobó en esta conversación.
- Restaurar todos los solos (`cubase_export_mix` con `solo`, y `cancel` si se abandona la exportación).
- No repetir nunca una escritura tras un timeout: releer el estado.
- No guardar nunca el proyecto si no se pide (`cubase_save_project`).
- Leer solo las exportaciones y archivos que señala el usuario.
