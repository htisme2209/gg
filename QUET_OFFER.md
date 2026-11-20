# Tìm offer Google One theo SKU

`query_sku.py` tra các mã sản phẩm qua BillingClient trên thiết bị hiện tại. Chế độ này không mở trang thanh toán, không đọc purchaseToken và không đăng ký gói.

Quét như trong ảnh, đồng thời kiểm tra email đang chọn trong Cửa hàng Play:

```powershell
python query_sku.py --discover --serial "127.0.0.1:7555" --account "htisme223@gmail.com"
```

Danh sách mặc định của `--discover` có **19.938 mã ứng viên duy nhất** sau khi loại trùng: 36 SKU ưu tiên, tổ hợp 15 tiền tố × 19 lựa chọn dung lượng × 70 kiểu đuôi và các tên rời. Dung lượng gồm lựa chọn rỗng và 18 mức từ `15gb` đến `100tb`; lựa chọn rỗng tạo được mã như `g1.ai.pro` mà không chèn dấu chấm thừa. Các mã như `g1.2tb.ai.subs_variant`, `g1.2tb.subs_variant`, `g1.play.2tb.ai` được ưu tiên tra trước. Đây là danh sách ứng viên, không phải danh mục sản phẩm chính thức của Google.

Quét toàn bộ danh sách mở rộng, hiển thị cả offer trả phí trong báo cáo:

```powershell
python query_sku.py --discover --serial "127.0.0.1:7555" --account "htisme223@gmail.com" --batch-size 20 --all-offers
```

Với 20 SKU mỗi lô, danh sách này cần 997 lô truy vấn; thời gian chạy phụ thuộc phản hồi của Google Play.

Xem danh sách ứng viên mà chưa kết nối thiết bị:

```powershell
python query_sku.py --discover --dry-run
```

## Danh sách Offer ID và Base Plan ID

```powershell
python query_sku.py --candidate-offers
python query_sku.py --candidate-offers --offer-tier 2 --include-underscores
python query_sku.py --candidate-base-plans
```

- **Tầng 1** là mặc định. Các mẫu có sẵn xuất hiện trước, theo sau là mẫu chung có hoặc không có năm 2024–2027, các cách đảo thứ tự như `eft-3mo` và `3mo-eft`, mẫu giảm giá như `3mo-50off` và mẫu EFT thường gặp cho OEM, Chromebook, nhà mạng và nhóm tài khoản.
- **Tầng 2** gồm toàn bộ tầng 1 và bổ sung thời lượng, kiểu ưu đãi và cách đặt năm cho đối tác. Các mẫu phổ biến có thêm quý, nửa năm và hậu tố, chẳng hạn `eft-3mo-q1-2026` và `6months-eft-ss-h2-2026`.
- **`--include-underscores`** thêm dạng như `eft_3mo` và `free_trial_1m` cho tầng được chọn. Có thể dùng cờ này với cả hai tầng.

Các lệnh trên in danh sách ứng viên ngoại tuyến. Truy vấn BillingClient dùng Product ID và trả về Offer ID, Base Plan ID cùng các giai đoạn giá của sản phẩm.

## Tra SKU trên thiết bị

Tra riêng các mã trong ảnh:

```powershell
python query_sku.py g1.2tb.ai.subs_variant g1.2tb.subs_variant g1.play.2tb.ai --serial "127.0.0.1:7555" --account "htisme223@gmail.com"
```

Có thể thêm mã từ file văn bản bằng `--sku-file duong-dan-file`; mỗi dòng một SKU, phần sau dấu `#` là chú thích. Kết hợp với `--discover` để bổ sung mã vào bộ quét, hoặc dùng riêng để chỉ tra danh sách đó.

Danh sách `oem_skus.txt` phục vụ lượt tra Xiaomi, OPPO và Pixel: gồm 20 SKU đã từng được API trả về và 230 tên SKU dự đoán có từ khóa `xiaomi`, `redmi`, `poco`, `oppo`, `pixel`. Các tên dự đoán chưa phải danh mục sản phẩm chính thức. Redmi/Poco chỉ được dùng như từ khóa tìm kiếm liên quan Xiaomi.

```powershell
python query_sku.py --sku-file oem_skus.txt --serial "127.0.0.1:7555" --account "htisme223@gmail.com" --batch-size 20 --all-offers
```

Đối chiếu tên hãng trong mã sản phẩm, Offer ID, base plan, tên và tag của dữ liệu trả về. Offer mang tên chung không đủ để gán cho hãng chỉ từ một mã viết tắt. Không thấy kết quả trên giả lập/tài khoản hiện tại chưa chứng minh hãng đó không có chương trình trên thiết bị hoặc tài khoản khác.

Mặc định truy vấn 10 SKU mỗi lô, cách nhau 0,75 giây. `--batch-size` nhận 1–20; `--delay` và `--timeout` điều chỉnh khoảng nghỉ và thời gian chờ. Mỗi lô chỉ hoàn tất khi đã nhận toàn bộ offer, kể cả khi không có sản phẩm hoặc không có dùng thử miễn phí. Lỗi và hết thời gian chờ được ghi riêng, không tính là kết quả rỗng thành công.

Bảng kết quả có mã sản phẩm, Base Plan ID, Offer ID, thời gian miễn phí và các giai đoạn giá tiếp theo. Thời hạn lấy từ API. Ví dụ `P13W` hoặc 13 chu kỳ `P1W` là 13 tuần. Giá dùng chuỗi đã định dạng và loại tiền do Play trả về. Khi dùng giá dự phòng, công cụ chia giá trị micros cho 1.000.000 và hiển thị loại tiền có trong dữ liệu.

Báo cáo nằm ở `ultra0-report/offer-scan-<thời điểm>.json` và `.md`. JSON giữ tất cả offer/giai đoạn giá và kết quả từng lô; bảng mặc định chỉ hiện offer bắt đầu miễn phí. Dùng `--all-offers` để hiện cả offer trả phí, `--output ten-bao-cao` để chọn tên báo cáo. Offer token được bỏ khỏi báo cáo mặc định; `--include-tokens` lưu thêm vào JSON nếu cần phân tích.

Scanner dùng đúng `--serial`, kiểm tra phiên bản Frida và mở lại Google One để truy vấn. Nếu chỉ định `--account`, email đọc từ Play phải khớp; scanner không tự chuyển tài khoản. Công cụ không sửa proxy/VPN của thiết bị.

SKU không được trả về có thể không tồn tại hoặc không khả dụng với ứng dụng, tài khoản hay khu vực hiện tại. Việc tìm thấy offer chưa bảo đảm đủ điều kiện đăng ký; quyết định cuối cùng thuộc Google Play. Không thể liệt kê mọi SKU từ đường dẫn web quản lý gói đăng ký cá nhân.
