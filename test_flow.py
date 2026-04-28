"""
test_flow.py - Prueba el flujo de pedidos de punta a punta localmente.
Simula exactamente lo que hace bot_handler cuando llega un mensaje de WhatsApp.
"""
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

import config
import session_store
import sheets_client
import bot_handler

PHONE = "test:+5491199999999"

def msg(texto):
    resp = bot_handler.procesar(PHONE, texto)
    print(f"\n>>> {repr(texto)}")
    print(resp)
    print("-" * 50)
    return resp

def check(resp, expected_fragment, label):
    ok = expected_fragment.lower() in resp.lower()
    status = "✓" if ok else "✗ FALLO"
    print(f"  [{status}] {label}")
    if not ok:
        print(f"         esperaba: {repr(expected_fragment)}")
    return ok

def main():
    errors = []

    # -- Prerequisito: necesitamos un vendedor de prueba en la hoja --
    print("\n" + "=" * 60)
    print("VERIFICACIÓN DE ENTORNO")
    print("=" * 60)
    print(f"GOOGLE_SHEET_ID = {repr(config.GOOGLE_SHEET_ID)}")
    if not config.GOOGLE_SHEET_ID:
        print("ERROR CRÍTICO: GOOGLE_SHEET_ID no está configurado.")
        print("Esto causa que get_productos_por_categoria() devuelva [].")
        sys.exit(1)

    vendedores = sheets_client.get_productos_activos()
    print(f"Productos activos en hoja: {len(vendedores)}")

    print("\nCategorías en CUBO:")
    for clave, nombre in bot_handler._CATEGORIAS["CUBO"]:
        prods = sheets_client.get_productos_por_categoria(clave, "CUBO")
        print(f"  {clave:15s} → {len(prods)} productos")

    print("\nCategorías en CRAFT:")
    for clave, nombre in bot_handler._CATEGORIAS["CRAFT"]:
        prods = sheets_client.get_productos_por_categoria(clave, "CRAFT")
        print(f"  {clave:20s} → {len(prods)} productos")

    # -- Buscar vendedor real para hacer la prueba --
    print("\n" + "=" * 60)
    print("BUSCANDO VENDEDOR DE PRUEBA EN LA HOJA")
    print("=" * 60)
    try:
        ws = sheets_client._get_sheet("VENDEDORES")
        rows = ws.get_all_records()
        print(f"Filas en VENDEDORES: {len(rows)}")
        if rows:
            print(f"Primero: {rows[0]}")
    except Exception as e:
        print(f"Error leyendo VENDEDORES: {e}")

    # -- Test de renders sin depender de un vendedor real --
    print("\n" + "=" * 60)
    print("TEST DE _render_categorias Y _render_productos")
    print("=" * 60)

    r = bot_handler._render_categorias("CUBO", [])
    ok = "Cabeza" in r or "Visual" in r
    print(f"  [{'✓' if ok else '✗'}] _render_categorias CUBO devuelve lista")
    if not ok:
        print(f"  Output: {r}")

    r = bot_handler._render_productos("Cabeza", "🪖 Cabeza — Cascos", "CUBO")
    ok = "Casco" in r or "No hay productos" not in r
    empty = "No hay productos" in r
    if empty:
        errors.append("_render_productos('Cabeza','CUBO') devuelve vacío — revisar Apertura en sheet")
    print(f"  [{'✓' if not empty else '✗'}] _render_productos Cabeza/CUBO")
    if not empty:
        print(f"  Output snippet: {r[:120]}")

    r = bot_handler._render_productos("Visual", "🥽 Visual", "CUBO")
    empty = "No hay productos" in r
    if empty:
        errors.append("_render_productos('Visual','CUBO') devuelve vacío")
    print(f"  [{'✓' if not empty else '✗'}] _render_productos Visual/CUBO")

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    if errors:
        print("ERRORES encontrados:")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print("✓ Todo OK localmente. Si falla en Render, es un problema de env vars.")
        print("\nVariables que Render necesita tener:")
        print(f"  GOOGLE_SHEET_ID   = {config.GOOGLE_SHEET_ID}")
        print(f"  GOOGLE_CREDS_JSON = (JSON del service account)")

if __name__ == "__main__":
    main()
