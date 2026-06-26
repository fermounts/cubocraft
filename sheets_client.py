import json
import logging
import os
import re
from datetime import date, datetime, timedelta

import gspread
import pytz
from google.oauth2.service_account import Credentials

_TZ_ARG = pytz.timezone("America/Argentina/Buenos_Aires")

import config

logger = logging.getLogger(__name__)

LIMITE_CREDITO = 100_000

_MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

METODOS: dict[str, str] = {
    "1": "Transferencia bancaria",
    "2": "Efectivo",
    "3": "MercadoPago",
}

_gc: gspread.Client | None = None


def _load_creds_data(value: str | None) -> dict:
    if not value:
        raise RuntimeError("GOOGLE_CREDS_JSON no está configurado en las variables de entorno.")
    value = value.strip()
    if value.endswith(".json") and os.path.isfile(value):
        with open(value) as f:
            return json.load(f)
    return json.loads(value)


def _get_client() -> gspread.Client:
    global _gc
    if _gc is None:
        creds_data = _load_creds_data(config.GOOGLE_CREDS_JSON)
        creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
        _gc = gspread.authorize(creds)
    return _gc


def _get_sheet(name: str) -> gspread.Worksheet:
    if not config.GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID no está configurado en las variables de entorno.")
    return _get_client().open_by_key(config.GOOGLE_SHEET_ID).worksheet(name)


def _normalize_phone(phone: str) -> str:
    return phone.removeprefix("whatsapp:").lstrip("+").strip()


# ── Vendedores ────────────────────────────────────────────────────────────────

def get_vendedora_by_phone(phone: str) -> dict | None:
    try:
        ws = _get_sheet("VENDEDORES")
        target = _normalize_phone(phone)
        logger.info("get_vendedora_by_phone → raw=%r  normalizado=%r", phone, target)
        for r in ws.get_all_records():
            stored = _normalize_phone(str(r.get("Teléfono", "")))
            logger.debug("  comparando stored=%r vs target=%r", stored, target)
            if stored == target and str(r.get("Activa", "")).upper() in ("SI", "1", "TRUE", "VERDADERO"):
                return r
        logger.warning("get_vendedora_by_phone → sin match para %r", target)
        return None
    except Exception as e:
        logger.error("get_vendedora_by_phone error: %s", e)
        return None


def get_vendedor_by_id(vid: str) -> dict | None:
    try:
        ws = _get_sheet("VENDEDORES")
        for r in ws.get_all_records():
            if str(r.get("ID", "")) == vid:
                return r
        return None
    except Exception as e:
        logger.error("get_vendedor_by_id error: %s", e)
        return None


def get_vendedores_activos() -> list[dict]:
    """Todos los vendedores con Activa=SI."""
    try:
        ws = _get_sheet("VENDEDORES")
        return [r for r in ws.get_all_records()
                if str(r.get("Activa", "")).upper() in ("SI", "1", "TRUE")]
    except Exception as e:
        logger.error("get_vendedores_activos error: %s", e)
        return []


def validar_login(phone: str, pin: str) -> dict | None:
    """Valida teléfono + PIN contra VENDEDORES. Devuelve dict del vendedor o None."""
    try:
        ws = _get_sheet("VENDEDORES")
        phone_norm = re.sub(r"[^\d]", "", phone)
        for r in ws.get_all_records():
            stored = re.sub(r"[^\d]", "", str(r.get("Teléfono", "")))
            if stored == phone_norm and str(r.get("PIN", "")).strip() == str(pin).strip():
                return r
        return None
    except Exception as e:
        logger.error("validar_login error: %s", e)
        return None


# ── Productos ─────────────────────────────────────────────────────────────────

def get_productos_por_categoria(categoria: str, empresa: str) -> list[dict]:  # noqa: ARG001
    try:
        ws = _get_sheet("PRODUCTOS")
        resultado = [
            r for r in ws.get_all_records()
            if str(r.get("Apertura", "")).strip() == categoria
            and str(r.get("Activo", "")).upper() in ("SI", "1", "TRUE", "VERDADERO")
        ]
        logger.debug("get_productos_por_categoria(%r) → %d productos", categoria, len(resultado))
        return resultado
    except Exception as e:
        logger.error("get_productos_por_categoria error categoria=%r: %s", categoria, e)
        return []


