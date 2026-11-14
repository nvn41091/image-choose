# Chọn ảnh cưới

**Bản web cho điện thoại và PC:** mã nguồn trong [`web/`](web/README.md), nhận link Google Drive, nhập backup từ app PC, lưu trên thiết bị/Firebase và deploy bằng GitHub Actions. Xem [hướng dẫn chạy và triển khai web](web/README.md). Bản Python bên dưới vẫn hoạt động độc lập.

Ứng dụng Windows bằng PySide6 để xem ảnh studio gửi, so sánh biểu cảm, chọn ảnh theo gói cưới và xuất danh sách gửi lại studio. Ứng dụng làm việc với thư mục ảnh trên máy và giữ nguyên nội dung, tên và vị trí của ảnh nguồn.

## Dành cho khách hàng

1. Mở `ChonAnhCuoi.exe`, bấm **Chọn thư mục** và chọn thư mục ảnh xem trước. Bấm vào một thư mục con trong tab **Tất cả ảnh** để mở, hoặc bấm **Thư mục cha** để quay lên.
2. Dùng **Ảnh mỗi hàng** để chọn từ 3 đến 10 ảnh một hàng. Dùng tim và số sao để xem lại ảnh thích. Nhấp đúp để xem lớn hoặc chọn 2–4 ảnh rồi bấm **So sánh**. Con lăn dùng để phóng to và kéo chuột để di chuyển. Trong chế độ so sánh, các ảnh di chuyển và phóng to cùng nhau.
3. Gán loại như **Album** hoặc **Phóng lớn**. Dùng Ctrl hoặc Shift để chọn nhiều ảnh. Ghi yêu cầu hậu kỳ ở bảng bên phải. Thanh gói cưới cho biết số lượng đã chọn và hỏi trước khi chọn vượt giới hạn.
4. Kiểm tra tab **Ảnh đã chọn**, bấm **Hoàn tất và xuất danh sách** rồi chọn một thư mục có sẵn để lưu. Gói gồm `danh_sach_anh.xlsx`, `lightroom.txt` và `photo_tags.json`. Nếu chọn tạo ZIP, bạn có thể gửi riêng file ZIP cho studio.

**Tác vụ → Loại ảnh và gói cưới** cho phép sửa tên khách hàng, thêm và sửa loại, đổi màu, phím tắt và số ảnh tối đa. Các lựa chọn tự lưu vào `photo_tags.json` cạnh thư mục ảnh. Khi tiếp tục trên máy khác, đặt tệp này cùng bộ ảnh xem trước và giữ cấu trúc thư mục ảnh.

**Tác vụ → Sao chép ảnh theo loại** tạo bản sao ảnh xem trước trong thư mục đích, giữ cấu trúc thư mục con bên trong từng loại. Tên thư mục được điều chỉnh cho phù hợp với Windows.

## Đánh giá và đề xuất ảnh

1. Bấm **Đánh giá ảnh** trên thanh tác vụ hoặc **Tác vụ → Đánh giá và chọn ảnh**.
2. Chọn phạm vi: **Ảnh đang chọn**, **Thư mục hiện tại (kèm thư mục con)** hoặc **Tất cả thư mục ảnh**. Hai phạm vi thư mục lấy toàn bộ ảnh bên trong, kể cả ảnh đang ẩn bởi bộ lọc.
3. Mặc định chọn **Dùng gói ChatGPT (đăng nhập)**. Bấm **Continue with ChatGPT**, đăng nhập và cấp quyền trong trình duyệt, sau đó quay lại ứng dụng. Không cần nhập API key. Chọn model hỗ trợ ảnh từ danh sách được tải cho đúng tài khoản, rồi nhập tiêu chí như “nụ cười tự nhiên, bố cục cân đối, phù hợp album cưới”.
4. Kiểm tra số ảnh và số lượt đánh giá, tích đồng ý gửi ảnh rồi bấm **Đánh giá ảnh**. Chế độ gói ChatGPT sử dụng hạn mức/số dư ChatGPT, không dùng API credit và không tự chuyển sang API key nếu thiếu quyền hoặc hết hạn mức. Bấm **Quản lý hạn mức** để mở cài đặt sử dụng ChatGPT.
5. Ứng dụng gửi từng nhóm tối đa 12 ảnh, hiển thị tiến độ và cho phép **Dừng sau nhóm hiện tại**. Ảnh hỏng hoặc không đọc được được bỏ qua và báo trên giao diện. Khi dừng hoặc gặp lỗi API, kết quả các nhóm đã hoàn tất vẫn được giữ để duyệt. Thời gian chờ mạng của mỗi yêu cầu là 60 giây; không tự gửi lại yêu cầu bị lỗi.
6. Xem điểm 0–100, lý do và gợi ý chỉnh sửa. Di chuột lên ô để đọc đầy đủ nội dung; nhấp đúp một dòng hoặc bấm **Xem ảnh lớn** để duyệt ảnh. Đặt **Số ảnh đề xuất**, bấm **Chọn ảnh điểm cao nhất**, rồi điều chỉnh dấu tích từng ảnh. Số ảnh đề xuất ban đầu theo chỗ còn lại trong gói Album, hoặc 20 nếu không có giới hạn.
7. Chọn loại ảnh để gán, đánh dấu yêu thích, ghi đè số sao hoặc thêm gợi ý hậu kỳ vào ghi chú. Bấm **Áp dụng cho ảnh đã tích** để lưu. Ứng dụng hỏi trước khi vượt giới hạn gói; ghi chú mới được thêm sau ghi chú cũ. Việc đánh giá không tự thay đổi lựa chọn.

