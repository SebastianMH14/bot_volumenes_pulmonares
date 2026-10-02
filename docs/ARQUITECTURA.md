# Arquitectura — Bot Volúmenes Pulmonares

| | |
|---|---|
| **Proyecto** | Ampliación del Bot RPA de Espirometrías, CEMDE (Fase 2, cotización CEMDE-2026-01) |
| **Alcance** | Carga automática de informes de volúmenes pulmonares por pletismografía, sede Laureles, consultorio 22 |
| **Estado** | En producción desde el 2026-09-30 en el equipo del consultorio 22. Lector, selectores y carga validados en campo; pendientes en §11 |
| **Autor** | Sebastián Molina Henao |

---

## 1. Contexto

Hoy la terapeuta envía por correo cada informe PDF de volúmenes pulmonares y alguien lo adjunta a mano en la historia clínica de Sunu. En el kickoff (23/09/2026) se acordó cambiar el correo por una **carpeta estándar** en el equipo del consultorio: la terapeuta guarda ahí el PDF y el bot lo sube.

```mermaid
flowchart LR
    T([Terapeuta]) -->|guarda PDF| C[(Carpeta estándar<br/>equipo consultorio 22)]
    E[Equipo de pletismografía] -->|genera informe PDF| T
    C --> B[[Bot Volúmenes Pulmonares]]
    B -->|Selenium: busca paciente<br/>y adjunta PDF| S[(Sunu<br/>cemde.sunu.be)]
    B -->|SMTP| M([Reporte diario<br/>Carlos / CEMDE])
    S --> P([Profesional: lee y firma])
```

**Fuera de alcance:** la lectura y firma médica en Sunu (el bot solo adjunta), crear registros de volúmenes en Sunu, y otras sedes o tipos de examen.

## 2. Componentes

```mermaid
flowchart TB
    main[main.py<br/>orquestador + CLI]
    cfg[config.py<br/>.env]
    lec[lector_pdf.py<br/>cédula + fecha]
    ban[bandeja.py<br/>carpetas + Registro]
    sun[sunu.py<br/>Selenium]
    rep[reporte.py<br/>txt + correo]
    cb[circuit_breaker.py]
    log[logger.py]
    exp[explorar_sunu.py<br/>diagnóstico]

    main --> lec & ban & sun & rep & cb & log
    lec -.-> pdfplumber[(pdfplumber)]
    sun --> cfg
    rep --> cfg
    main --> cfg
    exp --> sun
```

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `main.py` | Orquesta las fases (lectura → carga → reporte), CLI (`--solo-leer`, `--sin-correo`), límite de tiempo, reinicio del navegador, limpieza de `debug/` | todos |
| `config.py` | Única fuente de configuración (`.env`). Crea las carpetas de trabajo al importarse | `python-dotenv` |
| `modules/lector_pdf.py` | Extrae la **cédula** y la **fecha del examen** del PDF. Funciones puras sobre texto más `extraer_texto` (pdfplumber, import diferido) | `pdfplumber` |
| `modules/bandeja.py` | Lista los PDF de la carpeta de entrada, los mueve a `procesados/` y `errores/` sin sobrescribir, y mantiene el `Registro` persistente por hash | stdlib |
| `modules/sunu.py` | Login, búsqueda global de pacientes, pestaña de volúmenes, fila por fecha, modal de adjuntos y capturas de diagnóstico | `selenium`, `config` |
| `modules/reporte.py` | Arma el cuerpo del reporte, lo guarda en `data/` y lo envía por SMTP con reintentos (si falla, deja copia local) | `config` |
| `modules/circuit_breaker.py` | Corta el lote ante N fallos consecutivos con la misma causa | — |
| `explorar_sunu.py` | Herramienta de solo lectura: vuelca pestañas y HTML del perfil para confirmar selectores | `sunu` |
| `run_bot.bat` | Lanzador de la tarea programada: usa el `venv`, fuerza UTF-8 y agrega la salida a `logs\tarea_programada.log` | `venv` |

`sunu.py`, `circuit_breaker.py`, `logger.py` y la lógica de correo vienen de `bot_espirometrias`, que ya está probado en producción (ver §9).