def get_productos_activos() -> list[dict]:
    try:
        ws = _get_sheet("PRODUCTOS")
        return [
            r for r in ws.get_all_records()
            if str(r.get("Activo", "")).upper() in ("SI", "1", "TRUE", "VERDADERO")
        ]
    except Exception as e:
        logger.error("get_productos_activos error: %s", e)
        return []


def get_producto_by_id(pid: str) -> dict | None:
    try:
        ws = _get_sheet("PRODUCTOS")
        for r in ws.get_all_records():
            if str(r.get("ID", "")).strip().upper() == str(pid).strip().upper():
                return r
        return None
    except Exception as e:
        logger.error("get_producto_by_id error: %s", e)
        return None


# ── Pedidos ───────────────────────────────────────────────────────────────────

def registrar_pedido(
    vendedor: dict,
    producto: dict,
    cantidad: int,
    descuento_pct: float,
    id_campana: str,
) -> str:
    try:
        ws = _get_sheet("PEDIDOS")
        precio = float(producto.get("Precio_Vendedor", 0))
        subtotal = round(precio * cantidad * (1 - descuento_pct / 100), 2)
        pid = f"P{datetime.now(_TZ_ARG).strftime('%Y%m%d%H%M%S')}"
        ws.append_row([
            pid,
            datetime.now(_TZ_ARG).strftime("%Y-%m-%d %H:%M:%S"),
            str(vendedor.get("ID", "")),
            str(vendedor.get("Nombre", "")),
            str(producto.get("ID", "")),
            str(producto.get("Nombre", "")),
            str(cantidad),
            str(precio),
            str(descuento_pct),
            f"{subtotal:.2f}",
            str(id_campana or ""),
            "PENDIENTE",
        ])
        logger.info("Pedido registrado: %s", pid)
        return pid
    except Exception as e:
        logger.error("registrar_pedido error: %s", e)
        return "ERROR"


def get_ultimo_pedido(vendedor: dict) -> dict | None:
    pedidos = get_ultimos_pedidos(vendedor, limite=1)
    return pedidos[0] if pedidos else None


def get_ultimos_pedidos(vendedor: dict, limite: int = 5) -> list[dict]:
    try:
        ws = _get_sheet("PEDIDOS")
        vid = str(vendedor.get("ID", ""))
        nombre = str(vendedor.get("Nombre", ""))
        pedidos = [
            r for r in ws.get_all_records()
            if str(r.get("ID_Vendedor", "")) == vid or str(r.get("Nombre_Vendedor", "")) == nombre
        ]
        return pedidos[-limite:] if pedidos else []
    except Exception as e:
        logger.error("get_ultimos_pedidos error: %s", e)
        return []


# ── Pagos ─────────────────────────────────────────────────────────────────────

def get_balance_vendedor(vendedor: dict) -> dict:
    try:
        vid = str(vendedor.get("ID", ""))
        pedidos = _get_sheet("PEDIDOS").get_all_records()
        pagos   = _get_sheet("PAGOS").get_all_records()

        def _f(v):
            try:
                return float(v or 0)
            except (ValueError, TypeError):
                return 0.0

        total_pedidos = sum(
            _f(r.get("Total"))
            for r in pedidos
            if str(r.get("ID_Vendedor", "")) == vid
            and str(r.get("Estado", "")).upper() != "CANCELADO"
        )
        pagos_confirmados = sum(
            _f(r.get("Monto"))
            for r in pagos
            if str(r.get("ID_Vendedor", "")) == vid
            and str(r.get("Estado", "")).upper() == "CONFIRMADO"
        )
        pagos_pendientes = sum(
            _f(r.get("Monto"))
            for r in pagos
            if str(r.get("ID_Vendedor", "")) == vid
            and str(r.get("Estado", "")).upper() == "PENDIENTE"
        )
        deuda_real         = round(total_pedidos - pagos_confirmados, 2)
        credito_provisional = round(pagos_pendientes, 2)
        neto               = round(deuda_real - credito_provisional, 2)
        disponible         = round(LIMITE_CREDITO - neto, 2)
        return {
            "total_pedidos": total_pedidos,
            "pagos_confirmados": pagos_confirmados,
            "pagos_pendientes": pagos_pendientes,
            "deuda_real": deuda_real,
            "credito_provisional": credito_provisional,
            "neto": neto,
            "disponible": disponible,
        }
    except Exception as e:
        logger.error("get_balance_vendedor error: %s", e)
        return {
            "total_pedidos": 0, "pagos_confirmados": 0, "pagos_pendientes": 0,
            "deuda_real": 0, "credito_provisional": 0, "neto": 0,
            "disponible": float(LIMITE_CREDITO),
        }


