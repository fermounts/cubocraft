"""
setup_sheets.py
Crea el Spreadsheet CUBOCRAFT con todas las pestañas, encabezados y datos iniciales.
Uso: python3 setup_sheets.py
Requiere: GOOGLE_CREDS_JSON en .env — puede ser la ruta a un .json o el JSON inline.
"""

import json
import sys
import time
import os

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()


def _load_creds_data(value: str) -> dict:
    """Acepta ruta a archivo .json o JSON inline como string."""
    value = value.strip()
    if value.endswith(".json") and os.path.isfile(value):
        with open(value) as f:
            return json.load(f)
    return json.loads(value)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Encabezados por pestaña ────────────────────────────────────────────────────

HEADERS = {
    "VENDEDORES":          ["ID", "Nombre", "Teléfono", "Zona", "Perfil", "Activa"],
    "PRODUCTOS":           ["ID", "Apertura", "Nombre", "Especificación_Técnica", "ID_Norma_Ref", "Costo", "Precio_Vendedor", "Activo"],
    "PEDIDOS":             ["ID_Pedido", "Fecha", "ID_Vendedor", "Nombre_Vendedor", "ID_Producto", "Nombre_Producto", "Cantidad", "Precio_Unit", "Descuento_Pct", "Total", "ID_Campaña", "Estado"],
    "PAGOS":               ["ID_Pago", "Fecha", "ID_Vendedor", "Nombre_Vendedor", "Monto", "Metodo", "Comprobante", "Estado", "Anulado"],
    "CAMPAÑAS":            ["ID_Campaña", "Nombre", "Fecha_Inicio", "Fecha_Fin", "Descuento_Pct", "Monto_Minimo", "Activa"],
    "RANKING":             ["ID_Vendedor", "Nombre", "Posición_Semana", "Categoría", "Ventas_Semana", "Ventas_Mes"],
    "CANDIDATOS":          ["Nombre", "Teléfono", "Zona", "Fecha", "Estado", "Notas"],
    "CONOCIMIENTO_TECNICO":["ID_Norma", "Nombre_Norma", "Alcance", "Aplicación_en_Obra"],
}

# ── Catálogo EPP ───────────────────────────────────────────────────────────────
# Columnas: ID | Apertura | Nombre | Especificación_Técnica | ID_Norma_Ref | Costo | Precio_Vendedor | Activo

