import re
import shutil
import subprocess
import sys
from pathlib import Path


def is_bluestacks_running() -> bool:
    return False


def update_conf(conf_path: Path):
    if not conf_path.exists():
        return False

    bak_path = conf_path.with_suffix(".conf.bak")
    try:
        if not bak_path.exists():
            shutil.copy2(conf_path, bak_path)
            print(f"   [+] Da sao luu file goc: {bak_path}")
    except PermissionError:
        print(f"   [!] Can quyen Administrator de ghi file vao: {conf_path.parent}")
        raise

    try:
        text = conf_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"   [!] Loi doc file: {e}")
        return False
    lines = text.splitlines()

    # Dictionary các key cần đảm bảo giá trị = "1"
    keys_to_enable = {
        'bst.feature.rooting': '"1"',
        'bst.enable_adb_access': '"1"',
        'bst.enable_adb_remote_access': '"1"',
    }

    # Bật root cho tất cả các instance tìm thấy
    instances = set(re.findall(r'bst\.instance\.([A-Za-z0-9_]+)\.', text))
    instances.update({"Baklava64", "Baklava64_u1", "Pie64"})
    run_dir = conf_path.parent / "run"
    if run_dir.exists():
        for j in run_dir.glob("fus-*.json"):
            try:
                vm_name = re.search(r'"vm"\s*:\s*"([^"]+)"', j.read_text(encoding="utf-8"))
                if vm_name:
                    instances.add(vm_name.group(1))
            except Exception:
                pass

    for inst in instances:
        keys_to_enable[f'bst.instance.{inst}.enable_root_access'] = '"1"'

    updated_keys = set()
    new_lines = []
    for line in lines:
        matched = False
        for k, v in keys_to_enable.items():
            if line.startswith(f"{k}="):
                new_lines.append(f"{k}={v}")
                updated_keys.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for k, v in keys_to_enable.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}")

    conf_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"   [OK] Da kich hoat Root va ADB cho: {conf_path}")
    return True


def main():
    non_interactive = "--yes" in sys.argv or "-y" in sys.argv
    print("=" * 60)
    print("   CONG CU BAT ROOT VA ADB CHO BLUESTACKS DESKTOP")
    print("=" * 60)

    if is_bluestacks_running():
        print("\n[CANH BAO] BlueStacks hoac HD-Player dang chay!")
        print("Vui long dong hoan toan BlueStacks o khay he thong roi chay lai script.")
        if not non_interactive:
            input("\nNhan Enter de thoat...")
        return 1

    targets = [
        Path(r"C:\ProgramData\BlueStacks_polar\bluestacks.conf"),
        Path(r"C:\ProgramData\BlueStacks_nxt\bluestacks.conf"),
    ]

    found = False
    for p in targets:
        if p.exists():
            print(f"\nDang xu ly: {p}")
            try:
                if update_conf(p):
                    found = True
            except PermissionError:
                print("\n[LOI QUYEN HAN] Khong the ghi file cau hinh vi thieu quyen Administrator!")
                print("-> Hay nhap chuot phai vao file bat va chon: 'Run as administrator'")
                if not non_interactive:
                    input("\nNhan Enter de thoat...")
                return 1
            except Exception as e:
                print(f"\n[LOI] {e}")

    if not found:
        print("\n[LOI] Khong tim thay file bluestacks.conf tren may.")
        if not non_interactive:
            input("\nNhan Enter de thoat...")
        return 1

    print("\n" + "=" * 60)
    print("   THANH CONG! Root va ADB da duoc bat.")
    print("   Bay gio ban co the mo BlueStacks Desktop va su dung.")
    print("=" * 60)
    if not non_interactive:
        input("\nNhan Enter de hoan tat...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