def get_saldo(vendedor: dict) -> float:
    try:
        ws = _get_sheet("PAGOS")
        vid = str(vendedor.get("ID", ""))
        total = sum(
            float(r.get("Monto", 0))
            for r in ws.get_all_records()
            if str(r.get("ID_Vendedor", "")) == vid
            and str(r.get("Estado", "")).upper() != "ANULADO"
        )
        return round(total, 2)
    except Exception as e:
        logger.error("get_saldo error: %s", e)
        return 0.0


def registrar_pago(
    vendedor: dict,
    monto: float,
    metodo: str,
    comprobante: str,
) -> tuple[str, float, float]:
    try:
        ws = _get_sheet("PAGOS")
        pid = f"PAG{datetime.now(_TZ_ARG).strftime('%Y%m%d%H%M%S')}"
        ws.append_row([
            pid,
            datetime.now(_TZ_ARG).strftime("%Y-%m-%d %H:%M:%S"),
            str(vendedor.get("ID", "")),
            str(vendedor.get("Nombre", "")),
            str(monto),
            metodo,
            str(comprobante or ""),
            "PENDIENTE",
        ])
        logger.info("Pago registrado como PENDIENTE: %s", pid)
        return pid, 0.0, 0.0
    except Exception as e:
        logger.error("registrar_pago error: %s", e)
        return "ERROR", 0.0, 0.0


def get_pedidos_pendientes(vendedor: dict) -> list[dict]:
    try:
        ws = _get_sheet("PEDIDOS")
        vid = str(vendedor.get("ID", ""))
        return [
            r for r in ws.get_all_records()
            if str(r.get("ID_Vendedor", "")) == vid
            and str(r.get("Estado", "")).upper() == "PENDIENTE"
        ]
    except Exception as e:
        logger.error("get_pedidos_pendientes error: %s", e)
        return []


def cancelar_pedido(id_pedido: str, id_vendedor: str) -> bool:
    try:
        ws = _get_sheet("PEDIDOS")
        records = ws.get_all_values()
        headers = records[0]
        col_id = headers.index("ID_Pedido")
        col_vid = headers.index("ID_Vendedor")
        col_estado = headers.index("Estado")
        for i, row in enumerate(records[1:], start=2):
            if row[col_id] == id_pedido and row[col_vid] == id_vendedor:
                if row[col_estado].upper() == "PENDIENTE":
                    ws.update_cell(i, col_estado + 1, "CANCELADO")
                    logger.info("Pedido %s cancelado", id_pedido)
                    return True
        return False
    except Exception as e:
        logger.error("cancelar_pedido error: %s", e)
        return False


def get_pagos_confirmados_todos() -> list[dict]:
    try:
        ws = _get_sheet("PAGOS")
        return [
            r for r in ws.get_all_records()
            if str(r.get("Estado", "")).upper() == "CONFIRMADO"
        ]
    except Exception as e:
        logger.error("get_pagos_confirmados_todos error: %s", e)
        return []


def anular_pago(id_pago: str) -> bool:
    try:
        ws = _get_sheet("PAGOS")
        records = ws.get_all_values()
        headers = records[0]
        col_id = headers.index("ID_Pago")
        col_estado = headers.index("Estado")
        for i, row in enumerate(records[1:], start=2):
            if row[col_id] == id_pago:
                ws.update_cell(i, col_estado + 1, "ANULADO")
                logger.info("Pago %s anulado", id_pago)
                return True
        return False
    except Exception as e:
        logger.error("anular_pago error: %s", e)
        return False


def get_pagos_pendientes_todos() -> list[dict]:
    try:
        ws = _get_sheet("PAGOS")
        return [
            r for r in ws.get_all_records()
            if str(r.get("Estado", "")).upper() == "PENDIENTE"
        ]
    except Exception as e:
        logger.error("get_pagos_pendientes_todos error: %s", e)
        return []


def confirmar_pago(id_pago: str) -> bool:
    try:
        ws = _get_sheet("PAGOS")
        records = ws.get_all_values()
        headers = records[0]
        col_id = headers.index("ID_Pago")
        col_estado = headers.index("Estado")
        for i, row in enumerate(records[1:], start=2):
            if row[col_id] == id_pago and row[col_estado].upper() == "PENDIENTE":
                ws.update_cell(i, col_estado + 1, "CONFIRMADO")
                logger.info("Pago %s confirmado", id_pago)
                return True
        return False
    except Exception as e:
        logger.error("confirmar_pago error: %s", e)
        return False


