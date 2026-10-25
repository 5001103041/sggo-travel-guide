# SGGo! - Cẩm Nang Du Lịch & Lộ Trình Thông Minh Sài Gòn

Dự án môn học: **Công nghệ Phần mềm (COMP1044)**  
Nhóm sinh viên thực hiện: **SGGo Team**  
Trưởng nhóm: **Trương Khánh Duy**  

### Danh sách thành viên nhóm & Phân công nhiệm vụ:
| STT | Họ và tên | MSSV / Email | Vai trò & Trách nhiệm chính | Nhánh Git phụ trách |
|:---:|:---|:---|:---|:---|
| 1 | **Quách Gia Huy** | `quachhuygiaa2608@gmail.com` | Thiết kế CSDL SQLite, Repository địa điểm và API xác thực người dùng | `feature/auth-and-database` |
| 2 | **Trương Khánh Duy** *(Lead)* | `dora.word.003@gmail.com` | Trưởng nhóm: Tối ưu lộ trình di chuyển bằng Nearest Neighbor TSP và Trợ lý Gemini AI | `feature/ai-routing-engine` |
| 3 | **Nguyễn Thị Kiều My** | `kieumyn528@gmail.com` | Xây dựng giao diện responsive Tailwind CSS và Bản đồ số Leaflet OpenStreetMap | `feature/frontend-map-layout` |
| 4 | **Lê Trương Thảo Nguyên** | `letruongthaonguyen2006@gmail.com` | Xử lý luồng khám phá nhanh 3 bước, danh sách yêu thích và Dashboard Admin CMS | `feature/client-logic-admin` |
| 5 | **Phan Thị Ngọc Minh** | `50011030411@student.hcmue.edu.vn` (50011030411) | Bộ kiểm thử tự động pytest, CI/CD pipeline và Hồ sơ đặc tả môn CNPM | `feature/testing-documentation` |

## 1. Giới thiệu
SGGo! là nền tảng web hướng dẫn du lịch và đề xuất lộ trình văn hóa - ẩm thực thông minh tại TP.HCM với kho 201 địa điểm thực tế xác thực qua Google Maps.

## 2. Hướng dẫn cài đặt & khởi chạy Backend
```bash
# Cài đặt môi trường ảo Python
python -m venv venv
venv\Scripts\activate  # Trên Windows

# Cài đặt thư viện phụ thuộc
pip install -r backend/requirements.txt

# Khởi chạy server API (Uvicorn)
uvicorn backend.main:app --reload --port 8000
```
Truy cập tài liệu API tự động tại: `http://localhost:8000/docs`

## 3. Kiến Trúc Hệ Thống & Tính Năng Nổi Bật
- **Hệ thống bản đồ tương tác (Leaflet + OpenStreetMap):** Ghim 201 địa điểm đặc trưng với icon tùy biến, lọc theo danh mục, tính khoảng cách thực tế.
- **Thuật toán tối ưu lộ trình (Nearest Neighbor):** Tự động sắp xếp thứ tự ghé thăm nhiều trạm để giảm thiểu quãng đường di chuyển (bài toán TSP).
- **Trợ lý văn hóa thông minh (Google Gemini AI + Dynamic Dwell Fitting):** Gợi ý lịch trình cá nhân hóa dựa trên giờ rảnh, đối tượng đi cùng và ngân sách, kèm lời bình văn hóa bản địa sâu sắc.
- **Phân quyền người dùng & CSDL SQLite:** Hỗ trợ đăng ký, đăng nhập, quản trị địa điểm CRUD và trích xuất tọa độ Google Maps tự động.
- **Đặc tả & Kiểm thử chuyên nghiệp:** Đầy đủ sơ đồ Use Case, Activity Diagram, BPMN 2.0.2 và bộ test tự động pytest 27 test cases đạt 100% pass.

## 4. Hướng dẫn chạy kiểm thử
```bash
pytest tests/ -v
```
