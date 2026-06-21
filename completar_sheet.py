#!/usr/bin/env python3
"""
completar_sheet.py — CUBOCRAFT
"""

import argparse
import json
import os
import time
import sys
from datetime import datetime, date
from pathlib import Path

SPREADSHEET_ID   = "1X819OQZwYdu7ldCBYWVxnxBSd7nJAlcGpvjNQw1iSBA"
SERVICE_ACCOUNT_FILE = "credentials.json"
GEMINI_API_KEY   = "AIzaSyAqzd6NyXE7EdgPw7wOLmKFEZhKY9Focy4"
CHECKPOINT_FILE = Path("completar_sheet_progress.json")
DELAY_ENTRE_REQUESTS = 65

def conectar_sheets():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID)

def cargar_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"procesados": [], "errores": []}

def guardar_checkpoint(cp):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    print(f"[{ts()}] {msg}", flush=True)

def cargar_datos_prueba(sheet):
    log("━━━ PARTE 1: Cargando datos de prueba ━━━")
    hoy = date.today().isoformat()
    try:
        ws = sheet.worksheet("CAMPAÑAS")
        if len(ws.get_all_values()) <= 1:
            rows = [
                ["C001", "Lanzamiento Invierno 2026", "2026-06-01", "2026-06-30", "10", "5000", "SI"],
                ["C002", "Combo EPP Obra", "2026-06-01", "2026-07-31", "15", "15000", "SI"],
            ]
            ws.append_rows(rows)
            log("  ✅ CAMPAÑAS — 2 filas agregadas")
        else:
            log("  ℹ️  CAMPAÑAS ya tiene datos, se omite")
    except Exception as e:
        log(f"  ⚠️  CAMPAÑAS error: {e}")
    try:
        ws = sheet.worksheet("PAGOS")
        if len(ws.get_all_values()) <= 1:
            rows = [
                ["PAG001", "2026-05-10", "V001", "Fernando", "22500", "Transferencia", "COMP-001", "Confirmado", "NO"],
                ["PAG002", "2026-05-15", "V001", "Fernando", "6800", "Efectivo", "", "Confirmado", "NO"],
                ["PAG003", "2026-05-20", "V001", "Fernando", "4800", "Transferencia", "COMP-003", "Confirmado", "NO"],
                ["PAG004", "2026-06-01", "V001", "Fernando", "18000", "Transferencia", "COMP-004", "Confirmado", "NO"],
                ["PAG005", "2026-06-02", "V001", "Fernando", "6300", "Efectivo", "", "Pendiente", "NO"],
            ]
            ws.append_rows(rows)
            log("  ✅ PAGOS — 5 filas agregadas")
        else:
            log("  ℹ️  PAGOS ya tiene datos, se omite")
    except Exception as e:
        log(f"  ⚠️  PAGOS error: {e}")
    try:
        ws = sheet.worksheet("RANKING")
        if len(ws.get_all_values()) <= 1:
            rows = [["V001", "Fernando", "1", "Oro", "52100", "108400"]]
            ws.append_rows(rows)
            log("  ✅ RANKING — 1 fila agregada")
        else:
            log("  ℹ️  RANKING ya tiene datos, se omite")
    except Exception as e:
        log(f"  ⚠️  RANKING error: {e}")
    try:
        ws = sheet.worksheet("CANDIDATOS")
        if len(ws.get_all_values()) <= 1:
            rows = [
                ["Carlos Méndez", "5491155667788", "GBA Norte", hoy, "Interesado", "EPP construcción, quiere presupuesto"],
                ["María González", "5491166778899", "CABA", "2026-06-01", "Contactado", "Preguntó por membranas"],
                ["Obra Martínez SA", "5491177889900", "GBA Sur", "2026-05-28", "Pendiente", "Empresa constructora, volumen alto"],
            ]
            ws.append_rows(rows)
            log("  ✅ CANDIDATOS — 3 filas agregadas")
        else:
            log("  ℹ️  CANDIDATOS ya tiene datos, se omite")
    except Exception as e:
        log(f"  ⚠️  CANDIDATOS error: {e}")
    log("━━━ PARTE 1 completa ━━━\n")