# ── Campañas / descuentos ─────────────────────────────────────────────────────

def aplicar_mejor_descuento(
    vendedor: dict,
    total: float,
) -> tuple[dict | None, float, float]:
    try:
        ws = _get_sheet("CAMPAÑAS")
        hoy = date.today().isoformat()
        mejor: dict | None = None
        mejor_pct = 0.0
        for c in ws.get_all_records():
            if str(c.get("Activa", "")).upper() not in ("SI", "1", "TRUE"):
                continue
            if not (str(c.get("Fecha_Inicio", "")) <= hoy <= str(c.get("Fecha_Fin", "9999"))):
                continue
            try:
                minimo = float(c.get("Minimo_Compra", 0))
                pct = float(c.get("Descuento_Pct", 0))
            except (ValueError, TypeError):
                continue
            if total >= minimo and pct > mejor_pct:
                mejor = c
                mejor_pct = pct
        total_final = round(total * (1 - mejor_pct / 100), 2)
        return mejor, mejor_pct, total_final
    except Exception as e:
        logger.error("aplicar_mejor_descuento error: %s", e)
        return None, 0.0, float(total)


# ── Ranking ───────────────────────────────────────────────────────────────────

def _safe_float(v) -> float:
    try:
        return float(str(v).replace(",", ".") if v else "0")
    except (ValueError, TypeError):
        return 0.0


def _calcular_ranking_total(mes_actual: str, pedidos: list[dict]) -> list[dict]:
    """Ranking combinado (todos los productos) del mes, acepta lista de pedidos ya cargada."""
    totales: dict[str, dict] = {}
    for p in pedidos:
        if str(p.get("Estado", "")).upper() == "CANCELADO":
            continue
        if not str(p.get("Fecha", "")).startswith(mes_actual):
            continue
        vid = str(p.get("ID_Vendedor", ""))
        nombre = str(p.get("Nombre_Vendedor", ""))
        total = _safe_float(p.get("Total", 0))
        if vid not in totales:
            totales[vid] = {"nombre": nombre, "total": 0.0}
        totales[vid]["total"] += total
    if not totales:
        return []
    cats = ["Oro", "Plata", "Bronce"]
    ranking = sorted(totales.items(), key=lambda x: x[1]["total"], reverse=True)
    return [
        {
            "ID_Vendedor": vid,
            "Nombre": info["nombre"],
            "Total_Mes": round(info["total"], 2),
            "Posición": pos,
            "Categoría": cats[pos - 1] if pos <= 3 else "—",
        }
        for pos, (vid, info) in enumerate(ranking, start=1)
    ]


def calcular_ranking_semanal(inicio: date, fin: date) -> list[dict]:
    """Ranking combinado (todos los productos) de la semana inicio→fin inclusive."""
    try:
        ini_str = inicio.isoformat()
        fin_str = fin.isoformat()

        pedidos  = _get_sheet("PEDIDOS").get_all_records()
        prods_map = {
            str(r.get("ID", "")): str(r.get("Apertura", ""))
            for r in _get_sheet("PRODUCTOS").get_all_records()
        }

        totales: dict[str, dict] = {}
        for p in pedidos:
            if str(p.get("Estado", "")).upper() == "CANCELADO":
                continue
            fecha_str = str(p.get("Fecha", ""))[:10]
            if not (ini_str <= fecha_str <= fin_str):
                continue
            vid      = str(p.get("ID_Vendedor", ""))
            nombre   = str(p.get("Nombre_Vendedor", ""))
            total    = _safe_float(p.get("Total", 0))
            apertura = prods_map.get(str(p.get("ID_Producto", "")), "")
            if vid not in totales:
                totales[vid] = {"nombre": nombre, "total": 0.0, "pedidos": 0, "aperturas": []}
            totales[vid]["total"]   += total
            totales[vid]["pedidos"] += 1
            if apertura and apertura not in totales[vid]["aperturas"]:
                totales[vid]["aperturas"].append(apertura)

        if not totales:
            return []

        cats    = ["Oro", "Plata", "Bronce"]
        ranking = sorted(totales.items(), key=lambda x: x[1]["total"], reverse=True)
        return [
            {
                "ID_Vendedor":  vid,
                "Nombre":       info["nombre"],
                "Total_Semana": round(info["total"], 2),
                "Pedidos":      info["pedidos"],
                "Posición":     pos,
                "Categoría":    cats[pos - 1] if pos <= 3 else "—",
                "Aperturas":    info["aperturas"],
            }
            for pos, (vid, info) in enumerate(ranking, start=1)
        ]
    except Exception as e:
        logger.error("calcular_ranking_semanal %s→%s error: %s", inicio, fin, e)
        return []


