# google-ultra

Google One có offer dùng thử miễn phí 12 tháng cho AI Ultra, không trang nào hiển thị cả, chỉ có trong giá trị trả về của thư viện thanh toán Play (BillingClient). Script này nối «tra offer → mở trang thanh toán Play → xác nhận 0 đồng → mở gói» thành một lệnh duy nhất.

Nguyên lý là mượn chính tiến trình của Google One để gọi BillingClient, không cần Xposed, không cần sửa APK.

## Nhận được gì

Nhận được là **Ultra 5x, 20TB, 12 tháng $0**, hủy trước khi hết hạn thì không mất tiền. Sau khi mở, trang đăng ký Play sẽ ghi «Sắp bị trừ 2027-11-17 US$99.99/tháng», đó là giá sau khi hết dùng thử, không phải trừ ngay bây giờ.

Gói 30TB (20x) cũng tra được offer, nhưng khi thanh toán Play sẽ kiểm tra lại lần nữa, đa số tài khoản sẽ hiện «Bạn không đủ điều kiện dùng thử miễn phí». Script này sẽ không bấm vào gói đó.

## Cần gì

Một điện thoại Android đã root, cắm USB vào máy tính. Magisk, KernelSU, APatch đều được, giả lập cũng được.

Máy tính cần Python 3.9 trở lên, cộng thêm hai gói:

```bash
pip3 install frida
```

adb thì lấy trong platform-tools của Android SDK. Cài xong, chạy `adb devices` thấy điện thoại là được. Chưa cài bao giờ thì trên Mac chạy `brew install android-platform-tools`, trên Windows tải gói platform-tools về, giải nén rồi thêm thư mục đó vào PATH.

Trên điện thoại bật «Tùy chọn nhà phát triển → Gỡ lỗi USB», cắm vào rồi bấm cho phép trong hộp thoại hiện lên.

## Cách dùng

Đăng ký lần đầu tra offer rồi gọi thanh toán bằng `offerToken`, không yêu cầu gói đăng ký trước đó. Khi dùng `--stack`, script đọc `purchaseToken` của đúng tài khoản và truyền thông số nâng cấp gói, mặc định chế độ 5 (`CHARGE_FULL_PRICE`). Không tìm thấy token hoặc lỗi đọc dữ liệu sẽ dừng nâng cấp.

Với AI Pro, bước đọc cache hỗ trợ hai SKU nguồn chính xác: `g1.2tb.ai.subs_variant` và `g1.play.2tb.ai`, kể cả khi Play thêm thông tin trang trí vào `doc_id`. Mặc định script tìm trên cả hai SKU của đúng tài khoản. Nếu có các token đang hoạt động khác nhau giữa các sản phẩm, script dừng với `purchase_token_ambiguous` thay vì tự chọn một token. Dùng `--token-product` để chỉ định SKU nguồn hiện tại; tham số này dùng được với `--diagnose-token` và `--stack`. Offer đích vẫn do `--plan` chọn.

```powershell
python ultra0.py --account "current@device" --no-add --force --plan pro6
```

Thử offer `pro6c` trên tài khoản đã có gói:

```powershell
python ultra0.py --serial "127.0.0.1:7555" --account "htisme223@gmail.com" --no-add --no-switch --stack --plan pro6c
```

Thử đúng SKU `g1.play.2tb.ai`, Offer ID `eft-3mo` bằng `--plan pro3`:

```powershell
python ultra0.py --serial "127.0.0.1:7555" --account "htisme223@gmail.com" --no-add --no-switch --stack --plan pro3 --mode 5
```

Lệnh này dùng token gói hiện tại để gửi yêu cầu thay thế. Khi đăng ký lần đầu, bỏ `--stack` và `--mode 5`. Offer đã quét có 3 tháng miễn phí, sau đó 489.000 ₫/tháng; điều kiện và thời hạn áp dụng thực tế cần đối chiếu trên trang thanh toán Play. Nếu không có đúng `eft-3mo` bắt đầu miễn phí, script không chọn offer khác. Script có thể tự bấm đăng ký khi nhận diện giá 0 đồng/dùng thử miễn phí.