PROMPT_FICHA = """Eres un redactor técnico de fichas de productos para construcción y EPP.

REGLA ABSOLUTA: NUNCA inventes números de normas, valores numéricos, voltajes, temperaturas,
resistencias químicas, certificaciones ni cualquier dato que no esté textualmente en la
Especificación_Técnica proporcionada. Si un dato no figura en la especificación, escribí
exactamente: "No especificado en la ficha técnica del proveedor".

Producto: {nombre}
Categoría: {apertura}
Especificación_Técnica (ÚNICA fuente de datos cuantitativos y normas): {especificacion}
Norma de referencia del catálogo (usala solo si figura también en la especificación): {norma}

Respondé ÚNICAMENTE con un JSON válido, sin texto adicional, sin markdown.
El JSON debe tener exactamente estas claves:

{{"DESCRIPCION": "Descripción del producto basada exclusivamente en la Especificación_Técnica. Sin datos inventados.",
"MODO_USO": "Instrucciones de uso derivadas de la especificación y la categoría del producto.",
"RENDIMIENTO": "Rendimiento o cobertura si figura en la especificación. Si no figura: 'No especificado en la ficha técnica del proveedor'.",
"PROPORCIONES": "Proporciones de mezcla si aplica y figuran en la especificación. Si no aplica o no figura: 'No aplica' o 'No especificado en la ficha técnica del proveedor'.",
"TIEMPO_SECADO": "Tiempo de secado/curado si figura en la especificación. Si no aplica (EPP, herramientas): 'No aplica para este tipo de producto'.",
"NORMATIVA": "Copiar textualmente la norma de la Especificación_Técnica. Si no figura ninguna norma en la especificación: 'No especificado en la ficha técnica del proveedor'. NUNCA escribir una norma que no esté en la especificación.",
"PRECAUCIONES": "Precauciones de uso, almacenamiento y mantenimiento relevantes para este tipo de producto."}}"""

def generar_ficha_gemini(nombre, apertura, especificacion, norma, modelo):
    prompt = PROMPT_FICHA.format(nombre=nombre, apertura=apertura, especificacion=especificacion, norma=norma)
    response = modelo.generate_content(prompt)
    texto = response.text.strip()
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"):
            texto = texto[4:]
    return json.loads(texto.strip())