def get_dashboard_supervisor() -> dict:
    """Datos para el dashboard del supervisor: resumen mes, año, ranking y campañas."""
    try:
        mes_actual = datetime.now(_TZ_ARG).strftime("%Y-%m")
        anio_actual = str(datetime.now(_TZ_ARG).year)

        pedidos = _get_sheet("PEDIDOS").get_all_records()
        pagos   = _get_sheet("PAGOS").get_all_records()

        total_mes = 0.0
        cant_pedidos_mes = 0
        total_anio = 0.0
        for p in pedidos:
            if str(p.get("Estado", "")).upper() == "CANCELADO":
                continue
            fecha = str(p.get("Fecha", ""))
            total = _safe_float(p.get("Total", 0))
            if fecha.startswith(mes_actual):
                total_mes += total
                cant_pedidos_mes += 1
            if fecha.startswith(anio_actual):
                total_anio += total

        pagos_pend = sum(
            1 for p in pagos
            if str(p.get("Estado", "")).upper() == "PENDIENTE"
        )

        ranking = _calcular_ranking_total(mes_actual, pedidos)

        hoy = date.today().isoformat()
        campanias_raw = _get_sheet("CAMPAÑAS").get_all_records()
        campanias = [
            {
                "Nombre": c.get("Nombre", ""),
                "Descuento_Pct": c.get("Descuento_Pct", 0),
                "Fecha_Fin": c.get("Fecha_Fin", ""),
            }
            for c in campanias_raw
            if str(c.get("Activa", "")).upper() in ("SI", "1", "TRUE")
            and str(c.get("Fecha_Fin", "9999")) >= hoy
        ]

        return {
            "total_mes": round(total_mes, 2),
            "cant_pedidos_mes": cant_pedidos_mes,
            "pagos_pendientes": pagos_pend,
            "total_anio": round(total_anio, 2),
            "ranking": ranking,
            "campanias": campanias,
        }
    except Exception as e:
        logger.error("get_dashboard_supervisor error: %s", e)
        return {}


def get_dashboard_vendedor(vid: str) -> dict:
    """Datos para el dashboard de un vendedor: mes, año, deuda, posición."""
    try:
        mes_actual = datetime.now(_TZ_ARG).strftime("%Y-%m")
        anio_actual = str(datetime.now(_TZ_ARG).year)

        pedidos = _get_sheet("PEDIDOS").get_all_records()

        total_mes = 0.0
        cant_mes = 0
        total_anio = 0.0
        for p in pedidos:
            if str(p.get("Estado", "")).upper() == "CANCELADO":
                continue
            if str(p.get("ID_Vendedor", "")) != vid:
                continue
            fecha = str(p.get("Fecha", ""))
            total = _safe_float(p.get("Total", 0))
            if fecha.startswith(mes_actual):
                total_mes += total
                cant_mes += 1
            if fecha.startswith(anio_actual):
                total_anio += total

        vendedor_dict = get_vendedor_by_id(vid) or {}
        balance = get_balance_vendedor(vendedor_dict)

        ranking_total = _calcular_ranking_total(mes_actual, pedidos)
        posicion = next((r for r in ranking_total if r["ID_Vendedor"] == vid), None)

        return {
            "total_mes": round(total_mes, 2),
            "cant_mes": cant_mes,
            "total_anio": round(total_anio, 2),
            "deuda_real": balance.get("deuda_real", 0),
            "disponible": balance.get("disponible", 0),
            "pagos_pendientes_monto": balance.get("pagos_pendientes", 0),
            "ranking": posicion,
        }
    except Exception as e:
        logger.error("get_dashboard_vendedor vid=%r error: %s", vid, e)
        return {}