Điểm giữa các nhóm chỉ mang tính tham khảo, không phải một lượt so sánh trực tiếp toàn bộ bộ ảnh. Hãy kiểm tra lại độ đa dạng, ảnh trùng và độ nét ở bản lớn trước khi chốt. Số sao khi áp dụng được quy đổi theo mỗi 20 điểm thành một sao, tối thiểu một sao.

Chỉ bản xem trước thu nhỏ tối đa 1280 px, đã bỏ EXIF/GPS, cùng tiêu chí bạn nhập được gửi tới OpenAI. Tên tệp, đường dẫn, ghi chú và thông tin gói cưới không được đưa vào yêu cầu. Yêu cầu đặt `store: false`. Ảnh nguồn được giữ nguyên. Tham khảo [tài liệu OpenAI về phân tích ảnh](https://developers.openai.com/api/docs/guides/images-vision) và [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

### Sắp xếp theo điểm và số sao

- Chọn một ảnh rồi nhập **Điểm ảnh** từ 0 đến 100 trong bảng bên phải. Điểm được lưu theo đường dẫn của từng ảnh, kể cả khi hai thư mục có tệp trùng tên. Chọn **Chưa chấm** để bỏ điểm; không thay đổi số sao hoặc loại ảnh. Chỉ có thể nhập điểm khi chọn đúng một ảnh.
- Trong **Tất cả ảnh** hoặc **Ảnh đã chọn**, dùng hộp **Sắp xếp** để chọn điểm cao → thấp/thấp → cao, số sao nhiều → ít/ít → nhiều, hoặc tên ảnh A → Z/Z → A. Hai tab dùng chung thứ tự; ứng dụng nhớ lựa chọn khi mở lại. Khi ẩn bộ lọc hoặc dùng chế độ tập trung, có thể đổi thứ tự qua **Hiển thị → Sắp xếp ảnh**.
- Ảnh chưa có điểm hoặc chưa đánh sao nằm cuối khi sắp xếp theo tiêu chí tương ứng. Điểm 0 vẫn là một kết quả hợp lệ. Ảnh bằng điểm/sao được xếp tiếp theo đường dẫn; thẻ thư mục luôn ở trước ảnh.
- Bảng kết quả đánh giá có hộp **Sắp xếp kết quả** và cột **Sao**. Bấm tiêu đề **Điểm**, **Sao** hoặc **Ảnh / thư mục** để đổi thứ tự. Dấu tích và ảnh đang xem được giữ theo đúng tệp khi sắp xếp. Nút **Chọn ảnh điểm cao nhất** luôn chọn theo điểm, dù bảng đang sắp xếp theo sao hay theo tên.
- Điểm của các ảnh đã đánh giá thành công tự lưu vào `photo_tags.json`, tách biệt với số sao. Sau khi dừng hoặc gặp lỗi ở nhóm tiếp theo, điểm của các nhóm đã hoàn tất vẫn được giữ. Điểm được hiển thị trên thẻ ảnh và trong tooltip; backup/restore cũng giữ điểm này. Điểm không tự gán loại, yêu thích hoặc ghi đè sao.
- Phiên cũ chưa có trường điểm được xem là chưa đánh giá. Cần đánh giá lại để có điểm dùng cho sắp xếp; ứng dụng không tự gửi lại ảnh.
- Gợi ý thêm vào ghi chú không có tiền tố `[ChatGPT]`. Khi mở phiên cũ, ứng dụng bỏ tiền tố này ở đầu dòng và lưu lại nếu có quyền ghi, giữ nguyên nội dung còn lại, điểm và số sao. Các lần nhắc `[ChatGPT]` ở giữa dòng được giữ nguyên.

### Đăng nhập bằng ChatGPT

- Luồng chính thức **Sign in with ChatGPT → ChatGPT plan usage** mở trình duyệt hệ thống. Người dùng nhập thông tin đăng nhập và cấp quyền trên trang OpenAI. Ứng dụng không nhận mật khẩu. Phải cấp quyền dùng gói; chỉ đăng nhập danh tính chưa đủ để đánh giá ảnh.
- Có thể chọn tài khoản đã lưu hoặc **Thêm tài khoản ChatGPT**. Mỗi tài khoản/workspace có phiên riêng; danh sách model được tải lại khi đổi tài khoản. Nếu danh sách chưa tải được, bấm **Tải model**. Chọn model có hỗ trợ ảnh; tính năng còn phụ thuộc quyền mà OpenAI cấp cho tài khoản và ứng dụng.
- Phiên được gia hạn khi gần hết hạn. Tệp `%LOCALAPPDATA%\ChonAnhCuoi\auth\chatgpt.dat` được mã hóa bằng Windows DPAPI, gắn với tài khoản Windows hiện tại; không nằm trong thư mục ảnh, bản backup hoặc gói gửi studio. Ứng dụng xác minh chữ ký và danh tính từ OpenAI trước khi thay phiên đang dùng.
- Bấm **Đăng xuất** để thu hồi phiên và xóa credential trên máy; tên tài khoản vẫn được giữ để đăng nhập lại. Nếu không xác nhận được việc thu hồi do mất mạng, ứng dụng báo rõ và bạn có thể ngắt kết nối ứng dụng trong cài đặt ChatGPT.
- **Hủy đăng nhập** dừng chờ phản hồi trình duyệt. Không nhận được kết quả phân tích hoàn chỉnh, thiếu quyền hoặc chạm giới hạn thì ứng dụng dừng, giữ kết quả các nhóm đã xong và không đổi sang phương thức thanh toán khác.
- Trang callback trong trình duyệt chỉ xác nhận đã nhận phản hồi, chưa phải đăng nhập xong. Ứng dụng còn phải đổi mã và xác thực phiên với OpenAI. Nếu mã bị từ chối (`invalid_grant`), ứng dụng giữ registration đã cấp và mở lại đúng một lượt xác thực mới với state/nonce/PKCE mới. Hãy tiếp tục trên thẻ mới, không tải lại thẻ callback cũ. Nếu vẫn lỗi, ứng dụng hiển thị thông báo kèm HTTP/mã lỗi an toàn để chẩn đoán; không ghi authorization code hoặc token vào log.
- Luồng này hiện nằm trong chương trình dành cho ứng dụng mã nguồn mở chạy cục bộ theo điều kiện của OpenAI. Cần kiểm tra điều kiện trước khi phát hành ứng dụng đóng nguồn, thu phí hoặc chạy trên máy chủ. Việc thêm đăng nhập không tự cấp quyền hay bảo đảm mọi tài khoản Pro đều truy cập được. Tham khảo [phạm vi hỗ trợ](https://developers.openai.com/siwc/token-sharing-open-source) và [giới hạn hiện tại](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

Nếu muốn dùng API riêng, chủ động chuyển **Cách sử dụng → OpenAI API key (tính phí API)**. Nhập khóa hoặc dùng biến `OPENAI_API_KEY`, chọn model hỗ trợ ảnh và Structured Outputs (mặc định `gpt-4.1-mini`). Khóa chỉ được giữ trong bộ nhớ của phiên ứng dụng; cần đồng ý riêng trước khi gửi ảnh bằng chế độ API.

## Backup và restore

- **Sao lưu và khôi phục → Sao lưu dữ liệu và ảnh** tạo ZIP mới tại thư mục bạn chọn. Mặc định lưu toàn bộ dữ liệu lựa chọn: tên khách hàng, loại ảnh, giới hạn gói, loại đã gán, sao, yêu thích và ghi chú. Các bản ghi ảnh đang tạm vắng cũng được giữ. Tích **Kèm toàn bộ ảnh** để lưu thêm tất cả ảnh trong cây thư mục đang mở, giữ nguyên cấu trúc và nội dung. Ảnh RAW, tệp phụ khác và cài đặt giao diện không thuộc bản backup. API key không nằm trong backup.
- **Sao lưu và khôi phục → Khôi phục từ backup** mở ZIP do tính năng backup tạo, hoặc `photo_tags.json`. Ứng dụng kiểm tra dữ liệu và hiển thị thông tin trước khi phục hồi.
- **Khôi phục cả bộ ảnh vào thư mục mới**: chỉ khả dụng khi ZIP có ảnh. Chọn thư mục cha; ứng dụng tạo thư mục `Khoi-phuc-…`, khôi phục ảnh cùng dữ liệu và mở bộ ảnh này. Các ảnh đã có ở nơi khác không bị ghi đè. ZIP hỏng hoặc thiếu dung lượng sẽ không công bố thư mục kết quả.
- **Chỉ khôi phục dữ liệu**: mở bộ ảnh đích trước, giữ cấu trúc thư mục giống bản backup, rồi bỏ chọn khôi phục cả bộ ảnh. Ứng dụng báo số bản ghi khớp và chưa khớp, hỏi trước khi thay toàn bộ lựa chọn, rồi giữ bản JSON cũ trong `%LOCALAPPDATA%\ChonAnhCuoi\backups\Truoc-khoi-phuc-….json`. Bạn có thể dùng chính tệp này để quay về dữ liệu trước đó. Bản ghi chưa khớp vẫn được giữ để dùng khi ảnh xuất hiện lại.
- Nếu `photo_tags.json` hiện tại bị lỗi, có thể khôi phục từ backup khi ứng dụng vẫn giữ được khóa ghi của thư mục. Không được khôi phục dữ liệu vào thư mục đang mở ở phiên khác.

Sao lưu và khôi phục chạy trên luồng nền. Khi sao lưu kèm ảnh, không đổi tên hoặc sửa ảnh cho tới khi hoàn tất; nếu ảnh đã thay đổi sau lần quét, mở lại thư mục để quét lại trước khi sao lưu.

Trong menu **Hiển thị**, bạn có thể bật/tắt thanh tác vụ, đường dẫn, tiến độ gói, bộ lọc, bảng chọn và ghi chú, cùng thanh trạng thái. Bật **Tập trung vào ảnh** để mở rộng lưới. Ứng dụng nhớ bố cục đã chọn. Khi ẩn bảng chọn và ghi chú, bạn vẫn có thể nhấp chuột phải lên ảnh để gán loại, đánh sao, đánh dấu yêu thích hoặc mở ghi chú. Menu **Hiển thị** cũng có **Giao diện tối** và **Ảnh mỗi hàng**.

| Phím | Thao tác |
| --- | --- |
| `1`–`9` | Gán hoặc bỏ loại tương ứng. |
| `0`, `Delete` | Bỏ tất cả loại khỏi các ảnh đang chọn. |
| `Shift+1`–`Shift+5` | Đánh giá sao. Bấm lại cùng số sao để bỏ đánh giá. |
| `F` | Bật hoặc tắt yêu thích. |
| `C` | So sánh 2–4 ảnh. |
| `Ctrl+Shift+F` | Bật hoặc tắt chế độ tập trung vào ảnh. |
| `←`, `→`, `Esc` | Chuyển ảnh hoặc đóng trình xem. |
| `F1` | Mở danh sách phím tắt. |

## Dành cho studio

Đặt `goi_chup.json` mã hóa UTF-8 trong thư mục gốc của bộ ảnh. Tệp khởi tạo tên khách hàng và số lượng tối đa khi khách mở thư mục lần đầu. Sau khi đã có `photo_tags.json`, ứng dụng dùng cấu hình trong phiên đã lưu.

```json
{
  "customer_name": "Minh và An",
  "limits": {
    "album": 60,
    "phong_lon": 2,
    "anh_de_ban": 4,
    "mang_xa_hoi": null,
    "chinh_sua": null
  }
}
```

`null` hoặc bỏ trống một mã trong `limits` nghĩa là không giới hạn. Số `0` là giới hạn bằng 0 và vẫn cho phép khách xác nhận chọn vượt gói.

- Excel có sheet tổng hợp và sheet riêng cho từng loại. Tab **Ảnh đã chọn** tập hợp ảnh đã gán loại từ mọi thư mục trong bộ ảnh. Gói xuất gồm cả ảnh đã gán loại đang ẩn vì bộ lọc.
- `lightroom.txt` có một dòng cho mỗi loại. Tên ảnh đã bỏ đuôi và phân cách bằng dấu phẩy. Khi có tên trùng hoặc chứa dấu phẩy, dùng các đường dẫn tương đối trong `photo_tags.json` để xác định ảnh.
- Mở **Studio → Đối chiếu và sao chép RAW**, chọn `photo_tags.json` khách gửi, rồi chọn thư mục RAW. Ứng dụng tìm `.CR2`, `.CR3`, `.NEF` và `.ARW`, ưu tiên đường dẫn tương đối cùng tên và sau đó tìm theo tên duy nhất. Xem danh sách ảnh còn thiếu hoặc có nhiều kết quả trước khi sao chép. Chọn thư mục đích bên ngoài thư mục ảnh nguồn.

## Chạy mã nguồn trên Windows

Cài Python 3.11 trở lên bản 64 bit. Từ thư mục dự án, chạy PowerShell. Nếu trình cài Python không cung cấp lệnh `py`, dùng `python -m venv .venv` ở bước đầu.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Chạy kiểm thử dữ liệu và giao diện Qt.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Bộ kiểm thử giao diện tạo thư mục 5.000 ảnh thử. Có thể đặt `$env:QT_QPA_PLATFORM = 'offscreen'` trước khi chạy nếu môi trường thiếu màn hình.

## Đóng gói một file EXE

Chạy trên Windows từ thư mục dự án sau khi cài các phụ thuộc. Đoạn lệnh tạm giới hạn `PATH` ở thư mục hệ thống để PyInstaller lấy đúng DLL mà Qt cần, rồi khôi phục `PATH` khi hoàn tất.

```powershell
$appBuildPath = $env:Path
try {
    $env:Path = "$env:WINDIR\System32;$env:WINDIR"
    .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed `
      --workpath build/windows --name ChonAnhCuoi --icon assets/app.ico `
      --add-data 'assets:assets' main.py
} finally {
    $env:Path = $appBuildPath
}
```

Sao chép `dist\ChonAnhCuoi.exe` sang máy Windows 64 bit chưa cài Python để kiểm tra trước khi phát hành. Mở EXE, chọn một thư mục ảnh thử, gán loại, đóng và mở lại để kiểm tra phiên tự lưu, rồi xuất và mở gói ZIP.

## Cấu trúc và lưu trữ

- `main.py` khởi tạo Qt, tiếng Việt, log và phiên gần nhất. `ui/` chứa các cửa sổ và model lưới. `core/` xử lý quét, đọc ảnh, cache, lưu và xuất. `assets/` chứa icon và hình hướng dẫn.
- `photo_tags.json` phiên bản 1 gồm `customer_name`, `categories` và `photos`. Mỗi khóa ảnh là một đường dẫn tương đối. Bản ghi lưu `category_ids`, `stars`, `favorite`, `note`, `updated_at` theo UTC và `ai_score` tùy chọn (số nguyên 0–100, `null` hoặc thiếu trường nghĩa là chưa đánh giá).
- `%LOCALAPPDATA%\ChonAnhCuoi` chứa cache thumbnail và `ChonAnhCuoi.log`. Nếu không lưu được phiên, ứng dụng giữ lựa chọn đang chỉnh sửa và hiện nút **Thử lưu lại**. Nếu một phiên khác đang ghi hoặc dữ liệu JSON bị lỗi, ứng dụng mở thư mục ở chế độ chỉ đọc.
