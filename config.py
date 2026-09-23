import os
from dotenv import load_dotenv

load_dotenv()

# ── Sunu ──────────────────────────────────────────────────
URL_NUBE = os.getenv("URL_NUBE") or "https://cemde.sunu.be"
USUARIO = os.getenv("USUARIO", "")
PASSWORD = os.getenv("PASSWORD", "")

# Identificación de la instancia (aparece en el asunto y cuerpo del reporte)
SEDE_LOCAL = (os.getenv("SEDE_LOCAL") or "LAURELES").upper()
CONSULTORIO = os.getenv("CONSULTORIO") or "22"

# ── Rutas ─────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
DEBUG_DIR = os.path.join(BASE_DIR, "debug")

# Carpeta estándar donde la terapeuta deja los informes PDF de volúmenes.
# Dentro de ella el bot crea "procesados/" y "errores/".
CARPETA_ENTRADA = os.getenv("CARPETA_ENTRADA") or os.path.join(BASE_DIR, "bandeja")
CARPETA_PROCESADOS = os.path.join(CARPETA_ENTRADA, "procesados")
CARPETA_ERRORES = os.path.join(CARPETA_ENTRADA, "errores")

REGISTRO_FILE = os.path.join(DATA_DIR, "registro.json")

for _d in (DATA_DIR, LOG_DIR, DEBUG_DIR, CARPETA_ENTRADA, CARPETA_PROCESADOS, CARPETA_ERRORES):
    os.makedirs(_d, exist_ok=True)

# Retención de capturas/volcados de debug (contienen datos de pacientes).
DEBUG_RETENTION_DAYS = int(os.getenv("DEBUG_RETENTION_DAYS", "14"))

# Corridas en las que un PDF puede quedar pendiente (ej. la fila aún no existe
# en Sunu) antes de moverlo a errores/ para revisión manual.
MAX_INTENTOS = int(os.getenv("MAX_INTENTOS", "3"))

# ── Email ─────────────────────────────────────────────────
EMAIL_REMITENTE = os.getenv("EMAIL_REMITENTE", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_DESTINATARIOS = os.getenv("EMAIL_DESTINATARIOS", "")
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))

# ── Selectores de Sunu (perfil del paciente → Volúmenes Pulmonares) ──
# PENDIENTE: confirmar con `python explorar_sunu.py <cedula>`. Los valores por
# defecto siguen el patrón de la pestaña de espirometría (#tab-espirometria).
SEL_TAB_VOLUMENES = os.getenv("SEL_TAB_VOLUMENES") or "a.link-tab[href='#tab-volumenes-pulmonares']"
SEL_CONTENEDOR_VOLUMENES = os.getenv("SEL_CONTENEDOR_VOLUMENES") or "#tab-volumenes-pulmonares"