def calcular_ranking_empresa(empresa: str) -> list[dict]:
    """Ranking mensual filtrando pedidos por prefijo de producto (EPP→CUBO, MC→CRAFT)."""
    try:
        mes_actual = datetime.now(_TZ_ARG).strftime("%Y-%m")
        ws = _get_sheet("PEDIDOS")
        pedidos = ws.get_all_records()

        totales: dict[str, dict] = {}
        for p in pedidos:
            if str(p.get("Estado", "")).upper() == "CANCELADO":
                continue
            if not str(p.get("Fecha", "")).startswith(mes_actual):
                continue
            id_prod = str(p.get("ID_Producto", "")).upper()
            if empresa == "CUBO" and not id_prod.startswith("EPP"):
                continue
            if empresa == "CRAFT" and not id_prod.startswith("MC"):
                continue
            vid = str(p.get("ID_Vendedor", ""))
            nombre = str(p.get("Nombre_Vendedor", ""))
            try:
                total = float(str(p.get("Total", "0")).replace(",", "."))
            except ValueError:
                total = 0.0
            if vid not in totales:
                totales[vid] = {"nombre": nombre, "total": 0.0}
            totales[vid]["total"] += total

        if not totales:
            return []

        cats = ["Oro", "Plata", "Bronce"]
        ranking = sorted(totales.items(), key=lambda x: x[1]["total"], reverse=True)
        return [
            {
                "ID_Vendedor": vid,
                "Nombre": info["nombre"],
                "Total_Mes": round(info["total"], 2),
                "Posición": pos,
                "Categoría": cats[pos - 1] if pos <= 3 else "—",
            }
            for pos, (vid, info) in enumerate(ranking, start=1)
        ]
    except Exception as e:
        logger.error("calcular_ranking_empresa empresa=%r error: %s", empresa, e)
        return []


# ── Candidatos ────────────────────────────────────────────────────────────────

def get_candidatas_pendientes() -> list[dict]:
    try:
        ws = _get_sheet("CANDIDATOS")
        result = []
        for i, r in enumerate(ws.get_all_records(), start=2):
            if str(r.get("Estado", "")).upper() in ("PENDIENTE", ""):
                r["_row"] = i
                result.append(r)
        return result
    except Exception as e:
        logger.error("get_candidatas_pendientes error: %s", e)
        return []


def pasar_candidata_a_vendedoras(candidata: dict) -> str:
    try:
        ws = _get_sheet("VENDEDORES")
        nueva_id = f"V{datetime.now(_TZ_ARG).strftime('%Y%m%d%H%M%S')}"
        ws.append_row([
            nueva_id,
            str(candidata.get("Nombre", "")),
            str(candidata.get("Teléfono", "")),
            str(candidata.get("Zona", "")),
            str(candidata.get("Perfil", "")),
            "SI",
            "AMBAS",
        ])
        logger.info("Candidata %s → VENDEDORES id=%s", candidata.get("Nombre"), nueva_id)
        return nueva_id
    except Exception as e:
        logger.error("pasar_candidata_a_vendedoras error: %s", e)
        return "ERROR"


def actualizar_candidata(fila: int, estado: str, notas: str) -> None:
    try:
        ws = _get_sheet("CANDIDATOS")
        headers = ws.row_values(1)
        col_estado = headers.index("Estado") + 1 if "Estado" in headers else None
        col_notas = headers.index("Notas") + 1 if "Notas" in headers else None
        if col_estado:
            ws.update_cell(fila, col_estado, estado)
        if col_notas:
            ws.update_cell(fila, col_notas, str(notas or ""))
        logger.info("Candidata row=%d updated: estado=%s", fila, estado)
    except Exception as e:
        logger.error("actualizar_candidata error: %s", e)


# ── Conocimiento técnico ──────────────────────────────────────────────────────

def get_conocimiento_tecnico() -> list[dict]:
    try:
        return _get_sheet("CONOCIMIENTO_TECNICO").get_all_records()
    except Exception as e:
        logger.error("get_conocimiento_tecnico error: %s", e)
        return []


# ── RAG: hojas de validación ──────────────────────────────────────────────────

_HEADERS_PENDIENTES = [
    "ID", "FECHA", "PREGUNTA", "RESPUESTA_DADA",
    "FUENTE", "ESTADO", "RESPUESTA_CORREGIDA", "VALIDADO_POR",
]
_HEADERS_BASE_CONOCIMIENTO = [
    "ID", "CATEGORIA", "PREGUNTA", "RESPUESTA_VALIDADA",
    "FUENTE_ORIGINAL", "VALIDADO_POR", "FECHA_VALIDACION",
]


def _ensure_sheet(name: str, headers: list[str]) -> gspread.Worksheet:
    if not config.GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID no está configurado.")
    spreadsheet = _get_client().open_by_key(config.GOOGLE_SHEET_ID)
    try:
        return spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=1000, cols=len(headers))
        ws.append_row(headers)
        logger.info("Hoja creada: %s", name)
        return ws


