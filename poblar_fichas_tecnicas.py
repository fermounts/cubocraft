"""
Pobla la hoja FICHAS_TECNICAS_BORRADOR consultando Gemini por cada producto
de la hoja PRODUCTOS.

Límites free tier gemini-2.5-flash: 5 RPM / 20 RPD.
El script reanuda automáticamente: salta productos ya procesados con éxito.

Uso:
    python3 poblar_fichas_tecnicas.py
"""

import json
import os
import re
import time

import gspread
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from google.genai.errors import ClientError, ServerError
from google.oauth2.service_account import Credentials

load_dotenv()

# ── Configuración ─────────────────────────────────────────────────────────────

SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MODELO = "gemini-2.5-flash"
PAUSA_RPM = 13        # segundos entre llamadas (5 RPM → 12s mínimo)
MAX_RETRY_RPM = 2     # reintentos ante error 429 por minuto

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS_FICHAS = [
    "ID_PRODUCTO", "NOMBRE", "APERTURA",
    "DESCRIPCION", "MODO_USO", "RENDIMIENTO",
    "PROPORCIONES", "TIEMPO_SECADO", "NORMATIVA",
    "PRECAUCIONES", "FUENTE", "ESTADO",
]

SHEET_FICHAS = "FICHAS_TECNICAS_BORRADOR"


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_gc() -> gspread.Client:
    raw = os.environ["GOOGLE_CREDS_JSON"].strip()
    if raw.endswith(".json") and os.path.isfile(raw):
        with open(raw) as f:
            data = json.load(f)
    else:
        data = json.loads(raw)
    creds = Credentials.from_service_account_info(data, scopes=SCOPES)
    return gspread.authorize(creds)


def _ensure_fichas_sheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(SHEET_FICHAS)
        print(f"  Hoja '{SHEET_FICHAS}' existente.")
        return ws
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=SHEET_FICHAS, rows=500, cols=len(HEADERS_FICHAS))
        ws.append_row(HEADERS_FICHAS)
        print(f"  Hoja '{SHEET_FICHAS}' creada.")
        return ws


def _ids_ya_procesados(ws_fichas: gspread.Worksheet) -> set[str]:
    """Devuelve IDs con ESTADO != 'Error' (ya tienen ficha válida)."""
    try:
        registros = ws_fichas.get_all_records()
        return {
            str(r.get("ID_PRODUCTO", ""))
            for r in registros
            if str(r.get("ESTADO", "")).strip() != "Error"
        }
    except Exception:
        return set()


# ── Prompt Gemini ─────────────────────────────────────────────────────────────

def _prompt(producto: dict) -> str:
    nombre = producto.get("Nombre", "")
    spec = producto.get("Especificación_Técnica", "")
    norma = producto.get("ID_Norma_Ref", "")
    partes = [f'Buscá la ficha técnica oficial del producto "{nombre}".']
    if spec:
        partes.append(f"Especificación conocida: {spec}.")
    if norma:
        partes.append(f"Norma de referencia: {norma}.")
    partes.append(
        "Devolvé SOLO un JSON con estos campos (sin texto adicional, sin markdown):\n"
        '{\n'
        '  "descripcion": "descripción técnica del producto",\n'
        '  "modo_uso": "cómo se aplica o usa",\n'
        '  "rendimiento": "rendimiento por m² o unidad",\n'
        '  "proporciones": "proporciones de mezcla si aplica, sino null",\n'
        '  "tiempo_secado": "tiempo de secado/fragüe si aplica, sino null",\n'
        '  "normativa": "normas IRAM/CIRSOC que cumple",\n'
        '  "precauciones": "precauciones de uso",\n'
        '  "fuente": "URL o nombre del documento fuente"\n'
        '}'
    )
    return "\n".join(partes)


def _extraer_json(texto: str | None) -> dict:
    if not texto:
        raise ValueError("Respuesta vacía de Gemini")
    texto = re.sub(r"```(?:json)?\s*", "", texto).replace("```", "").strip()
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if not match:
        raise ValueError(f"No se encontró JSON: {texto[:120]!r}")
    return json.loads(match.group())


def _extraer_retry_delay(error_msg: str) -> float:
    """Extrae retryDelay en segundos del mensaje de error 429."""
    m = re.search(r"retry[_ ]in\s+([\d.]+)s", error_msg, re.IGNORECASE)
    return float(m.group(1)) if m else 60.0


# ── Procesamiento con retry RPM ───────────────────────────────────────────────

class CuotaDiariaAgotada(Exception):
    pass


