"""Read-only Billing subscription metadata; never returns or uses purchase tokens."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import threading

import query_sku
import ultra0


def sanitize_purchases(payload):
    """Allowlist metadata even if an unexpected runtime sends extra receipt fields."""
    values = payload.get("purchases")
    if not isinstance(values, list):
        raise ValueError("invalid_purchase_list")
    result = []
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("products"), list):
            raise ValueError("invalid_purchase_metadata")
        products = item["products"]
        if any(not isinstance(product, str) or len(product) > 200 or
               not re.fullmatch(r"g1\.[a-z0-9._-]+", product) for product in products):
            raise ValueError("invalid_product_id")
        state = item.get("purchase_state")
        if type(state) is not int or state not in (0, 1, 2):
            raise ValueError("invalid_purchase_state")
        row = {"products": list(dict.fromkeys(products)), "purchase_state": state}
        for field in ("auto_renewing", "acknowledged", "token_present"):
            if type(item.get(field)) is not bool:
                raise ValueError("invalid_purchase_flags")
            row[field] = item[field]
        result.append(row)
    return result


def query_current_subscriptions(session, timeout=30):
    done = threading.Event()
    lock = threading.Lock()
    result = {"status": "running", "purchases": [], "code": None, "error_stage": None}
    script = None

    def finish(status, stage=None, code=None, purchases=None):
        with lock:
            if done.is_set():
                return
            result.update(status=status, error_stage=stage, code=code,
                          purchases=purchases if purchases is not None else [])
            done.set()

    def on_message(message, data):
        if message.get("type") == "error":
            finish("error", "runtime")
            return
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        event = payload.get("ev")
        code = payload.get("code")
        if type(code) is not int:
            code = None
        if event == "purchases_error":
            # Do not forward exception descriptions or arbitrary runtime strings.
            allowed = {"bridge", "application", "bootstrap", "setup", "disconnected",
                       "query", "callback", "serialize", "initialize", "context", "metadata",
                       "response", "purchase_parse", "java_bridge", "initialization", "module", "client"}
            stage = payload.get("stage")
            finish("error", stage if isinstance(stage, str) and stage in allowed else "runtime", code=code)
        elif event == "purchases_complete":
            if code != 0:
                finish("error", "query", code=code)
                return
            try:
                purchases = sanitize_purchases(payload)
            except (TypeError, ValueError):
                finish("error", "metadata", code=code)
                return
            finish("complete", code=0, purchases=purchases)

    try:
        source = Path(__file__).with_name("purchase_scan.js").read_text(encoding="utf-8")
        script = session.create_script(source)
        script.on("message", on_message)
        script.load()
        if not done.wait(timeout):
            finish("timeout", "timeout")
    except Exception:
        finish("error", "runtime")
    finally:
        if script is not None:
            for operation in (lambda: script.exports_sync.dispose(), script.unload):
                try:
                    operation()
                except Exception:
                    pass
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Đọc trạng thái đăng ký hiện tại qua Billing, không mở thanh toán")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--account", required=True, help="Email hiện chọn trong Play; không tự chuyển tài khoản")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--allow-unverified-ui", action="store_true",
                        help="Chẩn đoán Billing hiện tại khi không đọc được email Play; không xác minh chủ token")
    parser.add_argument("--output", type=Path, help="File JSON riêng để lưu metadata không chứa token")
    args = parser.parse_args(argv)
    account = args.account.strip().casefold()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", account) or args.timeout <= 0:
        parser.error("Cần email thật và timeout > 0")
    session = None
    now = datetime.now()
    report = {"at": now.isoformat(timespec="seconds"), "serial": args.serial,
              "requested_play_account": account, "play_account": None,
              "play_ui_account_verified": False,
              "payer_account_verified": False,
              "status": "running", "purchases": [], "code": None, "error_stage": None}
    setup_stage = "device_setup"

    def on_stage(stage):
        nonlocal setup_stage
        setup_stage = stage

    try:
        # The existing scanner helper verifies the selected Play UI account and opens
        # Google One for a query. It never calls subscription-confirmation functions.
        # This optional path is confined to metadata diagnostics, not stack/token lookup.
        required_account = None if args.allow_unverified_ui else account
        session, report["play_account"] = query_sku.prepare_device(args.serial, required_account, on_stage=on_stage)
        if report["play_account"] and report["play_account"] != account:
            setup_stage = "play_account_mismatch"
            raise RuntimeError("Play account mismatch")
        report["play_ui_account_verified"] = report["play_account"] == account
        report.update(query_current_subscriptions(session, args.timeout))
    except KeyboardInterrupt:
        report.update(status="interrupted", error_stage="interrupted")
    except Exception:
        # Frida/Java errors may include object contents: report fixed stage labels only.
        report.update(status="error", error_stage=setup_stage)
    finally:
        if session:
            try:
                session.detach()
            except Exception:
                pass
    path = args.output or ultra0.REPORT_DIR / f"purchase-check-{now:%Y%m%d-%H%M%S}-{ultra0.time.time_ns() % 1000000:06d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ultra0.note(f"Billing: {report['status']}; {len(report['purchases'])} bản ghi đăng ký")
    for purchase in report["purchases"]:
        products = ", ".join(purchase["products"]) or "SKU ngoài Google One"
        renewal = "bật" if purchase["auto_renewing"] else "tắt"
        ultra0.note(f"{products}: state={purchase['purchase_state']}, gia hạn={renewal}, token_present={purchase['token_present']}")
    if report["error_stage"]:
        ultra0.warn(f"Lỗi tại bước {report['error_stage']}; Billing code={report['code']}")
    if not report["play_ui_account_verified"]:
        ultra0.note("Chưa xác minh được email Play; dữ liệu chỉ mô tả ngữ cảnh Billing của ứng dụng hiện tại")
    ultra0.note("Billing không trả email chủ giao dịch; kết quả này chưa xác minh tài khoản sở hữu token")
    ultra0.note(f"Báo cáo: {path.resolve()}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
