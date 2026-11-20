# Hướng dẫn thử nghiệm BlueStacks Desktop (Bản 16 / Polaris) song song MuMu Player

Tài liệu này hướng dẫn cách thiết lập **BlueStacks Desktop** (phiên bản `16.0.2.17` cài tại `C:\Program Files\BlueStacks_polar\`, kiến trúc Android `Baklava64`) để giả lập Samsung Galaxy S26 Ultra mà **tuyệt đối không ảnh hưởng** đến cấu hình MuMu Player hiện tại.

---

## 1. Thông tin BlueStacks Desktop trên máy bạn
* **Tên ứng dụng:** BlueStacks Desktop (Polaris v16)
* **Đường dẫn cài đặt:** `C:\Program Files\BlueStacks_polar\`
* **Đường dẫn dữ liệu & cấu hình:** `C:\ProgramData\BlueStacks_polar\bluestacks.conf`
* **Công cụ ADB đi kèm:** `C:\Program Files\BlueStacks_polar\HD-Adb.exe`
* **Cổng kết nối ADB:** `127.0.0.1:6610`

---

## 2. Kích hoạt ADB và Quyền ROOT trên BlueStacks Desktop

1. **Đóng hoàn toàn BlueStacks Desktop**:
   - Nhấp chuột phải vào biểu tượng BlueStacks ở khay đồng hồ Windows (góc dưới cùng bên phải) -> Chọn **Thoát / Exit**.
2. **Kích hoạt tự động**:
   - Bấm đúp chạy file: **`BS_bat_root_va_adb_tu_dong.bat`**.
   - Script sẽ tự động tạo bản sao lưu `bluestacks.conf.bak` và kích hoạt các quyền `rooting`, `enable_adb_access`, `enable_adb_remote_access`.
3. Mở lại **BlueStacks Desktop**.

---

## 3. Cấu hình Model thiết bị trên BlueStacks Desktop (Samsung S26 Ultra)

1. Mở **BlueStacks Desktop**.
2. Bấm vào biểu tượng **Bánh răng (Cài đặt / Settings)** ở thanh điều hướng bên phải.
3. Chọn thẻ **Điện thoại (Phone)**:
   - Tại mục **Hồ sơ thiết bị (Device profile)**, chọn **Tạo hồ sơ tùy chỉnh (Create a custom profile)**.
   - **Nhà sản xuất (Manufacturer):** `samsung`
   - **Thương hiệu (Brand):** `samsung`
   - **Mẫu máy (Model):** `SM-S948B` (hoặc mã tùy chỉnh cho S26 Ultra / S25 Ultra).
4. Bấm **Lưu thay đổi (Save changes)**.

---

## 4. Đăng nhập Google Play Store

1. Mở ứng dụng **Google Play Store** trên BlueStacks Desktop.
2. Đăng nhập tài khoản Google bạn cần quét offer / nâng cấp.
3. Kiểm tra xem tài khoản đã gắn thẻ thanh toán hợp lệ chưa.

---

## 5. Chạy thử nghiệm bằng bộ công cụ riêng (Prefix `BS_`)

Toàn bộ script thử nghiệm đã được cấu hình tự động trỏ tới công cụ ADB của BlueStacks Desktop (`127.0.0.1:5555`):

* **`BS_0_Kiem_tra_moi_truong.bat`**: Kiểm tra kết nối ADB, Root, Frida và Module thanh toán trên BlueStacks Desktop.
* **`BS_1_Xem_danh_sach_offer.bat`**: Quét toàn bộ danh sách offer đang hiển thị cho thiết bị BlueStacks (chỉ đọc, không mua).
* **`BS_2_Pro_12_thang_Buoc_1.bat`**: Đăng ký gói 12 tháng đầu tiên trên BlueStacks.
* **`BS_3_Pro_Them_6_thang_Buoc_2.bat`**: Nâng cấp cộng thêm 6 tháng (`--stack`).

---

## 6. Quy trình Revert về MuMu Player (Bất cứ lúc nào)

Khi bạn muốn dừng thử nghiệm BlueStacks Desktop và quay lại MuMu Player:
1. Đóng BlueStacks Desktop.
2. Khởi động lại **MuMu Player 12**.
3. Bấm đúp chạy file **`0_Kiem_tra_moi_truong.bat`** (file gốc của MuMu).
4. Sử dụng tiếp các file gốc từ `1_` đến `5_`. Toàn bộ dữ liệu của MuMu vẫn giữ nguyên 100% trong `MUMU_CONTEXT_BACKUP.md`.