PRODUCTOS_EPP = [
    ["EPP-001", "Cabeza",       "Casco de Seguridad Clase A",
     "Polietileno de alta densidad, suspensión de 6 puntos, ranuras para accesorios, colores surtidos",
     "IRAM-3620", 3200, 4800, "SI"],
    ["EPP-002", "Cabeza",       "Casco de Seguridad Clase B (dieléctrico)",
     "ABS dieléctrico, resistencia eléctrica hasta 20.000 V, suspensión de 6 puntos",
     "IRAM-3620", 4500, 6800, "SI"],
    ["EPP-003", "Visual",       "Antiparras de Seguridad Clear",
     "Policarbonato transparente, montura PVC, ventilación indirecta, resistente a impactos y rayaduras",
     "IRAM-3635", 1200, 1800, "SI"],
    ["EPP-004", "Visual",       "Antiparras de Seguridad Grises (solar)",
     "Policarbonato UV400, montura PVC, ventilación indirecta, filtro solar CAT 3",
     "IRAM-3635", 1400, 2100, "SI"],
    ["EPP-005", "Visual",       "Lentes Panorámicas con Ventilación",
     "Visor panorámico PC 1mm, ventilación directa/indirecta, compatible con tapabocas",
     "IRAM-3635", 2800, 4200, "SI"],
    ["EPP-006", "Manos",        "Guantes de Cuero Vaqueta T8",
     "Cuero de descarne 1,2 mm, costura doble, refuerzo en palma, talla 8 (M)",
     "IRAM-3649", 1800, 2700, "SI"],
    ["EPP-007", "Manos",        "Guantes de Cuero Vaqueta T9",
     "Cuero de descarne 1,2 mm, costura doble, refuerzo en palma, talla 9 (L)",
     "IRAM-3649", 1800, 2700, "SI"],
    ["EPP-008", "Manos",        "Guantes de Nitrilo Negro T8 (caja x100)",
     "Nitrilo sin polvo 4 g, color negro, ambidiestro, apto alimentos y productos químicos, talla M",
     "IRAM-3649", 5500, 8200, "SI"],
    ["EPP-009", "Manos",        "Guantes de Nitrilo Naranja Grip T9",
     "Nitrilo con acabado grip en palma, resistencia a corte nivel B, talla L",
     "IRAM-3649", 2200, 3300, "SI"],
    ["EPP-010", "Calzado",      "Calzado de Seguridad Bajo con Puntera (N°41)",
     "Bota baja PU/Cuero, puntera de acero 200 J, plantilla antiperforación, suela antideslizante, N°41",
     "IRAM-3627", 15000, 22500, "SI"],
    ["EPP-011", "Calzado",      "Calzado de Seguridad Bajo con Puntera (N°42)",
     "Bota baja PU/Cuero, puntera de acero 200 J, plantilla antiperforación, suela antideslizante, N°42",
     "IRAM-3627", 15000, 22500, "SI"],
    ["EPP-012", "Calzado",      "Calzado de Seguridad Bajo con Puntera (N°43)",
     "Bota baja PU/Cuero, puntera de acero 200 J, plantilla antiperforación, suela antideslizante, N°43",
     "IRAM-3627", 15000, 22500, "SI"],
    ["EPP-013", "Calzado",      "Bota de Seguridad Alta (N°42)",
     "Bota alta PVC/Cuero, puntera acero, caña alta 20 cm, resistente a aceites, N°42",
     "IRAM-3627", 18500, 27800, "SI"],
    ["EPP-014", "Altura",       "Arnés de Cuerpo Completo Clase III",
     "Poliéster 45mm, 5 puntos de amarre, argolla dorsal y esternal, hebillas de aluminio",
     "IRAM-3655", 12000, 18000, "SI"],
    ["EPP-015", "Altura",       "Eslinga con Absorbedor de Energía 1,5m",
     "Poliéster con absorbedor cosido, gancho doble seguro, largo 1,5 m, carga máx. 150 kg",
     "IRAM-3655", 8500, 12800, "SI"],
    ["EPP-016", "Respiratoria", "Respirador Semimáscara con Filtros P100",
     "Semimáscara silicona talla única, 2 filtros P100 incluidos, válvula exhalación",
     "IRAM-3632", 6800, 10200, "SI"],
    ["EPP-017", "Respiratoria", "Respirador Desechable FFP2 (caja x20)",
     "Mascarilla filtrante FFP2 sin válvula, 4 capas, eficiencia ≥94%, caja 20 unidades",
     "IRAM-3632", 4500, 6800, "SI"],
    ["EPP-018", "Auditiva",     "Tapones Auditivos Espuma 3M 1100 (bolsa x100 pares)",
     "Espuma PU SNR 37 dB, desechable, higiénicamente empacado, bolsa x100 pares",
     "IRAM-3659", 3500, 5200, "SI"],
    ["EPP-019", "Auditiva",     "Orejeras de Copa SNR 28 dB",
     "Orejeras copa ajuste diadema, SNR 28 dB, almohadillas reemplazables, plegables",
     "IRAM-3659", 5800, 8700, "SI"],
    ["EPP-020", "Cuerpo",       "Chaleco Reflectivo Clase 2 (talle único)",
     "Poliéster amarillo flúor, 2 bandas plateadas 5 cm, cierre con velcro, talle único ajustable",
     "IRAM-3931", 2500, 3800, "SI"],
    ["EPP-021", "Cuerpo",       "Rodilleras de Trabajo Profesional",
     "Carcasa ABS con espuma EVA 20mm, correas regulables, protección EN 14404",
     "IRAM-4241", 4200, 6300, "SI"],
    ["EPP-022", "Cuerpo",       "Cinturón Lumbar de Trabajo (talle L)",
     "Nylon reforzado, soporte lumbar en ABS, breteles regulables, anillo D lateral, talle L",
     "IRAM-4241", 5500, 8200, "SI"],
]

# ── Catálogo MC (Métodos Constructivos — CRAFT) ───────────────────────────────

