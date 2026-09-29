# CLAUDE.md

Bot RPA (Python + Selenium) que adjunta los informes PDF de **volúmenes pulmonares** en la historia clínica de **Sunu** (`cemde.sunu.be`) para CEMDE, sede Laureles, consultorio 22. Arquitectura y decisiones: [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

## Comandos

```bash
python -m unittest discover tests      # tests (no requieren Sunu ni pdfplumber)
python main.py --solo-leer             # lee PDFs de la bandeja; no entra a Sunu ni mueve archivos
python main.py --sin-correo            # corrida real sin enviar el reporte
python explorar_sunu.py <cedula>       # vuelca pestañas/HTML del perfil a debug/; no modifica Sunu
python -m py_compile main.py config.py explorar_sunu.py modules/*.py
```

Windows, Python 3.10+. `pdfplumber` se importa de forma diferida en `lector_pdf.extraer_texto`; los tests de parseo trabajan sobre texto y no lo necesitan.

## Reglas del proyecto

- **Datos de pacientes nunca van a git.** `bandeja/`, `data/`, `logs/`, `debug/`, `*.pdf` y `.env` están en `.gitignore`. Los tests usan datos ficticios; al agregar casos a partir de informes reales, anonimizar cédula y nombre.
- **No tocar `bot_espirometrias`** (repo hermano en `../bot_espirometrias`). Se puede leer como referencia, pero no se edita, no se hace commit ni push allí.
- **No hacer push** sin que el usuario lo pida. Mensajes de commit en español, en imperativo/presente como los existentes.
- **El bot solo adjunta el PDF.** Nunca automatizar la lectura/firma médica ("Leer y firmar") ni crear registros clínicos en Sunu; está fuera del alcance contratado.
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

## Estado actual (pendientes de validar en campo)

- `SEL_TAB_VOLUMENES` / `SEL_CONTENEDOR_VOLUMENES` son suposiciones (`#tab-volumenes-pulmonares`); confirmar con `explorar_sunu.py`.
- Se asume que la fila de volúmenes ya existe en Sunu cuando se atiende al paciente, y que el modal de adjuntos usa las mismas clases que espirometría.
- Los patrones de `lector_pdf.py` se hicieron con el informe visto en el kickoff; validar con PDFs reales y convertirlos en tests.