## 3. Flujo de ejecución

```mermaid
sequenceDiagram
    autonumber
    participant TS as Programador de tareas
    participant M as main.py
    participant B as bandeja / Registro
    participant L as lector_pdf
    participant S as Sunu (Selenium)
    participant R as reporte

    TS->>M: run_bot.bat → main.py
    M->>B: listar_pdfs(CARPETA_ENTRADA)
    loop cada PDF
        M->>B: hash_archivo → ¿ya_finalizado?
        alt ya subido antes (mismo hash)
            M->>B: mover a procesados/
        else nuevo o pendiente
            M->>L: leer_informe(pdf)
            alt ilegible / sin cédula / sin fecha
                M->>B: registrar "error" + mover a errores/
            else válido
                L-->>M: cédula, fecha
            end
        end
    end
    M->>S: init_browser + login
    loop cada informe válido
        M->>S: abrir_paciente(cédula)
        M->>S: abrir_pestania_volumenes
        M->>S: buscar_fila_por_fecha(fecha)
        M->>S: subir_pdf(fila, pdf)
        Note over M,S: espera a que Sunu termine la carga por partes (§6)
        alt ok / ya_cargado
            M->>B: registrar + mover a procesados/
        else falla
            M->>B: registrar "pendiente" (intentos+1)
            Note over M,B: si intentos ≥ MAX_INTENTOS → errores/
        end
        M->>M: circuit breaker
    end
    M->>R: construir_cuerpo → guardar_local → enviar_email
```

## 4. Ciclo de vida de un informe

```mermaid
stateDiagram-v2
    [*] --> EnBandeja: la terapeuta guarda el PDF
    EnBandeja --> Errores: PDF_ILEGIBLE / SIN_CEDULA / SIN_FECHA
    EnBandeja --> Leido: cédula + fecha OK
    EnBandeja --> Procesados: mismo hash ya subido
    Leido --> Procesados: subido / ya_cargado en Sunu
    Leido --> Pendiente: falla en Sunu
    Pendiente --> Leido: siguiente corrida
    Pendiente --> Errores: intentos ≥ MAX_INTENTOS
    Procesados --> [*]
    Errores --> [*]: revisión manual
```

Un informe **pendiente** se queda en la raíz de la carpeta de entrada, así que se reintenta solo en la siguiente corrida sin intervención de nadie.

## 5. Datos y persistencia

```
CARPETA_ENTRADA/                 (Desktop\VOLUMENES ALEJA, en el equipo del consultorio)
├── *.pdf                        pendientes de procesar
├── procesados/AAAA-MM-DD/       subidos o ya cargados (fecha de la corrida, no del examen)
├── errores/AAAA-MM-DD/          para revisión manual
└── <subcarpetas de la terapeuta> histórico anterior al bot; no se leen

<proyecto>/
├── data/registro.json           estado por hash (ver abajo)
├── data/reporte_*.txt           copia local de cada reporte
├── data/EMAIL_NO_ENVIADO_*.txt  reportes cuyo correo falló
├── logs/bot_*.txt               log detallado por corrida
└── debug/*.png|*.html           capturas de fallos (se purgan a los DEBUG_RETENTION_DAYS)
```

**`data/registro.json`**: un diccionario indexado por el SHA-256 del PDF.

```json
{
  "9f2c…": {
    "intentos": 1,
    "archivo": "Nombre apellido_LVM_22092026_110217.pdf",
    "estado": "pendiente",
    "cedula": "12345678",
    "fecha": "2026-09-22",
    "motivo": "FILA_NO_ENCONTRADA",
    "actualizado": "2026-09-23T19:00:05"
  }
}
```

- **Estados:** `subido` y `ya_cargado` son finales. `pendiente` suma un intento. `error` queda para revisión.
- **Escritura:** atómica (archivo `.tmp` y luego `replace`). Si el registro se corrompe, se respalda como `registro.corrupto_*.json` y se empieza de cero. En el peor caso se reintenta un informe y Sunu lo reporta como `ya_cargado`.