def _llamar_gemini(cliente: genai.Client, prompt: str) -> dict:
    for intento in range(MAX_RETRY_RPM + 1):
        try:
            resp = cliente.models.generate_content(
                model=MODELO,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    max_output_tokens=1024,
                    response_mime_type="application/json",
                    thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                ),
            )
            return _extraer_json(resp.text)

        except ClientError as e:
            msg = str(e)
            if "PerDay" in msg or "Per Day" in msg or "per_day" in msg.lower():
                raise CuotaDiariaAgotada("Cuota diaria de Gemini agotada (20 req/día free tier).")
            if "429" in msg:
                delay = _extraer_retry_delay(msg) + 2
                print(f"\n  [429 RPM] Esperando {delay:.0f}s antes de reintentar ({intento+1}/{MAX_RETRY_RPM})...")
                time.sleep(delay)
                continue
            raise

        except ServerError as e:
            if intento < MAX_RETRY_RPM:
                print(f"\n  [503] Esperando 15s...")
                time.sleep(15)
                continue
            raise

    raise RuntimeError("Máximo de reintentos alcanzado")


def procesar_producto(cliente: genai.Client, producto: dict) -> tuple[list, bool]:
    pid = producto.get("ID", "")
    nombre = producto.get("Nombre", "")
    apertura = producto.get("Apertura", "")

    try:
        datos = _llamar_gemini(cliente, _prompt(producto))
        fila = [
            pid, nombre, apertura,
            datos.get("descripcion", ""),
            datos.get("modo_uso", ""),
            datos.get("rendimiento", ""),
            datos.get("proporciones") or "",
            datos.get("tiempo_secado") or "",
            datos.get("normativa", ""),
            datos.get("precauciones", ""),
            datos.get("fuente", ""),
            "Borrador",
        ]
        return fila, True
    except CuotaDiariaAgotada:
        raise
    except Exception as e:
        fila = [pid, nombre, apertura, "", "", "", "", "", "", "", str(e)[:200], "Error"]
        return fila, False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== Poblar FICHAS_TECNICAS_BORRADOR ===\n")

    gc = _get_gc()
    spreadsheet = gc.open_by_key(SHEET_ID)

    print("Leyendo PRODUCTOS...")
    ws_prod = spreadsheet.worksheet("PRODUCTOS")
    todos = [
        p for p in ws_prod.get_all_records()
        if str(p.get("Activo", "")).upper() in ("SI", "1", "TRUE", "VERDADERO")
    ]
    print(f"  {len(todos)} productos activos.\n")

    ws_fichas = _ensure_fichas_sheet(spreadsheet)
    ya_ok = _ids_ya_procesados(ws_fichas)
    if ya_ok:
        print(f"  {len(ya_ok)} productos ya tienen ficha — se omiten.\n")

    pendientes = [p for p in todos if str(p.get("ID", "")) not in ya_ok]
    print(f"  {len(pendientes)} productos a procesar.\n")

    link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    cliente = genai.Client(api_key=GEMINI_API_KEY)

    ok = 0
    errores = 0
    filas_pendientes: list[list] = []
    cuota_agotada = False

    for i, producto in enumerate(pendientes, 1):
        nombre = producto.get("Nombre", "?")
        print(f"[{i:02d}/{len(pendientes)}] {nombre}...", end=" ", flush=True)

        try:
            fila, exito = procesar_producto(cliente, producto)
        except CuotaDiariaAgotada as e:
            print(f"\n\n  STOP: {e}")
            print(f"  Procesados en esta sesión: {ok} OK / {errores} errores.")
            print(f"  Quedan {len(pendientes) - i + 1} productos. Volvé a ejecutar mañana.")
            cuota_agotada = True
            break

        if exito:
            print("OK")
            ok += 1
        else:
            print(f"ERROR — {fila[-2][:80]}")
            errores += 1

        filas_pendientes.append(fila)

        if len(filas_pendientes) >= 10:
            ws_fichas.append_rows(filas_pendientes, value_input_option="RAW")
            filas_pendientes = []

        if i < len(pendientes):
            time.sleep(PAUSA_RPM)

    if filas_pendientes:
        ws_fichas.append_rows(filas_pendientes, value_input_option="RAW")

    print(f"\n{'='*42}")
    print(f"  Procesados exitosamente : {ok}")
    print(f"  Con error               : {errores}")
    if cuota_agotada:
        restantes = len(pendientes) - ok - errores
        print(f"  Sin procesar (cuota)    : {restantes}")
    print(f"  Total acumulado en hoja : {len(ya_ok) + ok}")
    print(f"\n  Hoja: {link}")
    print(f"  Pestaña: {SHEET_FICHAS}")
    print(f"{'='*42}")


if __name__ == "__main__":
    main()
