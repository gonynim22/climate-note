"""Screen preferences without relying on the order of QGuiApplication.screens()."""

import json


def describe_screen(screen) -> dict:
    """Capture values while QScreen is alive; never dereference a removed screen."""
    identity = {}
    for key, method in (("name", "name"), ("serial", "serialNumber"),
                        ("manufacturer", "manufacturer"), ("model", "model")):
        getter = getattr(screen, method, None)
        identity[key] = getter().strip() if getter else ""
    geometry = screen.availableGeometry()
    return {"version": 1, **identity, "origin": [geometry.x(), geometry.y()]}


def decode_screen(value: str) -> dict | None:
    """Invalid/unknown imported preferences fall back to the legacy index."""
    try:
        record = json.loads(value)
    except (TypeError, ValueError):
        return None
    if (not isinstance(record, dict) or type(record.get("version")) is not int
            or record["version"] != 1):
        return None
    if not all(isinstance(record.get(key), str)
               for key in ("name", "serial", "manufacturer", "model")):
        return None
    origin = record.get("origin")
    if not isinstance(origin, list) or len(origin) != 2 or any(
            type(value) is not int or abs(value) > 2**31 - 1 for value in origin):
        return None
    return record


def match_screen(record: dict | None, screens):
    """Return only a unique match; missing or ambiguous devices are not adopted."""
    if record is None:
        return None
    candidates = [(screen, describe_screen(screen)) for screen in screens]
    if record["serial"]:
        candidates = [(screen, info) for screen, info in candidates
                      if info["serial"] == record["serial"] and all(
                          not record[key] or info[key] == record[key]
                          for key in ("manufacturer", "model"))]
        if len(candidates) == 1:
            return candidates[0][0]
    # Connector/name is only a fallback together with the available device
    # metadata. A non-matching serial must never fall back to the same name.
    if not record["name"]:
        return None
    candidates = [screen for screen, info in candidates
                  if info["name"] == record["name"] and all(
                      not record[key] or info[key] == record[key]
                      for key in ("manufacturer", "model"))]
    return candidates[0] if len(candidates) == 1 else None


def encode_screen(screen) -> str:
    return json.dumps(describe_screen(screen), ensure_ascii=False)