## 6. Manejo de errores y resiliencia

| Situación | Dónde | Efecto | ¿Cuenta intento? |
|---|---|---|---|
| `PDF_ILEGIBLE`, `SIN_CEDULA`, `SIN_FECHA` | lectura | Pasa directo a `errores/` | — |
| `PACIENTE_NO_ENCONTRADO` | Sunu | Pendiente | Sí |
| `FILA_NO_ENCONTRADA` (no hay fila con la fecha del examen: no existe o se creó con otra fecha) | Sunu | Pendiente | Sí |
| `MODAL_NO_ABRIO`, `BOTON_*` | Sunu | Pendiente + captura en `debug/` | Sí |
| `SIN_CONFIRMACION` (Sunu mostró la alerta roja de fallo, pidió renovar la sesión o no terminó en 180 s) | Sunu | Pendiente + captura en `debug/` | Sí |
| `TIMEOUT`, `ERROR_INESPERADO` | Sunu | Pendiente + captura | Sí |
| Falla el login o el navegador no arranca | Sunu | Se aborta la carga y el correo sale con **[ALERTA]** | **No** |
| El navegador deja de responder a mitad del lote | Sunu | Hasta 2 reinicios; después se aborta con alerta | No (los restantes no se tocan) |
| 5 fallos consecutivos con la misma causa | circuit breaker | Se aborta el lote con **[ALERTA]** | Solo los ya procesados |
| Se pasa de 1 hora de ejecución | `main.py` | Se detiene; el resto queda para la próxima corrida | No |
| Falla el SMTP | reporte | 3 reintentos; si no sale, copia en `data/EMAIL_NO_ENVIADO_*` | — |

Lo que guía estas reglas: **un problema del sistema (Sunu caído, UI cambiada, red) nunca debe mandar informes buenos a `errores/`**. Por eso el login no cuenta como intento y el circuit breaker corta antes de agotar el lote.

**Confirmación de la carga.** Sunu sube el PDF en partes de 512 KiB (un informe de volúmenes pesa ~1,3 MB, o sea 3 partes) y muestra "Subiendo parte N de M...". Solo al recibir la última reemplaza el contenido del modal por la vista del adjunto: el archivo listado con estado "Pendiente", el visor (`iframe.visorPdfAdjuntoFormato`) y el formulario de lectura/firma del profesional. El bot da la carga por buena únicamente cuando ese reemplazo ocurre (el input de subida queda *stale*). Aceptar el texto de estado como éxito hacía que el bot cerrara el modal y navegara al siguiente paciente con la carga a medias, y marcara el informe como subido.

**"Ya cargado".** Si al abrir el modal no aparece el input de subida, el informe cuenta como ya cargado solo si el modal lista un archivo o muestra el visor. El contenedor `div.adjuntos-formato-proceso` no sirve como evidencia: está siempre, también sin archivos.

## 7. Decisiones de diseño