def _similitud(query: str, stored: str) -> float:
    """Fracción de palabras significativas del query presentes en stored."""
    palabras_q = {w for w in query.lower().split() if len(w) > 3}
    if not palabras_q:
        return 0.0
    palabras_s = set(stored.lower().split())
    return len(palabras_q & palabras_s) / len(palabras_q)


def buscar_en_base_conocimiento(pregunta: str) -> dict | None:
    try:
        ws = _ensure_sheet("BASE_CONOCIMIENTO", _HEADERS_BASE_CONOCIMIENTO)
        mejor: dict | None = None
        mejor_sim = 0.0
        for r in ws.get_all_records():
            sim = _similitud(pregunta, str(r.get("PREGUNTA", "")))
            if sim > mejor_sim:
                mejor_sim = sim
                mejor = r
        if mejor and mejor_sim >= 0.70:
            logger.info("BASE_CONOCIMIENTO hit sim=%.2f para %r", mejor_sim, pregunta)
            return mejor
        return None
    except Exception as e:
        logger.error("buscar_en_base_conocimiento error: %s", e)
        return None


def registrar_pendiente_validacion(pregunta: str, respuesta: str, fuente: str) -> str:
    try:
        ws = _ensure_sheet("PENDIENTES_VALIDACION", _HEADERS_PENDIENTES)
        pid = f"PV{datetime.now(_TZ_ARG).strftime('%Y%m%d%H%M%S')}"
        ws.append_row([
            pid,
            datetime.now(_TZ_ARG).strftime("%Y-%m-%d %H:%M:%S"),
            pregunta,
            respuesta,
            fuente,
            "Pendiente",
            "",
            "",
        ])
        logger.info("Pendiente registrado: %s", pid)
        return pid
    except Exception as e:
        logger.error("registrar_pendiente_validacion error: %s", e)
        return "ERROR"


def get_base_conocimiento() -> list[dict]:
    """Devuelve registros de BASE_CONOCIMIENTO excluyendo los de ESTADO=Borrador.

    La hoja tiene 7 headers oficiales pero las fichas técnicas escritas por
    completar_sheet.py usan hasta 12 columnas; la col 12 (índice 11) es ESTADO.
    Los registros Q&A del pipeline de validación no tienen col 12 (ESTADO vacío),
    y se incluyen siempre porque ya pasaron por revisión.
    """
    try:
        ws = _ensure_sheet("BASE_CONOCIMIENTO", _HEADERS_BASE_CONOCIMIENTO)
        rows = ws.get_all_values()
        if not rows:
            return []
        result = []
        for row in rows[1:]:
            if not any(row):
                continue
            estado = row[11].strip() if len(row) > 11 else ""
            if estado == "Borrador":
                continue
            d = {h: (row[i] if i < len(row) else "") for i, h in enumerate(_HEADERS_BASE_CONOCIMIENTO)}
            # Col 9 (índice 8) = NORMATIVA para fichas técnicas (fuera de los 7 headers oficiales)
            d["NORMATIVA"] = row[8].strip() if len(row) > 8 else ""
            result.append(d)
        return result
    except Exception as e:
        logger.error("get_base_conocimiento error: %s", e)
        return []


def registrar_pendiente(pregunta: str, respuesta: str, fuente: str) -> str:
    return registrar_pendiente_validacion(pregunta, respuesta, fuente)


_HEADERS_GAPS = [
    "ID", "FECHA", "PHONE", "PREGUNTA",
    "CATEGORIA_PROBABLE", "ATRIBUTO_SOLICITADO", "CONFIANZA", "ESTADO",
]


def registrar_gap_conocimiento(
    pregunta: str,
    phone: str,
    categoria: str = "",
    atributo: str = "",
    confianza: str = "",
) -> str:
    try:
        ws = _ensure_sheet("GAPS_BASE_CONOCIMIENTO", _HEADERS_GAPS)
        gid = f"GAP{datetime.now(_TZ_ARG).strftime('%Y%m%d%H%M%S')}"
        ws.append_row([
            gid,
            datetime.now(_TZ_ARG).strftime("%Y-%m-%d %H:%M:%S"),
            phone,
            pregunta,
            categoria,
            atributo,
            confianza,
            "Pendiente",
        ])
        logger.info("Gap registrado: %s categoria=%r atributo=%r", gid, categoria, atributo)
        return gid
    except Exception as e:
        logger.error("registrar_gap_conocimiento error: %s", e)
        return "ERROR"