PRODUCTOS_MC = [
    ["MC-001", "Terminaciones",      "Cinta de Señalización Amarilla/Negra (rollo 200m)",
     "Polietileno PE, 7 cm de ancho, no adhesiva, patrón peligro, rollo 200 m",
     "ISO-3864", 1500, 2300, "SI"],
    ["MC-002", "Terminaciones",      "Cinta de Señalización Roja/Blanca (rollo 200m)",
     "Polietileno PE, 7 cm de ancho, no adhesiva, patrón prohibición, rollo 200 m",
     "ISO-3864", 1500, 2300, "SI"],
    ["MC-003", "Terminaciones",      "Señal de Seguridad Obligación 20x20 cm",
     "PVC rígido 1mm fotoluminiscente, adhesivo posterior, modelos a elección",
     "ISO-3864", 850, 1280, "SI"],
    ["MC-004", "Terminaciones",      "Señal de Evacuación y Emergencia 20x30 cm",
     "PVC rígido 1mm fotoluminiscente, flecha y salida de emergencia, borde verde",
     "ISO-3864", 1100, 1650, "SI"],
    ["MC-005", "Reparaciones",       "Kit de Botiquín de Primeros Auxilios Laboral",
     "Contenido mínimo Ley 24557, maletín plástico IP54, 42 artículos, sin medicamentos",
     "IRAM-2507", 9500, 14300, "SI"],
    ["MC-006", "Reparaciones",       "Extintor CO2 5 kg (recargado/certificado)",
     "CO2 5 kg, válvula latón, manguera con corneta, certificado IRAM, apto equipos eléctricos",
     "IRAM-3517", 18000, 27000, "SI"],
    ["MC-007", "Reparaciones",       "Extintor ABC Polvo 4 kg (recargado/certificado)",
     "Polvo ABC 4 kg, válvula latón, manómetro, certificado IRAM, apto clase A/B/C",
     "IRAM-3517", 12000, 18000, "SI"],
    ["MC-008", "Terminaciones",      "Tapa de Calzado (cubre-zapato) PP T. Única (par)",
     "Polipropileno no tejido, elástico perimetral, uso único, color blanco, talla única",
     "ISO-13688", 120, 180, "SI"],
    ["MC-009", "Terminaciones",      "Cofia Desechable Polipropileno (bolsa x100)",
     "PP no tejido 17 g, elástico perimetral, uso único, color azul, bolsa x100 unidades",
     "ISO-13688", 2200, 3300, "SI"],
    ["MC-010", "Terminaciones",      "Traje Tyvek con Capucha Talla L",
     "DuPont Tyvek 400 blanco, costura sellada, elástico en muñecas/tobillos/capucha, talla L",
     "ISO-13688", 4500, 6800, "SI"],
    ["MC-011", "Reparaciones",       "Soporte de Pared para Extintor Universal",
     "Acero estampado galvanizado, soporta extintores 1-9 kg, instalación con 2 tornillos",
     "IRAM-3517", 680, 1020, "SI"],
    ["MC-012", "Reparaciones",       "Delantal de Cuero para Soldadura",
     "Cuero vacuno 1,5 mm largo 90 cm, costuras reforzadas, ojales doble refuerzo",
     "IRAM-4241", 7800, 11700, "SI"],
    ["MC-013", "Reparaciones",       "Máscara de Soldar Automática Oscurecimiento DIN 9-13",
     "Pantalla ABS, celda solar + batería, DIN fijo 9-13 seleccionable, velocidad 1/25.000 s",
     "IRAM-3635", 22000, 33000, "SI"],
    ["MC-014", "Terminaciones",      "Botella Tomador de Agua 1L con Mosquetón",
     "BPA free, tapa rosca + mosquetón acero, 1 litro, colores surtidos",
     "N/A", 1800, 2700, "SI"],
    ["MC-015", "Reparaciones",       "Candado de Bloqueo LOTO Rojo (con etiqueta)",
     "Acero endurecido, llave maestra única, conjunto con etiqueta PELIGRO, anilla 25 mm",
     "ISO-3864", 2800, 4200, "SI"],
]

PRODUCTOS_DATA = PRODUCTOS_EPP + PRODUCTOS_MC

# ── Normativas técnicas ────────────────────────────────────────────────────────
# Columnas: ID_Norma | Nombre_Norma | Alcance | Aplicación_en_Obra