| # | Decisión | Motivo | Alternativa descartada |
|---|---|---|---|
| D1 | **Carpeta estándar** como entrada | Acordado en el kickoff. La terapeuta no usa ningún software nuevo y el bot no depende de leer un buzón de correo | Leer el correo de la terapeuta (credenciales de correo y formato de mensajes variable) |
| D2 | **Cédula tomada del contenido del PDF** | El nombre del archivo que genera el equipo trae nombre y fecha, pero no la cédula. Buscar en Sunu por nombre no es confiable | Pedir a la terapeuta que renombre cada archivo (error humano) |
| D3 | **Dos capas contra duplicados**: hash del archivo en el registro local y detección de "ya cargado" en el modal de Sunu | El hash evita trabajo si se copia el mismo archivo otra vez. Sunu cubre el caso de reexportar el mismo examen (bytes distintos) o de una carga manual previa | Solo una de las dos |
| D4 | **Repositorio separado** de `bot_espirometrias`, copiando el código de Sunu | Flujo distinto (sin MirSpiro ni Excel) y despliegue independiente. Cambiar este bot no pone en riesgo el que ya está en producción | Librería compartida. Se puede revisar si aparece un tercer bot |
| D5 | **Botón de adjuntos buscado dentro de la fila** encontrada | Con varios exámenes o pestañas hay varios botones en el DOM. Buscar en todo el documento puede adjuntar el PDF al examen equivocado | `driver.find_element` global (como en `bot_espirometrias`) |
| D6 | **Selectores de la pestaña de volúmenes configurables en `.env`** | Sunu ya rediseñó `/pacientes` el 2026-08-31. Ajustar un selector no debe exigir un despliegue de código | Selectores fijos en el código |
| D7 | **El fallo de sesión no cuenta intento** | Evita que una caída de Sunu mande todos los informes a `errores/` después de `MAX_INTENTOS` corridas | Contar intento en cualquier falla |
| D8 | **`pdfplumber` con import diferido** | Los tests de parseo corren sin la dependencia, y un problema al instalarla no rompe la lectura de configuración | Import a nivel de módulo |
| D9 | **Texto con `use_text_flow`** | El informe dibuja la fecha encima de la etiqueta "Fecha de la sesión:"; ordenando por posición, pdfplumber intercala los caracteres y la fecha nunca se leía del contenido | Depender de la fecha del nombre del archivo (falla si se renombra) |
| D10 | **Confirmación = Sunu reemplaza el modal** (§6) | Es lo único que Sunu hace al terminar todas las partes | Texto de estado o spinner (se ven antes de terminar) |
| D11 | **La fila se busca solo por la fecha exacta del examen** | La fecha de la fila es la de creación del registro. Si se creó otro día no hay forma segura de saber cuál es, y menos con varias filas; se deja para adjuntar a mano | Tomar la única fila o la más cercana (puede ser otro examen) |
| D12 | **La tarea no se recupera si se perdió** (`StartWhenAvailable` desactivado) | Tras un arranque se ejecutarían a la vez las dos tareas atrasadas y chocarían en el equipo. Un día perdido solo retrasa los informes al siguiente | Recuperar la corrida al encender |

## 8. Despliegue y operación

- **Dónde corre:** el equipo del consultorio 22 (EC-300, Windows), el mismo donde la terapeuta guarda los PDF. Instalado en `C:\Users\user\bot_volumenes_pulmonares`.
- **Cómo se programa:** tarea "Bot Volumenes Pulmonares" del Programador de tareas, diaria a las 22:00, que ejecuta `run_bot.bat`. Corre con la sesión de Windows iniciada y **desbloqueada** (Chrome corre visible) y no recupera corridas perdidas (D12).
- **Convivencia con `bot_espirometrias`:** está instalado en el mismo equipo, con su tarea a las 21:00 (tarda de 3 a 30 minutos). Maneja MIR Spiro con foco de ventana y teclado, así que **los dos bots no deben correr al mismo tiempo**; por eso volúmenes va una hora después.
- **Instalación:** `venv`, `pip install -r requirements.txt`, `.env` a partir de `.env.example`, con `CARPETA_ENTRADA` apuntando a la carpeta acordada.
- **Puesta en marcha (hecha):**
  1. 2026-09-28: `--solo-leer` con 33 informes reales; se corrigió el lector (D9).
  2. 2026-09-30: `explorar_sunu.py`; se corrigió el selector de la pestaña (`#tab-volumen-pulmonar`).
  3. 2026-09-30: primera corrida real con `--sin-correo`: 7 informes subidos y verificados uno por uno en Sunu, 1 pendiente por no tener registro. Se corrigió la confirmación de carga (D10).
  4. Tarea programada activa desde el 2026-09-28; primer correo automático el 2026-09-30.
- **Monitoreo:** el correo diario a tres direcciones de CEMDE. Si llega un asunto con `[ALERTA]` o hay informes en `errores/`, requiere revisión el mismo día. Un correo sin informes varios días seguidos puede indicar que la terapeuta guarda los PDF en otro lugar.

## 9. Relación con `bot_espirometrias`

