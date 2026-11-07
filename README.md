# SGGo! — Cẩm Nang Du Lịch & Lập Lịch Trình Thông Minh TP.HCM (Sài Gòn)

> **Đồ án môn học:** Công nghệ Phần mềm (COMP1044)  
> **Nhóm sinh viên thực hiện:** SGGo Team  
> **Trưởng nhóm:** Quách Gia Huy  

---

## 1. Giới Thiệu Dự Án

**SGGo! (Sài Gòn Go!)** là nền tảng web ứng dụng hỗ trợ người dân và du khách khám phá ẩm thực, văn hóa và lập lịch trình di chuyển thông minh tại Thành phố Hồ Chí Minh. Nền tảng sở hữu kho dữ liệu thực tế gồm **hơn 200 địa điểm** được xác thực (quán ăn, cà phê, điểm di tích, bảo tàng, workshop thủ công, khu vui chơi) trải dài khắp các quận trung tâm TP.HCM.

Hệ thống tích hợp thuật toán tối ưu lộ trình nhiều điểm dừng (**TSP Nearest Neighbor**) kết hợp mô hình trí tuệ nhân tạo **Google Gemini AI** nhằm cá nhân hóa lịch trình theo thời gian rảnh thực tế, ngân sách, bối cảnh bạn đồng hành và ghi chú khẩu vị/sở thích riêng.

---

## 2. Các Tính Năng Nổi Bật

### 🌟 Tab 1: Khám Phá Địa Điểm (Explore & Discover)
* **Kho dữ liệu 200+ địa điểm thực tế:** Phân chia rõ ràng giữa Ẩm thực (Ăn uống) và Điểm đến (Tham quan & Vui chơi).
* **Bộ lọc đa tiêu chí:** Lọc tức thì theo Thể loại, Quận (Quận 1, 3, 5, 10, Bình Thạnh...), Khoảng giá, Giờ mở/đóng cửa và Địa điểm đề cử.
* **Thông tin chuyên sâu từ Google Maps:**
  * Điểm đánh giá ⭐ và số lượt nhận xét thực tế.
  * Khung giờ cao điểm (`peak_hours`) kèm trạng thái đông khách.
  * **Đánh giá tiêu biểu 5★** trích xuất từ nhận xét thực tế của khách hàng.
  * **Lưu ý & phản hồi thực tế** (bãi đỗ xe, lưu ý phục vụ, giờ đông).
  * Nút mở trực tiếp trang chỉ đường Google Maps chính thức.

### 🗺️ Tab 2: Tự Chọn Địa Điểm & Bản Đồ Hành Trình (Interactive Map)
* **Bản đồ tương tác Leaflet & OpenStreetMap:** Hiển thị vị trí trực quan với các điểm ghim phân biệt danh mục.
* **Định vị GPS thời gian thực (HTML5 Geolocation):** Xác định vị trí người dùng tức thì (0ms) để tính khoảng cách và định tuyến.
* **Tính cự ly chuẩn xác:** Kết hợp mô hình trắc địa **Haversine** và định tuyến đường phố thực tế **OSRM (OpenStreetMap)**.
* **Tự chọn trạm dừng thủ công:** Cho phép người dùng tự chọn danh sách quán yêu thích và xem lộ trình tối ưu chống ngược đường.

### 🧭 Tab 3: Lập Lịch Trình Thông Minh SGGo Planner (AI & Heuristic TSP)
* **Động cơ gợi ý lai 2 lớp (Hybrid Pipeline):**
  1. *Lớp 1 (Backend Python Rule-based):* Sàng lọc cứng giờ mở cửa, thể loại, chấm điểm độ phù hợp bạn đồng hành (Tier 1 / Tier 2 / Tier 3) và giới hạn ngân sách.
  2. *Lớp 2 (Google Gemini AI):* Thấu hiểu ngữ nghĩa sâu của ghi chú riêng (**Take note**), đối chiếu với bình luận thực tế để loại trừ món kiêng cữ/dị ứng và chọn không gian chuẩn gu.
* **Mô hình Dừng Chân Lai 7 Nhóm Học Thuật (Hybrid Dwell Allocation):**
  * Tự động phân bổ thời lượng lưu lại phù hợp cho từng loại hình quán (cà phê: 45-60p, quán lẩu/nướng: 70-90p, workshop: 75-105p, di tích: 45-60p).
  * **Bộ co giãn tự động theo giờ rảnh:** Điều chỉnh thời gian dừng chân để tổng thời gian (di chuyển + dừng chân) luôn vừa vặn trong khung giờ rảnh của người dùng.
* **Kiểm soát ràng buộc chặt chẽ (Business Rule 3):**
  * Tự động phát hiện và cảnh báo khi khung giờ rảnh quá ngắn hoặc ngân sách không đủ cho số trạm mong muốn (`TIME_TOO_SHORT`, `BUDGET_TOO_LOW`).
  * Nút hỗ trợ *"Tự động áp dụng điều chỉnh gợi ý"* với 1 chạm.
* **Báo cáo phân tích lộ trình chuyên sâu:**
  * Tiếp nhận và trích dẫn nổi bật yêu cầu trong Take note.
  * Tách bạch rõ ràng: *Vì sao chọn Trạm 1*, *Vì sao chọn Trạm 2*, *Vì sao chọn Trạm 3*.
  * Giải thích *Logic kết hợp lộ trình* (dòng chảy trải nghiệm xuyên suốt chuyến đi).