CONOCIMIENTO_TECNICO_DATA = [
    ["IRAM-3620",
     "IRAM 3620 — Cascos de Protección para la Industria",
     "Establece requisitos de desempeño, ensayos y marcado para cascos de protección. Clases A (uso general), B (dieléctrico) y C (conducción de calor limitada).",
     "Obligatorio en toda tarea con riesgo de caída de objetos o golpes en la cabeza: obras civiles, montajes, demoliciones, excavaciones y trabajos en altura."],

    ["IRAM-3627",
     "IRAM 3627 — Calzado de Seguridad",
     "Define requisitos para calzado que protege pies contra impactos (≥200 J), compresión, perforación plantar y riesgos eléctricos. Categorías SB, S1, S2, S3.",
     "Obligatorio en tareas de manipulación de cargas, uso de herramientas de corte, trabajo en altura y zonas con objetos punzantes o pesados."],

    ["IRAM-3635",
     "IRAM 3635 — Protectores Oculares y Faciales",
     "Regula protectores contra partículas, líquidos, radiación óptica y arco eléctrico. Clasifica lentes, antiparras y pantallas faciales según tipo de riesgo.",
     "Obligatorio en trabajos de esmerilado, corte, soldadura, uso de productos químicos, desbaste y cualquier tarea que genere proyección de partículas o líquidos."],

    ["IRAM-3649",
     "IRAM 3649 — Guantes de Protección",
     "Especifica ensayos de resistencia a abrasión, corte, desgarro, perforación y penetración química. Niveles de desempeño por categoría de riesgo.",
     "Selección según tarea: cuero/vaqueta para manipulación mecánica y carga; nitrilo para químicos; neoprene para electricidad. Indispensable en casi toda tarea manual."],

    ["IRAM-3655",
     "IRAM 3655 — Arneses, Eslingas y Sistemas de Detención de Caídas",
     "Establece requisitos constructivos y de ensayo para arneses de cuerpo completo, eslingas con absorbedor, líneas de vida y anclajes. Carga dinámica mínima 15 kN.",
     "Obligatorio en todo trabajo en altura ≥1,80 m sin protección colectiva. Incluye montajes de estructuras, techos, fachadas, torres y trabajos en andamios."],

    ["IRAM-3632",
     "IRAM 3632 — Equipos de Protección Respiratoria",
     "Norma para equipos filtrantes (P1/P2/P3), máscaras semimáscara y de cara completa, y SCBA. Define requisitos de fuga, resistencia respiratoria y tiempo de servicio.",
     "Obligatorio ante exposición a polvos (lijado, demolición), humos (soldadura, pintura), gases y vapores tóxicos. Seleccionar filtro según agente químico involucrado."],

    ["IRAM-3659",
     "IRAM 3659 — Protectores Auditivos",
     "Regula tapones y orejeras copa. Define el NRR (Noise Reduction Rating) y SNR. Obligatoria la señalización de zona de uso cuando ruido ≥85 dB(A).",
     "Obligatorio en áreas con nivel de ruido sostenido ≥85 dB: uso de amoladoras, compresoras, martillos hidráulicos, sierras circulares y compactadoras."],

    ["IRAM-3931",
     "IRAM 3931 — Ropa de Señalización de Alta Visibilidad",
     "Clasifica chalecos y prendas reflectivas en Clase 1, 2 y 3 según superficie de material fluorescente y retroreflectivo. Requisitos de color y lavabilidad.",
     "Clase 2 o 3 obligatorio para trabajadores expuestos al tránsito vehicular: viales, mantenimiento de rutas, operación de maquinaria pesada y trabajos nocturnos."],

    ["IRAM-4241",
     "IRAM 4241 — Ropa de Protección General",
     "Cubre requisitos para indumentaria de trabajo contra riesgos mecánicos (abrasión, corte, desgarro), térmicos y químicos de baja concentración.",
     "Aplicable a delantales de cuero para soldadura, trajes de protección química, ropa ignífuga y equipos complementarios de trabajo en talleres y plantas."],

    ["ISO-3864",
     "ISO 3864 — Símbolos Gráficos — Colores y Señales de Seguridad",
     "Define el sistema de colores (rojo=peligro/prohibición, amarillo=advertencia, verde=seguridad, azul=obligación) y pictogramas para señalización de seguridad.",
     "Base para toda señalización en obra: carteles de advertencia, cintas de balizamiento, señales de evacuación, zonas restringidas y rutas de escape."],

    ["IRAM-3517",
     "IRAM 3517 — Extintores de Incendio Portátiles",
     "Establece clasificación (A, B, C, D, K), capacidad extintora, ensayos de presión y estanquidad, marcado y frecuencia de recarga. Instalación según riesgo.",
     "Obligatorio en toda obra con presencia de combustibles, equipos eléctricos o depósitos de gas. Ubicar a máx. 15 m del riesgo con soporte visible y libre de obstrucción."],
]


