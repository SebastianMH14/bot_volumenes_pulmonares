# Bot Volúmenes Pulmonares — RPA CEMDE

Automatiza la carga de los informes de **volúmenes pulmonares por pletismografía (pre y post broncodilatador)** en la historia clínica de **Sunu** (`cemde.sunu.be`).

Hoy la terapeuta envía cada informe por correo y alguien lo adjunta a mano en Sunu. Con el bot, la terapeuta solo guarda el PDF en una **carpeta estándar** del equipo del consultorio y el bot hace el resto.

Es la Fase 2 de la ampliación cotizada en CEMDE-2026-01. La Fase 1 (espirometrías del consultorio 22) se hace en el repositorio [`bot_espirometrias`](https://github.com/SebastianMH14/bot_espirometrias), del que este proyecto reutiliza el login, la búsqueda de pacientes y el modal de adjuntos de Sunu.

---

## Cómo funciona

```
Terapeuta ──guarda PDF──▶ CARPETA_ENTRADA/
                               │
                     1. Lectura (pdfplumber)
                        cédula + fecha del examen
                               │
                     2. Carga (Selenium)
                        Sunu → perfil del paciente → Volúmenes Pulmonares
                        → fila de esa fecha → Adjuntos → sube PDF
                               │
             ┌─────────────────┼──────────────────┐
             ▼                 ▼                  ▼
      procesados/AAAA-MM-DD  (se queda en la     errores/AAAA-MM-DD
      subido o ya cargado    carpeta: pendiente,  ilegible, sin cédula,
                             se reintenta)        o agotó MAX_INTENTOS
                               │
                     3. Reporte diario (correo + data/reporte_*.txt)
```

1. **Lectura**: el nombre del archivo que genera el equipo **no trae la cédula** (ej. `Nombre apellido_LVM_22092026_110217.pdf`), así que se lee del contenido del PDF (`ID: ...`). La fecha del examen sale de la etiqueta de la sesión. Si no aparece, se toma del nombre del archivo. La fecha de nacimiento se descarta.
2. **Carga**: busca al paciente por cédula, abre la pestaña *Volúmenes Pulmonares*, ubica la fila con la fecha del examen y adjunta el PDF **en el botón de esa fila**. Si Sunu muestra que ya había un adjunto, lo registra como *ya cargado* y no lo sube otra vez.
3. **Reporte**: correo con asunto `Reporte diario Bot Volúmenes Pulmonares - LAURELES - Consultorio 22 - AAAA-MM-DD`, con subidos, pendientes y errores.

**Qué hace el bot si algo falla:**
- **El mismo archivo aparece dos veces:** el bot guarda la huella digital (SHA-256) de cada PDF en `data/registro.json`. Si un PDF ya subido vuelve a aparecer en la carpeta, se archiva sin volver a subirlo.
- **La fila del examen todavía no existe en Sunu:** el informe queda pendiente y se reintenta en las siguientes corridas. Tras `MAX_INTENTOS` intentos pasa a `errores/` para revisión manual.
- **No se puede iniciar sesión en Sunu:** no se cuenta como intento de ningún informe, así que ninguno termina en `errores/` por una caída de Sunu.
- **Falla estructural:** si 5 informes seguidos fallan por la misma causa, el bot se detiene y manda el correo con `[ALERTA]` (circuit breaker, igual que en `bot_espirometrias`).

> El bot **solo adjunta** el PDF. La lectura y firma médica en Sunu siguen a cargo del profesional.

## Requisitos

- Windows con Chrome instalado (Selenium Manager descarga el driver)
- Python 3.10+
- Usuario de Sunu con permiso para consultar pacientes y cargar adjuntos
- Informes PDF con texto seleccionable (no escaneados)

## Instalación

```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # completar credenciales y CARPETA_ENTRADA
```

## Configuración (`.env`)

| Variable | Descripción |
|---|---|
| `URL_NUBE` | URL base de Sunu (`https://cemde.sunu.be`) |
| `USUARIO` / `PASSWORD` | Credenciales de Sunu |
| `SEDE_LOCAL` / `CONSULTORIO` | Identifican la instancia en el reporte (`LAURELES` / `22`) |
| `CARPETA_ENTRADA` | Carpeta estándar donde la terapeuta deja los PDF (ej. `C:\Volumenes`) |
| `MAX_INTENTOS` | Corridas que un informe puede quedar pendiente antes de pasar a `errores/` (defecto 3) |
| `DEBUG_RETENTION_DAYS` | Días que se guardan capturas de `debug/`, que tienen datos de pacientes (defecto 14) |
| `EMAIL_*` | Remitente, contraseña de aplicación, destinatarios y SMTP del reporte |
| `SEL_TAB_VOLUMENES` / `SEL_CONTENEDOR_VOLUMENES` | Selectores de la pestaña de volúmenes en el perfil del paciente |

## Uso

```bash
# Corrida normal: lee, carga a Sunu y envía el reporte
python main.py

# Solo lectura: muestra cédula y fecha de cada PDF, sin entrar a Sunu ni mover archivos
python main.py --solo-leer

# Sin correo (pruebas)
python main.py --sin-correo

# Diagnóstico: confirma los selectores de la pestaña de volúmenes (no modifica nada)
python explorar_sunu.py <cedula_de_un_paciente_con_volumenes>
```

Para producción, programar `run_bot.bat` en el **Programador de tareas de Windows** del equipo del consultorio, después del horario de atención (usa el `venv`, fuerza UTF-8 y agrega la salida a `logs\tarea_programada.log`; acepta los mismos argumentos que `main.py`). La sesión de Windows debe quedar desbloqueada, porque Chrome corre visible.

## Estructura

```
├── main.py               # Orquesta lectura → carga → reporte
├── config.py             # Configuración desde .env
├── explorar_sunu.py      # Diagnóstico de selectores de la pestaña de volúmenes
├── modules/
│   ├── lector_pdf.py     # Extrae cédula y fecha del informe
│   ├── bandeja.py        # Carpeta de entrada, procesados/errores y registro por hash
│   ├── sunu.py           # Selenium: login, perfil, pestaña de volúmenes, adjuntos
│   ├── reporte.py        # Reporte local y por correo
│   ├── circuit_breaker.py
│   └── logger.py
└── tests/                # python -m unittest discover tests
```

Diseño, decisiones y manejo de errores: [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

Salidas (no se versionan, tienen datos de pacientes): `data/registro.json`, `data/reporte_*.txt`, `logs/`, `debug/`.

## Pendientes por confirmar (semana 1)

Salen del kickoff con CEMDE del 23/09/2026:

- [ ] **Acceso remoto** al equipo del consultorio 22 (Diana).
- [x] **Carpeta estándar**: `Desktop\VOLUMENES ALEJA`. La terapeuta debe guardar los PDF nuevos en la raíz, no en subcarpetas.
- [ ] **Selectores de Sunu**: correr `explorar_sunu.py` con un paciente real y ajustar `SEL_TAB_VOLUMENES` / `SEL_CONTENEDOR_VOLUMENES`.
- [ ] **¿La fila de volúmenes se crea sola** al atender al paciente, o hay que usar *Crear Volúmenes Pulmonares*? El bot asume que ya existe.
- [ ] **Modal de adjuntos**: confirmar que usa las mismas clases que espirometría (`btnVerAdjuntosFormato`, `inputAdjuntoFormatoPdf`, `btnSubirAdjuntoFormato`).
- [x] **Informes reales**: `lector_pdf.py` validado con 33 PDF reales (2026-09-28); su formato quedó como caso de prueba (`INFORME_REAL`, datos ficticios).

## Tests

```bash
python -m unittest discover tests
```

Cubren el parseo de fechas y cédula (incluida la mezcla de columnas que produce pdfplumber) y el manejo de la carpeta y el registro. La automatización de Sunu se valida con `explorar_sunu.py` y corridas con `--sin-correo`.