def completar_fichas(sheet, forzar=False):
    if not GEMINI_API_KEY:
        log("⚠️  GEMINI_API_KEY vacío — saltando fichas técnicas")
        log("   Completá la variable GEMINI_API_KEY en el script y volvé a correr con --solo-fichas")
        return
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    modelo = genai.GenerativeModel("gemini-2.5-flash")
    log("━━━ PARTE 2: Generando fichas técnicas ━━━")
    ws_prod = sheet.worksheet("PRODUCTOS")
    productos = ws_prod.get_all_records()
    log(f"  📦 {len(productos)} productos en hoja PRODUCTOS")
    ws_bc = sheet.worksheet("BASE_CONOCIMIENTO")
    all_bc_values = ws_bc.get_all_values()
    cabecera = all_bc_values[0] if all_bc_values else []
    col_index = {col: i+1 for i, col in enumerate(cabecera)}
    bc_map = {}
    if "ID_PRODUCTO" in cabecera:
        id_col_idx = cabecera.index("ID_PRODUCTO")
        for i, row in enumerate(all_bc_values[1:], start=2):
            if len(row) > id_col_idx and row[id_col_idx]:
                bc_map[row[id_col_idx]] = i
    checkpoint = cargar_checkpoint()
    procesados = set(checkpoint["procesados"])
    errores_previos = set(checkpoint["errores"])
    pendientes = []
    for prod in productos:
        pid = prod.get("ID", "")
        if not pid:
            continue
        if pid in procesados and not forzar:
            continue
        if pid in bc_map:
            fila_num = bc_map[pid]
            estado_col = col_index.get("ESTADO")
            if estado_col:
                row_data = all_bc_values[fila_num - 1] if fila_num - 1 < len(all_bc_values) else []
                estado_actual = row_data[estado_col - 1] if len(row_data) >= estado_col else ""
                if estado_actual == "Aprobado" and not forzar:
                    procesados.add(pid)
                    continue
        pendientes.append(prod)
    total = len(pendientes)
    log(f"  🔧 {total} productos a procesar")
    if total == 0:
        log("  ✅ Todos los productos ya tienen ficha aprobada")
        return
    tiempo_estimado = total * DELAY_ENTRE_REQUESTS
    log(f"  ⏱  Tiempo estimado: ~{tiempo_estimado//60} min")
    for i, prod in enumerate(pendientes, 1):
        pid      = prod.get("ID", "")
        nombre   = prod.get("Nombre", "")
        apertura = prod.get("Apertura", "")
        espec    = prod.get("Especificación_Técnica", "")
        norma    = prod.get("ID_Norma_Ref", "")
        log(f"  [{i}/{total}] {pid} — {nombre}")
        try:
            ficha = generar_ficha_gemini(nombre, apertura, espec, norma, modelo)
            nueva_fila = [
                pid, nombre, apertura,
                ficha.get("DESCRIPCION", ""), ficha.get("MODO_USO", ""),
                ficha.get("RENDIMIENTO", ""), ficha.get("PROPORCIONES", ""),
                ficha.get("TIEMPO_SECADO", ""), ficha.get("NORMATIVA", ""),
                ficha.get("PRECAUCIONES", ""),
                f"Generado automáticamente {ts()}", "Borrador",
            ]
            if pid in bc_map:
                fila_num = bc_map[pid]
                rango = f"A{fila_num}:{chr(64+len(nueva_fila))}{fila_num}"
                ws_bc.update(rango, [nueva_fila])
                log(f"       ✅ Actualizado fila {fila_num}")
            else:
                ws_bc.append_row(nueva_fila)
                log(f"       ✅ Fila nueva agregada")
            procesados.add(pid)
            errores_previos.discard(pid)
        except json.JSONDecodeError as e:
            log(f"       ⚠️  JSON inválido para {pid}: {e}")
            checkpoint["errores"] = list(errores_previos | {pid})
        except Exception as e:
            log(f"       ❌ Error en {pid}: {e}")
            checkpoint["errores"] = list(errores_previos | {pid})
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                log(f"       ⏳ Rate limit — esperando 90 segundos extra...")
                time.sleep(90)
        checkpoint["procesados"] = list(procesados)
        guardar_checkpoint(checkpoint)
        if i < total:
            log(f"       ⏳ Esperando {DELAY_ENTRE_REQUESTS}s...")
            time.sleep(DELAY_ENTRE_REQUESTS)
    log(f"\n  📊 Resumen: {len(procesados)} procesados, {len(checkpoint['errores'])} errores")
    log("━━━ PARTE 2 completa ━━━\n")

def main():
    parser = argparse.ArgumentParser(description="Completa el Sheet CUBOCRAFT")
    parser.add_argument("--solo-fichas", action="store_true")
    parser.add_argument("--solo-datos",  action="store_true")
    parser.add_argument("--forzar",      action="store_true")
    args = parser.parse_args()
    if not Path(SERVICE_ACCOUNT_FILE).exists():
        log(f"❌ No encontré {SERVICE_ACCOUNT_FILE}")
        sys.exit(1)
    log("🚀 Iniciando completar_sheet.py — CUBOCRAFT")
    try:
        sheet = conectar_sheets()
        log(f"   ✅ Conectado al Sheet: {sheet.title}\n")
    except Exception as e:
        log(f"❌ Error conectando al Sheet: {e}")
        sys.exit(1)
    if not args.solo_fichas:
        cargar_datos_prueba(sheet)
    if not args.solo_datos:
        completar_fichas(sheet, forzar=args.forzar)
    log("🏁 Script finalizado")

if __name__ == "__main__":
    main()