| Pieza | Origen | Cambios |
|---|---|---|
| Login y `init_browser` | `modules/nube.py` | Sin preferencias de descarga (acá no se descargan Excel) |
| `abrir_paciente` (búsqueda global) | `modules/subir_sunu.py` | Ninguno |
| Modal de adjuntos (`_ya_cargado`, confirmación, cierre) | `modules/subir_sunu.py` | El botón se busca dentro de la fila (D5); la confirmación espera a que Sunu reemplace el modal (D10) y `_ya_cargado` exige un archivo listado o el visor |
| `CircuitBreaker`, logger | `modules/` | Nombre del logger `bot_volumenes` |
| Reporte por correo | `main.py` | Asunto etiquetado por consultorio y secciones de volúmenes |

Si Sunu cambia la búsqueda global o el modal de adjuntos, el ajuste probablemente haya que hacerlo **en ambos repositorios**.

**Riesgo conocido en `bot_espirometrias`** (no se corrige desde este repo): su `_esperar_confirmacion_subida` sigue aceptando el texto de estado o el spinner oculto como éxito, y el mensaje de fallo de Sunu ("No fue posible cargar el PDF.") no contiene "error", así que también pasa. Sus PDF (~125 KB) caben en una sola parte, lo que reduce el riesgo pero no lo elimina. Conviene portar allá la confirmación de D10.

## 10. Seguridad y privacidad

- **Tipo de datos:** son datos de salud, es decir, **datos sensibles** según la Ley 1581 de 2012. Los tratan el PDF, el nombre del archivo (trae el nombre del paciente), `data/registro.json`, los logs y las capturas de `debug/`.
- **Qué nunca se versiona:** `bandeja/`, `data/`, `logs/`, `debug/`, `*.pdf` y `.env` están en `.gitignore`. Los tests usan datos ficticios.
- **Qué no se muestra:** al revisar logs, reportes o capturas se resume con conteos o se enmascara. El título del modal de adjuntos de Sunu trae la cédula y el nombre del paciente.
- **Retención:** las capturas de `debug/` se purgan automáticamente (`DEBUG_RETENTION_DAYS`, 14 días por defecto). `procesados/` y `logs/` crecen sin límite. Hay que acordar con CEMDE cuánto tiempo guardarlos (ver §11).
- **Credenciales:** van solo en `.env`, en el equipo del consultorio. El correo usa contraseña de aplicación, no la contraseña real de la cuenta.

## 11. Riesgos y pendientes

| Riesgo o pendiente | Mitigación / acción |
|---|---|
| ~~Selectores de la pestaña de volúmenes supuestos~~ | **Resuelto 2026-09-30:** confirmados con `explorar_sunu.py` (`#tab-volumen-pulmonar`) |
| ~~Patrones del lector sacados de un solo informe~~ | **Resuelto 2026-09-28:** validado con 33 PDF reales; el formato quedó como test anonimizado |
| ~~La carga podía cortarse y marcarse como subida~~ | **Resuelto 2026-09-30:** confirmación por reemplazo del modal (D10), validada con 7 informes |
| La fila de volúmenes **no siempre existe** (1 de 8 en la primera tanda) o se crea **con otra fecha** (el 2026-10-01 se crearon dos filas del 01/10 para un examen del 29/09) | El informe queda pendiente y luego va a `errores/` para adjuntarlo a mano (D11). Acordar con CEMDE quién crea el registro y con qué fecha. Crearlo desde el bot es un cambio de alcance |
| Un adjunto **rechazado** ("Marcar como rechazado (examen para repetir)") | Ver cómo queda el modal: si reaparece el input de subida, un PDF nuevo se sube normal; si no, `_ya_cargado` lo daría por cargado. Revisar con el primer caso real |
| PDF escaneado sin capa de texto | Termina en `errores/` como `PDF_ILEGIBLE`. Si pasa seguido, evaluar OCR |
| La terapeuta guarda el PDF en otra carpeta | La guía de uso y el reporte diario lo hacen visible (menos informes de los esperados). El 30/09 y el 01/10 no llegó ningún PDF nuevo; confirmar con la terapeuta |
| Retención de `procesados/` y `logs/` sin política | Acordar un plazo con CEMDE y agregar la purga |
