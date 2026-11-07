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
