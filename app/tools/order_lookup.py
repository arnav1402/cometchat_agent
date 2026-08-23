import json
import re
from functools import lru_cache
from pathlib import Path

from app.config import ORDERS_FILE


@lru_cache(maxsize=1)
def _load_orders_index() -> dict:
    path = Path(ORDERS_FILE)
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    orders = payload.get("orders", [])
    return {str(order.get("order_id", "")).strip().upper(): order for order in orders if order.get("order_id")}


def lookup_order(raw_id):
    if raw_id is None or str(raw_id).strip() == "":
        return {"ok": False, "missing_id": True, "not_found": False, "order": None, "error": "Missing order ID."}

    normalized = str(raw_id).strip().upper()
    index = _load_orders_index()
    order = index.get(normalized)
    if order is None:
        return {"ok": False, "missing_id": False, "not_found": True, "order": None, "error": f"Order not found: {normalized}"}

    item_payload = []
    for item in order.get("items", []):
        item_payload.append({
            "name": item.get("name"),
            "quantity": item.get("quantity"),
            "final_sale": item.get("final_sale"),
        })

    result = {
        "order_id": order.get("order_id"),
        "membership_tier": order.get("membership_tier"),
        "items": item_payload,
        "placed_at": order.get("placed_at"),
        "status": order.get("status"),
        "status_updated_at": order.get("status_updated_at"),
        "shipped_at": order.get("shipped_at"),
        "delivered_at": order.get("delivered_at"),
        "carrier": order.get("carrier"),
        "tracking_number": order.get("tracking_number"),
        "estimated_delivery": order.get("estimated_delivery"),
        "customer_safe_message": order.get("customer_safe_message"),
    }

    if str(order.get("status", "")).lower() in {"cancelled", "returned"}:
        result["estimated_delivery"] = None

    return {"ok": True, "missing_id": False, "not_found": False, "order": result}
