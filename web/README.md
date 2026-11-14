# Khoảnh khắc — bản web Chọn ảnh cưới

Web tĩnh React + TypeScript + Vite, chạy trên GitHub Pages, không cần thuê server. Giao diện tiếng Việt cho điện thoại và PC. App Python/PySide6 ở thư mục gốc tiếp tục hoạt động độc lập.

## Chạy trên máy

Cần Node.js 22.12+ hoặc 24 và npm.

```powershell
cd web
npm ci
npm run dev
```

Mở `http://localhost:5173`. `npm test`, `npm run build` kiểm tra dữ liệu và bản production. Kiểm thử trình duyệt: `npx playwright install chromium` rồi `npm run test:e2e`; hoặc đặt `$env:PLAYWRIGHT_CHANNEL='chrome'` để dùng Chrome đã cài.

## Các tính năng

- Dán link thư mục hoặc tệp Google Drive, quét thư mục con, phân trang API, hỗ trợ resource key và Shared Drive có quyền truy cập. Từ chối đường dẫn trùng vì Drive cho phép nhiều ảnh cùng tên trong cùng thư mục.
- Kết nối Google chỉ xin `drive.readonly`. Có thể đọc thư mục công khai bằng API key riêng. Access token giữ trong bộ nhớ; hết hạn thì người dùng bấm kết nối lại. Không scrape trang Drive, không sửa ảnh nguồn.
- Duyệt thư mục, lọc tên/ghi chú/loại/sao, yêu thích, điểm 0–100, sắp xếp tên/điểm/sao, chọn nhiều ảnh, phím tắt, chế độ tập trung và giao diện tối.
- Gán nhiều loại, sửa tên/màu/phím/giới hạn gói và tên khách hàng; hỏi trước khi vượt gói. `goi_chup.json` hoặc `photo_tags.json` ở gốc Drive/thư mục máy được đọc khi mở lần đầu.
- Xem lớn, zoom/pan, so sánh 2–4 ảnh với góc nhìn đồng bộ; chụm hai ngón tay trên điện thoại.
- Xuất ZIP gồm `danh_sach_anh.xlsx` (tổng hợp + từng loại), `lightroom.txt`, `photo_tags.json`. Danh sách xuất giữ cả ảnh ẩn và ảnh tạm vắng.
- Backup ZIP/JSON tương thích PC hai chiều; giữ đường dẫn, điểm 0, sao, ghi chú, gói và các bản ghi chưa khớp. Có kiểm tra ZIP và xem trước số ảnh/bản ghi, giữ một bản trước khi thay dữ liệu.
- Nhập thư mục/ảnh từ máy vào IndexedDB, xem lại không cần chọn lại tệp; backup kèm ảnh nhập thành bộ mới.
- Tải ảnh đã chọn hoặc RAW đã khớp thành ZIP chia theo loại. RAW ưu tiên đường dẫn, sau đó tên duy nhất; báo thiếu/trùng trước khi tải.
- Bắt buộc đăng nhập Google trước khi vào ứng dụng. Một lần đồng ý cấp quyền danh tính và đọc Drive; Firebase xác thực người dùng. Sau đăng nhập tự mở workspace đang dùng, hiển thị tên bộ ảnh và email tài khoản trên PC/điện thoại.
- Mọi thay đổi loại ảnh, sao, yêu thích, điểm, ghi chú, gói và dữ liệu khôi phục tự đồng bộ Firestore. Web lưu trước vào IndexedDB riêng theo UID, gửi bản mới mỗi khoảng 500 ms, giữ hàng đợi khi mất mạng và tự gửi tiếp khi có mạng. Nhận cập nhật từ thiết bị khác qua onSnapshot và gộp các trường thay đổi bằng transaction để giữ những sửa đổi độc lập.
- AI qua Firebase callable function tùy chọn: thu nhỏ JPEG 1280 px, loại metadata bằng canvas, nhóm tối đa 12, consent riêng, dừng sau nhóm hiện tại, lưu điểm của các nhóm hoàn tất và chỉ gán loại/sao/ghi chú sau khi duyệt.

## Deploy frontend bằng GitHub Actions