* **Cảnh báo giờ cao điểm theo thời gian thực ghé quán:**
  * Trùng giờ cao điểm $\rightarrow$ Cảnh báo màu đỏ nổi bật kèm lời khuyên đặt bàn.
  * Không trùng giờ cao điểm $\rightarrow$ Thông báo màu xanh trấn an người dùng yên tâm trải nghiệm.
* **Điều hướng liên hoàn Google Maps Multi-stop:** Xuất đường dẫn chỉ đường xe máy liên hoàn qua tất cả các trạm dừng (`travelmode=two_wheeler`).

### ⚙️ Tab 4: Bảng Điều Khiển Quản Trị (Admin Dashboard)
* **Quản trị địa điểm toàn diện (CRUD):** Thêm mới, chỉnh sửa thông tin, xóa quán, gán nhãn quán đề cử, ẩn/hiện quán (`is_hidden`).
* **Trích xuất thông minh từ Google Maps URL:** Tự động giải mã kinh độ, vĩ độ GPS, tên quán và địa chỉ từ link Google Maps.
* **Nhập / Xuất dữ liệu đa năng:** Hỗ trợ Import file CSV dữ liệu hàng loạt và tải file CSV mẫu chuẩn.
* **Quản trị người dùng & Phân quyền:** Quản lý danh sách tài khoản, chuyển đổi quyền Admin / User.

---

## 3. Cấu Trúc Thư Mục Dự Án

```text
chonchodichoi11/
├── backend/
│   ├── main.py                 # FastAPI Application, REST Endpoints & Logic định tuyến AI
│   ├── database.py             # SQLite Data Access Layer, Schema & Seed Data
│   ├── enriched_places.json    # Kho dữ liệu gốc 200+ địa điểm đã chuẩn hóa
│   ├── requirements.txt        # Thư viện phụ thuộc backend
│   ├── sggo.db                 # CSDL SQLite lưu trữ dữ liệu thực tế
│   ├── check_stats.py          # Script kiểm tra trạng thái CSDL & Fallback
│   └── test_routing_math.py    # Kiểm thử độc lập công thức Haversine
├── frontend/
│   ├── index.html              # Giao diện chính người dùng (Responsive Web App)
│   ├── app.js                  # Frontend State, Leaflet Map, Fetch API & DOM Rendering
│   ├── style.css               # Tùy biến UI, Animations & Custom Scrollbar
│   └── images/                 # Kho ảnh địa điểm đã được tối ưu
│       ├── places/
│       └── verified/
├── tests/
│   ├── test_api.py             # Kiểm thử REST API Endpoints (Health check, Places, 404)
│   ├── test_routing.py         # Kiểm thử thuật toán Haversine, Nearest Neighbor TSP, Dwell
│   └── test_sggo_suite.py      # Bộ 53 test cases kiểm thử tự động RTM & Business Rules
├── main.py                     # Entrypoint phục vụ Cloud Deployment (Render / Railway)
├── render.yaml                 # Cấu hình triển khai tự động lên nền tảng Render
├── requirements.txt            # Thư viện phụ thuộc cấp root
├── run_app.bat                 # Script chạy nhanh 1 chạm trên Windows
└── README.md                   # Tài liệu hướng dẫn dự án
```

---

## 4. Hướng Dẫn Cài Đặt & Khởi Chạy

### Cách 1: Khởi chạy nhanh bằng File Script (Dành cho Windows)
Chỉ cần nhấp đúp vào file **`run_app.bat`** tại thư mục gốc. Hệ thống sẽ tự động:
1. Mở sẵn trình duyệt tại địa chỉ `http://127.0.0.1:8000`.
2. Khởi động máy chủ backend FastAPI với chế độ tự động reload.

### Cách 2: Khởi chạy thủ công qua Terminal / Command Prompt

**Bước 1:** Khởi tạo môi trường ảo Python (khuyên dùng Python 3.11+):
```bash
# Tạo môi trường ảo
python -m venv venv

# Kích hoạt trên Windows:
venv\Scripts\activate

# Hoặc trên macOS / Linux:
source venv/bin/activate
```

**Bước 2:** Cài đặt các thư viện cần thiết:
```bash
pip install -r requirements.txt
```

**Bước 3 (Tùy chọn):** Cấu hình Google Gemini API Key:
Sao chép file mẫu và cấu hình API Key:
```bash
cp backend/.env.example backend/.env
```
Mở file `backend/.env` và điền key của bạn:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
*(Lưu ý: Nếu không cấu hình Gemini API Key, hệ thống vẫn hoạt động bình thường 100% nhờ Động cơ Định tuyến Heuristic Rule-based dự phòng tích hợp sẵn).*

**Bước 4:** Khởi chạy máy chủ:
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Truy cập giao diện web tại: **`http://localhost:8000`**  
Xem tài liệu OpenAPI tương tác (Swagger UI) tại: **`http://localhost:8000/docs`**

---

## 5. Hướng Dẫn Chạy Toàn Bộ Bộ Kiểm Thử (Unit Tests)
