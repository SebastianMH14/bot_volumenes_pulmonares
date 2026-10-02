# CLAUDE.md

Bot RPA (Python + Selenium) que adjunta los informes PDF de **volúmenes pulmonares** en la historia clínica de **Sunu** (`cemde.sunu.be`) para CEMDE, sede Laureles, consultorio 22. Arquitectura y decisiones: [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

## Comandos

En el equipo de producción se usa el `venv`: `.\venv\Scripts\python.exe` en lugar de `python`.

```bash
python -m unittest discover tests      # tests: no requieren Sunu, navegador ni pdfplumber
python main.py --solo-leer             # lee PDFs de la bandeja; no entra a Sunu ni mueve archivos
python main.py --sin-correo            # corrida real sin enviar el reporte
python explorar_sunu.py <cedula>       # vuelca pestañas/HTML del perfil a debug/; no modifica Sunu
python -m py_compile main.py config.py explorar_sunu.py modules/*.py
run_bot.bat [args de main.py]          # lo que corre la tarea programada (venv, PYTHONUTF8=1, salida a logs\tarea_programada.log)
```

Windows, Python 3.10+. `pdfplumber` se importa de forma diferida en `lector_pdf.extraer_texto`; los tests de parseo trabajan sobre texto y no lo necesitan. `tests/test_sunu.py` importa `config`, que lee el `.env` y crea las carpetas de trabajo. `explorar_sunu.py` espera Enter al final; sin terminal interactiva: `echo | python explorar_sunu.py <cedula>`.

## Reglas del proyecto

- **Datos de pacientes nunca van a git.** `bandeja/`, `data/`, `logs/`, `debug/`, `*.pdf` y `.env` están en `.gitignore`. Los tests usan datos ficticios; al agregar casos a partir de informes reales, anonimizar cédula y nombre.
- **Tampoco se muestran en la salida.** El nombre de cada PDF trae el nombre del paciente, y los logs, `data/`, `debug/` y el título del modal de adjuntos de Sunu traen cédula y nombre. Al revisar, resumir con conteos o enmascarar (dígitos, nombres en MAYÚSCULAS, nombres de archivo).
- **Las contraseñas del `.env`** (Sunu y contraseña de aplicación de Gmail) las pone el usuario; no escribirlas ni mostrarlas.
- **No tocar `bot_espirometrias`** (repo hermano en `../bot_espirometrias`). Se puede leer como referencia, pero no se edita, no se hace commit ni push allí.
- **No hacer push** sin que el usuario lo pida. Mensajes de commit en español, en imperativo/presente como los existentes.
- **El bot solo adjunta el PDF.** Nunca automatizar la lectura/firma médica ("Procesar lectura", `formFirmarAdjuntoFormato`) ni crear registros clínicos en Sunu; está fuera del alcance contratado.
- **Nunca ejecutar `main.py` sin `--solo-leer`** contra Sunu real sin confirmación del usuario: sube archivos a historias clínicas.

## Convenciones de código

- Código, logs, comentarios y mensajes en español; logger único `logging.getLogger("bot_volumenes")`.
- Configuración solo en `config.py` desde `.env`; usar `os.getenv(X) or default` (una variable vacía no debe romper el default).
- Selectores de Sunu:
  - Anclar al contenedor de la pestaña (`config.SEL_CONTENEDOR_VOLUMENES`): el id `table` se repite en varias pestañas del perfil.
  - El botón de adjuntos se busca **dentro de la fila** encontrada, nunca con `driver.find_element` global.
- Motivos de pendiente/error como constantes en MAYÚSCULAS (`PACIENTE_NO_ENCONTRADO`, `FILA_NO_ENCONTRADA`, `SIN_CEDULA`, …); aparecen tal cual en el reporte.
- Cada fallo de Selenium deja captura + HTML con `sunu.diagnostico(driver, tag)`.
- Un fallo de sesión/login no debe contar como intento de ningún informe (si no, una caída de Sunu manda todo a `errores/`).

## Comportamiento de Sunu (validado en campo)

- Selectores confirmados el 2026-09-30: pestaña `#tab-volumen-pulmonar` (tabla Fecha | Acciones | Adjuntos, fecha `DD/MM/AAAA`) y modal `#modalAdjuntosFormato` con las mismas clases que espirometría.
- La fila de volúmenes **no siempre existe** (1 de 8 pacientes en la primera tanda) y su fecha es la de **creación del registro**, que puede no coincidir con la del examen: el 2026-10-01 se crearon dos filas con fecha 01/10 para un examen del 29/09. El bot solo adjunta en la fila con la fecha del examen; si no la hay queda `FILA_NO_ENCONTRADA` y tras `MAX_INTENTOS` pasa a `errores/` para adjuntarlo a mano. No relajar ese criterio: adjuntaría el informe al examen equivocado.
- Sunu sube el PDF en partes ("Subiendo parte 1 de 3...", los informes pesan ~1,3 MB) y solo al terminar reemplaza el contenido del modal. `_esperar_confirmacion` espera ese reemplazo (el input queda stale); no volver a aceptar el texto de estado como confirmación, porque navegar antes corta la carga. Un fallo sale como alerta roja ("No fue posible cargar el PDF.") o como aviso de sesión.
- Con un adjunto, el modal lista el archivo (estado "Pendiente"), muestra `iframe.visorPdfAdjuntoFormato` y el formulario de lectura/firma, sin input de subida. `_ya_cargado` exige esa evidencia: `div.adjuntos-formato-proceso` envuelve todo el modal y está siempre.
- `lector_pdf.py` validado el 2026-09-28 con 33 informes reales: cédula y fecha desde el contenido en 33/33. El informe dibuja el valor de la fecha encima de la etiqueta, por eso `extraer_texto` usa `use_text_flow=True`; no quitarlo.

## Producción

- `C:\Users\user\bot_volumenes_pulmonares` en el equipo EC-300. Tarea "Bot Volumenes Pulmonares" diaria a las 22:00 vía `run_bot.bat`, una hora después de "Bot Espirometrias" (21:00), que maneja MIR Spiro con teclado y foco: los dos bots no deben coincidir. Por eso la tarea tiene desactivado "iniciar si se perdió" (`StartWhenAvailable`): tras un arranque se arrancarían las dos a la vez.
- `CARPETA_ENTRADA` = `Desktop\VOLUMENES ALEJA`. El bot solo lee la raíz; las subcarpetas por fecha de la terapeuta son histórico y no se tocan.
- Primera subida real el 2026-09-30: 7 informes subidos y verificados uno por uno en Sunu. El reporte diario va a tres direcciones de CEMDE.

## Pendientes

- Ver cómo muestra Sunu un adjunto rechazado ("Marcar como rechazado (examen para repetir)") antes de tocar `_ya_cargado`: si reaparece el input de subida, un PDF nuevo se subiría bien.
- Acordar con CEMDE quién crea los registros de volúmenes que faltan y con qué fecha.
- Política de retención de `procesados/` y `logs/` (crecen sin límite).