Thời gian quy đổi và khả năng mua offer do Google Play quyết định. Lỗi “The item you requested is not available for purchase” được ghi riêng; việc nhìn thấy offer trong API không bảo đảm nâng được từ 24 lên 30 tháng. Mỗi lần chạy lưu thêm báo cáo có thời điểm trong `ultra0-report/history/` để đối chiếu plan, offer đã chọn, chế độ và mã lỗi.

Nếu trang Play báo “Something went wrong on our end. Please try again.”, script dừng xác nhận và ghi `billing_error` cùng nội dung giao diện. `launched.code=0` chỉ xác nhận Play đã mở luồng thanh toán, chưa chứng minh giao dịch hay cộng thêm thời hạn thành công. Thông báo lỗi chung này chưa xác định được nguyên nhân cụ thể hoặc điều kiện sử dụng offer.

Nếu gặp `purchase_token_not_found`, kiểm tra cache đúng tài khoản trước:

```powershell
python ultra0.py --serial "127.0.0.1:7555" --account "htisme223@gmail.com" --diagnose-token
```

Lệnh này chỉ đọc dữ liệu cache Play, không mở ứng dụng, không đổi tài khoản, không chạy Frida và không mở thanh toán. Báo cáo riêng `ultra0-report/token-check-*.json` chỉ lưu số lượng bản ghi/lý do bị loại, không lưu giá trị token và không ghi đè báo cáo đăng ký. `no_account_rows` nghĩa là cache thiếu dữ liệu email này; `no_product_rows` nghĩa là không có SKU phù hợp; `no_usable_token` kèm số lượng theo từng lý do loại. Các trạng thái này chưa đủ để kết luận gói đã hết hạn hoặc không tồn tại. Có thể mở trang Gói đăng ký trong Play bằng đúng tài khoản để tải lại dữ liệu, rồi chạy lại lệnh chẩn đoán.

Sau khi dùng `pro3`, nếu gói nguồn hiện tại là `g1.play.2tb.ai`, kiểm tra riêng cache của SKU đó:

```powershell
python ultra0.py --serial "127.0.0.1:7555" --account "htisme223@gmail.com" --diagnose-token --token-product g1.play.2tb.ai
```

Khi chẩn đoán chọn được token của SKU nguồn này, có thể gửi lại yêu cầu `pro3` với chế độ 5:

```powershell
python ultra0.py --serial "127.0.0.1:7555" --account "htisme223@gmail.com" --no-add --no-switch --stack --plan pro3 --mode 5 --token-product g1.play.2tb.ai
```

`--token-product g1.play.2tb.ai` chỉ lọc token của gói đang có; nó không tự chọn offer đích hay bảo đảm Play chấp nhận thay thế hoặc cộng thêm thời hạn. Xem `token_diagnostics.selected_product` trong báo cáo để biết SKU nguồn đã chọn; trường này chỉ chứa mã sản phẩm, không chứa giá trị token.

Nếu vẫn `no_account_rows`, xem `token_diagnostics.database_summary`: `ownership_rows=0` là bảng cache trống; số dòng lớn hơn 0 chỉ cho biết có dữ liệu cache khác, không chứng minh gói thuộc email khác. `device_diagnostics` ghi serial và mã người dùng Android; đường dẫn cache hiện đọc hồ sơ Android 0. Nếu `resumed_play_user` khác 0, Play đang mở ở hồ sơ khác. Không tự lấy token từ tài khoản hoặc hồ sơ khác khi thiếu dữ liệu đích.

`token_diagnostics.target_inventory` phân biệt bản ghi ứng dụng Google One (`google_one_app_rows`) với các mã sản phẩm `g1.*` của đúng tài khoản. Cài lại ứng dụng có thể tạo bản ghi ứng dụng mà chưa có bản ghi gói đăng ký. Danh sách inventory chỉ mô tả cache; việc chọn token nâng cấp vẫn giới hạn ở hai SKU AI Pro tương thích nêu trên, hoặc SKU nguồn được chọn bằng `--token-product` trong danh sách đó. SKU khác xuất hiện trong inventory không tự được dùng để nâng cấp.

