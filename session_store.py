import threading
import logging

logger = logging.getLogger(__name__)

_store: dict = {}
_lock = threading.Lock()


def get(phone: str) -> dict:
    with _lock:
        return dict(_store.get(phone, {}))


def set(phone: str, estado: str, **kwargs) -> None:
    with _lock:
        session = dict(_store.get(phone, {}))
        session["estado"] = estado
        session.update(kwargs)
        _store[phone] = session
    logger.debug("Session set | phone=%s estado=%s", phone, estado)


def clear(phone: str) -> None:
    with _lock:
        _store.pop(phone, None)
    logger.debug("Session cleared | phone=%s", phone)


def debug_all() -> dict:
    with _lock:
        return dict(_store)