def bold_header(ws: gspread.Worksheet, n_cols: int) -> None:
    """Aplica negrita y color de fondo a la fila de encabezados."""
    ws.format(f"A1:{chr(64 + n_cols)}1", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.18, "green": 0.47, "blue": 0.71},
        "horizontalAlignment": "CENTER",
    })
    # Texto en blanco
    ws.format(f"A1:{chr(64 + n_cols)}1", {
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
    })


def freeze_header(ws: gspread.Worksheet) -> None:
    ws.freeze(rows=1)


def setup_tabs(sh: gspread.Spreadsheet) -> None:
    default_ws = sh.sheet1
    default_ws.update_title(list(HEADERS.keys())[0])
    first_tab = True

    for tab_name, headers in HEADERS.items():
        print(f"  → Pestaña: {tab_name}")
        if first_tab:
            ws = sh.worksheet(tab_name)
            first_tab = False
        else:
            # Si la pestaña ya existe (populate-only), la usamos; si no, la creamos.
            try:
                ws = sh.worksheet(tab_name)
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(title=tab_name, rows=500, cols=len(headers))
                time.sleep(0.5)

        ws.update(range_name="A1", values=[headers])
        freeze_header(ws)
        bold_header(ws, len(headers))


def load_data(sh: gspread.Spreadsheet) -> None:
    print("  → Cargando PRODUCTOS...")
    sh.worksheet("PRODUCTOS").update(range_name="A2", values=PRODUCTOS_DATA)
    print(f"     {len(PRODUCTOS_DATA)} productos ({len(PRODUCTOS_EPP)} EPP + {len(PRODUCTOS_MC)} MC).")

    print("  → Cargando CONOCIMIENTO_TECNICO...")
    sh.worksheet("CONOCIMIENTO_TECNICO").update(range_name="A2", values=CONOCIMIENTO_TECNICO_DATA)
    print(f"     {len(CONOCIMIENTO_TECNICO_DATA)} normativas.")


def main() -> None:
    # Modo populate-only: python3 setup_sheets.py <SHEET_ID>
    existing_id = sys.argv[1] if len(sys.argv) > 1 else None

    creds_json = os.getenv("GOOGLE_CREDS_JSON")
    if not creds_json:
        print("ERROR: GOOGLE_CREDS_JSON no está definido en .env")
        sys.exit(1)

    print("Conectando con Google Sheets...")
    creds_data = _load_creds_data(creds_json)
    creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
    gc = gspread.authorize(creds)

    if existing_id:
        print(f"Modo populate-only → abriendo spreadsheet {existing_id}...")
        sh = gc.open_by_key(existing_id)
        spreadsheet_id = existing_id
    else:
        print("Creando spreadsheet 'CUBOCRAFT'...")
        sh = gc.create("CUBOCRAFT")
        spreadsheet_id = sh.id
        print(f"  → Creado. ID: {spreadsheet_id}")

    setup_tabs(sh)
    load_data(sh)

    if not existing_id:
        service_email = creds_data.get("client_email", "")
        if service_email:
            sh.share(service_email, perm_type="user", role="writer", notify=False)

    print("\n" + "=" * 60)
    print("CUBOCRAFT Spreadsheet listo.")
    print(f"GOOGLE_SHEET_ID={spreadsheet_id}")
    print("=" * 60)
    print(f"\nURL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
    if not existing_id:
        print("\nAgregá al .env:  GOOGLE_SHEET_ID=" + spreadsheet_id)


if __name__ == "__main__":
    main()