Khi trang Play vẫn hiển thị gói còn thời hạn nhưng cache không có dữ liệu, có thể truy vấn trạng thái đăng ký qua Billing:

```powershell
python query_purchases.py --serial "127.0.0.1:7555" --account "htisme223@gmail.com"
```

Công cụ này kiểm tra email đang chọn trong Play, mở lại Google One và dùng Frida/module có sẵn để gọi `queryPurchasesAsync` cho loại `subs`. Công cụ chỉ đọc, không mở thanh toán hay xác nhận/ghi nhận giao dịch. Báo cáo `purchase-check-*.json` chỉ lưu SKU, trạng thái (`1` đã mua, `2` đang chờ), cờ gia hạn, cờ xác nhận và `token_present`; không xuất giá trị token. `auto_renewing=false` có thể là đã tắt gia hạn hoặc gói trả trước, chưa chứng minh gói đã hết hạn. Billing không trả email chủ giao dịch hay ngày hết hạn, nên `payer_account_verified` luôn là `false`; kết quả này không tự trở thành token đầu vào của `--stack`. Kết quả rỗng thành công được phân biệt với lỗi Billing hoặc hết thời gian chờ.

Nếu chỉ bước đọc email giao diện Play thất bại, thêm `--allow-unverified-ui` để chẩn đoán metadata Billing của ứng dụng hiện tại. Báo cáo ghi `play_ui_account_verified=false` khi không đọc được email; dữ liệu đó chưa gắn với email yêu cầu. Nếu đọc được một email khác email yêu cầu, công cụ vẫn dừng. Tùy chọn này chỉ có ở công cụ chẩn đoán, không bỏ xác minh tài khoản khi `--stack`.

Snapshot token bao gồm `library.db` và `library.db-wal` nếu có; chỉ sao chép DB chính có thể bỏ sót giao dịch đã ghi vào WAL. Script kiểm tra hash trước/sau khi sao chép, hash khi tải về và tính toàn vẹn SQLite; dữ liệu thay đổi liên tục hoặc không đọc được sẽ trả `purchase_token_read_failed`. Script cần quyền root hiện có và lệnh `sha256sum` trên thiết bị; chế độ chẩn đoán không tự đổi quyền adbd hay sửa cơ sở dữ liệu Play.

Tự kiểm tra môi trường trước một lượt, nó sẽ kiểm tra thiết bị, root, frida-server, đẩy module thanh toán, tiện tay tắt luôn proxy và Clash nào đang chặn mạng của Play:

```bash
python3 ultra0.py --check
```

Toàn xanh là chạy tài khoản được rồi.

Tài khoản viết vào một file văn bản, mỗi dòng một tài khoản, các trường cách nhau bằng bốn dấu gạch ngang:

```
email----mật khẩu----email khôi phục----khóa 2FA----số thẻ----ngày hết hạn----CVC----chủ thẻ----mã bưu chính
```

Mấy mục sau để trống cũng được. Tài khoản mới mua thường không có 2FA thì để trống:

```
abc123@gmail.com----mypassword----
```

Có thẻ thì:

```
abc123@gmail.com----mypassword--------4242424242424242----10/29----326----ZHANG SAN----97201
```

Địa chỉ không điền sẽ mặc định dùng `123 Main St, Portland, OR 97201`, Oregon được miễn thuế tiêu thụ.

Chạy:

```bash
python3 ultra0.py accounts.txt
```

Chạy một tài khoản cũng được:

```bash
python3 ultra0.py --account "abc@gmail.com:mật khẩu:khóa 2FA"
```

Muốn xem kết quả thì mở trang đăng ký để đối chiếu:

```
Cửa hàng Play → ảnh đại diện → Thanh toán và gói đăng ký → Gói đăng ký
```

## Bên trong nó làm gì

