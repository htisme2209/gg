# BẢN LƯU NGỮ CẢNH GỐC (MUMU PLAYER CONTEXT BACKUP)
*Thời điểm ghi nhận: 19/11/2026*

Tài liệu này lưu trữ toàn bộ cấu hình, kịch bản và thông số của hệ thống hiện tại chạy trên **MuMu Player 12**. 
Bất cứ khi nào cần quay lại (Revert) từ BlueStacks về MuMu Player, chỉ cần tham chiếu tài liệu này.

---

## 1. Cấu hình Giả lập MuMu Player 12
- **Cổng ADB kết nối:** `127.0.0.1:16384` (hoặc `127.0.0.1:7555` nếu là MuMu 6/bản cũ).
- **Quyền Root:** Đã bật trong Cài đặt MuMu -> Cài đặt quyền -> Bật quyền ROOT.
- **Kiến trúc Android:** x86_64.
- **Frida Server:** Phiên bản `16.5.9` đặt tại `/data/local/tmp/frida-server`.
- **Tài khoản Google Play:** `htisme223@gmail.com` (hoặc tài khoản đang đăng nhập trong máy `current@device`).

---

## 2. Danh sách các file script gốc của MuMu Player (KHÔNG ĐƯỢC THAY ĐỔI)
Các file này luôn trỏ mặc định tới MuMu Player:
1. `0_Kiem_tra_moi_truong.bat`: Chạy kiểm tra kết nối, root, frida và module thanh toán.
2. `1_Xem_danh_sach_offer.bat`: Quét danh sách offer của gói Google AI Pro (`pro12`).
3. `2_Pro_12_thang_Buoc_1.bat`: Đăng ký gói 12 tháng đầu tiên (`--plan pro12`).
4. `3_Pro_Them_6_thang_Buoc_2.bat`: Nâng cấp đợt 2 thêm 6 tháng (`--stack --plan pro6`).
5. `4_Pro_Them_6_thang_Buoc_3.bat`: Nâng cấp đợt 3 thêm 6 tháng (`--stack --plan pro6b`).
6. `5_Pro_Du_phong_6_thang.bat`: Thử nghiệm nâng cấp dự phòng (`--stack --plan pro6c`).

---

## 3. Cách Revert về MuMu Player (Quy trình 1 bước)
Khi muốn dừng thử nghiệm BlueStacks và tiếp tục chạy trên MuMu Player:
1. Tắt BlueStacks (nếu đang mở).
2. Khởi động MuMu Player 12 (đảm bảo Root và ADB đã bật trong Cài đặt MuMu).
3. Bấm đúp chuột chạy file **`0_Kiem_tra_moi_truong.bat`**.
   - Nếu màn hình báo `✅ Đã kết nối thiết bị: 127.0.0.1:16384` là toàn bộ hệ thống đã trở về MuMu Player 100%.
4. Tiếp tục sử dụng các file `.bat` gốc đánh số từ `1_` đến `5_` bình thường.
