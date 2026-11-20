"""Read-only Google One offer discovery. Run --help or --discover --dry-run."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from itertools import product
import json
from pathlib import Path
import re
import threading
import time

import ultra0


KNOWN_PRODUCTS = (
    "g1.2tb.ai.subs_variant", "g1.2tb.subs_variant", "g1.play.2tb.ai",
    "g1.play.20tb", "g1.play.ai.pro", "g1.ai.pro", "g1.30tb",
    "g1.30gb", "g1.30gb.lite", "g1.100gb", "g1.100gb.annual",
    "g1.100gb.subs_variant", "g1.200gb", "g1.200gb.annual",
    "g1.200gb.subs_variant", "g1.2tb", "g1.2tb.ai", "g1.2tb.annual",
    "g1.2tb.ai.annual", "g1.5tb", "g1.10tb", "g1.20tb",
    "g1.play.30gb", "g1.play.100gb", "g1.play.200gb", "g1.play.2tb",
    "g1.play.2tb.subs_variant", "g1.play.2tb.ai.subs_variant",
    "g1.play.5tb", "g1.play.10tb", "g1.play.30tb", "g1.ai.ultra",
    "g1.play.ai.ultra", "g1.ai.plus", "g1.play.ai.plus",
    "g1.youtube_premium_individual_add_on",
)
PREFIXES = (
    "g1", "g1.play", "g1.web", "g1.ios", "g1.promo", "g1.trial",
    "g1.offer", "g1.student", "g1.edu", "g1.family", "g1.partner",
    "g1.carrier", "g1.lite", "g1.basic", "g1.standard",
)
CAPACITIES = (
    "", "15gb", "30gb", "50gb", "100gb", "200gb", "250gb", "400gb",
    "500gb", "1tb", "2tb", "3tb", "4tb", "5tb", "10tb", "20tb",
    "30tb", "50tb", "100tb",
)
SUFFIXES = (
    "", ".ai", ".pro", ".subs_variant", ".ai.subs_variant", ".annual",
    ".gemini", ".ultra", ".plus", ".ai.pro", ".ai.annual", ".ai.ultra",
    ".ai.plus", ".pro.subs_variant", ".ultra.subs_variant", ".monthly",
    ".ai.monthly", ".yearly", ".ai.yearly", ".premium",
    ".lite", ".basic", ".standard", ".max", ".advanced", ".student", ".edu",
    ".family", ".individual", ".ai.lite", ".ai.basic", ".ai.standard",
    ".ai.premium", ".ai.max", ".ai.student", ".ai.family", ".gemini.pro",
    ".gemini.ultra", ".gemini.plus", ".gemini.advanced",
    ".lite.subs_variant", ".basic.subs_variant", ".standard.subs_variant",
    ".plus.subs_variant", ".premium.subs_variant", ".annual.subs_variant",
    ".monthly.subs_variant", ".ai.pro.subs_variant", ".ai.ultra.subs_variant",
    ".ai.plus.subs_variant", ".quarterly", ".semiannual", ".weekly",
    ".prepaid", ".trial", ".free_trial", ".promo", ".promotional", ".offer",
    ".intro", ".eft", ".bundle", ".base", ".add_on", ".addon",
    ".youtube_premium", ".youtube_premium_individual_add_on", ".fitbit",
    ".fitbit_premium", ".nest_aware",
)
LOOSE_PRODUCTS = tuple(f"{prefix}.{name}" for prefix in PREFIXES
                       for name in ("ai", "pro", "gemini", "ultra", "plus",
                                    "ai.pro", "ai.ultra", "ai.plus", "ai.lite", "2tb.ai", "5tb.ai"))

KNOWN_OFFERS = (
    # Dạng chung (Generic EFT / Trial / Intro)
    "eft-1mo", "eft-2mo", "eft-3mo", "eft-6mo", "eft-9mo", "eft-12mo", "eft-1yr",
    "eft-1m", "eft-3m", "eft-6m", "eft-12m",
    "eft-14d", "eft-30d", "eft-90d",
    "1mo-eft", "3mo-eft", "6mo-eft", "12mo-eft",
    "1month-eft", "3months-eft", "6months-eft", "12months-eft", "1year-eft",
    "free-trial", "free-trial-1mo", "free-trial-3mo", "free-trial-1m",
    "intro-1mo", "intro-3mo", "intro-6mo",
    "promo-1mo", "promo-3mo", "promo-6mo", "promo-12mo",
    "50off-3mo", "50off-6mo", "75off-3mo", "discount-3mo", "discount-6mo",
    # Samsung
    "6months-eft-ss-2026", "3months-eft-ss-2026", "12months-eft-ss-2026",
    "6months-eft-ss-2025", "6months-eft-samsung-2026", "6months-eft-galaxy-2026",
    "eft-6mo-ss", "eft-6mo-ss-2026", "eft-3mo-ss",
    # Pixel
    "12months-eft-pixel-2026", "1year-eft-pixel-2026", "6months-eft-pixel-2026",
    "12months-eft-pixel-2025", "12months-eft-pixel-pro-2026",
    "eft-12mo-pixel", "eft-6mo-pixel",
    # Xiaomi / OnePlus / OEM khác
    "6months-eft-xiaomi-2026", "3months-eft-xiaomi-2026",
    "6months-eft-op-2026", "3months-eft-op-2026",
    "6months-eft-oneplus-2026", "3months-eft-oneplus-2026",
    "3months-eft-oppo-2026", "6months-eft-oppo-2026",
    "3months-eft-moto-2026", "6months-eft-moto-2026",
    "3months-eft-honor-2026", "6months-eft-honor-2026",
    "3months-eft-vivo-2026", "3months-eft-nothing-2026",
    # Chromebook / Student / Ecosystem
    "12months-eft-chromebook-2026", "12months-eft-cbplus-2026", "1year-eft-cbplus-2026",
    "12months-eft-student-2026", "1year-eft-student-2026", "student-eft-12mo",
    "student-discount", "edu-eft-12mo", "winback-3mo", "winback-50off",
)

OFFER_DURATIONS_LONG = (
    "1month", "2months", "3months", "4months", "6months", "9months", "12months", "1year",
)
OFFER_DURATIONS_SHORT = (
    "14d", "30d", "60d", "90d",
    "1m", "2m", "3m", "6m", "12m", "1y",
    "1mo", "2mo", "3mo", "4mo", "6mo", "9mo", "12mo", "1yr",
)
OFFER_DURATIONS = OFFER_DURATIONS_LONG + OFFER_DURATIONS_SHORT

PARTNER_OFFER_TYPES = ("eft", "trial", "promo", "intro", "offer")
OFFER_TYPES = PARTNER_OFFER_TYPES + (
    "free-trial", "free", "intro-price", "discount", "50off", "75off", "half-off",
    "winback", "churn", "upsell", "upgrade", "retention",
)

OFFER_PARTNERS = (
    # Samsung
    "ss", "samsung", "galaxy", "s25", "s26", "fold7", "fold8", "flip7", "flip8",
    # Pixel / Google
    "pixel", "pxl", "pixel-pro", "pixel9", "pixel10", "pixel11", "google", "fi", "googlefi",
    # Xiaomi
    "xiaomi", "xm", "mi", "redmi", "poco",
    # OnePlus & BBK
    "op", "oneplus", "oppo", "vivo", "realme", "iqoo",
    # OEM khác
    "moto", "motorola", "honor", "nothing", "sony", "asus", "lenovo", "tcl", "tecno", "infinix", "hmd", "nokia",
    # Chromebook / PC
    "chromebook", "cb", "cbplus", "chromebook-plus", "acer", "hp", "dell",
    # Nhà mạng (Carriers)
    "tmo", "tmobile", "vzw", "verizon", "att", "vodafone", "ee", "o2",
    "kddi", "docomo", "softbank", "telstra", "optus", "jio", "airtel", "rogers", "bell",
    # Nhóm tài khoản / Dịch vụ kèm theo
    "student", "edu", "campus", "ytp", "playpass", "newuser", "family", "workspace",
    "winback", "churn", "upsell", "upgrade", "retention",
)

OFFER_YEARS = ("2024", "2025", "2026", "2027")
OFFER_CAMPAIGN_PERIODS = tuple(
    f"{period}-{year}" for year, period in product(OFFER_YEARS, ("q1", "q2", "q3", "q4", "h1", "h2"))
)

OFFER_SUFFIXES = (
    "-ai", "-pro", "-ultra", "-plus", "-lite",
    "-100gb", "-200gb", "-2tb", "-5tb",
    "-monthly", "-annual", "-v1", "-v2", "-v3",
)

BASE_PLANS = (
    "monthly", "annual", "yearly", "p1m", "p1y", "p3m", "p6m",
    "1m", "1y", "1mo", "1yr", "1month", "1year",
    "base", "default", "standard", "prepaid",
    "g1-monthly", "g1-annual", "monthly-plan", "annual-plan",
)

OFFER_CORE_DURATIONS = ("1mo", "3mo", "6mo", "12mo", "1yr", "1month", "3months", "6months", "12months", "1year")
OFFER_CAMPAIGN_DURATIONS = ("1month", "3months", "6months", "12months")
OFFER_CAMPAIGN_TYPES = ("eft", "trial", "free-trial", "intro", "intro-price", "promo", "discount", "50off", "75off")


def _partner_offer_patterns(partner, offer_type, duration):
    return (
        f"{duration}-{offer_type}-{partner}", f"{offer_type}-{duration}-{partner}",
        f"{partner}-{duration}-{offer_type}", f"{partner}-{offer_type}-{duration}",
    )


def build_offer_candidates(include_underscores: bool = False, *, tier: int = 1) -> list[str]:
    """Sinh Offer ID ứng viên ngoại tuyến, ưu tiên các mẫu được khai báo sẵn."""
    if tier not in (1, 2):
        raise ValueError("Tầng Offer ID phải là 1 hoặc 2")

    candidates = list(KNOWN_OFFERS)
    generic = [
        pattern
        for offer_type, duration in product(OFFER_TYPES, OFFER_DURATIONS)
        for pattern in (f"{offer_type}-{duration}", f"{duration}-{offer_type}")
    ]
    candidates.extend(generic)
    candidates.extend(f"{pattern}-{year}" for pattern, year in product(generic, OFFER_YEARS))
    for partner, duration in product(OFFER_PARTNERS, OFFER_CORE_DURATIONS):
        candidates.extend(_partner_offer_patterns(partner, "eft", duration))
        candidates.extend(f"{duration}-eft-{partner}-{year}" for year in OFFER_YEARS)

    if tier == 2:
        # Mở rộng thứ tự và thời lượng. Chỉ ghép hậu tố và kỳ chiến dịch với các mẫu phổ biến.
        campaign_suffixes = (
            OFFER_SUFFIXES
            + tuple(f"-{period}" for period in OFFER_CAMPAIGN_PERIODS)
            + tuple(f"-{year}{suffix}" for year, suffix in product(OFFER_YEARS, ("-ai", "-pro", "-2tb")))
        )
        for partner, offer_type, duration in product(OFFER_PARTNERS, PARTNER_OFFER_TYPES, OFFER_DURATIONS):
            candidates.extend(_partner_offer_patterns(partner, offer_type, duration))
        for offer_type, duration in product(OFFER_CAMPAIGN_TYPES, OFFER_CORE_DURATIONS):
            for pattern in (f"{offer_type}-{duration}", f"{duration}-{offer_type}"):
                candidates.extend(f"{pattern}{suffix}" for suffix in campaign_suffixes)
        for partner, duration in product(OFFER_PARTNERS, OFFER_CORE_DURATIONS):
            patterns = _partner_offer_patterns(partner, "eft", duration)
            candidates.extend(f"{pattern}-{year}" for pattern, year in product(patterns, OFFER_YEARS))
        for partner, duration in product(OFFER_PARTNERS, OFFER_CAMPAIGN_DURATIONS):
            pattern = f"{duration}-eft-{partner}"
            candidates.extend(f"{pattern}{suffix}" for suffix in campaign_suffixes)
            candidates.extend(f"{duration}-{offer_type}-{partner}-{year}" for offer_type, year
                              in product(PARTNER_OFFER_TYPES, OFFER_YEARS))

    unique = dict.fromkeys(candidates)
    if include_underscores:
        unique.update(dict.fromkeys(candidate.replace("-", "_") for candidate in unique))
    return list(unique)


# Bí danh tương thích
build_candidate_offers = build_offer_candidates


def build_candidates(skus=(), discover=False, sku_file=None):
    """Candidate names are guesses, not a store catalogue."""
    values = list(skus)
    if sku_file:
        values.extend(line.split("#", 1)[0].strip()
                      for line in Path(sku_file).read_text(encoding="utf-8-sig").splitlines())
    if discover:
        values.extend(KNOWN_PRODUCTS)
        values.extend(f"{prefix}{'.' + capacity if capacity else ''}{suffix}" for prefix in PREFIXES
                      for capacity in CAPACITIES for suffix in SUFFIXES)
        values.extend(LOOSE_PRODUCTS)
    if not values or not any(str(v).strip() for v in values):
        values = list(KNOWN_PRODUCTS)
    result = []
    seen = set()
    for value in values:
        sku = str(value).strip()
        if not sku:
            continue
        if (len(sku) > 200 or not re.fullmatch(r"[a-z0-9][a-z0-9._]*", sku)
                or ".." in sku or sku.endswith(".")):
            raise ValueError(f"SKU không hợp lệ: {sku!r}")
        if sku not in seen:
            seen.add(sku)
            result.append(sku)
    return result


def generate_candidates():
    return build_candidates(discover=True)


def format_period(period, cycles=1):
    period = str(period or "")
    match = re.fullmatch(r"P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?", period)
    if not match or not any(match.groups()):
        return period or "chưa rõ kỳ hạn"
    try:
        count = max(1, int(cycles))
    except (TypeError, ValueError):
        count = 1
    return " ".join(f"{int(number) * count} {unit}"
                    for number, unit in zip(match.groups(), ("năm", "tháng", "tuần", "ngày"))
                    if number and int(number))


def _is_zero(phase):
    try:
        return Decimal(str(phase.get("micros"))) == 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _price(phase):
    if phase.get("formatted_price"):
        return str(phase["formatted_price"])
    try:
        amount = Decimal(str(phase["micros"])) / Decimal(1_000_000)
        return f"{amount:f} {phase.get('currency') or '?'}"
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return "chưa rõ giá"


def offer_row(offer):
    phases = offer.get("phases") or [{
        "micros": offer.get("micros"), "period": offer.get("period"),
        "formatted_price": offer.get("formatted_price"), "currency": offer.get("currency"),
    }]
    free = _is_zero(phases[0])
    free_phases = []
    if free:
        for phase in phases:
            if not _is_zero(phase):
                break
            free_phases.append(phase)
    trial = "Không có"
    if free_phases:
        trial = " + ".join("miễn phí định kỳ" if p.get("recurrence_mode") == 1
                           else format_period(p.get("period"), p.get("cycles", 1))
                           for p in free_phases)
        trial = f"{_price(phases[0])} · {trial}"
    later = phases[len(free_phases):] if free else phases
    prices = []
    for phase in later:
        price = f"{_price(phase)} / {format_period(phase.get('period'))}"
        if phase.get("recurrence_mode") == 2 and phase.get("cycles"):
            price += f" trong {format_period(phase.get('period'), phase['cycles'])}"
        elif phase.get("recurrence_mode") == 3:
            price += " (một lần)"
        prices.append(price)
    after = " → ".join(prices)
    return {
        "product": offer.get("product", ""), "offer_id": offer.get("id") or "(gói cơ bản)",
        "base_plan": offer.get("base_plan") or "",
        "title": offer.get("title") or offer.get("name") or "",
        "free": free, "trial": trial, "after": after or "API chưa trả giá sau ưu đãi",
    }


class OfferScanner:
    """One Billing connection; a batch ends only after query_complete."""
    def __init__(self, session, timeout=30):
        self.session = session
        self.timeout = timeout
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.pending = {}
        self.fatal = None
        source = Path(__file__).with_name("offer_scan.js").read_text(encoding="utf-8")
        self.script = session.create_script(source)
        self.script.on("message", self._on_message)

    def _fail(self, message):
        with self.lock:
            self.fatal = str(message)
            self.ready.set()
            for request in self.pending.values():
                request["errors"].append(self.fatal)
                request["done"].set()

    def _on_message(self, message, data):
        if message.get("type") == "error":
            self._fail(message.get("description", "Lỗi JavaScript Frida"))
            return
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        event = payload.get("ev")
        if event == "ready":
            self.ready.set()
            return
        if event in ("scan_error", "disconnected"):
            self._fail(payload.get("m") or f"{event}: {payload.get('code', '')}")
            return
        with self.lock:
            request = self.pending.get(payload.get("batch"))
            if request is None or request["done"].is_set():
                return
            if event == "offer":
                request["offers"].append(payload)
            elif event == "product":
                request["products"].append(payload.get("product"))
            elif event == "query_error":
                request["errors"].append(payload.get("m") or "Lỗi đọc ProductDetails")
            elif event == "query_complete":
                request["completion"] = payload
                request["done"].set()

    def start(self):
        self.script.load()
        if not self.ready.wait(self.timeout):
            raise RuntimeError("Hết thời gian chờ kết nối Billing")
        if self.fatal:
            raise RuntimeError(self.fatal)

    def query(self, products, batch_id):
        if not products or len(products) > 20:
            raise ValueError("Mỗi lô cần từ 1 đến 20 SKU")
        request = {"done": threading.Event(), "offers": [], "products": [],
                   "errors": [], "completion": None}
        with self.lock:
            if self.fatal:
                raise RuntimeError(self.fatal)
            if batch_id in self.pending:
                raise ValueError("batch_id đang được sử dụng")
            self.pending[batch_id] = request
        timed_out = False
        try:
            try:
                self.script.exports_sync.query(batch_id, list(products))
            except Exception as e:
                request["errors"].append(str(e))
                request["done"].set()
            if not request["done"].wait(self.timeout):
                timed_out = True
                request["errors"].append("Hết thời gian chờ ProductDetails")
        finally:
            with self.lock:
                self.pending.pop(batch_id, None)
        completion = request["completion"] or {}
        code = completion.get("code")
        status = "timeout" if timed_out else "ok" if code == 0 and not request["errors"] else "error"
        returned = list(dict.fromkeys(request["products"] + completion.get("products", [])))
        if code not in (None, 0):
            request["errors"].append(f"Billing code {code}: {completion.get('msg', '')}")
        return {"batch": batch_id, "requested": list(products), "status": status, "code": code,
                "products": returned, "offers": request["offers"], "errors": request["errors"],
                "not_returned": [p for p in products if p not in returned] if status == "ok" else []}

    def close(self):
        try:
            self.script.exports_sync.dispose()
        except Exception:
            pass
        finally:
            self.script.unload()


def _without_tokens(value):
    if isinstance(value, dict):
        return {k: _without_tokens(v) for k, v in value.items()
                if k not in ("token", "offerToken", "purchaseToken", "old_token")}
    if isinstance(value, list):
        return [_without_tokens(v) for v in value]
    return value


def _table(offers, show_all=False):
    rows = [offer_row(o) for o in offers]
    rows = [r for r in rows if show_all or r["free"]]
    lines = ["| Sản phẩm | Base Plan ID | Offer ID | Thử miễn phí | Sau đó |",
             "| --- | --- | --- | --- | --- |"]
    for row in rows:
        cells = [str(row[k]).replace("|", "\\|").replace("\n", " ")
                 for k in ("product", "base_plan", "offer_id", "trial", "after")]
        lines.append("| " + " | ".join(cells) + " |")
    if not rows:
        lines.append("| Chưa có offer phù hợp được trả về | | | | |")
    return "\n".join(lines)


def write_reports(report, output_prefix, include_tokens=False):
    prefix = Path(output_prefix)
    if prefix.suffix.lower() in (".json", ".md"):
        prefix = prefix.with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path, md_path = Path(str(prefix) + ".json"), Path(str(prefix) + ".md")
    public = report if include_tokens else _without_tokens(report)
    json_path.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
    md = (f"# Kết quả tra offer Google One\n\nThời điểm: {report.get('at', '')}\n\n"
          f"Tài khoản Play: {report.get('play_account') or 'không xác định từ giao diện'}\n\n"
          f"Trạng thái: {report.get('status')} · {len(report.get('candidates', []))} SKU ứng viên · "
          f"{len(report.get('products', []))} sản phẩm trả về.\n\n"
          + _table(report.get("offers", []), report.get("show_all", False)))
    if report.get("errors"):
        md += "\n\nLỗi truy vấn:\n\n" + "\n".join(f"- {e}" for e in report["errors"])
    md += ("\n\nSKU không được trả về có thể không tồn tại hoặc không khả dụng trong tài khoản/khu vực này. "
           "Offer xuất hiện trong API chưa bảo đảm tài khoản đủ điều kiện đăng ký.\n")
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def prepare_device(serial=None, account=None, on_stage=None):
    def stage(name):
        if on_stage:
            on_stage(name)

    stage("dependencies")
    import frida
    import setup_env
    ultra0.ADB_CANDIDATES += setup_env.ADB_CANDIDATES + [str(Path(__file__).parent / "platform-tools" / "adb.exe")]
    stage("adb_discovery")
    ultra0.ADB = ultra0.find_adb()
    stage("device_selection")
    if serial:
        ultra0.SERIAL = serial
        ultra0.sh("get-state", check=True)
    else:
        ultra0.pick_device()
    stage("root")
    ultra0.ensure_root()
    stage("frida_server")
    ultra0.ensure_frida_server()
    stage("billing_module")
    ultra0.ensure_module_apk()
    stage("play_process")
    ultra0.ensure_vending()
    stage("play_account_read")
    current = ultra0.current_play_account(open_store=True)
    if account and account != "current@device" and current != account.strip().casefold():
        stage("play_account_mismatch" if current else "play_account_unverified")
        raise RuntimeError(f"Tài khoản Play đọc được là {current or 'không rõ'}, cần {account}")
    if not current:
        ultra0.warn("Chưa đọc được email Play; báo cáo sẽ không gắn với email cụ thể")
    stage("app_start")
    pid = ultra0.launch_app()
    if not pid:
        raise RuntimeError("Không khởi động được Google One")
    stage("frida_attach")
    session = frida.get_device(ultra0.SERIAL, timeout=10).attach(pid)
    stage("prepared")
    return session, current


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tra offer Google One theo SKU, chỉ đọc dữ liệu Billing")
    parser.add_argument("skus", nargs="*", help="SKU chỉ định, có thể kết hợp --discover")
    parser.add_argument("--discover", action="store_true",
                        help=f"Quét tổ hợp {len(PREFIXES)} tiền tố × {len(CAPACITIES)} dung lượng "
                             f"(có lựa chọn rỗng) × {len(SUFFIXES)} đuôi + SKU ưu tiên")
    parser.add_argument("--sku-file", type=Path, help="File SKU, mỗi dòng một mã; hỗ trợ chú thích #")
    parser.add_argument("--serial", help="ADB serial của giả lập/điện thoại")
    parser.add_argument("--account", help="Email Play cần xác minh trước khi tra; không tự chuyển tài khoản")
    parser.add_argument("--batch-size", type=int, default=10, help="Số SKU mỗi lô, từ 1 đến 20 (mặc định 10)")
    parser.add_argument("--delay", type=float, default=0.75, help="Giãn cách giữa hai lô, giây (mặc định 0.75)")
    parser.add_argument("--timeout", type=float, default=30, help="Thời gian chờ mỗi lô/kết nối Billing, giây")
    parser.add_argument("--all-offers", action="store_true", help="Hiện cả offer trả phí trong bảng; JSON luôn chứa tất cả")
    parser.add_argument("--include-tokens", action="store_true", help="Lưu thêm offerToken vào JSON")
    parser.add_argument("--output", type=Path, help="Tên gốc cho hai báo cáo .json và .md")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in danh sách SKU ứng viên, không kết nối thiết bị")
    candidate_modes = parser.add_mutually_exclusive_group()
    candidate_modes.add_argument("--candidate-offers", action="store_true",
                                 help="In danh sách Offer ID ứng viên ngoại tuyến")
    candidate_modes.add_argument("--candidate-base-plans", action="store_true",
                                 help="In danh sách Base Plan ID ứng viên ngoại tuyến")
    parser.add_argument("--offer-tier", type=int, choices=(1, 2),
                        help="Tầng Offer ID ứng viên (mặc định 1; tầng 2 gồm cả tầng 1)")
    parser.add_argument("--include-underscores", action="store_true",
                        help="Thêm phiên bản dấu gạch dưới cho Offer ID ứng viên")
    args = parser.parse_args(argv)
    if not args.candidate_offers and (args.offer_tier is not None or args.include_underscores):
        parser.error("--offer-tier và --include-underscores dùng cùng --candidate-offers")
    if args.candidate_offers:
        tier = args.offer_tier or 1
        offers = build_candidate_offers(args.include_underscores, tier=tier)
        print(f"Tổng cộng {len(offers)} Offer ID ứng viên · tầng {tier}")
        print("\n".join(offers))
        return 0
    if args.candidate_base_plans:
        print(f"Tổng cộng {len(BASE_PLANS)} Base Plan ID ứng viên")
        print("\n".join(BASE_PLANS))
        return 0
    if not 1 <= args.batch_size <= 20 or args.delay < 0 or args.timeout <= 0:
        parser.error("Cần batch-size 1..20, delay >= 0, timeout > 0")
    try:
        candidates = build_candidates(args.skus, args.discover, args.sku_file)
    except (OSError, ValueError) as e:
        parser.error(str(e))
    print(f"Tổng cộng {len(candidates)} SKU ứng viên (chưa xác nhận tồn tại)", flush=True)
    if args.dry_run:
        print("\n".join(candidates))
        return 0
    now = datetime.now(timezone(timedelta(hours=7)))
    report = {"at": now.isoformat(), "serial": args.serial, "play_account": None,
              "status": "running", "candidates": candidates, "products": [], "offers": [],
              "batches": [], "errors": [], "show_all": args.all_offers}
    session = scanner = None
    try:
        session, report["play_account"] = prepare_device(args.serial, args.account)
        report["serial"] = ultra0.SERIAL
        scanner = OfferScanner(session, args.timeout)
        scanner.start()
        chunks = [candidates[i:i + args.batch_size] for i in range(0, len(candidates), args.batch_size)]
        for index, batch in enumerate(chunks, 1):
            result = scanner.query(batch, index)
            report["batches"].append({k: v for k, v in result.items() if k != "offers"})
            report["offers"].extend(result["offers"])
            report["products"].extend(p for p in result["products"] if p not in report["products"])
            report["errors"].extend(f"Lô {index}: {e}" for e in result["errors"])
            print(f"[{index}/{len(chunks)}] {result['status']} · "
                  f"{len(result['products'])} sản phẩm · {len(result['offers'])} offer", flush=True)
            if index < len(chunks):
                time.sleep(args.delay)
        report["status"] = "partial" if report["errors"] else "complete"
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        report["errors"].append("Người dùng dừng quét; báo cáo giữ kết quả đã nhận")
    except Exception as e:
        report["status"] = "partial" if report["batches"] else "error"
        report["errors"].append(str(e))
    finally:
        if scanner:
            try:
                scanner.close()
            except Exception as e:
                report["errors"].append(f"Đóng script: {e}")
        if session:
            try:
                session.detach()
            except Exception as e:
                report["errors"].append(f"Đóng kết nối Frida: {e}")
        if report["status"] == "complete" and report["errors"]:
            report["status"] = "partial"
    print("\n" + _table(report["offers"], args.all_offers))
    output = args.output or Path("ultra0-report") / f"offer-scan-{now:%Y%m%d-%H%M%S}"
    paths = write_reports(report, output, args.include_tokens)
    print(f"\nTrạng thái: {report['status']} · Báo cáo: {paths[0]} và {paths[1]}")
    for error in report["errors"]:
        print(f"  Lỗi: {error}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