1. Thêm tài khoản vào điện thoại (chưa có thì thêm, có rồi thì bỏ qua)
2. Chuyển tài khoản Play. Chuyển xong nhất định phải đọc lại từ bảng ảnh đại diện để đối chiếu, không khớp thì thoát ngay, không chạy sang tài khoản khác
3. Khởi động Google One, dùng Frida gắn vào, dùng `DexClassLoader` để tải module thanh toán
4. `queryProductDetailsAsync` tra `g1.play.20tb`, lấy về 5 offer
5. Chọn offer có thời gian miễn phí dài nhất (`eft-12month`, P1Y), gọi `launchBillingFlow` ở luồng chính
6. Canh trang thanh toán. Thấy giá là 0 hoặc «Dùng thử miễn phí 12 tháng» mới bấm đăng ký; thấy «không đủ điều kiện dùng thử miễn phí» thì đóng lại, tuyệt đối không bấm
7. Play đôi khi yêu cầu nhập lại mật khẩu, script tự điền
8. Mở trang đăng ký để đối chiếu, kết quả ghi vào `ultra0-report/`

## Khi thất bại thì ra sao

**Tài khoản không đủ điều kiện.** Play sẽ báo «Bạn không đủ điều kiện dùng thử miễn phí, tuy vậy bạn vẫn có thể đăng ký». Một tài khoản cơ bản chỉ có một cơ hội: dùng thử một khi đã bắt đầu, dù chưa xác nhận, offer cũng sẽ biến mất. Vì vậy đừng lấy tài khoản chính ra thử.

**Không có phương thức thanh toán.** Đăng ký bắt buộc phải có thẻ. Trang thêm thẻ của Play là WebView, adb không điền vào được, script sẽ dừng lại và nhắc bạn điền xong trên điện thoại rồi bấm Enter. Mỗi thiết bị chỉ cần gắn tay một lần, sau đó mọi tài khoản dùng chung thẻ đó.

**Tài khoản Play chưa chuyển qua.** Script sẽ in ra tài khoản đang thực sự đăng nhập rồi thoát. Lúc này chuyển tay trong Play rồi chạy lại kèm `--no-switch`, để nó chỉ kiểm tra mà không thử chuyển nữa:

```bash
python3 ultra0.py accounts.txt --no-switch
```

**Trang thanh toán không hiện lên.** Chạy lại một lần. Hai lần liên tiếp đều không hiện thì kiểm tra mạng của thiết bị: `settings get global http_proxy`, không phải `null` thì xóa đi; VPN kiểu Clash sẽ chiếm DNS, cũng làm Play không kết nối được.

## Một số tham số

```bash
--plan 5x      # chỉ mở 20TB
--plan 20x     # chỉ tra 30TB (đa số tài khoản không lấy được dùng thử)
--plan auto    # mặc định, tra cả hai gói, chọn gói miễn phí dài nhất
--no-add       # tài khoản đã có trên điện thoại, bỏ qua bước thêm tài khoản
--no-switch    # không tự chuyển tài khoản, chỉ kiểm tra tài khoản hiện tại
```

## Vài lưu ý

Thử xong nhớ vào Play hủy gói đăng ký, nếu không đến hạn sẽ bị trừ $99.99.

Script chỉ chạy trên máy của bạn, tài khoản, mật khẩu và số thẻ không ra mạng, cũng không tải lên đâu cả. File báo cáo nằm trong `ultra0-report/`, trong đó có chi tiết offer và kết quả từng bước.

Đoạn code này chỉ tận dụng việc «phía client lấy được offer dùng thử» trong quy trình thanh toán của Play, không sửa bất kỳ dữ liệu nào phía máy chủ.

## Quét thêm SKU và offer

Để tìm thêm offer ngoài danh sách có sẵn, dùng bộ quét chỉ đọc:

```powershell
python query_sku.py --discover --serial "127.0.0.1:7555" --account "htisme223@gmail.com"
```

Kết quả gồm thời gian miễn phí, giá sau ưu đãi và báo cáo JSON/Markdown. Xem [hướng dẫn quét offer](QUET_OFFER.md) để tra SKU riêng, thêm danh sách mã và xem trước bằng `--dry-run`.

## Trao đổi

Có vấn đề thì vào nhóm Telegram hỏi: https://t.me/VQD_SHARE (@VQD_SHARE).

<img src="assets/telegram-group.png" width="320" alt="Mã QR nhóm Telegram @VQD_SHARE">
