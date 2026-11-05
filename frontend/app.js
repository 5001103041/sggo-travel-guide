// -*- coding: utf-8 -*-
/**
 * app.js - XỬ LÝ TOÀN BỘ LOGIC GIAO DIỆN SGGO! TRAVEL GUIDE
 * Môn học: Công nghệ Phần mềm (COMP1044)
 * 
 * Các nâng cấp mới nhất:
 * 1. Thanh tóm tắt lựa chọn (Breadcrumb bar) xem lại những gì đã chọn
 * 2. Mở rộng 5 mức ngân sách + Tự nhập số tiền mong muốn
 * 3. Hiển thị bình luận 5 sao & Lưu ý giờ cao điểm trực tiếp lên từng thẻ quán
 * 4. Bộ lọc Admin từ A đến Z (Tên, Thể loại, Số sao, Mức giá)
 * 5. Bóc tách tự động thông tin từ link Google Maps
 * 6. Cho phép chỉnh sửa URL ảnh và xem trước ảnh trực tiếp
 */

const API_BASE = window.location.protocol === "file:"
  ? "http://127.0.0.1:8000/api"
  : "/api";

let currentUser = null;
let currentFlowOffset = 0;
let userChoices = { 
  category: null, 
  context: null, 
  price_level: null,
  custom_budget: null 
};
let allPlacesCache = [];
let csvToUploadText = "";
let aiCompanion = "ban_be";
let aiPurpose = "ca_hai";
let drawerMap = null;
let drawerMarker = null;

// ==============================================================================
// TRẠNG THÁI VỊ TRÍ GPS DÙNG CHUNG TOÀN HỆ THỐNG (TAB 1, TAB 2, TAB 3)
// ==============================================================================
let globalUserCoords = null; // { lat, lon, label } - Tọa độ dùng chung cả 3 Tab
let exploreUserCoords = null; // Tọa độ riêng Tab 2 (Tự chọn)
let userGPSCoords = null;    // Tọa độ riêng Tab 3 (Lập lộ trình AI)
let flowPrioritizeGps = false; // Cờ bật ưu tiên khoảng cách gần tôi ở Tab 1 (Khám phá nhanh)

function getAuthHeaders(customHeaders = {}) {
  const headers = { ...customHeaders };
  if (currentUser) {
    if (currentUser.role) headers["X-User-Role"] = currentUser.role;
    if (currentUser.id) headers["X-User-Id"] = String(currentUser.id);
  }
  return headers;
}

function expandClientAddressAbbreviations(text) {
  if (!text) return "";
  let s = " " + String(text) + " ";
  s = s.replace(/(?<=\s|\W)(?:đ|d)\.\s*/gi, "đường ");
  s = s.replace(/(?<=\s|\W)(?:đ|d)\s+(?=[a-zà-ỹ0-9])/gi, "đường ");
  s = s.replace(/(?<=\s|\W)p\.\s*/gi, "phường ");
  s = s.replace(/(?<=\s|\W)p\s*(?=[0-9]+)/gi, "phường ");
  s = s.replace(/(?<=\s|\W)q\.\s*/gi, "quận ");
  s = s.replace(/(?<=\s|\W)q\s*(?=[0-9]+)/gi, "quận ");
  s = s.replace(/(?<=\s|\W)tp\.\s*/gi, "thành phố ");
  s = s.replace(/(?:tp\.?\s*hcm|tp\.?\s*hồ\s*chí\s*minh|tphcm|hồ\s*chí\s*minh)/gi, "thành phố hồ chí minh");
  s = s.replace(/\btttm\b/gi, "trung tâm thương mại");
  s = s.replace(/\bkdc\b/gi, "khu dân cư");
  s = s.replace(/\bt(\d+)\b/gi, "tầng $1");
  return s.replace(/\s+/g, " ").trim();
}

document.addEventListener("DOMContentLoaded", () => {
  loadSavedUser();
  preloadPlaces();
  updateSelectionSummaryUI();
  initCustomSelects();
  onTimePickerChange();

  // Khôi phục GPS toàn cục từ sessionStorage nếu người dùng đã cấp quyền trước đó
  try {
    const savedGlobal = sessionStorage.getItem("sggo_global_coords");
    if (savedGlobal) {
      const parsed = JSON.parse(savedGlobal);
      if (parsed && typeof parsed.lat === "number" && typeof parsed.lon === "number") {
        setGlobalLocation(parsed.lat, parsed.lon, parsed.label || "Vị trí đã lưu", true);
      }
    }
  } catch (e) {}
});

// ==============================================================================
// 1. QUẢN LÝ TÀI KHOẢN & PHÂN QUYỀN (AUTH)
// ==============================================================================

function loadSavedUser() {
  const saved = localStorage.getItem("sggo_current_user");
  if (saved) {
    try {
      currentUser = JSON.parse(saved);
      updateAuthUI();
    } catch (e) {
      localStorage.removeItem("sggo_current_user");
      currentUser = null;
      updateAuthUI();
    }
  } else {
    currentUser = null;
    updateAuthUI();
  }
}

function updateAuthUI() {
  const authContainer = document.getElementById("authContainer");
  const navAdmin = document.getElementById("navAdmin");