Repo: `nvn41091/image-choose`. Địa chỉ dự kiến: `https://nvn41091.github.io/image-choose/`.

1. Repo **Settings → Pages → Source → GitHub Actions**.
2. Push nhánh `main` hoặc `master`. Workflow `.github/workflows/deploy-web.yml` chạy test dữ liệu, test PC/mobile, build và deploy `web/dist`. PR chỉ kiểm tra, không xuất bản.
3. Kiểm tra tab Actions, mở URL trong job `deploy` khi thành công.

Cấu hình Firebase web và OAuth Client ID người dùng cung cấp đã có giá trị mặc định công khai trong `src/config.ts`. Không có Client Secret hoặc Service Account trong repo. Có thể thay bằng **Settings → Secrets and variables → Actions → Variables**:

| Variable | Ý nghĩa |
|---|---|
| `VITE_GOOGLE_CLIENT_ID` | OAuth Client ID loại Web application |
| `VITE_GOOGLE_API_KEY` | Tùy chọn, API key đọc Drive công khai |
| `VITE_FIREBASE_CONFIG` | Toàn bộ Firebase web config dạng JSON thuần, không có `const` |
| `VITE_FIREBASE_REGION` | `asia-southeast1` |

Các biến `VITE_*` luôn công khai trên web. Không dùng cho khóa OpenAI, Client Secret hay JSON admin. Dùng `web/.env.local` khi chạy local hoặc nút **Cấu hình** trong web để ghi đè riêng trên thiết bị. Đổi cấu hình cần tải lại trang.

## Thiết lập Google Drive

Trong Google Cloud project `image-choose`:

1. Bật **Google Drive API** trong APIs & Services.
2. OAuth Client ID phải là **Web application**. Authorized JavaScript origins gồm `https://nvn41091.github.io` và `http://localhost:5173`. Không kèm đường dẫn `/image-choose/`. Luồng GIS popup không cần Client Secret hoặc redirect URI.
3. Cấu hình OAuth consent screen, scope `https://www.googleapis.com/auth/drive.readonly`. Trong chế độ Testing, thêm email sử dụng vào Test users. Tài khoản đó cần được chia sẻ quyền đọc thư mục Drive. Khi phát hành rộng, làm quy trình xác minh scope của Google nếu được yêu cầu.
4. Nếu dùng API key công khai: giới hạn API key theo **Google Drive API**, HTTP referrers `https://nvn41091.github.io/*` và localhost khi cần. API key không giúp truy cập Drive riêng tư. Firebase API key mặc định không tự được dùng làm Drive API key.

Repo này đã có key riêng **Image Choose Web - Google Drive**, chỉ cho Google Drive API và referrer `https://nvn41091.github.io/*`. Key được quản lý trong repository Variable `VITE_GOOGLE_API_KEY`, không ghi giá trị vào mã nguồn. Để trống ô Google API key trong cấu hình thiết bị sẽ dùng key được build từ GitHub Actions; một giá trị nhập riêng vẫn được ưu tiên trên thiết bị đó. Key production không dùng được từ localhost.

Khi chưa kết nối Drive và chưa cấu hình API key, nút **Kết nối Google & mở ảnh** sẽ mở đăng nhập Google ngay từ lần bấm đó, chờ người dùng đồng ý quyền đọc rồi mới quét thư mục. Màn hình đăng nhập đầu ứng dụng dùng chung luồng cấp quyền Google Drive và Firebase. Khi token hết hạn, lần mở tiếp theo yêu cầu kết nối lại; token không được lưu vào localStorage hoặc backup. Nếu Google chặn trình duyệt nhúng của ứng dụng, mở website trực tiếp bằng Chrome/Safari và cho phép popup.