def get_pendientes_del_dia() -> list[dict]:
    try:
        ws = _ensure_sheet("PENDIENTES_VALIDACION", _HEADERS_PENDIENTES)
        hoy = date.today().isoformat()
        return [r for r in ws.get_all_records() if str(r.get("FECHA", "")).startswith(hoy)]
    except Exception as e:
        logger.error("get_pendientes_del_dia error: %s", e)
        return []


def procesar_pendientes_aprobados() -> int:
    """Mueve a BASE_CONOCIMIENTO los pendientes con ESTADO Aprobada o Corregida.

    Devuelve la cantidad de registros procesados.
    """
    try:
        ws_pend = _ensure_sheet("PENDIENTES_VALIDACION", _HEADERS_PENDIENTES)
        ws_base = _ensure_sheet("BASE_CONOCIMIENTO", _HEADERS_BASE_CONOCIMIENTO)

        registros = ws_pend.get_all_records()
        headers = ws_pend.row_values(1)
        col_estado = headers.index("ESTADO") + 1 if "ESTADO" in headers else None
        if col_estado is None:
            logger.error("procesar_pendientes_aprobados: columna ESTADO no encontrada")
            return 0

        procesados = 0
        for i, r in enumerate(registros, start=2):
            estado = str(r.get("ESTADO", "")).strip()
            if estado not in ("Aprobada", "Corregida"):
                continue

            pregunta = str(r.get("PREGUNTA", ""))
            respuesta = (
                str(r.get("RESPUESTA_CORREGIDA", "")) if estado == "Corregida"
                else str(r.get("RESPUESTA_DADA", ""))
            )
            fuente = str(r.get("FUENTE", ""))
            validado_por = str(r.get("VALIDADO_POR", ""))

            nueva_id = f"BC{datetime.now(_TZ_ARG).strftime('%Y%m%d%H%M%S')}{procesados}"
            ws_base.append_row([
                nueva_id,
                "",
                pregunta,
                respuesta,
                fuente,
                validado_por,
                datetime.now(_TZ_ARG).strftime("%Y-%m-%d %H:%M:%S"),
            ])
            ws_pend.update_cell(i, col_estado, "Procesada")
            procesados += 1
            logger.info("Pendiente %s → BASE_CONOCIMIENTO %s", r.get("ID", "?"), nueva_id)

        return procesados
    except Exception as e:
        logger.error("procesar_pendientes_aprobados error: %s", e)
        return 0


def aprobar_pendiente(id_pendiente: str, respuesta_corregida: str, validador: str) -> bool:
    try:
        ws_pend = _ensure_sheet("PENDIENTES_VALIDACION", _HEADERS_PENDIENTES)
        registros = ws_pend.get_all_records()
        fila_idx: int | None = None
        registro: dict | None = None
        for i, r in enumerate(registros, start=2):
            if str(r.get("ID", "")) == id_pendiente:
                fila_idx = i
                registro = r
                break
        if fila_idx is None or registro is None:
            logger.warning("aprobar_pendiente: ID %s no encontrado", id_pendiente)
            return False

        ws_base = _ensure_sheet("BASE_CONOCIMIENTO", _HEADERS_BASE_CONOCIMIENTO)
        nueva_id = f"BC{datetime.now(_TZ_ARG).strftime('%Y%m%d%H%M%S')}"
        ws_base.append_row([
            nueva_id,
            "",
            str(registro.get("PREGUNTA", "")),
            respuesta_corregida or str(registro.get("RESPUESTA_DADA", "")),
            str(registro.get("FUENTE", "")),
            validador,
            datetime.now(_TZ_ARG).strftime("%Y-%m-%d %H:%M:%S"),
        ])

        headers = ws_pend.row_values(1)
        updates = {
            "ESTADO": "Aprobado",
            "RESPUESTA_CORREGIDA": respuesta_corregida,
            "VALIDADO_POR": validador,
        }
        for col_name, value in updates.items():
            if col_name in headers and value:
                ws_pend.update_cell(fila_idx, headers.index(col_name) + 1, value)

        logger.info("Pendiente %s aprobado → BASE_CONOCIMIENTO %s", id_pendiente, nueva_id)
        return True
    except Exception as e:
        logger.error("aprobar_pendiente error: %s", e)
        return False
