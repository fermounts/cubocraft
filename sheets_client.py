import json
import logging
import os
from datetime import date, datetime

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

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


# ── Productos ─────────────────────────────────────────────────────────────────

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
        pid = f"P{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ws.append_row([
            pid,
            str(vendedor.get("ID", "")),
            str(vendedor.get("Nombre", "")),
            str(producto.get("ID", "")),
            str(producto.get("Nombre", "")),
            str(cantidad),
            str(precio),
            str(descuento_pct),
            str(subtotal),
            str(id_campana or ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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

def get_saldo(vendedor: dict) -> float:
    try:
        ws = _get_sheet("PAGOS")
        vid = str(vendedor.get("ID", ""))
        total = sum(
            float(r.get("Monto", 0))
            for r in ws.get_all_records()
            if str(r.get("ID_Vendedor", "")) == vid
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
        saldo_anterior = get_saldo(vendedor)
        nuevo_saldo = round(saldo_anterior + float(monto), 2)
        pid = f"PAG{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ws.append_row([
            pid,
            str(vendedor.get("ID", "")),
            str(vendedor.get("Nombre", "")),
            str(monto),
            metodo,
            str(comprobante or ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "CONFIRMADO",
        ])
        logger.info("Pago registrado: %s", pid)
        return pid, saldo_anterior, nuevo_saldo
    except Exception as e:
        logger.error("registrar_pago error: %s", e)
        return "ERROR", 0.0, 0.0


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

def get_ranking_vendedora(vendedor: dict) -> dict | None:
    try:
        ws = _get_sheet("RANKING")
        vid = str(vendedor.get("ID", ""))
        for r in ws.get_all_records():
            if str(r.get("ID_Vendedor", "")) == vid:
                return r
        return None
    except Exception as e:
        logger.error("get_ranking_vendedora error: %s", e)
        return None


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
        nueva_id = f"V{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ws.append_row([
            nueva_id,
            str(candidata.get("Nombre", "")),
            str(candidata.get("Teléfono", "")),
            str(candidata.get("Zona", "")),
            str(candidata.get("Perfil", "")),
            "SI",
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