[Google GIS token model](https://developers.google.com/identity/oauth2/web/guides/use-token-model), [Drive files.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list), [Drive resource keys](https://developers.google.com/workspace/drive/api/guides/resource-keys).

## Thiết lập Firebase đồng bộ (không cần server riêng)

Project `image-choose` đã được cấu hình trong phiên triển khai này: Google sign-in đã bật, domain `nvn41091.github.io` đã thêm, Firestore Standard `(default)` đã tạo tại `asia-southeast1`, rules trong repo đã xuất bản. Rules Playground đã kiểm tra: chưa đăng nhập bị chặn, đúng UID được đọc, UID khác bị chặn. Các bước dưới đây dùng khi dựng lại trên project khác. AI và Workload Identity Federation chưa được thiết lập.

1. Firebase Console → project `image-choose` → Authentication → Sign-in method: bật Google và chọn support email của bạn.
2. Authentication → Settings → Authorized domains: thêm `nvn41091.github.io` và `localhost` nếu test local. Màn hình đăng nhập dùng Google Identity Services xin openid/email/profile và drive.readonly, sau đó chuyển access token sang Firebase bằng GoogleAuthProvider.credential + signInWithCredential. Firebase xác thực danh tính cho rules theo UID.
3. Tạo Cloud Firestore **Standard edition** `(default)`, production mode. Chọn vùng phù hợp, ví dụ `asia-southeast1`; cân nhắc trước vì vị trí database không đổi trực tiếp được.
4. Triển khai `firebase/firestore.rules`. Không dùng rules công khai `allow read, write: if true`.

Lần đầu có thể deploy rules từ máy:

```powershell
npx firebase-tools@14 login
npx firebase-tools@14 deploy --only firestore:rules --project image-choose
```

Hoặc cấu hình Google Workload Identity Federation cho repo, cho service account deploy quyền quản lý Firestore rules, rồi tạo repository Variables `FIREBASE_WIF_PROVIDER`, `FIREBASE_DEPLOY_SERVICE_ACCOUNT`. Chạy Actions → **Deploy optional Firebase backend**, bỏ tích `include_ai` để chỉ deploy rules. Workflow không lưu private key dài hạn. Cần tự cấp các quyền IAM phù hợp cho service account theo chức năng triển khai thực tế; không dùng JSON Service Account trong frontend.

Đăng nhập Google trên PC hoặc điện thoại bằng cùng tài khoản: workspace gần nhất tự mở, mọi thao tác lựa chọn tự lưu Firebase. Header luôn hiển thị workspace/email; mục Đồng bộ cho biết trạng thái và có nút thử lại. Khi tải lại trang, phiên Firebase được khôi phục; token Drive chỉ ở bộ nhớ nên có thể cần bấm Kết nối lại Google Drive để đọc ảnh riêng tư. Ảnh nhập từ máy không được upload lên Firestore; muốn xem trên máy khác hãy nhập backup kèm ảnh hoặc đưa ảnh lên Drive.

## AI tùy chọn

Frontend tĩnh không thể dùng an toàn khóa OpenAI của chủ app. Bản web dùng Firebase Function làm proxy, không tái sử dụng đăng nhập ChatGPT qua localhost của app PC. Đây là OpenAI API tính phí riêng, không dùng hạn mức ChatGPT.

1. Firebase Functions cần project bật billing/Blaze; chỉ bật khi chấp nhận chi phí Google Cloud và OpenAI. Có thể dùng toàn bộ chức năng chọn ảnh mà không bật AI.
2. Cài dependencies: từ gốc repo `npm ci --prefix firebase/functions`.
3. Đặt secret: `npx firebase-tools@14 functions:secrets:set OPENAI_API_KEY --project image-choose` (nhập trực tiếp khi CLI hỏi).
4. Đăng nhập web để tạo Firebase user. Lấy UID trong Authentication → Users; tạo `firebase/functions/.env.image-choose` từ `.env.example`, đặt `AI_ALLOWED_UIDS=uid1,uid2` và `AI_DAILY_BATCH_LIMIT=20`. Bỏ trống allowlist nghĩa là AI bị tắt.
5. Deploy: `npx firebase-tools@14 deploy --only functions:photo-review --project image-choose`. Hoặc workflow backend với `include_ai=true` và repository Variable `AI_ALLOWED_UIDS` sau khi cấu hình WIF/IAM và Secret Manager.

Function giới hạn 1 instance, 4 request đồng thời, 20 nhóm/ngày/UID mặc định, 3 giây giữa các nhóm, 60 giây chờ OpenAI. Lượt lỗi vẫn tính vào hạn mức nội bộ. Không tự retry yêu cầu tính phí. Model mặc định `gpt-4.1-mini` có thể đổi trong `firebase/functions/review.js` nếu tài khoản của bạn có quyền model khác hỗ trợ ảnh + Structured Outputs.

Chưa thể kiểm thử AI thật khi chưa có OpenAI secret, allowlist và Firebase Function triển khai. [Firebase callable functions](https://firebase.google.com/docs/functions/callable), [OpenAI phân tích ảnh](https://developers.openai.com/api/docs/guides/images-vision), [Sign in with ChatGPT cho app mã nguồn mở](https://developers.openai.com/siwc/token-sharing-open-source).

## Chuyển dữ liệu PC ↔ web

- PC → web: PC tạo **Sao lưu dữ liệu và ảnh** (ZIP), web chọn **Nhập backup từ PC**. Backup chỉ dữ liệu: mở đúng Drive rồi nhập JSON/ZIP để thay dữ liệu bộ hiện tại; hoặc tạo bộ mới rồi mở Drive và tích dùng lựa chọn hiện tại.
- Web → PC: web chọn **Sao lưu dữ liệu và ảnh** hoặc tải JSON trong **Hoàn tất & xuất**; PC dùng chức năng khôi phục. Giữ cùng cấu trúc thư mục gốc để đường dẫn khớp. Web không tự bỏ thư mục con hoặc đoán theo tên ảnh trùng.
- Bộ ảnh lớn: đưa ảnh lên Google Drive theo đúng cấu trúc, backup chỉ `photo_tags.json`. Backup ZIP có ảnh và ZIP xuất ảnh/RAW trên web tối đa 256 MB tổng dữ liệu để tránh hết RAM trên điện thoại. ZIP64 chưa hỗ trợ. App PC dành cho sao chép và backup bộ RAW/ảnh lớn.

## Giới hạn của trình duyệt

- IndexedDB là bản lưu trên trình duyệt, không tự trở thành cloud. Xóa site data, chế độ riêng tư, thiếu dung lượng hoặc iOS thu hồi storage có thể mất dữ liệu; tải backup hoặc lưu Firebase định kỳ. Web không tự ghi vào thư mục ảnh như app PC.
- Drive lần đầu tải nội dung ảnh để tạo thumbnail 640 px trong cache trên thiết bị; khi mở lớn lấy ảnh gốc. Có tải lười và giới hạn 4 yêu cầu ảnh đồng thời. Bộ hàng nghìn ảnh được chia 60 ảnh/trang để hạn chế RAM; không tải cả bộ ảnh cùng lúc.
- JPEG/PNG/WebP tương thích tốt. TIFF phụ thuộc trình duyệt; chuyển ảnh xem trước sang JPG nếu không xem được. Web không decode RAW.
- Giao diện tùy chỉnh từng thanh công cụ của Qt không được sao chép nguyên bộ; web có bố cục responsive, bộ lọc đóng/mở và chế độ tập trung.
- Đồng bộ tự động bằng snapshot nén tối đa 900 KB trong Firestore; ảnh không nằm trong đó. Transaction gộp thay đổi khác trường và cộng/trừ các loại ảnh; nếu hai thiết bị sửa cùng một trường, lần ghi sau thắng. Lưu ý hạn mức Firestore khi chọn số lượng rất lớn.
- Workspace hiện tại lưu tại users/{uid}/settings/workspace, album tại users/{uid}/albums/{id}. Dữ liệu trên thiết bị nằm trong database IndexedDB riêng theo UID. Dữ liệu từ bản chưa đăng nhập được giữ nguyên và chỉ nhập vào tài khoản khi bấm Nhập dữ liệu cũ.
- Các test trình duyệt dùng route mock Firebase/GIS ở dev server để kiểm tra đăng nhập, phân tách tài khoản, tự mở workspace, tự lưu, mất mạng và cập nhật giữa thiết bị. Bản production không có cờ bỏ qua đăng nhập.
- Chưa có service worker/offline shell; cần mạng để mở website lần đầu, đọc Drive, đồng bộ và dùng AI.

Không commit ảnh cá nhân, bản backup khách hàng, token, OpenAI key, Client Secret hoặc khóa admin lên repo.
