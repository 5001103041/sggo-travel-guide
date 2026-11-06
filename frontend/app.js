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
  const viewAdmin = document.getElementById("viewAdmin");

  if (currentUser && currentUser.role === "admin") {
    // CHỈ TÀI KHOẢN ADMIN MỚI ĐƯỢC HIỆN NÚT ADMIN
    authContainer.innerHTML = `
      <div class="flex items-center gap-1.5 bg-rose-50 border border-rose-200/90 px-2.5 py-1 rounded-xl shadow-sm whitespace-nowrap">
        <span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse flex-shrink-0"></span>
        <span class="text-xs font-black text-rose-700">Admin</span>
        <button onclick="handleLogout()" title="Đăng xuất" class="ml-1 text-[11px] font-bold px-2 py-0.5 rounded-lg bg-rose-100 hover:bg-rose-200 text-rose-700 transition flex items-center gap-1">
          <i class="fa-solid fa-arrow-right-from-bracket text-[10px]"></i> Thoát
        </button>
      </div>
    `;
    if (navAdmin) {
      navAdmin.classList.remove("hidden");
      navAdmin.style.setProperty("display", "inline-flex", "important");
    }
  } else if (currentUser) {
    // NGƯỜI DÙNG THƯỜNG -> ẨN TUYỆT ĐỐI NÚT ADMIN
    authContainer.innerHTML = `
      <div class="flex items-center gap-1.5 bg-slate-100 border border-slate-200 px-2.5 py-1 rounded-xl shadow-sm whitespace-nowrap">
        <span class="text-xs font-bold text-slate-800 truncate max-w-[90px] flex items-center gap-1"><i class="fa-solid fa-user text-slate-400 text-[10px]"></i> ${currentUser.username || 'User'}</span>
        <button onclick="handleLogout()" title="Đăng xuất" class="ml-1 text-[11px] font-bold px-2 py-0.5 rounded-lg bg-white hover:bg-rose-50 text-slate-600 hover:text-[#E11D48] border border-slate-200 transition flex items-center gap-1">
          <i class="fa-solid fa-arrow-right-from-bracket text-[10px]"></i> Thoát
        </button>
      </div>
    `;
    if (navAdmin) {
      navAdmin.classList.add("hidden");
      navAdmin.style.setProperty("display", "none", "important");
    }
    if (viewAdmin && !viewAdmin.classList.contains("hidden")) {
      switchMode("flow");
    }
  } else {
    // CHƯA ĐĂNG NHẬP (KHÁCH VÃNG LAI) -> ẨN TUYỆT ĐỐI NÚT ADMIN
    authContainer.innerHTML = `
      <button onclick="openAuthModal()" id="btnAuth" class="px-3.5 py-1.5 rounded-xl text-xs font-bold bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 shadow-sm transition flex items-center gap-1.5 whitespace-nowrap flex-shrink-0">
        <i class="fa-regular fa-user text-slate-400"></i>
        <span>Đăng nhập</span>
      </button>
    `;
    if (navAdmin) {
      navAdmin.classList.add("hidden");
      navAdmin.style.setProperty("display", "none", "important");
    }
    if (viewAdmin && !viewAdmin.classList.contains("hidden")) {
      switchMode("flow");
    }
  }

  // Cập nhật lại danh sách quán để hiện / ẩn nút "Sửa quán (Admin)" ngay lập tức
  if (allPlacesCache && allPlacesCache.length > 0) {
    const gridEl = document.getElementById("allPlacesGrid");
    if (gridEl && gridEl.children.length > 0) {
      filterAllPlaces();
    }
  }
}

function openAuthModal() {
  document.getElementById("modalAuth").classList.remove("hidden");
}

function closeAuthModal() {
  document.getElementById("modalAuth").classList.add("hidden");
}

function setAuthTab(tab) {
  const formLogin = document.getElementById("formLogin");
  const formRegister = document.getElementById("formRegister");
  const tabLogin = document.getElementById("tabLogin");
  const tabRegister = document.getElementById("tabRegister");

  if (tab === "login") {
    formLogin.classList.remove("hidden");
    formRegister.classList.add("hidden");
    tabLogin.className = "flex-1 pb-3 text-xs font-bold border-b-2 border-[#E11D48] text-[#E11D48]";
    tabRegister.className = "flex-1 pb-3 text-xs font-bold text-slate-400";
  } else {
    formLogin.classList.add("hidden");
    formRegister.classList.remove("hidden");
    tabRegister.className = "flex-1 pb-3 text-xs font-bold border-b-2 border-emerald-600 text-emerald-600";
    tabLogin.className = "flex-1 pb-3 text-xs font-bold text-slate-400";
  }
}

function fillDemoAccount(user, pass) {
  setAuthTab("login");
  document.getElementById("loginUsername").value = user;
  document.getElementById("loginPassword").value = pass;
}

async function handleLogin(e) {
  e.preventDefault();
  const u = document.getElementById("loginUsername").value.trim();
  const p = document.getElementById("loginPassword").value.trim();

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Đăng nhập thất bại");

    currentUser = data.user;
    localStorage.setItem("sggo_current_user", JSON.stringify(currentUser));
    updateAuthUI();
    closeAuthModal();
    alert(`Xin chào ${currentUser.full_name}! Bạn đã đăng nhập thành công.`);

    if (currentUser.role === "admin") {
      switchMode("admin");
    } else {
      switchMode("flow");
    }
  } catch (err) {
    alert("Lỗi: " + err.message);
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const name = document.getElementById("regFullName").value.trim();
  const u = document.getElementById("regUsername").value.trim();
  const p = document.getElementById("regPassword").value.trim();

  try {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p, full_name: name })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Đăng ký thất bại");

    currentUser = data.user;
    localStorage.setItem("sggo_current_user", JSON.stringify(currentUser));
    updateAuthUI();
    closeAuthModal();
    alert(`Đăng ký thành công! Chào mừng ${currentUser.full_name} đến với SGGo.`);
  } catch (err) {
    alert("Lỗi: " + err.message);
  }
}

function handleLogout() {
  if (confirm("Bạn có chắc chắn muốn đăng xuất tài khoản?")) {
    currentUser = null;
    localStorage.removeItem("sggo_current_user");
    updateAuthUI();
    switchMode("flow");
  }
}

// ==============================================================================
// 2. TẢI DỮ LIỆU & ĐIỀU HƯỚNG TABS
// ==============================================================================

async function preloadPlaces() {
  try {
    const res = await fetch(`${API_BASE}/places`);
    allPlacesCache = await res.json();
    const countEl = document.getElementById("totalPlacesCount");
    if (countEl) countEl.innerText = allPlacesCache.length;
  } catch (e) {
    console.warn("Backend offline hoặc đang nạp CSDL.");
  }
}

function switchMode(mode) {
  const isAdmin = currentUser && currentUser.role === "admin";
  if (mode === "admin" && !isAdmin) {
    alert("Quyền truy cập bị từ chối: Khu vực này chỉ dành riêng cho Quản trị viên (Admin)!");
    openAuthModal();
    switchMode("flow");
    return;
  }

  document.getElementById("viewFlow").classList.toggle("hidden", mode !== "flow");
  document.getElementById("viewAI").classList.toggle("hidden", mode !== "ai");
  document.getElementById("viewAll").classList.toggle("hidden", mode !== "all");
  const viewAdmin = document.getElementById("viewAdmin");
  if (viewAdmin) viewAdmin.classList.toggle("hidden", mode !== "admin");

  // Khóa cuộn trang toàn cục trên màn hình desktop khi ở Tab 3 để chỉ cuộn độc lập 2 bên
  document.body.classList.toggle("ai-tab-active", mode === "ai");

  const standardTabs = {
    flow: document.getElementById("navFlow"),
    ai: document.getElementById("navAI"),
    all: document.getElementById("navAll")
  };

  Object.keys(standardTabs).forEach(k => {
    if (standardTabs[k]) {
      standardTabs[k].className = (k === mode) ? "tab-pill active whitespace-nowrap" : "tab-pill whitespace-nowrap";
    }
  });

  const navAdmin = document.getElementById("navAdmin");
  if (navAdmin) {
    if (isAdmin) {
      navAdmin.classList.remove("hidden");
      navAdmin.style.setProperty("display", "inline-flex", "important");
      navAdmin.className = (mode === "admin")
        ? "tab-pill active text-rose-600 font-extrabold whitespace-nowrap"
        : "tab-pill text-rose-600 font-bold whitespace-nowrap";
    } else {
      navAdmin.classList.add("hidden");
      navAdmin.style.setProperty("display", "none", "important");
    }
  }

  if (mode === "flow") {
    updateFlowGpsUI();
  }
  if (mode === "all") {
    if (!exploreUserCoords && (userGPSCoords || globalUserCoords)) {
      const src = userGPSCoords || globalUserCoords;
      setExploreLocationPreset(src.label || "Vị trí GPS của bạn", src.lat, src.lon);
    } else {
      filterAllPlaces();
    }
  }
  if (mode === "admin" && isAdmin) loadAdminDashboard();
}

function parsePlaceTiers(tagsStr) {
  if (!tagsStr || typeof tagsStr !== "string") return { tier1: [], tier2: [] };
  const str = tagsStr.trim();
  if (str.includes("tier1:") || str.includes("tier2:")) {
    const parts = str.split("|");
    let t1 = [], t2 = [];
    parts.forEach(p => {
      const trimmed = p.trim();
      if (trimmed.startsWith("tier1:")) {
        t1 = trimmed.replace("tier1:", "").split(",").map(x => x.trim()).filter(Boolean);
      } else if (trimmed.startsWith("tier2:")) {
        t2 = trimmed.replace("tier2:", "").split(",").map(x => x.trim()).filter(Boolean);
      }
    });
    return { tier1: t1, tier2: t2 };
  } else {
    const all = str.split(",").map(x => x.trim()).filter(Boolean);
    return { tier1: all.slice(0, 2), tier2: all.slice(2) };
  }
}

function onAdminTagChange(tag, tier) {
  const chkT1 = document.getElementById(`chk_t1_${tag}`);
  const chkT2 = document.getElementById(`chk_t2_${tag}`);
  if (tier === 1 && chkT1 && chkT1.checked) {
    if (chkT2) chkT2.checked = false;
  } else if (tier === 2 && chkT2 && chkT2.checked) {
    if (chkT1) chkT1.checked = false;
  }
  syncAdminTagsInput();
}

function syncAdminTagsInput() {
  const allTags = ['di_1_minh', 'hen_ho', 'nhom_ban', 'gia_dinh'];
  const t1 = [];
  const t2 = [];
  allTags.forEach(t => {
    const c1 = document.getElementById(`chk_t1_${t}`);
    const c2 = document.getElementById(`chk_t2_${t}`);
    if (c1 && c1.checked) t1.push(t);
    if (c2 && c2.checked) t2.push(t);
  });
  const hiddenInp = document.getElementById("formTags");
  if (hiddenInp) {
    hiddenInp.value = `tier1:${t1.join(",")}|tier2:${t2.join(",")}`;
  }
}

function isPlaceCurrentlyOpen(openStr, closeStr) {
  if (!openStr || !closeStr || openStr === "Chưa rõ" || closeStr === "Chưa rõ") return true;
  const now = new Date();
  const currentMinutes = now.getHours() * 60 + now.getMinutes();

  const [oH, oM] = openStr.split(":").map(Number);
  const [cH, cM] = closeStr.split(":").map(Number);
  if (isNaN(oH) || isNaN(cH)) return true;
  const openMinutes = oH * 60 + (oM || 0);
  const closeMinutes = cH * 60 + (cM || 0);

  if (openMinutes === closeMinutes) return true;

  if (closeMinutes < openMinutes) {
    // Mở xuyên đêm qua ngày hôm sau (ví dụ: 07:00 - 02:00, 10:00 - 04:00, 06:30 - 00:00)
    // Quán đang mở nếu: Đã qua giờ mở hôm nay (>= openMinutes) HOẶC chưa tới giờ đóng sáng hôm sau (<= closeMinutes)
    return currentMinutes >= openMinutes || currentMinutes <= closeMinutes;
  } else {
    // Mở trong ngày thông thường (ví dụ: 08:00 - 22:00)
    return currentMinutes >= openMinutes && currentMinutes <= closeMinutes;
  }
}

// ==============================================================================
// 2.5 HỆ THỐNG ĐỒNG BỘ ĐỊNH VỊ GPS LIÊN THÔNG 3 TAB (TAB 1, TAB 2, TAB 3)
// ==============================================================================

function setGlobalLocation(lat, lon, labelText = "Vị trí GPS của bạn", syncTabs = true) {
  const numLat = parseFloat(lat);
  const numLon = parseFloat(lon);
  if (isNaN(numLat) || isNaN(numLon)) return;

  globalUserCoords = { lat: numLat, lon: numLon, label: labelText };
  exploreUserCoords = { lat: numLat, lon: numLon };
  userGPSCoords = { lat: numLat, lon: numLon };

  try {
    sessionStorage.setItem("sggo_global_coords", JSON.stringify(globalUserCoords));
  } catch (e) {}

  if (syncTabs) {
    // 1. Đồng bộ sang Tab 2 (Tự chọn)
    const expInput = document.getElementById("exploreLocationInput");
    if (expInput) expInput.value = labelText;
    const expBadge = document.getElementById("exploreGpsStatusBadge");
    if (expBadge) expBadge.classList.remove("hidden");
    const expClear = document.getElementById("btnClearExploreLoc");
    if (expClear) expClear.classList.remove("hidden");
    const expBtn = document.getElementById("btnExploreGPS");
    if (expBtn) {
      expBtn.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-300"></i> <span>Đã nhận GPS</span>`;
      expBtn.disabled = false;
    }

    // 2. Đồng bộ sang Tab 3 (Lộ trình AI)
    const aiInput = document.getElementById("aiStartLoc");
    if (aiInput) aiInput.value = labelText;
    const aiIcon = document.getElementById("gpsStatusIcon");
    if (aiIcon) aiIcon.classList.remove("hidden");
    const aiBtn = document.getElementById("btnGetGPS");
    if (aiBtn) {
      aiBtn.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-600"></i> <span class="text-emerald-700">Đã nhận GPS</span>`;
      aiBtn.disabled = false;
    }
  }

  updateFlowGpsUI();
}

function clearGlobalLocation() {
  globalUserCoords = null;
  exploreUserCoords = null;
  userGPSCoords = null;
  flowPrioritizeGps = false;

  try {
    sessionStorage.removeItem("sggo_global_coords");
  } catch (e) {}

  // 1. Reset Tab 1
  updateFlowGpsUI();
  const stepFinish = document.getElementById("stepFinish");
  if (stepFinish && !stepFinish.classList.contains("hidden")) {
    showFinishResults(0);
  }

  // 2. Reset Tab 2
  const expInput = document.getElementById("exploreLocationInput");
  const expBadge = document.getElementById("exploreGpsStatusBadge");
  const expClear = document.getElementById("btnClearExploreLoc");
  const expBtn = document.getElementById("btnExploreGPS");
  const radiusSelect = document.getElementById("allRadiusFilter");
  if (expInput) expInput.value = "";
  if (expBadge) expBadge.classList.add("hidden");
  if (expClear) expClear.classList.add("hidden");
  if (expBtn) expBtn.innerHTML = `<i class="fa-solid fa-crosshairs"></i> <span>Dùng GPS hiện tại</span>`;
  if (radiusSelect) radiusSelect.value = "all";

  const sortSelect = document.getElementById("allSortFilter");
  if (sortSelect && sortSelect.value === "distance_asc") {
    sortSelect.value = "default";
  }

  // 3. Reset Tab 3
  const aiInput = document.getElementById("aiStartLoc");
  const aiIcon = document.getElementById("gpsStatusIcon");
  const aiBtn = document.getElementById("btnGetGPS");
  if (aiInput) aiInput.value = "";
  if (aiIcon) aiIcon.classList.add("hidden");
  if (aiBtn) {
    aiBtn.innerHTML = `<i class="fa-solid fa-location-crosshairs"></i> <span>Dùng GPS hiện tại</span>`;
    aiBtn.disabled = false;
  }
}

function updateFlowGpsUI() {
  const btn = document.getElementById("btnFlowToggleGps");
  if (!btn) return;
  btn.disabled = false;

  if (globalUserCoords && flowPrioritizeGps) {
    btn.className = "text-[11px] font-extrabold px-3 py-1 rounded-full border border-emerald-400 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 transition flex items-center gap-1.5 shadow-2xs cursor-pointer select-none";
    btn.setAttribute("title", `Vị trí: ${globalUserCoords.label} - Bấm để tắt ưu tiên khoảng cách`);
    btn.innerHTML = `
      <i class="fa-solid fa-circle-check text-emerald-600 text-xs"></i>
      <span>Đang ưu tiên gần tôi</span>
      <span onclick="event.stopPropagation(); clearGlobalLocation();" class="text-slate-400 hover:text-rose-600 ml-0.5 p-0.5 rounded cursor-pointer" title="Hủy vị trí GPS">
        <i class="fa-solid fa-xmark text-[10px]"></i>
      </span>
    `;
  } else if (globalUserCoords && !flowPrioritizeGps) {
    btn.className = "text-[11px] font-bold px-3 py-1 rounded-full border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 transition flex items-center gap-1.5 shadow-2xs cursor-pointer select-none";
    btn.setAttribute("title", `Đã nhận vị trí: ${globalUserCoords.label} - Bấm để bật ưu tiên gần bạn`);
    btn.innerHTML = `
      <i class="fa-solid fa-location-dot text-emerald-600 text-xs"></i>
      <span>Bật ưu tiên gần tôi</span>
      <span onclick="event.stopPropagation(); clearGlobalLocation();" class="text-slate-400 hover:text-rose-600 ml-0.5 p-0.5 rounded cursor-pointer" title="Hủy vị trí GPS">
        <i class="fa-solid fa-xmark text-[10px]"></i>
      </span>
    `;
  } else {
    btn.className = "text-[11px] font-bold px-3 py-1 rounded-full border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 transition flex items-center gap-1.5 shadow-2xs cursor-pointer select-none";
    btn.setAttribute("title", "Bấm 1 lần dùng chung GPS cho cả 3 Tab (Ưu tiên quán gần bạn)");
    btn.innerHTML = `<i class="fa-solid fa-location-crosshairs text-slate-400 text-xs"></i><span>Ưu tiên gần tôi (GPS)</span>`;
  }
}

function toggleFlowGpsPriority() {
  const btn = document.getElementById("btnFlowToggleGps");
  if (globalUserCoords) {
    flowPrioritizeGps = !flowPrioritizeGps;
    updateFlowGpsUI();
    // Nếu đang mở danh sách kết quả của Khám phá nhanh thì tính toán lại ngay
    const stepFinish = document.getElementById("stepFinish");
    if (stepFinish && !stepFinish.classList.contains("hidden")) {
      showFinishResults(0);
    }
    return;
  }

  if (!navigator.geolocation) {
    alert("Trình duyệt của bạn không hỗ trợ định vị GPS Geolocation.");
    return;
  }

  if (btn) {
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-emerald-600 text-xs"></i> <span>Đang lấy GPS...</span>`;
    btn.disabled = true;
  }

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      flowPrioritizeGps = true;
      const label = `GPS (${lat.toFixed(4)}, ${lon.toFixed(4)})`;
      setGlobalLocation(lat, lon, label, true);
      // setGlobalLocation() tự động gọi updateFlowGpsUI() -> mở khóa nút và đổi ngay sang biểu tượng tích xanh (không còn quay)

      const stepFinish = document.getElementById("stepFinish");
      if (stepFinish && !stepFinish.classList.contains("hidden")) {
        showFinishResults(0);
      }
    },
    (err) => {
      updateFlowGpsUI();
      alert("Không thể lấy vị trí GPS: " + err.message + ". Bạn vẫn có thể trải nghiệm Khám phá nhanh 3 bước bình thường!");
    },
    { timeout: 8000, enableHighAccuracy: true }
  );
}

// ==============================================================================
// 3. KHÁM PHÁ NHANH & THANH TÓM TẮT LỰA CHỌN (BREADCRUMB)
// ==============================================================================

function updateSelectionSummaryUI() {
  const catEl = document.getElementById("summaryCategory");
  const ctxEl = document.getElementById("summaryContext");
  const bdgEl = document.getElementById("summaryBudget");
  if (!catEl || !ctxEl || !bdgEl) return;

  // 1. Cập nhật Mục đích
  if (userChoices.category === "an_uong") {
    catEl.innerHTML = `<span class="truncate">1. Đi Ăn Uống</span>`;
    catEl.className = "cursor-pointer py-1.5 px-2 rounded-xl border border-rose-300 bg-rose-50 text-[#E11D48] font-black shadow-xs transition flex items-center justify-center gap-1 text-center truncate";
  } else if (userChoices.category === "di_choi") {
    catEl.innerHTML = `<span class="truncate">1. Đi Vui Chơi</span>`;
    catEl.className = "cursor-pointer py-1.5 px-2 rounded-xl border border-teal-300 bg-teal-50 text-teal-800 font-black shadow-xs transition flex items-center justify-center gap-1 text-center truncate";
  } else {
    catEl.innerHTML = `<span class="truncate">1. Mục đích</span>`;
    catEl.className = "cursor-pointer py-1.5 px-2 rounded-xl border border-slate-200 bg-slate-50 text-slate-500 hover:border-[#E11D48] hover:bg-rose-50/60 transition flex items-center justify-center gap-1 text-center truncate";
  }

  // 2. Cập nhật Bối cảnh
  const ctxMap = {
    "di_1_minh": "2. Đi 1 mình",
    "nguoi_yeu": "2. Cặp đôi",
    "ban_be": "2. Nhóm bạn",
    "gia_dinh": "2. Gia đình"
  };
  if (userChoices.context && userChoices.context in ctxMap) {
    ctxEl.innerHTML = `<span class="truncate">${ctxMap[userChoices.context]}</span>`;
    ctxEl.className = "cursor-pointer py-1.5 px-2 rounded-xl border border-rose-300 bg-rose-50 text-[#E11D48] font-black shadow-xs transition flex items-center justify-center gap-1 text-center truncate";
  } else {
    ctxEl.innerHTML = `<span class="truncate">2. Đi cùng</span>`;
    ctxEl.className = "cursor-pointer py-1.5 px-2 rounded-xl border border-slate-200 bg-slate-50 text-slate-500 hover:border-[#E11D48] hover:bg-rose-50/60 transition flex items-center justify-center gap-1 text-center truncate";
  }

  // 3. Cập nhật Ngân sách
  const bdgMap = {
    "free": "3. Miễn phí (0đ)",
    "under_50k": "3. < 50k",
    "50k_100k": "3. 50k - 100k",
    "100k_250k": "3. 100k - 250k",
    "above_250k": "3. > 250k",
    "all": "3. Tùy duyên"
  };
  if (userChoices.price_level === "custom" && userChoices.custom_budget) {
    const formatted = userChoices.custom_budget >= 1000000 
      ? (userChoices.custom_budget / 1000000).toFixed(1) + 'Tr' 
      : (userChoices.custom_budget / 1000) + 'k';
    bdgEl.innerHTML = `<span class="truncate">3. ${formatted}</span>`;
    bdgEl.className = "cursor-pointer py-1.5 px-2 rounded-xl border border-rose-300 bg-rose-50 text-[#E11D48] font-black shadow-xs transition flex items-center justify-center gap-1 text-center truncate";
  } else if (userChoices.price_level && userChoices.price_level in bdgMap) {
    bdgEl.innerHTML = `<span class="truncate">${bdgMap[userChoices.price_level]}</span>`;
    bdgEl.className = "cursor-pointer py-1.5 px-2 rounded-xl border border-rose-300 bg-rose-50 text-[#E11D48] font-black shadow-xs transition flex items-center justify-center gap-1 text-center truncate";
  } else {
    bdgEl.innerHTML = `<span class="truncate">3. Ngân sách</span>`;
    bdgEl.className = "cursor-pointer py-1.5 px-2 rounded-xl border border-slate-200 bg-slate-50 text-slate-500 hover:border-[#E11D48] hover:bg-rose-50/60 transition flex items-center justify-center gap-1 text-center truncate";
  }
}

function selectAnswer(key, value, nextStep) {
  userChoices[key] = value;
  currentFlowOffset = 0;
  if (key === "price_level") {
    userChoices.custom_budget = null;
  }
  updateSelectionSummaryUI();
  initCustomSelects();

  if (nextStep === "finish") {
    showFinishResults(0);
  } else {
    document.querySelectorAll(".step-card").forEach(el => el.classList.add("hidden"));
    document.getElementById(`step${nextStep}`).classList.remove("hidden");
  }
}

function handleCustomBudgetSubmit() {
  const input = document.getElementById("customBudgetInput");
  const val = parseInt(input.value);
  if (!val || val <= 0) {
    alert("Vui lòng nhập một số tiền hợp lệ (ví dụ: 75000)!");
    return;
  }
  // Nếu người dùng nhập số tiền quá nhỏ dưới 20.000đ
  if (val < 20000) {
    // Hỗ trợ trường hợp người dùng gõ tắt số tròn nghìn (ví dụ gõ 100 với ý 100.000đ)
    if (val >= 20 && val <= 999) {
      const suggestVal = val * 1000;
      if (confirm(`Bạn vừa nhập "${val.toLocaleString()}đ". Có phải bạn muốn tìm quán với ngân sách "${suggestVal.toLocaleString()}đ" không?`)) {
        input.value = suggestVal;
        userChoices.price_level = "custom";
        userChoices.custom_budget = suggestVal;
        currentFlowOffset = 0;
        updateSelectionSummaryUI();
        initCustomSelects();
        showFinishResults(0);
        return;
      }
    }
    alert("Ngân sách tự nhập tối thiểu cho ăn uống tại TP.HCM là 20.000đ (hoặc chọn '0đ' để xem địa điểm tham quan miễn phí). Vui lòng nhập số tiền từ 20.000đ trở lên nhé!");
    return;
  }
  userChoices.price_level = "custom";
  userChoices.custom_budget = val;
  currentFlowOffset = 0;
  updateSelectionSummaryUI();
  initCustomSelects();
  showFinishResults(0);
}


function goBackStep(step) {
  document.querySelectorAll(".step-card").forEach(el => el.classList.add("hidden"));
  document.getElementById(`step${step}`).classList.remove("hidden");
}

function restartFlow() {
  userChoices = { category: null, context: null, price_level: null, custom_budget: null };
  currentFlowOffset = 0;
  const customInp = document.getElementById("customBudgetInput");
  if (customInp) customInp.value = "";
  updateSelectionSummaryUI();
  initCustomSelects();
  document.querySelectorAll(".step-card").forEach(el => el.classList.add("hidden"));
  document.getElementById("step1").classList.remove("hidden");
}

async function showFinishResults(offset = 0) {
  currentFlowOffset = Math.max(0, offset);
  document.querySelectorAll(".step-card").forEach(el => el.classList.add("hidden"));
  const finishContainer = document.getElementById("stepFinish");
  finishContainer.classList.remove("hidden");

  // Cập nhật trạng thái nút Quay lại 3 quán trước
  const btnPrev = document.getElementById("btnPrevFlow");
  if (btnPrev) {
    btnPrev.disabled = (currentFlowOffset <= 0);
  }

  // Cập nhật badge tóm tắt tiêu chí khoa học
  const criteriaBadge = document.getElementById("finishCriteriaBadge");
  if (criteriaBadge) {
    const catText = userChoices.category === "an_uong" ? "Ẩm thực" : (userChoices.category === "di_choi" ? "Điểm đến" : "Mục đích");
    const ctxMap = { "di_1_minh": "Đi 1 mình", "nguoi_yeu": "Cặp đôi", "ban_be": "Bạn bè", "gia_dinh": "Gia đình" };
    const bdgMap = { "under_50k": "< 50k", "50k_100k": "50k-100k", "100k_250k": "100k-250k", "above_250k": "> 250k" };
    const ctxText = ctxMap[userChoices.context] || "Đồng hành";
    let bdgText = bdgMap[userChoices.price_level] || "Ngân sách";
    if (userChoices.price_level === "custom" && userChoices.custom_budget) {
      bdgText = `${userChoices.custom_budget.toLocaleString()}đ`;
    }
    criteriaBadge.innerHTML = "";
  }

  const resultsBox = document.getElementById("flowResults");
  resultsBox.innerHTML = `<div class="p-8 text-center text-xs text-slate-500 font-bold"><i class="fa-solid fa-spinner fa-spin mr-2"></i> Đang tìm kiếm và chọn lọc địa điểm phù hợp nhất...</div>`;

  try {
    const activeCoords = globalUserCoords || exploreUserCoords || userGPSCoords;
    const now = new Date();
    const clientTimeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    const payload = { 
      ...userChoices, 
      offset: currentFlowOffset,
      user_lat: activeCoords ? activeCoords.lat : null,
      user_lon: activeCoords ? activeCoords.lon : null,
      prioritize_distance: Boolean(flowPrioritizeGps && activeCoords),
      client_time: clientTimeStr
    };
    const res = await fetch(`${API_BASE}/quick-recommend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const places = await res.json();

    const fallbackEl = document.getElementById("flowFallbackNotice");
    if (fallbackEl) {
      const closedItem = places.find(p => p.closed_warning);
      const freeItem = places.find(p => p.free_fallback_notice);
      if (closedItem && closedItem.closed_warning) {
        fallbackEl.innerHTML = `<i class="fa-solid fa-moon text-indigo-600 mr-2 text-sm flex-shrink-0"></i><span>${closedItem.closed_warning}</span>`;
        fallbackEl.classList.remove("hidden");
      } else if (freeItem && freeItem.free_fallback_notice) {
        fallbackEl.innerHTML = `<i class="fa-solid fa-circle-info text-amber-600 mr-2 text-sm flex-shrink-0"></i><span>${freeItem.free_fallback_notice}</span>`;
        fallbackEl.classList.remove("hidden");
      } else {
        fallbackEl.classList.add("hidden");
      }
    }

    renderFinishCards(places);
  } catch (e) {
    resultsBox.innerHTML = `<div class="p-4 bg-red-50 text-red-600 rounded-xl text-xs">Chưa thể kết nối CSDL Backend.</div>`;
  }
}

function prevFlowResults() {
  if (currentFlowOffset >= 3) {
    currentFlowOffset -= 3;
    showFinishResults(currentFlowOffset);
    document.getElementById("stepFinish")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function rotateFlowResults() {
  currentFlowOffset += 3;
  showFinishResults(currentFlowOffset);
  document.getElementById("stepFinish")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// HÀM HIỂN THỊ ẢNH CHÂN THỰC: 1 LÀ ẢNH THẬT, 2 LÀ HIỂN THỊ "CHƯA CÓ ẢNH" (KHÔNG DÙNG ẢNH ẢO)
function renderPlaceImage(p, widthClass = "w-full", heightClass = "h-full", customClass = "") {
  const imgSrc = p.image_url;
  if (imgSrc && imgSrc.trim()) {
    return `
      <img src="${imgSrc}" onerror="this.outerHTML='<div class=\'${widthClass} ${heightClass} bg-slate-100 rounded-2xl flex flex-col items-center justify-center text-slate-400 border border-slate-200 select-none\'><i class=\'fa-solid fa-camera text-slate-300 text-xl mb-1\'></i><span class=\'text-[11px] font-bold text-slate-400\'>Chưa có ảnh</span></div>';" class="${widthClass} ${heightClass} object-cover rounded-2xl shadow-inner ${customClass}" alt="${p.name}" />
    `;
  }
  return `
    <div class="${widthClass} ${heightClass} bg-slate-100 border border-slate-200 rounded-2xl flex flex-col items-center justify-center text-slate-400 select-none ${customClass}">
      <i class="fa-solid fa-camera text-slate-300 text-2xl mb-1"></i>
      <span class="text-[11px] font-bold text-slate-400">Chưa có ảnh</span>
    </div>
  `;
}

// ==============================================================================
// TAB 1: THẺ GỢI Ý KẾT QUẢ 2 CỘT RỘNG RÃI (DÀNH RIÊNG CHO TAB KHÁM PHÁ NHANH)
// CỰC KỲ NHẤN MẠNH: TÊN QUÁN, SỐ SAO (NGAY DƯỚI TÊN), GIÁ TIỀN, MỞ CỬA, 2 COMMENT
// ==============================================================================
function buildRecommendCardHTML(p, idx) {
  const isEat = p.category === "an_uong";
  const hasHours = Boolean(p.hours_display || (p.open_time && p.close_time));
  const isOpen = (typeof p.is_currently_open === "boolean")
    ? p.is_currently_open
    : isPlaceCurrentlyOpen(p.open_time, p.close_time);
  const gmapsUrl = p.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.name + ' ' + p.address)}`;

  const isFree = (p.min_price === 0 && p.max_price === 0);
  const cleanPrice = p.price_display ? p.price_display.replace(/Khoảng\s*/gi, "").replace(/\(.*?\)/g, "").trim() : null;
  const priceRangeFormatted = cleanPrice
    ? cleanPrice
    : (isFree
      ? "Miễn phí vé vào cổng"
      : `${p.min_price ? p.min_price.toLocaleString() + 'đ' : ''} – ${p.max_price ? p.max_price.toLocaleString() + 'đ' : ''}`);

  // Làm sạch và định dạng Giờ cao điểm (Nhấn mạnh nổi bật đồng điệu với Mức giá)
  const rawPeak = (p.peak_hours && p.peak_hours !== 'Chưa rõ') ? p.peak_hours : '';
  const cleanPeakHours = rawPeak.replace(/\s*\([^\)]*đông[^\)]*\)/gi, '').trim();
  const hasPeak = Boolean(cleanPeakHours && cleanPeakHours !== 'Chưa rõ');
  const cleanPeakHoursText = hasPeak ? cleanPeakHours : 'Chưa rõ (quán chưa cập nhật)';
  const peakHoursFontSize = !hasPeak 
    ? 'text-xs font-semibold text-amber-800/80 italic' 
    : (cleanPeakHours.length > 20 ? 'text-base sm:text-lg' : 'text-xl sm:text-2xl');

  // Khoảng cách: CHỈ HIỂN THỊ KHI NGƯỜI DÙNG CÓ BẬT ĐỊNH VỊ GPS VÀ CÓ KHOẢNG CÁCH
  let distanceHTML = "";
  const distVal = (typeof p.distance_km === "number" && !isNaN(p.distance_km)) 
    ? p.distance_km 
    : ((typeof p.distanceKm === "number" && !isNaN(p.distanceKm)) ? p.distanceKm : null);
  const userHasCoords = Boolean(globalUserCoords || exploreUserCoords || userGPSCoords);

  if (distVal !== null && userHasCoords) {
    const isWalk = distVal <= 0.6;
    const walkTime = Math.max(1, Math.round(distVal * 12));
    const bikeTime = Math.max(1, Math.round(distVal * 2.5));
    const distStr = distVal < 1 ? `${Math.round(distVal * 1000)}m` : `${distVal.toFixed(1)} km`;

    distanceHTML = `
      <span class="ml-2 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold ${isWalk ? 'bg-emerald-100 text-emerald-900 border border-emerald-300' : 'bg-blue-100 text-blue-900 border border-blue-300'} whitespace-nowrap inline-flex items-center gap-1">
        <i class="fa-solid ${isWalk ? 'fa-person-walking' : 'fa-motorcycle'} text-[11px]"></i>
        <span>Cách bạn ${distStr}</span>
        <span class="font-normal opacity-85">(${isWalk ? `~${walkTime}p đi bộ` : `~${bikeTime}p xe máy`})</span>
      </span>
    `;
  }

  const imageHtml = renderPlaceImage(p, "w-full", "h-full");

  return `
    <div class="recommend-card-2col">
      <div class="grid grid-cols-1 md:grid-cols-12 gap-6 md:gap-7 items-stretch">
        
        <!-- ==================== CỘT TRÁI (45% - FACTS & THÔNG TIN CỐT LÕI) ==================== -->
        <div class="md:col-span-5 flex flex-col justify-between">
          <div>
            <!-- Ảnh Quán Lớn + Badge Thứ Hạng + Trạng Thái Mở Cửa Nhấn Mạnh Ngay Trên Ảnh (KHÔNG CLICK VÀO ẢNH) -->
            <div class="relative w-full h-52 sm:h-56 rounded-2xl overflow-hidden mb-3.5 border border-slate-200/90 shadow-xs select-none">
              ${imageHtml}
              <!-- Container 2 Badge Tránh Đè Lẫn Nhau -->
              <div class="absolute top-3 left-3 right-3 flex items-center justify-between gap-2 pointer-events-none">
                <!-- Badge Thứ hạng -->
                <span class="text-xs font-black uppercase text-white bg-[#E11D48] px-3 py-1 rounded-xl shadow-md shrink-0">
                  GỢI Ý #${idx + 1}
                </span>
                <!-- TRẠNG THÁI MỞ CỬA: RÚT GỌN TINH TẾ, KHÔNG TRÀN LẤN -->
                ${p.closed_warning ? `
                  <span class="bg-amber-600/95 backdrop-blur-xs text-white text-[11px] font-black px-2.5 py-1 rounded-full shadow-md flex items-center gap-1.5 uppercase tracking-wide shrink-0">
                    <i class="fa-solid fa-clock text-xs"></i>
                    <span>Mở lúc ${p.open_time} sáng mai</span>
                  </span>
                ` : (hasHours ? (isOpen ? `
                  <span class="bg-emerald-600/95 backdrop-blur-xs text-white text-[11px] font-black px-2.5 py-1 rounded-full shadow-md flex items-center gap-1.5 uppercase tracking-wide shrink-0">
                    <span class="w-2 h-2 rounded-full bg-white animate-pulse"></span>
                    <span>Đang mở cửa</span>
                  </span>
                ` : `
                  <span class="bg-rose-600/95 backdrop-blur-xs text-white text-[11px] font-black px-2.5 py-1 rounded-full shadow-md flex items-center gap-1.5 uppercase tracking-wide shrink-0">
                    <span class="w-2 h-2 rounded-full bg-white"></span>
                    <span>Đã đóng cửa</span>
                  </span>
                `) : '')}
              </div>
            </div>

            <!-- Thể loại & Quận & Tag đề cử (Gom thành 1 hàng ngang tinh tế) -->
            <div class="flex items-center gap-2 flex-wrap mb-2.5">
              <span class="text-[11px] font-black uppercase text-[#E11D48] bg-[#FFE4E6] px-2.5 py-0.5 rounded-lg tracking-wider">
                ${isEat ? 'Ẩm Thực Sài Gòn' : 'Điểm Đến & Vui Chơi'}
              </span>
              ${p.district ? `
                <span class="text-[11px] font-bold text-slate-600 bg-slate-100 border border-slate-200 px-2.5 py-0.5 rounded-lg flex items-center gap-1">
                  <i class="fa-solid fa-location-dot text-[#E11D48] text-[10px]"></i>
                  <span>${p.district}</span>
                </span>
              ` : ''}
              ${distanceHTML}
              ${p.is_admin_choice === 1 ? '<span class="text-[10px] bg-amber-100 text-amber-900 font-extrabold px-2 py-0.5 rounded-md border border-amber-300 flex items-center gap-1"><i class="fa-solid fa-crown text-amber-600"></i> Quán Đề Cử</span>' : ''}
            </div>

            ${p.closed_warning ? `
              <div class="mb-2.5 p-2.5 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800 flex items-start gap-2">
                <i class="fa-solid fa-moon text-amber-600 mt-0.5"></i>
                <span><strong>Lưu ý:</strong> ${p.closed_warning}</span>
              </div>
            ` : ''}
            <!-- Tên quán (Headline lớn, đậm nét) -->
            <h3 onclick="openPlaceDetailById(${p.id})" class="font-black text-slate-900 text-xl sm:text-2xl tracking-tight leading-snug mb-2 hover:text-[#E11D48] transition cursor-pointer" title="Bấm để xem chi tiết quán">
              ${p.name}
            </h3>

            <!-- SỐ SAO & ĐÁNH GIÁ (GỌN GÀNG, KHÔNG BAO GIỜ BỊ TRÀN HÀNG) -->
            <div class="flex items-center gap-2.5 mb-4 flex-nowrap">
              ${(p.rating && p.rating > 0) ? `
              <div class="rating-pill-prominent shadow-2xs shrink-0">
                <i class="fa-solid fa-star text-amber-500 text-sm"></i>
                <span class="text-base font-black text-amber-950">${p.rating}</span>
                <span class="text-xs text-amber-700 font-extrabold">/ 5.0</span>
              </div>` : `
              <div class="rating-pill-prominent shadow-2xs shrink-0 bg-slate-100 text-slate-500 border border-slate-200">
                <i class="fa-regular fa-star text-slate-400 text-sm"></i>
                <span class="text-xs font-bold text-slate-600">Chưa có sao</span>
              </div>`}
              <span class="text-xs font-bold text-slate-500 truncate">${(p.reviews_count && p.reviews_count > 0) ? `(${parseInt(p.reviews_count).toLocaleString()} đánh giá)` : '(Chưa có đánh giá)'}</span>
            </div>
          </div>

          <!-- MỨC GIÁ: CỰC KỲ NHẤN MẠNH RIÊNG BIỆT Ở ĐÁY CỘT TRÁI -->
          <div class="price-block-prominent">
            <div class="flex items-center justify-between w-full mb-1">
              <span class="text-[11px] font-black uppercase text-slate-500 tracking-wider flex items-center gap-1.5 whitespace-nowrap">
                <i class="fa-solid fa-wallet text-[#E11D48] text-xs flex-shrink-0"></i>
                <span class="whitespace-nowrap">Mức giá tham khảo</span>
              </span>
            </div>
            <div class="flex items-baseline gap-1.5 whitespace-nowrap">
              <span class="text-xl sm:text-2xl font-black text-emerald-800 tracking-tight whitespace-nowrap">
                ${priceRangeFormatted}
              </span>
            </div>
          </div>
        </div>

        <!-- ==================== CỘT PHẢI (55% - EXPERIENCE, 2 REVIEWS & ACTIONS) ==================== -->
        <div class="md:col-span-7 flex flex-col justify-between pl-0 md:pl-6 md:border-l md:border-slate-200/90 pt-5 md:pt-0 border-t md:border-t-0 border-slate-200/90">
          <div>
            <!-- Giờ Cao Điểm: Nhấn mạnh nổi bật tương tự Mức giá -->
            <div class="peak-hours-prominent mb-4">
              <div class="flex items-center justify-between w-full mb-1">
                <span class="text-[11px] font-black uppercase text-amber-800 tracking-wider flex items-center gap-1.5 whitespace-nowrap">
                  <i class="fa-solid fa-clock-rotate-left text-amber-600 text-xs flex-shrink-0"></i>
                  <span>Giờ cao điểm</span>
                </span>
              </div>
              <div class="flex items-baseline gap-1.5">
                <span class="${peakHoursFontSize} font-black text-amber-950 tracking-tight leading-tight">
                  ${cleanPeakHoursText}
                </span>
              </div>
            </div>

            <!-- 2 KHỐI COMMENT KHEN & CHÊ: CỰC KỲ NHẤN MẠNH DẠNG REVIEW CARDS -->
            <div class="space-y-3 mb-5">
              <!-- Khối Khen 5 sao -->
              <div class="review-card-khen shadow-2xs">
                <div class="flex items-center justify-between mb-1.5">
                  <span class="font-black text-emerald-950 uppercase text-xs tracking-wider flex items-center gap-1.5">
                    <i class="fa-solid fa-thumbs-up text-emerald-600 text-sm"></i>
                    <span>Đánh giá tiêu biểu từ Google Maps (5★):</span>
                  </span>
                </div>
                <p class="font-medium italic text-emerald-950 text-[13px] leading-relaxed">
                  ${p.best_review ? `"${p.best_review}"` : '<span class="text-slate-400 not-italic">Chưa có nhận xét khen</span>'}
                </p>
              </div>

              <!-- Khối Lưu ý / Góp ý -->
              <div class="review-card-luuy shadow-2xs">
                <div class="flex items-center justify-between mb-1.5">
                  <span class="font-black text-rose-950 uppercase text-xs tracking-wider flex items-center gap-1.5">
                    <i class="fa-solid fa-triangle-exclamation text-[#E11D48] text-sm"></i>
                    <span>Lưu ý & phản hồi thực tế từ Google Maps:</span>
                  </span>
                </div>
                <p class="font-medium italic text-slate-800 text-[13px] leading-relaxed">
                  ${p.worst_review ? `"${p.worst_review}"` : '<span class="text-slate-400 not-italic">Chưa có lưu ý đặc biệt</span>'}
                </p>
              </div>
            </div>
          </div>

          <!-- Hàng Nút Hành Động (Đáy cột phải) -->
          <div class="pt-4 border-t border-slate-100 flex items-center justify-between flex-wrap gap-2.5">
            <!-- Cụm trái: Chi tiết quán -->
            <div class="flex items-center gap-2">
              <button onclick="openPlaceDetailById(${p.id})" title="Xem đầy đủ thông tin" class="px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer shadow-xs">
                <i class="fa-solid fa-circle-info text-slate-600"></i>
                <span>Chi tiết quán</span>
              </button>
            </div>

            <!-- Cụm phải: Nút Sửa quán (Admin) đặt ngay sát bên cạnh Nút Google Maps -->
            <div class="flex items-center gap-2">
              ${(currentUser && currentUser.role === 'admin') ? `
                <button onclick="openEditPlaceModalById(${p.id})" title="Sửa dữ liệu quán" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer shadow-sm whitespace-nowrap">
                  <i class="fa-solid fa-pen-to-square"></i>
                  <span>Sửa quán</span>
                </button>
              ` : ''}
              <a href="${gmapsUrl}" target="_blank" title="Mở trang Google Maps chính thức của quán" class="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-black transition flex items-center gap-2 shadow-sm whitespace-nowrap">
                <i class="fa-brands fa-google text-sm"></i>
                <span>Google Maps</span>
                <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
              </a>
            </div>
          </div>
        </div>

      </div>
    </div>
  `;
}

// Render 3 quán kết quả bước Finish (Sử dụng Thẻ Gợi Ý 2 Cột Cực Kỳ Nhấn Mạnh)
function renderFinishCards(places) {
  const resultsBox = document.getElementById("flowResults");
  resultsBox.innerHTML = "";

  if (!places || places.length === 0) {
    resultsBox.innerHTML = `<div class="p-8 text-center text-xs text-slate-500 bg-white rounded-2xl border border-slate-200">Không tìm thấy địa điểm phù hợp, vui lòng thử lại tiêu chí khác.</div>`;
    return;
  }

  places.forEach((p, idx) => {
    resultsBox.innerHTML += buildRecommendCardHTML(p, currentFlowOffset + idx);
  });
}

// ==============================================================================
// 4. LẬP LỘ TRÌNH AI (ĐỊNH TUYẾN THÔNG MINH GPS & GEMINI AI)
// ==============================================================================

let leafletMap = null;
let leafletMarkersGroup = null;

function getCurrentGPSLocation() {
  const btn = document.getElementById("btnGetGPS");
  const input = document.getElementById("aiStartLoc");
  const icon = document.getElementById("gpsStatusIcon");

  if (!navigator.geolocation) {
    alert("Trình duyệt của bạn không hỗ trợ định vị GPS Geolocation.");
    return;
  }

  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Đang lấy GPS...</span>`;
  btn.disabled = true;

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const label = `Vị trí GPS hiện tại (${lat.toFixed(4)}, ${lon.toFixed(4)})`;
      flowPrioritizeGps = true;
      setGlobalLocation(lat, lon, label, true);
    },
    (err) => {
      alert("Không thể lấy vị trí GPS: " + err.message + ". Bạn có thể nhập địa chỉ hoặc bấm vào các nút gợi ý có sẵn.");
      btn.innerHTML = `<i class="fa-solid fa-location-crosshairs"></i> <span>Dùng GPS hiện tại</span>`;
      btn.disabled = false;
    },
    { timeout: 8000, enableHighAccuracy: true }
  );
}

function setStartLocation(loc) {
  document.getElementById("aiStartLoc").value = loc;
  userGPSCoords = null;
  const icon = document.getElementById("gpsStatusIcon");
  if (icon) icon.classList.add("hidden");
  const btn = document.getElementById("btnGetGPS");
  if (btn) btn.innerHTML = `<i class="fa-solid fa-location-crosshairs"></i> <span>Dùng GPS hiện tại</span>`;
}

function setFreeTimePreset(timeStr) {
  document.getElementById("aiTime").value = timeStr;
}

function selectAICompanion(val) {
  aiCompanion = val;
  const map = {
    di_1_minh: "comp_di_1_minh",
    nguoi_yeu: "comp_nguoi_yeu",
    ban_be: "comp_ban_be",
    gia_dinh: "comp_gia_dinh"
  };
  Object.keys(map).forEach(k => {
    const btn = document.getElementById(map[k]);
    if (!btn) return;
    if (k === val) {
      btn.className = "companion-chip active py-2.5 px-3 rounded-xl border-2 border-[#E11D48] bg-rose-50 font-bold text-[#E11D48] shadow-xs transition flex items-center justify-center gap-1.5 cursor-pointer text-center";
    } else {
      btn.className = "companion-chip py-2.5 px-3 rounded-xl border border-slate-200 bg-white font-bold text-slate-600 hover:border-slate-300 transition flex items-center justify-center gap-1.5 cursor-pointer text-center";
    }
  });
}

function selectAIPurpose(val) {
  aiPurpose = val;
  const map = {
    an_uong: "purp_an_uong",
    di_choi: "purp_di_choi",
    ca_hai: "purp_ca_hai"
  };
  Object.keys(map).forEach(k => {
    const btn = document.getElementById(map[k]);
    if (!btn) return;
    if (k === val) {
      btn.className = "purpose-chip active py-2.5 px-3 rounded-xl border-2 border-[#E11D48] bg-rose-50 font-bold text-[#E11D48] shadow-xs transition flex items-center justify-center gap-1.5 cursor-pointer text-center";
    } else {
      btn.className = "purpose-chip py-2.5 px-3 rounded-xl border border-slate-200 bg-white font-bold text-slate-600 hover:border-slate-300 transition flex items-center justify-center gap-1.5 cursor-pointer text-center";
    }
  });
}

function appendTakeNote(text) {
  const input = document.getElementById("aiTakeNote");
  if (!input) return;
  if (!input.value.trim()) {
    input.value = text;
  } else if (!input.value.includes(text)) {
    input.value = `${input.value.trim()}, ${text}`;
  }
}

function setContextPreset(ctxStr) {
  appendTakeNote(ctxStr);
}

function toggleItineraryMap() {
  const wrapper = document.getElementById("itineraryMapWrapper");
  const btn = document.getElementById("btnToggleMap");
  if (!wrapper) return;
  
  if (wrapper.classList.contains("hidden")) {
    wrapper.classList.remove("hidden");
    if (btn) btn.innerHTML = `<i class="fa-solid fa-chevron-up"></i> <span>Thu gọn bản đồ</span>`;
    setTimeout(() => {
      if (leafletMap) leafletMap.invalidateSize();
    }, 200);
  } else {
    wrapper.classList.add("hidden");
    if (btn) btn.innerHTML = `<i class="fa-solid fa-map"></i> <span>Hiện bản đồ</span>`;
  }
}

// Cấu hình các lớp bản đồ tương tác (Google Maps, OpenStreetMap, Vệ tinh) - Hoàn toàn không bị lỗi 'API key required'
function initLeafletTileLayers(mapInstance) {
  // 1. Google Maps Đường Phố (Mặc định: cực nét, 100% tiếng Việt chuẩn Sài Gòn, tốc độ cao, không cần API key)
  const googleStreets = L.tileLayer("https://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", {
    maxZoom: 20,
    subdomains: ["mt0", "mt1", "mt2", "mt3"],
    attribution: '&copy; <a href="https://maps.google.com" target="_blank" rel="noopener noreferrer">Google Maps</a>'
  });

  // 2. OpenStreetMap Chuẩn (Nguồn mở quốc tế)
  const osmStandard = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    subdomains: "abc",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>'
  });

  // 3. Google Maps Vệ Tinh Lai (Hybrid Satellite kèm tên đường)
  const googleHybrid = L.tileLayer("https://{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", {
    maxZoom: 20,
    subdomains: ["mt0", "mt1", "mt2", "mt3"],
    attribution: '&copy; Google Satellite'
  });

  // Mặc định nạp lớp bản đồ Google Maps vào bản đồ
  googleStreets.addTo(mapInstance);

  const baseLayers = {
    "Bản đồ đường phố (Google)": googleStreets,
    "Bản đồ giao thông (OSM)": osmStandard,
    "Ảnh vệ tinh Google": googleHybrid
  };

  // Tùy chọn: Nếu người dùng đã đăng ký key miễn phí tại carto.com/basemaps/apikey
  const cartoApiKey = window.CARTO_API_KEY || localStorage.getItem("CARTO_API_KEY");
  if (cartoApiKey) {
    const cartoLayer = L.tileLayer(`https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=${cartoApiKey}`, {
      attribution: '&copy; CARTO',
      subdomains: "abcd",
      maxZoom: 20
    });
    baseLayers["Bản đồ CartoDB"] = cartoLayer;
  }

  try {
    L.control.layers(baseLayers, null, { position: "topright", collapsed: true }).addTo(mapInstance);
  } catch (e) {
    console.warn("Không thể khởi tạo bộ chọn lớp bản đồ:", e);
  }

  return googleStreets;
}

// Hàm hỗ trợ thiết lập hoặc xóa Carto API key tùy chọn
window.setCartoApiKey = function(key) {
  if (key && key.trim()) {
    localStorage.setItem("CARTO_API_KEY", key.trim());
    alert("Đã lưu CARTO API Key thành công! Vui lòng tải lại trang (F5) để hiển thị thêm lớp CartoDB.");
  } else {
    localStorage.removeItem("CARTO_API_KEY");
    alert("Đã xóa CARTO API Key! Bản đồ tiếp tục dùng Google Maps mặc định.");
  }
};

function renderItineraryMap(startCoords, steps) {
  const mapContainer = document.getElementById("itineraryMap");
  if (!mapContainer || typeof L === "undefined") return;

  if (!leafletMap) {
    leafletMap = L.map("itineraryMap", {
      zoomControl: true,
      scrollWheelZoom: false
    });
    initLeafletTileLayers(leafletMap);
    leafletMarkersGroup = L.featureGroup().addTo(leafletMap);
  } else {
    leafletMarkersGroup.clearLayers();
  }

  const points = [];

  // 1. Marker Điểm xuất phát
  if (startCoords && startCoords.lat && startCoords.lon) {
    const startLatLng = [startCoords.lat, startCoords.lon];
    points.push(startLatLng);

    const startIcon = L.divIcon({
      className: "custom-leaflet-marker",
      html: `<div style="background-color: #10B981; color: white; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 2.5px solid white;"><i class="fa-solid fa-location-dot"></i></div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 32],
      popupAnchor: [0, -32]
    });

    L.marker(startLatLng, { icon: startIcon })
      .bindPopup(`<strong>Điểm xuất phát</strong><br>${document.getElementById("aiStartLoc").value}`)
      .addTo(leafletMarkersGroup);
  }

  // 2. Markers cho các trạm
  const colors = ["#E11D48", "#2563EB", "#059669", "#D97706"];
  steps.forEach((s, idx) => {
    if (s.lat && s.lon) {
      const latLng = [s.lat, s.lon];
      points.push(latLng);

      const stepIcon = L.divIcon({
        className: "custom-leaflet-marker",
        html: `<div style="background-color: ${colors[idx] || '#E11D48'}; color: white; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 2.5px solid white;">${idx + 1}</div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 32],
        popupAnchor: [0, -32]
      });

      const popupHtml = `
        <div style="min-width: 170px; font-family: sans-serif; line-height: 1.4;">
          <div style="font-weight: 800; font-size: 12px; color: #0F172A;">Trạm ${idx + 1}: ${s.action}</div>
          <div style="font-weight: 700; color: #E11D48; margin-top: 3px;">${s.location}</div>
          <div style="font-size: 11px; color: #64748B; margin-top: 2px;"><i class="fa-regular fa-clock" style="margin-right: 4px;"></i>${s.time}</div>
          ${s.must_try_tip ? `<div style="font-size: 11px; color: #047857; margin-top: 3px; font-weight: 600;"><i class="fa-regular fa-lightbulb" style="margin-right: 4px;"></i>${s.must_try_tip}</div>` : ''}
        </div>
      `;

      L.marker(latLng, { icon: stepIcon })
        .bindPopup(popupHtml)
        .addTo(leafletMarkersGroup);
    }
  });

  // 3. Vẽ polyline nối các trạm
  if (points.length >= 2) {
    L.polyline(points, {
      color: "#2563EB",
      weight: 4,
      opacity: 0.85,
      dashArray: "6, 8"
    }).addTo(leafletMarkersGroup);
    leafletMap.fitBounds(leafletMarkersGroup.getBounds(), { padding: [40, 40] });
  }

  setTimeout(() => {
    if (leafletMap) leafletMap.invalidateSize();
  }, 350);
}

// ==============================================================================
// 4.1 QUẢN LÝ NGÂN SÁCH, SỐ TRẠM & RÀNG BUỘC TAB 3 (G6-FR03, G6-FR05, G6-FR06)
// ==============================================================================

let aiBudgetLevel = "100k_250k";
let aiTargetBudget = 250000;
let aiShuffleSeed = 0;
let aiNumStops = 3;
let aiRadiusKm = null;

function selectAIStops(stops) {
  aiNumStops = stops;
  [2, 3, 4].forEach(s => {
    const btn = document.getElementById(`aistops_${s}`);
    if (btn) {
      if (s === stops) {
        btn.className = "companion-chip active py-2.5 px-3 rounded-xl border-2 border-[#E11D48] bg-rose-50 font-bold text-[#E11D48] shadow-xs transition text-center cursor-pointer";
      } else {
        btn.className = "companion-chip py-2.5 px-3 rounded-xl border border-slate-200 bg-white font-bold text-slate-600 hover:border-slate-300 transition text-center cursor-pointer";
      }
    }
  });
  const displayEl = document.getElementById("aiStopsDisplay");
  if (displayEl) {
    if (stops === 2) displayEl.innerText = "2 trạm (Nhanh gọn - 1 đến 2 tiếng)";
    else if (stops === 3) displayEl.innerText = "3 trạm (Tiêu chuẩn - 2 đến 3.5 tiếng)";
    else if (stops === 4) displayEl.innerText = "4 trạm (Khám phá trọn vẹn - 3.5 đến 5 tiếng)";
  }
}

function onTimePickerChange() {
  const startEl = document.getElementById("aiStartTime");
  const endEl = document.getElementById("aiEndTime");
  const displayEl = document.getElementById("aiFreeTimeDisplay");
  const hiddenTimeEl = document.getElementById("aiTime");

  if (!startEl || !endEl) return;

  const startVal = startEl.value || "14:00";
  const endVal = endEl.value || "18:30";

  const [h1, m1] = startVal.split(":").map(Number);
  const [h2, m2] = endVal.split(":").map(Number);

  let startMins = h1 * 60 + m1;
  let endMins = h2 * 60 + m2;

  if (endMins < startMins) {
    endMins += 24 * 60; // Trường hợp đi qua nửa đêm
  }

  const durationMins = endMins - startMins;
  const hours = Math.floor(durationMins / 60);
  const minutes = durationMins % 60;

  if (displayEl) {
    displayEl.innerText = `${hours}h ${minutes > 0 ? minutes + 'p ' : ''}(${durationMins} phút)`;
  }

  if (hiddenTimeEl) {
    hiddenTimeEl.value = `${startVal} - ${endVal}`;
  }
}

function setFreeTimePreset(startTime, endTime) {
  const startEl = document.getElementById("aiStartTime");
  const endEl = document.getElementById("aiEndTime");
  if (startEl && endEl) {
    if (!endTime && startTime && startTime.includes("-")) {
      const parts = startTime.split("-").map(s => s.trim());
      startEl.value = parts[0];
      endEl.value = parts[1];
    } else {
      startEl.value = startTime;
      endEl.value = endTime || "18:30";
    }
    onTimePickerChange();
  }
}

function selectAIRadius(radius, label) {
  aiRadiusKm = radius;
  ["all", "3", "5", "10", "20"].forEach(r => {
    const btn = document.getElementById(`airadius_${r}`);
    if (btn) {
      const match = (r === "all" && radius === null) || (parseFloat(r) === radius);
      if (match) {
        btn.className = "companion-chip active py-2 px-2.5 rounded-xl border-2 border-[#E11D48] bg-rose-50 font-bold text-[#E11D48] shadow-xs transition text-center cursor-pointer";
      } else {
        btn.className = "companion-chip py-2 px-2.5 rounded-xl border border-slate-200 bg-white font-bold text-slate-600 hover:border-slate-300 transition text-center cursor-pointer";
      }
    }
  });
  const displayEl = document.getElementById("aiRadiusDisplay");
  if (displayEl) {
    displayEl.innerText = label || (radius ? `Trong vòng ${radius} km` : "Toàn thành phố");
  }
}

function selectAIBudget(level, amount) {
  aiBudgetLevel = level;
  aiTargetBudget = amount;

  ["free", "under_100k", "100k_250k", "above_250k"].forEach(l => {
    const btn = document.getElementById(`aibudget_${l}`);
    if (btn) {
      if (l === level) {
        btn.className = "companion-chip active py-2 px-3 rounded-xl border-2 border-[#E11D48] bg-rose-50 font-bold text-[#E11D48] shadow-xs transition text-center cursor-pointer";
      } else {
        btn.className = "companion-chip py-2 px-3 rounded-xl border border-slate-200 bg-white font-bold text-slate-600 hover:border-slate-300 transition text-center cursor-pointer";
      }
    }
  });

  const customInput = document.getElementById("aiCustomBudget");
  if (customInput) customInput.value = "";

  const displayEl = document.getElementById("aiBudgetValueDisplay");
  if (displayEl) {
    if (level === "free") displayEl.innerText = "0đ (Miễn phí hoàn toàn)";
    else if (level === "under_100k") displayEl.innerText = "Dưới 100.000đ / người";
    else if (level === "100k_250k") displayEl.innerText = "100.000đ – 250.000đ / người";
    else if (level === "above_250k") displayEl.innerText = "Trên 250.000đ / người";
  }
}

function onCustomAIBudgetInput() {
  const customInput = document.getElementById("aiCustomBudget");
  if (!customInput) return;
  const val = parseInt(customInput.value.replace(/\D/g, ""), 10);
  if (!isNaN(val) && val > 0) {
    aiTargetBudget = val;
    aiBudgetLevel = "custom";
    ["free", "under_100k", "100k_250k", "above_250k"].forEach(l => {
      const btn = document.getElementById(`aibudget_${l}`);
      if (btn) {
        btn.className = "companion-chip py-2 px-3 rounded-xl border border-slate-200 bg-white font-bold text-slate-600 hover:border-slate-300 transition text-center cursor-pointer";
      }
    });
    const displayEl = document.getElementById("aiBudgetValueDisplay");
    if (displayEl) displayEl.innerText = `${val.toLocaleString()}đ / người (Tự nhập)`;
  }
}

let isPlannerSidebarCollapsed = false;

function togglePlannerSidebar() {
  const colLeft = document.getElementById("colLeftPlanner");
  const colRight = document.getElementById("colRightContent");
  const barExpand = document.getElementById("barExpandSidebar");
  if (!colLeft || !colRight) return;

  isPlannerSidebarCollapsed = !isPlannerSidebarCollapsed;
  if (isPlannerSidebarCollapsed) {
    colLeft.classList.add("hidden");
    colRight.classList.remove("lg:col-span-7", "xl:col-span-7");
    colRight.classList.add("lg:col-span-12", "xl:col-span-12");
    if (barExpand) barExpand.classList.remove("hidden");
  } else {
    colLeft.classList.remove("hidden");
    colRight.classList.remove("lg:col-span-12", "xl:col-span-12");
    colRight.classList.add("lg:col-span-7", "xl:col-span-7");
    if (barExpand) barExpand.classList.add("hidden");
  }

  // Cập nhật lại kích thước bản đồ Leaflet
  setTimeout(() => {
    if (typeof leafletMap !== "undefined" && leafletMap) {
      leafletMap.invalidateSize();
    }
  }, 300);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatAiSummaryHTML(rawText) {
  if (!rawText) return "";
  const lines = rawText.split("\n").map(l => l.trim()).filter(l => l.length > 0);
  let html = `<div class="space-y-2.5">`;

  lines.forEach(line => {
    const lower = line.toLowerCase();
    // Bỏ qua các dòng nhại lại chi phí / ngân sách / thời lượng rảnh
    if (lower.startsWith("cân đối chi phí") || lower.includes("hạn mức ngân sách") || lower.includes("tổng chi phí dự kiến")) {
      return;
    }
    if (lower.startsWith("tiếp nhận tiêu chí") || lower.startsWith("tiêu chí tiếp nhận")) {
      html += `
        <div class="text-xs font-black uppercase text-indigo-900 tracking-wider flex items-center gap-1.5 pt-1">
          <i class="fa-solid fa-clipboard-check text-indigo-600 text-sm"></i>
          <span>Tiếp nhận tiêu chí của bạn:</span>
        </div>
      `;
    } else if (lower.includes("lý do lựa chọn") || lower.includes("khi kết hợp") || lower.includes("sggo chọn") || lower.includes("đề xuất lộ trình")) {
      html += `
        <div class="text-xs font-black uppercase text-slate-900 tracking-wider flex items-center gap-1.5 pt-2 border-t border-slate-100">
          <i class="fa-solid fa-compass text-[#E11D48] text-sm"></i>
          <span>Lý do lựa chọn lộ trình:</span>
        </div>
      `;
    } else if (lower.includes("take note") || lower.includes("ghi chú riêng") || lower.startsWith("• ghi chú")) {
      let content = line.replace(/^[•\-\*]\s*(Ghi chú riêng \(Take note\):|Ghi chú riêng:|Ghi chú:)?\s*/i, "");
      html += `
        <div class="px-3.5 py-2.5 rounded-2xl bg-amber-50 border border-amber-200/90 text-amber-950 text-xs sm:text-[13px] flex items-start gap-2.5 font-medium shadow-2xs">
          <i class="fa-solid fa-note-sticky text-amber-600 text-sm mt-0.5 shrink-0"></i>
          <div class="leading-relaxed"><strong class="font-black text-amber-900">Ghi chú riêng của bạn:</strong> ${escapeHtml(content)}</div>
        </div>
      `;
    } else if (line.startsWith("•") || line.startsWith("-") || line.startsWith("*")) {
      let clean = line.replace(/^[•\-\*]\s*/, "");
      const colonIdx = clean.indexOf(":");
      if (colonIdx > 0 && lower.includes("logic kết hợp")) {
        const title = clean.substring(0, colonIdx).trim();
        const desc = clean.substring(colonIdx + 1).trim();
        html += `
          <div class="p-3.5 rounded-2xl bg-gradient-to-r from-indigo-50/90 via-sky-50/70 to-indigo-50/90 border border-indigo-200/90 text-xs sm:text-[13px] shadow-2xs">
            <div class="font-black text-indigo-950 flex items-center gap-2 mb-1">
              <span class="w-5 h-5 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-[10px] shrink-0 font-black"><i class="fa-solid fa-arrows-split-up-and-left"></i></span>
              <span class="text-indigo-950 font-black">${escapeHtml(title)}</span>
            </div>
            <p class="text-indigo-900 leading-relaxed font-medium pl-7">${escapeHtml(desc)}</p>
          </div>
        `;
      } else if (colonIdx > 0 && lower.includes("vì sao chọn")) {
        const title = clean.substring(0, colonIdx).trim();
        const desc = clean.substring(colonIdx + 1).trim();
        html += `
          <div class="p-3.5 rounded-2xl bg-slate-50/95 border border-slate-200/90 text-xs sm:text-[13px] shadow-2xs">
            <div class="font-black text-slate-900 flex items-center gap-2 mb-1">
              <span class="w-5 h-5 rounded-lg bg-rose-100 text-[#E11D48] flex items-center justify-center text-[10px] shrink-0 font-black"><i class="fa-solid fa-location-dot"></i></span>
              <span class="text-slate-950 font-black">${escapeHtml(title)}</span>
            </div>
            <p class="text-slate-700 leading-relaxed font-medium pl-7">${escapeHtml(desc)}</p>
          </div>
        `;
      } else {
        html += `
          <div class="flex items-start gap-2.5 text-xs sm:text-[13px] text-slate-800 font-medium pl-1 leading-relaxed">
            <span class="w-1.5 h-1.5 rounded-full bg-[#E11D48] mt-2 shrink-0"></span>
            <span>${escapeHtml(clean)}</span>
          </div>
        `;
      }
    } else {
      html += `<p class="text-xs sm:text-[13px] text-slate-800 leading-relaxed font-medium">${escapeHtml(line)}</p>`;
    }
  });

  html += `</div>`;
  return html;
}

async function requestAIItinerary(isShuffle = false) {
  if (!isShuffle) {
    aiShuffleSeed = 0;
  }
  const btn = document.getElementById("btnSubmitAI");
  const resultArea = document.getElementById("aiResultArea");
  const constraintAlert = document.getElementById("aiConstraintAlert");
  const container = document.getElementById("aiTimeline");
  const summary = document.getElementById("aiSummary");
  const btnGmaps = document.getElementById("btnGmapsMultiRoute");

  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Đang tính toán & tối ưu lịch trình...`;
  btn.disabled = true;

  const startLoc = document.getElementById("aiStartLoc")?.value.trim();
  if (!startLoc && !userGPSCoords) {
    alert("Vui lòng nhập điểm xuất phát hoặc bấm 'Dùng GPS hiện tại'!");
    document.getElementById("aiStartLoc")?.focus();
    btn.innerHTML = `<i class="fa-solid fa-route"></i> <span>Tạo Lịch Trình Khám Phá</span>`;
    btn.disabled = false;
    return;
  }

  const selectedModel = document.getElementById("aiModelSelect")?.value || "gemini-3.5-flash-lite";
  const takeNoteEl = document.getElementById("aiTakeNote");
  const takeNoteVal = takeNoteEl ? takeNoteEl.value.trim() : "";

  const startVal = document.getElementById("aiStartTime")?.value || "14:00";
  const endVal = document.getElementById("aiEndTime")?.value || "18:30";
  const freeTimeStr = `${startVal} - ${endVal}`;

  const payload = {
    user_id: currentUser ? currentUser.id : null,
    start_location: document.getElementById("aiStartLoc").value,
    start_lat: userGPSCoords ? userGPSCoords.lat : null,
    start_lon: userGPSCoords ? userGPSCoords.lon : null,
    free_time: freeTimeStr,
    companion: aiCompanion,
    purpose: aiPurpose,
    takenote: takeNoteVal,
    context: takeNoteVal,
    budget: aiBudgetLevel,
    budget_level: aiBudgetLevel,
    target_budget: aiTargetBudget,
    num_stops: aiNumStops,
    radius_km: aiRadiusKm,
    shuffle_seed: aiShuffleSeed,
    ai_model: selectedModel
  };

  try {
    const res = await fetch(`${API_BASE}/ai-itinerary`, {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || "Không thể lập lộ trình");

    // XỬ LÝ VI PHẠM RÀNG BUỘC (BUSINESS RULE 3 & KIỂM THỬ BẮT BUỘC)
    if (result.feasible === false) {
      if (resultArea) resultArea.classList.add("hidden");
      if (constraintAlert) {
        constraintAlert.classList.remove("hidden");
        let constraintTitle = "Điều kiện không thể đáp ứng";
        if (result.error_code === "TIME_TOO_SHORT") {
          constraintTitle = "Thời gian rảnh quá ngắn";
        } else if (result.error_code === "ALL_PLACES_CLOSED") {
          constraintTitle = "Địa điểm đã đóng cửa trong khung giờ này";
        } else if (result.error_code === "BUDGET_TOO_LOW") {
          constraintTitle = "Ngân sách không đủ cho lộ trình";
        }
        document.getElementById("aiConstraintTitle").innerText = constraintTitle;
        document.getElementById("aiConstraintMessage").innerText = result.message;
        document.getElementById("aiConstraintSuggestionText").innerText = result.suggestion;
        window._currentRelaxAction = {
          time: result.recommended_time || "14:00 - 18:30",
          budget: result.recommended_budget || null
        };
        constraintAlert.scrollIntoView({ behavior: "smooth" });
      }
      return;
    }

    // NẾU THỎA MÃN RÀNG BUỘC
    if (constraintAlert) constraintAlert.classList.add("hidden");
    const placeholderArea = document.getElementById("aiPlaceholderArea");
    if (placeholderArea) placeholderArea.classList.add("hidden");
    if (resultArea) resultArea.classList.remove("hidden");

    // Cập nhật nhãn trạng thái công nghệ minh bạch (Gemini & OpenStreetMap)
    const aiBadge = document.getElementById("aiModelBadge");
    const aiText = document.getElementById("aiModelText");
    if (aiBadge && aiText) {
      if (result.ai_status === "success") {
        aiBadge.className = "inline-flex items-center gap-1.5 text-[11px] font-black px-3 py-1 rounded-full bg-purple-50 text-purple-800 border border-purple-200 shadow-2xs";
        aiText.innerText = "Google Gemini";
      } else {
        aiBadge.className = "inline-flex items-center gap-1.5 text-[11px] font-black px-3 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200 shadow-2xs";
        aiText.innerText = "Thuật toán SGGo (Dự phòng)";
      }
    }

    const routeBadge = document.getElementById("routingEngineBadge");
    const routeText = document.getElementById("routingEngineText");
    if (routeBadge && routeText) {
      if (result.routing_source === "osrm") {
        routeBadge.className = "inline-flex items-center gap-1.5 text-[11px] font-black px-3 py-1 rounded-full bg-sky-50 text-sky-800 border border-sky-200 shadow-2xs";
        routeText.innerText = "OpenStreetMap";
      } else {
        routeBadge.className = "inline-flex items-center gap-1.5 text-[11px] font-black px-3 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200 shadow-2xs";
        routeText.innerText = "Haversine (Dự phòng)";
      }
    }

    const routeWarnEl = document.getElementById("routingWarningBanner");
    const routeWarnText = document.getElementById("routingWarningText");
    if (routeWarnEl && routeWarnText) {
      if (result.routing_warning) {
        routeWarnText.innerText = result.routing_warning;
        routeWarnEl.classList.remove("hidden");
      } else {
        routeWarnEl.classList.add("hidden");
      }
    }

    const spareBanner = document.getElementById("spareTimeBanner");
    const spareText = document.getElementById("spareTimeText");
    if (spareBanner && spareText) {
      if (result.spare_time_message) {
        spareText.innerText = result.spare_time_message;
        spareBanner.classList.remove("hidden");
      } else {
        spareBanner.classList.add("hidden");
      }
    }

    // Cập nhật số trạm trên các nút và tiêu đề
    const stopCount = result.steps ? result.steps.length : (result.num_stops || aiNumStops);
    const timelineTitle = document.getElementById("aiTimelineTitle");
    if (timelineTitle) {
      timelineTitle.innerHTML = `<i class="fa-solid fa-route text-[#E11D48]"></i> Dòng Thời Gian Hành Trình (Timeline ${stopCount} Chặng)`;
    }
    const gmapsBtnText = document.getElementById("btnGmapsMultiRouteText");
    if (gmapsBtnText) {
      gmapsBtnText.innerText = `MỞ TOÀN BỘ LỘ TRÌNH ${stopCount} TRẠM TRÊN GOOGLE MAPS (CHẾ ĐỘ DẪN ĐƯỜNG XE MÁY)`;
    }

    // Cập nhật KPI thẻ ngân sách & thời gian (G6-FR05 MUST)
    if (result.kpi) {
      const kpi = result.kpi;
      const budgetEl = document.getElementById("aiKpiBudget");
      const budgetBadge = document.getElementById("aiKpiBudgetBadge");
      if (budgetEl) budgetEl.innerText = `${kpi.total_min_cost.toLocaleString()}đ – ${kpi.total_max_cost.toLocaleString()}đ`;
      if (budgetBadge) {
        if (kpi.is_within_budget) {
          budgetBadge.className = "inline-flex items-center gap-1 text-[10px] font-extrabold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded-md mt-1";
          budgetBadge.innerHTML = `<i class="fa-solid fa-circle-check"></i> <span>Nằm trong ngân sách dự kiến</span>`;
        } else {
          budgetBadge.className = "inline-flex items-center gap-1 text-[10px] font-extrabold text-amber-700 bg-amber-100/80 px-2 py-0.5 rounded-md mt-1";
          budgetBadge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <span>Hơi vượt ngân sách</span>`;
        }
      }

      const durEl = document.getElementById("aiKpiDuration");
      const durBadge = document.getElementById("aiKpiDurationBadge");
      const h = Math.floor(kpi.total_duration_minutes / 60);
      const m = kpi.total_duration_minutes % 60;
      if (durEl) durEl.innerText = `${h > 0 ? h + ' giờ ' : ''}${m} phút (~${kpi.total_duration_minutes} phút)`;
      if (durBadge) {
        if (kpi.is_within_time) {
          durBadge.className = "inline-flex items-center gap-1 text-[10px] font-extrabold text-sky-700 bg-sky-100/80 px-2 py-0.5 rounded-md mt-1";
          durBadge.innerHTML = `<i class="fa-solid fa-circle-check"></i> <span>Vừa vặn khung giờ rảnh</span>`;
        } else {
          durBadge.className = "inline-flex items-center gap-1 text-[10px] font-extrabold text-amber-700 bg-amber-100/80 px-2 py-0.5 rounded-md mt-1";
          durBadge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <span>Dài hơn giờ rảnh ban đầu</span>`;
        }
      }
    }

    let summaryContent = result.summary || `Lộ trình ${result.steps ? result.steps.length : ''} trạm thuận đường tối ưu do hệ thống sắp xếp.`;
    summary.innerHTML = formatAiSummaryHTML(summaryContent);

    if (btnGmaps && result.gmaps_multi_url) {
      btnGmaps.href = result.gmaps_multi_url;
    }

    // Vẽ bản đồ Leaflet
    renderItineraryMap(result.start_coords, result.steps);

    // Render Timeline
    container.innerHTML = "";
    result.steps.forEach((s, idx) => {
      // 1. Chặng di chuyển nối tiếp giữa các trạm (Transit Stepper Connector)
      let transitConnectorHTML = "";
      if (idx === 0) {
        const startName = result.start_location || document.getElementById("aiStartLoc")?.value.trim() || "Điểm xuất phát của bạn";
        transitConnectorHTML = `
          <div class="flex flex-col items-center mb-5 relative">
            <!-- Thẻ điểm xuất phát ban đầu -->
            <div class="inline-flex items-center gap-2.5 px-4 py-2 rounded-2xl bg-slate-900 text-white text-xs font-black shadow-xs mb-1.5">
              <i class="fa-solid fa-location-crosshairs text-[#E11D48]"></i>
              <span>Điểm xuất phát: ${startName}</span>
            </div>

            <!-- Nét đứt phía trên dẫn từ điểm xuất phát xuống -->
            <div class="w-0.5 h-3.5 sm:h-4 border-l-2 border-dashed border-indigo-300"></div>
            
            <!-- Thẻ di chuyển xe máy từ Điểm xuất phát -> Chặng 1 -->
            <div class="inline-flex items-center gap-3 py-2.5 px-4 sm:px-6 rounded-2xl bg-gradient-to-r from-indigo-50/90 via-white to-indigo-50/90 border border-indigo-200/90 shadow-2xs hover:shadow-xs transition-all text-left">
              <div class="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-base shadow-xs shrink-0">
                <i class="fa-solid fa-motorcycle"></i>
              </div>
              <div class="leading-tight">
                <div class="text-[10px] sm:text-[11px] font-black uppercase tracking-wider text-indigo-900/80 flex items-center gap-1.5 mb-1">
                  <span>Khởi hành</span>
                  <i class="fa-solid fa-arrow-right text-[9px] text-indigo-400"></i>
                  <span>Chặng 1</span>
                </div>
                <div class="text-xs sm:text-sm font-black text-slate-800 flex items-center gap-2 flex-wrap">
                  <span>Chạy xe máy: ~${s.dist || '1.0'} km</span>
                  <span class="text-slate-300">•</span>
                  <span class="text-indigo-600 font-extrabold flex items-center gap-1"><i class="fa-regular fa-clock text-xs"></i> ~${s.t_min || '5'} phút</span>
                </div>
              </div>
              <div class="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-white border border-indigo-200 text-indigo-600 flex items-center justify-center text-xs sm:text-sm shadow-2xs shrink-0 ml-1.5" title="Di chuyển đến Chặng 1">
                <i class="fa-solid fa-arrow-down"></i>
              </div>
            </div>

            <!-- Nét đứt phía dưới kèm mũi tên chỉ thẳng vào Chặng 1 -->
            <div class="w-0.5 h-3.5 sm:h-4 border-l-2 border-dashed border-indigo-300"></div>
            <i class="fa-solid fa-caret-down text-indigo-500 -mt-1 text-sm"></i>
          </div>
        `;
      } else {
        transitConnectorHTML = `
          <div class="flex flex-col items-center my-4 sm:my-5 relative">
            <!-- Nét đứt phía trên dẫn từ chặng trước xuống -->
            <div class="w-0.5 h-4 sm:h-5 border-l-2 border-dashed border-indigo-300"></div>
            
            <!-- Thẻ di chuyển xe máy lớn & trực quan -->
            <div class="inline-flex items-center gap-3 py-2.5 px-4 sm:px-6 rounded-2xl bg-gradient-to-r from-indigo-50/90 via-white to-indigo-50/90 border border-indigo-200/90 shadow-2xs hover:shadow-xs transition-all text-left">
              <!-- Icon xe máy nổi bật -->
              <div class="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-base shadow-xs shrink-0">
                <i class="fa-solid fa-motorcycle"></i>
              </div>
              
              <!-- Thông tin hành trình & thời lượng -->
              <div class="leading-tight">
                <div class="text-[10px] sm:text-[11px] font-black uppercase tracking-wider text-indigo-900/80 flex items-center gap-1.5 mb-1">
                  <span>Chặng ${idx}</span>
                  <i class="fa-solid fa-arrow-right text-[9px] text-indigo-400"></i>
                  <span>Chặng ${idx + 1}</span>
                </div>
                <div class="text-xs sm:text-sm font-black text-slate-800 flex items-center gap-2 flex-wrap">
                  <span>Chạy xe máy: ~${s.dist || '1.0'} km</span>
                  <span class="text-slate-300">•</span>
                  <span class="text-indigo-600 font-extrabold flex items-center gap-1"><i class="fa-regular fa-clock text-xs"></i> ~${s.t_min || '5'} phút</span>
                </div>
              </div>
              
              <!-- Mũi tên chỉ hướng di chuyển từ trên xuống dưới -->
              <div class="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-white border border-indigo-200 text-indigo-600 flex items-center justify-center text-xs sm:text-sm shadow-2xs shrink-0 ml-1.5" title="Di chuyển tiếp theo theo chiều từ trên xuống dưới">
                <i class="fa-solid fa-arrow-down"></i>
              </div>
            </div>

            <!-- Nét đứt phía dưới kèm mũi tên chỉ thẳng vào trạm tiếp theo -->
            <div class="w-0.5 h-4 sm:h-5 border-l-2 border-dashed border-indigo-300"></div>
            <i class="fa-solid fa-caret-down text-indigo-500 -mt-1 text-sm"></i>
          </div>
        `;
      }

      const imgHtml = renderPlaceImage(s, "w-full", "h-full");
      const gmapsLink = s.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((s.name || s.location) + ' ' + (s.address || ''))}`;
      const isEat = s.category === "an_uong";
      const venueName = s.name || (s.location ? s.location.split("—")[0].trim() : `Trạm ${idx + 1}`);
      const venueRating = s.rating || 4.5;
      const venueReviews = s.reviews_count ? `(${s.reviews_count} đánh giá)` : "";
      const venueAddress = s.address || (s.location && s.location.includes("—") ? s.location.split("—")[1].split("⭐")[0].trim() : "");
      const venueDistrict = s.district || "";

      // Định dạng thời gian dừng chân trực quan (Ví dụ: 1h40p (~100 phút))
      const dwellFormatted = s.dwell_min >= 60 
        ? `${Math.floor(s.dwell_min / 60)}h${s.dwell_min % 60 > 0 ? (s.dwell_min % 60) + 'p' : ''} (~${s.dwell_min} phút)`
        : `~${s.dwell_min} phút`;

      container.innerHTML += `
        ${transitConnectorHTML}
        <div class="bg-white rounded-3xl border border-slate-200/90 shadow-xs hover:shadow-md hover:border-slate-300 transition-all overflow-hidden mb-5">
          <!-- KHỐI HEADER TRẠM: 3 DÒNG RIÊNG BIỆT RÕ RÀNG -->
          <div class="bg-slate-50/95 px-4 sm:px-6 py-4 border-b border-slate-200/90 space-y-2.5">
            <!-- DÒNG 1: THỨ TỰ CHẶNG & THỂ LOẠI / QUẬN -->
            <div class="flex items-center justify-between gap-2 flex-wrap">
              <span class="text-xs font-black uppercase text-white bg-[#E11D48] px-3.5 py-1.5 rounded-xl shadow-xs tracking-wider">
                CHẶNG ${idx + 1}
              </span>
              <span class="text-xs font-extrabold uppercase text-slate-700 bg-white border border-slate-200/90 px-3 py-1.5 rounded-xl shadow-2xs">
                ${isEat ? 'ẨM THỰC' : 'THAM QUAN & VUI CHƠI'} ${venueDistrict ? `• ${venueDistrict}` : ''}
              </span>
            </div>

            <!-- DÒNG 2: CHI PHÍ DỰ KIẾN (MỘT DÒNG RIÊNG NỔI BẬT) -->
            <div class="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-emerald-50 border border-emerald-200/80 text-emerald-950 font-bold text-xs sm:text-sm shadow-2xs">
              <i class="fa-solid fa-receipt text-emerald-600 text-sm"></i>
              <span class="text-emerald-800 font-bold">Chi phí dự kiến:</span>
              <span class="font-black text-emerald-950">${s.price_range}</span>
            </div>

            <!-- DÒNG 3: DỪNG CHÂN & KHUNG GIỜ (MỘT DÒNG RIÊNG NỔI BẬT) -->
            <div class="flex items-center justify-between gap-2 px-3.5 py-2 rounded-xl bg-rose-50 border border-rose-200/80 text-rose-950 font-bold text-xs sm:text-sm shadow-2xs">
              <div class="flex items-center gap-2">
                <i class="fa-solid fa-clock text-[#E11D48] text-sm"></i>
                <span class="text-rose-800 font-bold">Khung giờ:</span>
                <span class="font-black text-rose-950">${s.time}</span>
              </div>
              <span class="text-xs font-black text-rose-700 bg-rose-200/80 px-2.5 py-0.5 rounded-md">Dừng ${dwellFormatted}</span>
            </div>
          </div>

          <!-- NỘI DUNG THÂN THẺ (TẬP TRUNG VÀO TRẢI NGHIỆM CHÍNH & MÓN NÊN GỌI) -->
          <div class="p-4 sm:p-6">
            <div class="grid grid-cols-1 md:grid-cols-12 gap-5 items-start">
              
              <!-- Cột Trái (Ảnh Trạm: KHÔNG CLICK, KHÔNG OVERLAY NÚT ẢNH) -->
              <div class="md:col-span-4 relative h-48 sm:h-44 md:h-full min-h-[160px] rounded-2xl overflow-hidden border border-slate-200 shadow-2xs select-none">
                ${imgHtml}
              </div>

              <!-- Cột Phải (Thông Tin Quán) -->
              <div class="md:col-span-8 flex flex-col justify-between">
                <div>
                  <!-- Tên Quán + Số Sao & Lượt Đánh Giá CỰC KỲ NHẤN MẠNH -->
                  <div class="flex items-start justify-between gap-3 mb-3">
                    <h3 onclick="openPlaceDetailById(${s.place_id})" class="text-base sm:text-lg font-black text-slate-900 leading-snug hover:text-[#E11D48] transition cursor-pointer" title="${venueName}">
                      ${venueName}
                    </h3>
                    <div class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-2xl bg-amber-400 text-slate-950 font-black shadow-xs shrink-0 border border-amber-300">
                      <div class="flex items-center gap-1">
                        <i class="fa-solid fa-star text-white drop-shadow-xs text-sm"></i>
                        <span class="text-sm font-black tracking-tight text-white">${venueRating}</span>
                      </div>
                      ${venueReviews ? `<span class="text-[11px] font-black text-amber-950 bg-amber-100/90 px-2 py-0.5 rounded-lg">${venueReviews}</span>` : ''}
                    </div>
                  </div>

                  <!-- MÓN NÊN GỌI & TRẢI NGHIỆM CHÍNH (CỰC KỲ NỔI BẬT) -->
                  ${s.must_try_tip ? `
                    <div class="bg-gradient-to-r from-amber-50 to-orange-50 border-2 border-amber-300/80 rounded-2xl p-3.5 sm:p-4 mb-3 text-xs sm:text-[13px] text-amber-950 shadow-2xs">
                      <div class="font-black text-amber-900 flex items-center gap-2 uppercase text-xs tracking-wider mb-1.5">
                        <span class="px-2 py-0.5 bg-amber-500 text-white rounded-md text-[10px] font-black uppercase tracking-wider">NÊN THỬ</span>
                        <span class="font-black text-amber-950">${isEat ? 'Món ruột được khen nhiều nhất:' : 'Trải nghiệm nổi bật khi đến đây:'}</span>
                      </div>
                      <div class="font-extrabold text-slate-900 text-sm leading-relaxed">${escapeHtml(s.must_try_tip)}</div>
                    </div>
                  ` : ''}

                  <!-- CẢNH BÁO HOẶC TRẤN AN GIỜ CAO ĐIỂM (LUÔN HIỂN THỊ ĐỂ NGƯỜI DÙNG YÊN TÂM) -->
                  ${s.is_peak_hour ? `
                    <div class="mb-3 p-3 bg-rose-50 border border-rose-200/90 rounded-2xl text-xs sm:text-[13px] text-rose-950 flex items-start gap-2.5 font-medium shadow-2xs">
                      <div class="w-6 h-6 rounded-lg bg-rose-500 text-white flex items-center justify-center shrink-0 mt-0.5 text-xs shadow-2xs">
                        <i class="fa-solid fa-fire"></i>
                      </div>
                      <div class="leading-relaxed">
                        <strong class="font-black text-rose-900 uppercase text-[11px] tracking-wide block mb-0.5">Trùng giờ cao điểm của quán</strong>
                        <span>${escapeHtml(s.peak_warning || `Dự kiến quán rất đông khách vào khung giờ này (${s.peak_hours || ''}). Bạn nên chủ động đặt bàn trước hoặc ghé sớm!`)}</span>
                      </div>
                    </div>
                  ` : `
                    <div class="mb-3 p-3 bg-emerald-50/90 border border-emerald-200/90 rounded-2xl text-xs sm:text-[13px] text-emerald-950 flex items-start gap-2.5 font-medium shadow-2xs">
                      <div class="w-6 h-6 rounded-lg bg-emerald-600 text-white flex items-center justify-center shrink-0 mt-0.5 text-xs shadow-2xs">
                        <i class="fa-solid fa-check"></i>
                      </div>
                      <div class="leading-relaxed">
                        <strong class="font-black text-emerald-900 uppercase text-[11px] tracking-wide block mb-0.5">Không trùng giờ cao điểm</strong>
                        <span>${escapeHtml(s.peak_warning || `Khung giờ bạn ghé (${s.time}) không trùng giờ cao điểm của quán${s.peak_hours ? ` (giờ cao điểm: ${s.peak_hours})` : ''}. Quán thoáng đãng, bạn hoàn toàn yên tâm trải nghiệm!`)}</span>
                      </div>
                    </div>
                  `}

                  <!-- Cảnh Báo Giao Thông Nặng (Nếu có tắc đường) -->
                  ${s.traffic_warning && !s.traffic_warning.includes("bình thường") ? `
                    <div class="mb-3 p-2.5 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 flex items-start gap-2 font-medium">
                      <i class="fa-solid fa-triangle-exclamation text-amber-600 text-sm mt-0.5 flex-shrink-0"></i>
                      <div>${escapeHtml(s.traffic_warning)}</div>
                    </div>
                  ` : ''}
                </div>

                <!-- CHÂN THẺ: ĐỒNG BỘ PHONG CÁCH VỚI TAB 1 -->
                <div class="pt-3.5 border-t border-slate-100 flex items-center justify-between flex-wrap gap-2.5">
                  <div class="flex items-center gap-1.5 text-xs text-slate-500 font-semibold">
                    <i class="fa-regular fa-clock text-slate-400"></i>
                    <span>Mở cửa: ${s.open_hours}</span>
                  </div>

                  <div class="flex items-center gap-2">
                    <button onclick="openPlaceDetailById(${s.place_id})" title="Xem đầy đủ thông tin quán" class="px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer shadow-xs">
                      <i class="fa-solid fa-circle-info text-slate-600"></i>
                      <span>Chi tiết quán</span>
                    </button>
                    <a href="${gmapsLink}" target="_blank" title="Mở trang Google Maps chính thức của quán" class="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-black transition flex items-center gap-2 shadow-sm whitespace-nowrap">
                      <i class="fa-brands fa-google text-sm"></i>
                      <span>Google Maps</span>
                      <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                    </a>
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>
      `;
    });

    if (window.innerWidth < 1024) {
      resultArea.scrollIntoView({ behavior: "smooth" });
    } else {
      document.getElementById("viewAI")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (err) {
    alert("Lỗi: " + err.message);
  } finally {
    btn.innerHTML = `<i class="fa-solid fa-route"></i> <span>Tạo Lịch Trình Khám Phá</span>`;
    btn.disabled = false;
  }
}

function shuffleAIItinerary() {
  aiShuffleSeed++;
  requestAIItinerary(true);
}

function handleAutoRelaxConstraint() {
  if (window._currentRelaxAction) {
    if (window._currentRelaxAction.time) {
      setFreeTimePreset(window._currentRelaxAction.time);
    }
    if (window._currentRelaxAction.budget) {
      selectAIBudget("100k_250k", window._currentRelaxAction.budget);
    }
  } else {
    setFreeTimePreset("14:00", "18:30");
    selectAIBudget("100k_250k", 250000);
  }
  requestAIItinerary(false);
}

// ==============================================================================
// 5. TỰ CHỌN ĐỊA ĐIỂM (TAB 2: 40 QUÁN CHUẨN XÁC, ĐỊNH VỊ GPS, BỘ LỌC BÁN KÍNH & A-Z)
// ==============================================================================

// Bảng tọa độ các địa danh nổi tiếng tại Sài Gòn để nhận diện tức thì (0ms)
const KNOWN_SG_LANDMARKS = {
  "su pham": { name: "ĐH Sư Phạm TP.HCM (280 An Dương Vương)", lat: 10.7601, lon: 106.6823 },
  "280 an duong vuong": { name: "280 An Dương Vương, TP.HCM", lat: 10.7601, lon: 106.6823 },
  "an duong vuong": { name: "280 An Dương Vương, TP.HCM", lat: 10.7601, lon: 106.6823 },
  "an dong": { name: "Chợ An Đông, TP.HCM", lat: 10.7573, lon: 106.6713 },
  "cho an dong": { name: "Chợ An Đông, TP.HCM", lat: 10.7573, lon: 106.6713 },
  "thuan kieu": { name: "Thuận Kiều Plaza (190 Hồng Bàng)", lat: 10.7554, lon: 106.6577 },
  "binh tay": { name: "Chợ Bình Tây, TP.HCM", lat: 10.7497, lon: 106.6515 },
  "cho binh tay": { name: "Chợ Bình Tây, TP.HCM", lat: 10.7497, lon: 106.6515 },
  "ben thanh": { name: "Chợ Bến Thành, TP.HCM", lat: 10.7725, lon: 106.6980 },
  "cho ben thanh": { name: "Chợ Bến Thành, TP.HCM", lat: 10.7725, lon: 106.6980 },
  "nha tho duc ba": { name: "Nhà Thờ Đức Bà, TP.HCM", lat: 10.7798, lon: 106.6990 },
  "pho di bo": { name: "Phố Đi Bộ Nguyễn Huệ, TP.HCM", lat: 10.7744, lon: 106.7032 },
  "ho con rua": { name: "Hồ Con Rùa, TP.HCM", lat: 10.7828, lon: 106.6958 },
  "cho ray": { name: "Bệnh viện Chợ Rẫy (Nguyễn Chí Thanh)", lat: 10.7577, lon: 106.6596 },
  "benh vien cho ray": { name: "Bệnh viện Chợ Rẫy", lat: 10.7577, lon: 106.6596 },
  "y duoc": { name: "ĐH Y Dược TP.HCM (Hồng Bàng)", lat: 10.7562, lon: 106.6589 },
  "dai hoc y duoc": { name: "ĐH Y Dược TP.HCM", lat: 10.7562, lon: 106.6589 },
  "van lang": { name: "Công viên Văn Lang, TP.HCM", lat: 10.7585, lon: 106.6705 },
  "cong vien van lang": { name: "Công viên Văn Lang, TP.HCM", lat: 10.7585, lon: 106.6705 },
  "hung vuong": { name: "Hùng Vương Plaza (Hồng Bàng)", lat: 10.7570, lon: 106.6625 },
  "dai the gioi": { name: "Công viên Nước Đại Thế Giới", lat: 10.7530, lon: 106.6690 }
};

function removeVietnameseTones(str) {
  if (!str) return "";
  str = str.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  str = str.replace(/[đĐ]/g, "d");
  return str.toLowerCase().trim();
}

function calculateHaversineDistanceKm(lat1, lon1, lat2, lon2) {
  const R = 6371; // Bán kính Trái Đất (km)
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// 1. Lấy vị trí GPS hiện tại cho Tab Tự Chọn (tự động đồng bộ sang Tab 1 & Tab 3)
function getExploreGPSLocation() {
  const btn = document.getElementById("btnExploreGPS");

  if (!navigator.geolocation) {
    alert("Trình duyệt của bạn không hỗ trợ định vị GPS Geolocation.");
    return;
  }

  if (btn) {
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Đang lấy GPS...</span>`;
    btn.disabled = true;
  }

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const label = `Vị trí GPS hiện tại (${lat.toFixed(4)}, ${lon.toFixed(4)})`;
      flowPrioritizeGps = true;
      setGlobalLocation(lat, lon, label, true);

      // Tự động sắp xếp gần nhất trước
      const sortSelect = document.getElementById("allSortFilter");
      if (sortSelect && sortSelect.value === "default") {
        sortSelect.value = "distance_asc";
      }

      filterAllPlaces();
    },
    (err) => {
      alert("Không thể lấy vị trí GPS: " + err.message + ". Bạn có thể điền địa chỉ hoặc bấm vào các mốc gợi ý bên dưới!");
      if (btn) {
        btn.innerHTML = `<i class="fa-solid fa-crosshairs"></i> <span>Dùng GPS hiện tại</span>`;
        btn.disabled = false;
      }
    },
    { timeout: 8000, enableHighAccuracy: true }
  );
}

// 2. Chọn mốc vị trí gợi ý nhanh (tự động đồng bộ sang Tab 1 & Tab 3)
function setExploreLocationPreset(label, lat, lon) {
  flowPrioritizeGps = true;
  setGlobalLocation(lat, lon, label, true);

  const btn = document.getElementById("btnExploreGPS");
  if (btn) btn.innerHTML = `<i class="fa-solid fa-location-dot"></i> <span>Đã chọn mốc</span>`;

  const sortSelect = document.getElementById("allSortFilter");
  if (sortSelect && sortSelect.value === "default") {
    sortSelect.value = "distance_asc";
  }

  filterAllPlaces();
}

// 3. Xử lý khi người dùng tự gõ địa chỉ
async function onExploreLocationInputChange() {
  const input = document.getElementById("exploreLocationInput");
  const val = input ? input.value.trim() : "";
  if (!val) {
    clearExploreLocation();
    return;
  }

  const norm = removeVietnameseTones(val);
  let foundCoords = null;

  for (const k of Object.keys(KNOWN_SG_LANDMARKS)) {
    if (norm.includes(k)) {
      foundCoords = { lat: KNOWN_SG_LANDMARKS[k].lat, lon: KNOWN_SG_LANDMARKS[k].lon };
      break;
    }
  }

  if (!foundCoords) {
    try {
      const q = encodeURIComponent(`${val}, Ho Chi Minh City, Vietnam`);
      const resp = await fetch(`https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=1`, {
        headers: { "Accept-Language": "vi" }
      });
      const data = await resp.json();
      if (data && data.length > 0) {
        foundCoords = { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
      }
    } catch (e) {
      console.warn("Geocoding address error:", e);
    }
  }

  if (!foundCoords) {
    alert("Không thể xác định vị trí cho địa chỉ này trên bản đồ. Vui lòng nhập địa chỉ cụ thể hơn hoặc chọn một mốc có sẵn.");
    return;
  }

  flowPrioritizeGps = true;
  setGlobalLocation(foundCoords.lat, foundCoords.lon, val, true);

  const sortSelect = document.getElementById("allSortFilter");
  if (sortSelect && sortSelect.value === "default") {
    sortSelect.value = "distance_asc";
  }

  filterAllPlaces();
}

// 4. Hủy vị trí định vị (đồng bộ hủy cho toàn hệ thống)
function clearExploreLocation() {
  clearGlobalLocation();
  filterAllPlaces();
}

// Hàm thông báo nhắc nhở khi chức năng yêu cầu vị trí GPS/điểm mốc
function showLocationRequiredNotice(actionType) {
  const isSort = (actionType === "sort");
  const msg = isSort
    ? "Bạn chưa chọn vị trí!\n\nĐể sắp xếp các quán theo 'Khoảng cách: Gần nhất', bạn hãy bấm 'Dùng GPS hiện tại' hoặc bấm chọn một điểm mốc (Hồ Con Rùa, Chợ An Đông,...) ở khung định vị phía trên nhé!"
    : "Bạn chưa chọn vị trí!\n\nĐể lọc các quán trong bán kính mong muốn, bạn hãy bấm 'Dùng GPS hiện tại' hoặc nhập vị trí của bạn ở khung định vị phía trên nhé!";

  alert(msg);

  // Cuộn mượt và highlight khung định vị để người dùng bắt mắt ngay
  const locInput = document.getElementById("exploreLocationInput");
  const locCard = locInput ? locInput.closest(".bg-white") : null;
  if (locCard) {
    locCard.scrollIntoView({ behavior: "smooth", block: "center" });
    locCard.classList.add("ring-4", "ring-[#E11D48]/40", "transition-all", "duration-500");
    setTimeout(() => {
      locCard.classList.remove("ring-4", "ring-[#E11D48]/40");
    }, 2500);
  }
  if (locInput) {
    locInput.focus();
  }
}

// Xử lý khi người dùng đổi lựa chọn Sắp xếp
function handleSortFilterChange() {
  const sortSelect = document.getElementById("allSortFilter");
  const sortVal = sortSelect?.value;
  if (sortVal === "distance_asc" && !exploreUserCoords) {
    showLocationRequiredNotice("sort");
    sortSelect.value = "default";
    return;
  }
  filterAllPlaces();
}

// 5. Khi người dùng thay đổi bộ lọc bán kính
function onRadiusFilterChange() {
  const radiusSelect = document.getElementById("allRadiusFilter");
  const radius = radiusSelect?.value || "all";
  if (radius !== "all" && !exploreUserCoords) {
    showLocationRequiredNotice("radius");
    radiusSelect.value = "all";
    return;
  }
  filterAllPlaces();
}

// ==============================================================================
// TAB 2: THẺ CATALOG DU LỊCH 2 CỘT CÂN ĐỐI (DÀNH CHO TAB TỰ CHỌN 40 QUÁN)
// THIẾT KẾ DẠNG GRID THOÁNG ĐÃNG, KHÔNG BỊ TRÙNG LẶP KIỂU TAB 1
// ==============================================================================
function buildCatalogCardHTML(p) {
  const isEat = p.category === "an_uong";
  const isOpen = (typeof p.is_currently_open === "boolean")
    ? p.is_currently_open
    : isPlaceCurrentlyOpen(p.open_time, p.close_time);
  const gmapsUrl = p.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.name + ' ' + p.address)}`;

  const rawPrice = p.price_display
    ? p.price_display
    : ((p.min_price === 0 && p.max_price === 0)
      ? "Miễn phí vé"
      : `${p.min_price ? p.min_price.toLocaleString() + 'đ' : ''} – ${p.max_price ? p.max_price.toLocaleString() + 'đ' : ''}`);

  let cleanPrice = rawPrice;
  let priceUnit = "";
  if (cleanPrice.toLowerCase().includes("/người") || cleanPrice.toLowerCase().includes("/ người")) {
    cleanPrice = cleanPrice.replace(/\/\s*người/gi, "").trim();
    priceUnit = "/ người";
  } else if (cleanPrice.toLowerCase().includes("/vé") || cleanPrice.toLowerCase().includes("/ vé")) {
    cleanPrice = cleanPrice.replace(/\/\s*vé/gi, "").trim();
    priceUnit = "/ vé";
  }

  const displayHours = (p.peak_hours && p.peak_hours !== 'Chưa rõ')
    ? p.peak_hours.split('(')[0].trim()
    : ((p.open_time && p.close_time) ? `${p.open_time} – ${p.close_time}` : '08:00 – 22:30');

  let distanceHTML = "";
  if (typeof p.distanceKm === "number" && !isNaN(p.distanceKm) && exploreUserCoords) {
    const isWalk = p.distanceKm <= 0.6;
    const distStr = p.distanceKm < 1 ? `${Math.round(p.distanceKm * 1000)}m` : `${p.distanceKm.toFixed(1)} km`;
    distanceHTML = `
      <span class="px-2 py-0.5 rounded-md text-[10px] font-extrabold ${isWalk ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-blue-50 text-blue-800 border border-blue-200'} whitespace-nowrap inline-flex items-center gap-1">
        <i class="fa-solid ${isWalk ? 'fa-person-walking' : 'fa-motorcycle'} text-[10px]"></i>
        <span>${distStr}</span>
      </span>
    `;
  }

  const imageHtml = renderPlaceImage(p, "w-full", "h-full");

  return `
    <div class="catalog-card-v3">
      <!-- 1. Header ảnh quán tỷ lệ vàng chuẩn (KHÔNG CLICK VÀO ẢNH) -->
      <div class="card-image-box select-none">
        ${imageHtml}
        <!-- Badge thể loại -->
        <span class="absolute top-2.5 left-2.5 text-[10px] font-black uppercase text-[#E11D48] bg-white/95 backdrop-blur-xs px-2.5 py-0.5 rounded-lg shadow-sm">
          ${isEat ? 'Ẩm Thực' : 'Đi Chơi'}
        </span>
        <!-- Badge mở cửa -->
        <span class="absolute top-2.5 right-2.5 text-[10px] font-black uppercase ${isOpen ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'} px-2.5 py-0.5 rounded-lg shadow-sm">
          ${isOpen ? '🟢 Mở cửa' : '🔴 Đóng cửa'}
        </span>
      </div>

      <!-- 2. Thân thẻ thông tin (Unified Highlight Box: 1 ô viền bao quát nổi bật Giá & Giờ) -->
      <div class="p-4 flex-1 flex flex-col justify-between">
        <div>
          <!-- Tên quán + Badge Số sao nổi bật -->
          <div class="flex items-start justify-between gap-2 mb-2.5">
            <h4 onclick="openPlaceDetailById(${p.id})" class="font-black text-slate-900 text-sm sm:text-[15px] leading-snug line-clamp-1 hover:text-[#E11D48] transition cursor-pointer" title="${p.name}">
              ${p.name}
            </h4>
            <div class="inline-flex items-center gap-1 px-2.5 py-1 rounded-xl bg-amber-400 text-white font-black text-xs shadow-2xs shrink-0">
              <i class="fa-solid fa-star text-white text-[11px] drop-shadow-xs"></i>
              <span class="font-black text-white">${p.rating}</span>
            </div>
          </div>

          <!-- Ô VIỀN BAO QUÁT NỔI BẬT GIÁ TIỀN & GIỜ HOẠT ĐỘNG (1 KHỐI ĐỒNG NHẤT, SANG TRỌNG) -->
          <div class="bg-slate-50/80 border border-slate-200/80 rounded-2xl p-2.5 mb-3 shadow-2xs">
            <!-- Hàng 1: Giá tiền nổi bật -->
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5 min-w-0">
                <i class="fa-solid fa-receipt text-rose-500 text-xs flex-shrink-0"></i>
                <span class="text-xs sm:text-[13px] font-black text-slate-900 tracking-tight truncate">${cleanPrice}</span>
                ${priceUnit ? `<span class="text-[11px] text-slate-400 font-medium whitespace-nowrap">${priceUnit}</span>` : ''}
              </div>
              ${distanceHTML}
            </div>

            <!-- Vạch phân cách siêu mỏng -->
            <div class="border-t border-slate-200/60 my-1.5"></div>

            <!-- Hàng 2: Giờ mở cửa / Giờ cao điểm & Quận -->
            <div class="flex items-center justify-between text-[11px] text-slate-600 font-semibold gap-1.5 truncate">
              <span class="flex items-center gap-1.5 truncate">
                <i class="fa-regular fa-clock text-amber-500 text-[11px] flex-shrink-0"></i>
                <span class="truncate">${displayHours}</span>
              </span>
              <span class="text-slate-400 font-medium flex items-center gap-1 whitespace-nowrap flex-shrink-0">
                <i class="fa-solid fa-location-dot text-rose-500/70 text-[9px]"></i>
                <span>${p.district || 'TP.HCM'}</span>
              </span>
            </div>
          </div>
        </div>

        <!-- 3. Chân thẻ hành động -->
        <div class="pt-2.5 border-t border-slate-100 flex items-center justify-between gap-1.5">
          <div class="flex items-center gap-1.5">
            <button onclick="openPlaceDetailById(${p.id})" title="Xem chi tiết" class="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition flex items-center gap-1 cursor-pointer">
              <i class="fa-solid fa-circle-info text-[10px]"></i> <span>Chi tiết</span>
            </button>
            ${(currentUser && currentUser.role === 'admin') ? `
              <button onclick="openEditPlaceModalById(${p.id})" title="Sửa quán" class="px-2 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1 cursor-pointer">
                <i class="fa-solid fa-pen-to-square text-[10px]"></i>
              </button>
            ` : ''}
          </div>

          <a href="${gmapsUrl}" target="_blank" title="Xem thông tin & đánh giá trên Google Maps" class="px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1 whitespace-nowrap shadow-xs">
            <i class="fa-brands fa-google text-xs"></i> <span>Google Maps</span> <i class="fa-solid fa-arrow-up-right-from-square text-[9px]"></i>
          </a>
        </div>
      </div>
    </div>
  `;
}

function renderAllPlaces(places) {
  const container = document.getElementById("allPlacesGrid");
  container.innerHTML = "";

  // Bảo vệ đa tầng: loại trừ triệt để địa điểm bị ẩn khỏi Tab Khám Phá (Business Rule 2)
  const visiblePlaces = (places || []).filter(p => !p.is_hidden || p.is_hidden === 0);

  if (!visiblePlaces || visiblePlaces.length === 0) {
    container.innerHTML = `<div class="col-span-full p-10 text-center text-xs text-slate-400 bg-white rounded-2xl border border-dashed border-slate-200">Không tìm thấy địa điểm nào khớp với bộ lọc & bán kính đã chọn.<br><button onclick="clearExploreLocation()" class="mt-2 text-[#E11D48] font-bold underline cursor-pointer">Xóa bộ lọc bán kính để xem tất cả</button></div>`;
    return;
  }

  visiblePlaces.forEach(p => {
    container.innerHTML += buildCatalogCardHTML(p);
  });
}

function removeVietnameseTones(str) {
  if (!str) return "";
  str = str.toLowerCase();
  str = str.replace(/à|á|ạ|ả|ã|â|ầ|ấ|ậ|ẩ|ẫ|ă|ằ|ắ|ặ|ẳ|ẵ/g, "a");
  str = str.replace(/è|é|ẹ|ẻ|ẽ|ê|ề|ế|ệ|ể|ễ/g, "e");
  str = str.replace(/ì|í|ị|ỉ|ĩ/g, "i");
  str = str.replace(/ò|ó|ọ|ỏ|õ|ô|ồ|ố|ộ|ổ|ỗ|ơ|ờ|ớ|ợ|ở|ỡ/g, "o");
  str = str.replace(/ù|ú|ụ|ủ|ũ|ư|ừ|ứ|ự|ử|ữ/g, "u");
  str = str.replace(/ỳ|ý|ỵ|ỷ|ỹ/g, "y");
  str = str.replace(/đ/g, "d");
  str = str.replace(/\u0300|\u0301|\u0303|\u0309|\u0323/g, "");
  str = str.replace(/\u02C6|\u0306|\u031B/g, "");
  return str.trim();
}

function checkPlacePriceMatch(p, price) {
  if (price === "all") return true;
  const minP = p.min_price || 0;
  const maxP = p.max_price || 0;
  const isFree = (minP === 0 && maxP === 0);

  if (price === "free") {
    return isFree;
  }
  if (price === "under_50k" || price === "50000") {
    return isFree || (maxP > 0 && maxP <= 65000) || (minP > 0 && minP <= 50000 && maxP <= 75000);
  }
  if (price === "50k_100k") {
    if (isFree) return false;
    return (minP >= 40000 && minP <= 100000) || (maxP >= 50000 && maxP <= 120000) || (minP < 50000 && maxP >= 60000 && maxP <= 120000);
  }
  if (price === "100k_250k") {
    if (isFree) return false;
    return (minP >= 90000 && minP <= 250000) || (maxP >= 100000 && maxP <= 280000) || (minP <= 100000 && maxP >= 150000 && maxP <= 300000);
  }
  if (price === "above_250k") {
    if (isFree) return false;
    return (maxP >= 250000 || minP >= 200000);
  }
  if (price === "100000") {
    return isFree || minP <= 100000;
  }
  if (price === "250000") {
    return isFree || minP <= 250000;
  }
  return true;
}

function filterAllPlaces() {
  const q = document.getElementById("allSearchInput")?.value.trim() || "";
  const cat = document.getElementById("allCategoryFilter")?.value || "all";
  const tag = document.getElementById("allTagFilter")?.value || "all";
  const price = document.getElementById("allPriceFilter")?.value || "all";
  const sort = document.getElementById("allSortFilter")?.value || "default";
  const radius = document.getElementById("allRadiusFilter")?.value || "all";
  const radiusNum = radius !== "all" ? parseInt(radius) : null;

  // Cập nhật thông tin khoảng cách cho tất cả quán nếu đã có tọa độ
  allPlacesCache.forEach(p => {
    if (exploreUserCoords && p.lat && p.lon) {
      p.distanceKm = calculateHaversineDistanceKm(
        exploreUserCoords.lat,
        exploreUserCoords.lon,
        parseFloat(p.lat),
        parseFloat(p.lon)
      );
    } else {
      delete p.distanceKm;
    }
  });

  const normQ = removeVietnameseTones(q);

  let filtered = allPlacesCache.filter(p => {
    // 0. Bắt buộc: Quán bị ẩn không bao giờ được xuất hiện ở Tab Khám Phá (Business Rule 2)
    if (p.is_hidden === 1 || p.is_hidden === true) return false;

    // 1. Tìm kiếm thông minh (có dấu và không dấu tiếng Việt)
    let matchQ = true;
    if (normQ) {
      const normName = removeVietnameseTones(p.name || "");
      const normAddr = removeVietnameseTones(p.address || "");
      matchQ = normName.includes(normQ) || normAddr.includes(normQ);
    }

    // 2. Thể loại (Chỉ có 2 thể loại cốt lõi: Ẩm thực hoặc Đi chơi)
    const matchCat = (cat === "all") || (p.category === cat);

    // 3. Bối cảnh 2-Tier
    const pTiers = parsePlaceTiers(p.tags);
    const matchTag = (tag === "all") || pTiers.tier1.includes(tag) || pTiers.tier2.includes(tag);

    // 4. Mức giá chuẩn xác
    const matchPrice = checkPlacePriceMatch(p, price);

    // 5. Admin pick
    const matchAdminPick = (sort !== "admin_pick") || (p.is_admin_choice === 1);

    // 6. Lọc theo bán kính mét (nếu có vị trí)
    let matchRadius = true;
    if (radiusNum !== null) {
      if (typeof p.distanceKm === "number") {
        matchRadius = (p.distanceKm * 1000) <= radiusNum;
      } else {
        matchRadius = false;
      }
    }

    return matchQ && matchCat && matchTag && matchPrice && matchAdminPick && matchRadius;
  });

  // Sắp xếp
  if (sort === "distance_asc") {
    filtered.sort((a, b) => {
      const distA = typeof a.distanceKm === "number" ? a.distanceKm : 9999;
      const distB = typeof b.distanceKm === "number" ? b.distanceKm : 9999;
      return distA - distB;
    });
  } else if (sort === "rating_desc") {
    filtered.sort((a, b) => (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0));
  } else if (sort === "rating_asc") {
    filtered.sort((a, b) => (parseFloat(a.rating) || 0) - (parseFloat(b.rating) || 0));
  } else if (sort === "price_desc") {
    // Sắp xếp mức giá từ lớn tới bé (Cao đến thấp)
    filtered.sort((a, b) => {
      const pA = a.max_price || a.min_price || 0;
      const pB = b.max_price || b.min_price || 0;
      if (pB !== pA) return pB - pA;
      return (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0);
    });
  } else if (sort === "price_asc") {
    // Sắp xếp mức giá từ bé tới lớn (Thấp đến cao)
    filtered.sort((a, b) => {
      const pA = a.min_price || a.max_price || 0;
      const pB = b.min_price || b.max_price || 0;
      if (pA !== pB) return pA - pB;
      return (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0);
    });
  } else if (tag !== "all") {
    // Sắp xếp ưu tiên chuẩn 2-Tier: Quán có tag ở Tier 1 lên đầu, Tier 2 xếp sau, trong cùng Tier xếp theo rating cao
    filtered.sort((a, b) => {
      const tA = parsePlaceTiers(a.tags);
      const tB = parsePlaceTiers(b.tags);
      const rankA = tA.tier1.includes(tag) ? 1 : (tA.tier2.includes(tag) ? 2 : 3);
      const rankB = tB.tier1.includes(tag) ? 1 : (tB.tier2.includes(tag) ? 2 : 3);
      if (rankA !== rankB) return rankA - rankB;
      return (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0);
    });
  } else if (price !== "all") {
    // Khi đang lọc theo mức giá (ví dụ Dưới 50k) và sắp xếp là Mặc định: Tự động sắp xếp từ lớn tới bé
    filtered.sort((a, b) => {
      const pA = a.max_price || a.min_price || 0;
      const pB = b.max_price || b.min_price || 0;
      if (pB !== pA) return pB - pA;
      return (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0);
    });
  } else {
    // Mặc định: Quán Admin tuyển chọn (is_admin_choice) lên đầu, sau đó theo Rating cao nhất
    filtered.sort((a, b) => {
      if ((b.is_admin_choice || 0) !== (a.is_admin_choice || 0)) {
        return (b.is_admin_choice || 0) - (a.is_admin_choice || 0);
      }
      return (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0);
    });
  }

  // Cập nhật thanh đếm kết quả
  const countEl = document.getElementById("filteredPlacesCount");
  if (countEl) countEl.innerText = filtered.length;

  const radiusNotice = document.getElementById("activeRadiusNotice");
  if (radiusNotice) {
    if (radiusNum !== null && exploreUserCoords) {
      const radiusLabel = radiusNum < 1000 ? `${radiusNum} mét` : `${(radiusNum / 1000).toFixed(0)} km`;
      radiusNotice.innerHTML = `<i class="fa-solid fa-location-crosshairs text-emerald-600 mr-1.5"></i>Đang lọc trong bán kính <strong>${radiusLabel}</strong> (${filtered.length} quán)`;
      radiusNotice.classList.remove("hidden");
    } else {
      radiusNotice.classList.add("hidden");
    }
  }

  renderAllPlaces(filtered);
}

// Chức năng lưu quán yêu thích đã được xóa theo yêu cầu

// ==============================================================================
// 6. TRANG QUẢN TRỊ ADMIN (BỘ LỌC A-Z, TRÍCH XUẤT GOOGLE MAPS & CHỈNH ẢNH)
// ==============================================================================

let currentAdminSubTab = "places";

function switchAdminSubTab(subTab) {
  currentAdminSubTab = subTab;
  const btnPlaces = document.getElementById("adminSubTabPlaces");
  const btnUsers = document.getElementById("adminSubTabUsers");
  const secPlaces = document.getElementById("adminSectionPlaces");
  const secUsers = document.getElementById("adminSectionUsers");

  [btnPlaces, btnUsers].forEach(b => { if (b) b.className = "admin-subtab-btn"; });
  [secPlaces, secUsers].forEach(s => { if (s) s.classList.add("hidden"); });

  if (subTab === "places") {
    if (btnPlaces) btnPlaces.className = "admin-subtab-btn active";
    if (secPlaces) secPlaces.classList.remove("hidden");
  } else if (subTab === "users") {
    if (btnUsers) btnUsers.className = "admin-subtab-btn active";
    if (secUsers) secUsers.classList.remove("hidden");
    loadAdminUsers();
  }
}

async function loadAdminUsers() {
  try {
    const res = await fetch(`${API_BASE}/admin/users`, {
      headers: getAuthHeaders()
    });
    const users = await res.json();
    const countBadge = document.getElementById("adminUserCountBadge");
    const statUsers = document.getElementById("statTotalUsers");
    if (countBadge) countBadge.innerText = users.length;
    if (statUsers) statUsers.innerText = users.length;

    renderAdminUsersTable(users);
  } catch (e) {
    console.error("Lỗi tải danh sách người dùng:", e);
  }
}

function renderAdminUsersTable(users) {
  const tbody = document.getElementById("adminUsersTable");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!users || users.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-stone-400">Không có tài khoản người dùng nào.</td></tr>`;
    return;
  }

  users.forEach(u => {
    const isAdmin = u.role === "admin";
    const isSelf = currentUser && currentUser.id === u.id;

    tbody.innerHTML += `
      <tr class="hover:bg-stone-50/70 transition border-b border-stone-100">
        <td class="p-3.5 font-mono font-bold text-stone-400 whitespace-nowrap">#${u.id}</td>
        <td class="p-3.5 font-extrabold text-stone-900 whitespace-nowrap">${u.full_name} ${isSelf ? '<span class="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200 ml-1">Bạn</span>' : ''}</td>
        <td class="p-3.5 font-mono text-stone-600 whitespace-nowrap">@${u.username}</td>
        <td class="p-3.5 whitespace-nowrap">
          <span class="px-2.5 py-1 rounded-md text-[10px] font-black uppercase ${isAdmin ? 'bg-rose-50 text-rose-700 border border-rose-200' : 'bg-stone-100 text-stone-700 border border-stone-200'}">
            <i class="fa-solid ${isAdmin ? 'fa-user-gear' : 'fa-user'} mr-1"></i>
            ${isAdmin ? 'Quản Trị Viên' : 'Thành Viên'}
          </span>
        </td>
        <td class="p-3.5 text-stone-400 text-xs whitespace-nowrap">${u.created_at ? u.created_at.split('T')[0] : 'Ban đầu'}</td>
        <td class="p-3.5 text-center whitespace-nowrap bg-stone-50/50 border-l border-stone-100">
          <div class="flex items-center justify-center gap-1.5">
            <button onclick="toggleUserRole(${u.id}, '${u.role}')" class="px-3 py-1.5 ${isAdmin ? 'bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200' : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200'} rounded-xl font-bold text-xs flex items-center gap-1 transition cursor-pointer" title="Đổi quyền hạn">
              <i class="fa-solid ${isAdmin ? 'fa-arrow-down' : 'fa-arrow-up'} text-[10px]"></i>
              <span>${isAdmin ? 'Hạ quyền User' : 'Nâng quyền Admin'}</span>
            </button>
            <button onclick="handleDeleteUser(${u.id}, '${u.username}')" ${isSelf ? 'disabled' : ''} class="px-2.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-600 disabled:opacity-30 rounded-xl font-bold text-xs flex items-center gap-1 transition cursor-pointer" title="${isSelf ? 'Không thể tự xóa tài khoản đang đăng nhập' : 'Xóa tài khoản này'}">
              <i class="fa-solid fa-trash text-[11px]"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  });
}

async function toggleUserRole(userId, currentRole) {
  const newRole = currentRole === "admin" ? "user" : "admin";
  const label = newRole === "admin" ? "Quản trị viên (Admin)" : "Thành viên thông thường (User)";
  if (!confirm(`Bạn có chắc muốn đổi vai trò của tài khoản này thành ${label}?`)) return;

  try {
    const res = await fetch(`${API_BASE}/admin/users/${userId}/role`, {
      method: "PUT",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ role: newRole })
    });
    const data = await res.json();
    if (!res.ok) {
      alert("Lỗi: " + (data.detail || "Không thể cập nhật vai trò"));
      return;
    }
    alert(data.message || "Cập nhật vai trò thành công!");
    loadAdminUsers();
    // Nếu đổi chính tài khoản đang đăng nhập
    if (currentUser && currentUser.id === userId) {
      currentUser.role = newRole;
      localStorage.setItem("sggo_current_user", JSON.stringify(currentUser));
      updateAuthUI();
    }
  } catch (e) {
    alert("Lỗi kết nối máy chủ");
  }
}

async function handleDeleteUser(userId, username) {
  if (!confirm(`Cảnh báo: Bạn có chắc muốn xóa vĩnh viễn tài khoản @${username}? Thao tác này không thể hoàn tác.`)) return;

  try {
    const res = await fetch(`${API_BASE}/admin/users/${userId}`, {
      method: "DELETE",
      headers: getAuthHeaders()
    });
    const data = await res.json();
    if (!res.ok) {
      alert("Lỗi: " + (data.detail || "Không thể xóa tài khoản"));
      return;
    }
    alert(data.message || "Đã xóa tài khoản thành công!");
    loadAdminUsers();
  } catch (e) {
    alert("Lỗi kết nối máy chủ");
  }
}

async function loadAdminDashboard() {
  if (!currentUser || currentUser.role !== "admin") {
    alert("Chỉ Quản trị viên (Admin) mới có quyền truy cập khu vực này!");
    switchMode("flow");
    return;
  }

  try {
    const statsRes = await fetch(`${API_BASE}/admin/stats`, {
      headers: getAuthHeaders()
    });
    const stats = await statsRes.json();
    if (document.getElementById("statTotalPlaces")) document.getElementById("statTotalPlaces").innerText = stats.total_places;
    if (document.getElementById("statVerifiedPlaces")) document.getElementById("statVerifiedPlaces").innerText = stats.verified_places;
    if (document.getElementById("statTotalUsers")) document.getElementById("statTotalUsers").innerText = stats.total_users;
  } catch (e) {}

  try {
    const placesRes = await fetch(`${API_BASE}/places?include_hidden=true`);
    allPlacesCache = await placesRes.json();
    renderAdminPlacesTable(allPlacesCache);
    populateQuickEditSelect(allPlacesCache);
  } catch (e) {}

  loadAdminUsers();
}

function populateQuickEditSelect(places) {
  const sel = document.getElementById("quickEditPlaceSelect");
  if (!sel) return;
  const currentVal = sel.value;
  sel.innerHTML = `<option value="">-- Chọn quán cần chỉnh sửa ngay (${places.length} quán) --</option>`;
  places.forEach(p => {
    const isEat = p.category === "an_uong";
    sel.innerHTML += `<option value="${p.id}">#${p.id} - ${p.name} (${isEat ? 'Ẩm thực' : 'Đi chơi'})</option>`;
  });
  if (currentVal) sel.value = currentVal;
}

function handleQuickSelectEdit(placeId) {
  if (!placeId) return;
  openEditPlaceModalById(parseInt(placeId));
  const sel = document.getElementById("quickEditPlaceSelect");
  if (sel) sel.value = "";
}

function renderAdminPlacesTable(places) {
  const tbody = document.getElementById("adminPlacesTable");
  const countEl = document.getElementById("adminFilteredCount");
  tbody.innerHTML = "";

  if (countEl) countEl.innerText = `Hiển thị ${places.length} địa điểm`;

  if (!places || places.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-slate-400">Không có địa điểm nào khớp với bộ lọc.</td></tr>`;
    return;
  }

  places.forEach(p => {
    const isEat = p.category === "an_uong";
    const isHidden = (p.is_hidden === 1);
    const imageHtml = renderPlaceImage(p, "w-12", "h-10");

    tbody.innerHTML += `
      <tr class="hover:bg-blue-50/40 transition border-b border-slate-100 ${isHidden ? 'bg-slate-50/80 opacity-75' : ''}">
        <td class="p-3 font-mono font-bold text-slate-400 whitespace-nowrap">#${p.id}</td>
        <td class="p-3 whitespace-nowrap">
          <div class="w-12 h-10 flex-shrink-0">
            ${imageHtml}
          </div>
        </td>
        <td class="p-3 min-w-[190px] max-w-[260px]">
          <div class="font-extrabold text-slate-900 truncate flex items-center gap-1.5" title="${p.name}">
            <span class="truncate">${p.name}</span>
            ${p.is_admin_choice === 1 ? '<span class="text-[9px] bg-amber-100 text-amber-900 font-extrabold px-1.5 py-0.5 rounded border border-amber-300 whitespace-nowrap flex items-center gap-0.5"><i class="fa-solid fa-crown text-amber-600"></i> Pick</span>' : ''}
            ${isHidden ? '<span class="text-[9px] bg-rose-100 text-rose-700 font-extrabold px-1.5 py-0.5 rounded border border-rose-200 whitespace-nowrap flex items-center gap-0.5"><i class="fa-solid fa-eye-slash"></i> Đã ẩn</span>' : '<span class="text-[9px] bg-emerald-50 text-emerald-700 font-bold px-1.5 py-0.5 rounded border border-emerald-200 whitespace-nowrap flex items-center gap-0.5"><i class="fa-solid fa-eye"></i> Hiện</span>'}
          </div>
          <div class="text-[11px] text-slate-400 truncate" title="${p.address}">${p.address}</div>
        </td>
        <td class="p-3 whitespace-nowrap">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold ${isEat ? 'bg-rose-50 text-[#E11D48]' : 'bg-teal-50 text-teal-700'}">
            ${isEat ? 'Ẩm thực' : 'Đi chơi'}
          </span>
        </td>
        <td class="p-3 font-medium whitespace-nowrap text-slate-600">${(p.min_price === 0 && p.max_price === 0) ? 'Miễn phí' : `${p.min_price.toLocaleString()}đ - ${p.max_price.toLocaleString()}đ`}</td>
        <td class="p-3 whitespace-nowrap">
          <span class="font-bold text-amber-700 inline-flex items-center gap-1"><i class="fa-solid fa-star text-amber-500 text-[10px]"></i> ${p.rating}</span>
          <div class="text-[10px] text-slate-400 font-normal">${p.open_time} - ${p.close_time}</div>
        </td>
        <td class="p-3 text-center whitespace-nowrap bg-blue-50/30 border-l border-blue-100">
          <div class="flex items-center justify-center gap-1.5">
            <button onclick="handleToggleHidePlace(${p.id}, ${isHidden ? 0 : 1})" class="px-2.5 py-1.5 rounded-xl font-bold text-xs flex items-center gap-1 transition shadow-xs cursor-pointer ${isHidden ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : 'bg-slate-200 hover:bg-slate-300 text-slate-700'}" title="${isHidden ? 'Hiện lại quán này trên trang người dùng' : 'Ẩn quán này khỏi trang người dùng'}">
              <i class="fa-solid ${isHidden ? 'fa-eye' : 'fa-eye-slash'}"></i> <span>${isHidden ? 'Hiện lại' : 'Ẩn quán'}</span>
            </button>
            <button onclick="openEditPlaceModalById(${p.id})" class="px-2.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold text-xs flex items-center gap-1 transition shadow-xs cursor-pointer" title="Chỉnh sửa toàn bộ thông tin quán này">
              <i class="fa-solid fa-pen-to-square"></i> <span>Sửa</span>
            </button>
            <button onclick="handleDeletePlaceById(${p.id})" class="px-2 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-600 rounded-xl font-bold text-xs flex items-center gap-1 transition cursor-pointer" title="Xóa địa điểm">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  });
}

async function handleToggleHidePlace(placeId, targetHidden) {
  try {
    const res = await fetch(`${API_BASE}/admin/places/${placeId}/toggle-hide`, {
      method: "POST",
      headers: getAuthHeaders()
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Không thể thay đổi trạng thái ẩn.");
    }
    const data = await res.json();
    const p = allPlacesCache.find(x => Number(x.id) === Number(placeId));
    if (p) p.is_hidden = data.place.is_hidden;
    filterAdminTable();
  } catch (err) {
    alert("Lỗi: " + err.message);
  }
}

// ==============================================================================
// SẮP XẾP VÀ BỘ LỌC TỪ A ĐẾN Z CHO ADMIN (TÌM THEO ID, TÊN, ĐỊA CHỈ & XẾP THEO ID)
// ==============================================================================

let adminSortOrderId = "asc"; // "asc": Tăng dần (1 -> 201 chuẩn theo 7 nhóm học phần), "desc": Mới nhất (201 -> 1)

function toggleAdminSortOrder() {
  adminSortOrderId = (adminSortOrderId === "desc") ? "asc" : "desc";
  const icon = document.getElementById("adminSortIdIcon");
  if (icon) {
    if (adminSortOrderId === "desc") {
      icon.className = "fa-solid fa-arrow-down-9-1 text-[#E11D48] ml-1";
      if (icon.parentElement) icon.parentElement.setAttribute("title", "Đang xếp ID: Mới nhất đến cũ nhất (Bấm để đổi tăng dần)");
    } else {
      icon.className = "fa-solid fa-arrow-up-1-9 text-blue-600 ml-1";
      if (icon.parentElement) icon.parentElement.setAttribute("title", "Đang xếp ID: Cũ nhất đến mới nhất (Bấm để đổi giảm dần)");
    }
  }
  filterAdminTable();
}

function filterAdminTable() {
  const idQ = document.getElementById("adminSearchIdInput")?.value.trim() || "";
  const q = document.getElementById("adminSearchInput")?.value.trim() || "";
  const cat = document.getElementById("adminCategoryFilter")?.value || "all";
  const tag = document.getElementById("adminTagFilter")?.value || "all";
  const rating = document.getElementById("adminRatingFilter")?.value || "all";
  const price = document.getElementById("adminPriceFilter")?.value || "all";
  const status = document.getElementById("adminStatusFilter")?.value || "all";

  // 1. Xử lý ô tìm kiếm chuyên biệt theo ID (Tìm chính xác ID địa điểm)
  const cleanIdQ = idQ.replace(/^#/, "").replace(/^id\s*:?\s*/i, "").trim();

  // 2. Xử lý ô tìm kiếm theo Tên quán & Địa chỉ
  const normQ = removeVietnameseTones(q);

  const filtered = allPlacesCache.filter(p => {
    // A. Lọc chính xác theo ID quán (khi có nhập ô ID)
    if (cleanIdQ) {
      if (String(p.id) !== cleanIdQ) return false;
    }

    // B. Lọc theo Tên quán & Địa chỉ (nếu ô tìm kiếm chung có nhập)
    if (normQ) {
      // Dự phòng: nếu người dùng vẫn quen gõ #ID vào ô tên quán
      if (normQ.startsWith("#") && normQ.slice(1).trim().length > 0 && !isNaN(normQ.slice(1).trim())) {
        if (String(p.id) !== normQ.slice(1).trim()) return false;
      } else {
        const normName = removeVietnameseTones(p.name || "");
        const normAddr = removeVietnameseTones(p.address || "");
        if (!normName.includes(normQ) && !normAddr.includes(normQ)) return false;
      }
    }

    // C. Lọc theo Thể loại
    if (cat !== "all" && p.category !== cat) return false;
    
    // D. Lọc theo Thẻ bối cảnh (Context Tag - Tier 1 & Tier 2)
    if (tag !== "all") {
      const pTiers = parsePlaceTiers(p.tags || "");
      const matchTag = pTiers.tier1.includes(tag) || pTiers.tier2.includes(tag) || (p.tags && p.tags.includes(tag));
      if (!matchTag) return false;
    }

    // E. Lọc theo Đánh giá sao
    if (rating !== "all" && p.rating < parseFloat(rating)) return false;
    
    // F. Lọc theo Mức giá
    if (price === "free" && !checkPlacePriceMatch(p, "free")) return false;
    else if (price === "50000" && !checkPlacePriceMatch(p, "under_50k")) return false;
    else if (price === "100000" && (!checkPlacePriceMatch(p, "50k_100k") && !checkPlacePriceMatch(p, "under_50k"))) return false;
    else if (price === "above_100k" && p.max_price < 100000) return false;

    // G. Lọc theo Trạng thái ẩn/hiện
    if (status === "visible" && (p.is_hidden && p.is_hidden === 1)) return false;
    else if (status === "hidden" && (!p.is_hidden || p.is_hidden === 0)) return false;

    return true;
  });

  // Sắp xếp danh sách bảng Admin theo ID (Tăng dần hoặc Giảm dần)
  filtered.sort((a, b) => {
    // Nếu có nhập ô tìm ID, luôn ưu tiên quán khớp chính xác ID (VD: 18) lên vị trí đầu tiên
    if (cleanIdQ) {
      const isExactA = (String(a.id) === cleanIdQ);
      const isExactB = (String(b.id) === cleanIdQ);
      if (isExactA && !isExactB) return -1;
      if (!isExactA && isExactB) return 1;
    }
    const idA = Number(a.id) || 0;
    const idB = Number(b.id) || 0;
    return adminSortOrderId === "asc" ? (idA - idB) : (idB - idA);
  });

  renderAdminPlacesTable(filtered);
}

// KIỂM TRA VÀ CẢNH BÁO TRÙNG LẶP ĐỊA ĐIỂM TRONG FORM ADMIN (ĐA LỚP)
// ==============================================================================
// KIỂM TRA VÀ CHỐNG TRÙNG LẶP ĐỊA ĐIỂM THÔNG MINH ĐA LỚP TRÊN GIAO DIỆN ADMIN
// ==============================================================================

const CLIENT_COMPLEX_KEYWORDS = [
  "mall", "plaza", "center", "centre", "tttm", "bitexco", "landmark",
  "tầng ", "tang ", "lầu ", "lau ", "food court", "parkson", "takashimaya",
  "vincom", "aeon", "crescent", "gigamall", "nowzone", "sc vivocity",
  "lotte mart", "vạn hạnh mall", "van hanh mall", "chợ ", "cho ",
  "bạch đằng", "bach dang", "công viên", "cong vien", "thảo cầm viên", "thao cam vien", "bảo tàng", "bao tang"
];

const CLIENT_BRAND_STOPWORDS = new Set([
  "quan", "nha", "hang", "tiem", "ca", "phe", "cafe", "tra", "sua", "buffet", "vietnam", "am", "thuc", "food", "coffee", "tea",
  "van", "hanh", "mall", "plaza", "center", "centre", "tttm", "vincom", "aeon", "hung", "vuong", "bitexco", "landmark", "crescent",
  "gigamall", "nowzone", "takashimaya", "parkson", "lotte", "bach", "dang", "cho", "ben", "thanh"
]);

function isClientCommercialComplex(addr, name) {
  const text = ((addr || "") + " " + (name || "")).toLowerCase();
  return CLIENT_COMPLEX_KEYWORDS.some(k => text.includes(k));
}

function normalizeClientText(s) {
  const expanded = expandClientAddressAbbreviations(s || "");
  return expanded.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/[^a-z0-9\s,]/g, " ").replace(/\s+/g, " ").trim();
}

function splitClientHouseNumberAndStreet(text) {
  if (!text) return { num: "", street: "" };
  const norm = normalizeClientText(text);
  const part = norm.split(",")[0].trim();
  const m = part.match(/^([0-9]+[a-z0-9\/\-]*)(\s+)(.*)$/);
  if (m) {
    return { num: m[1].trim(), street: m[3].trim() };
  }
  return { num: "", street: part };
}

function extractClientFloorNumber(text) {
  if (!text) return "";
  const norm = normalizeClientText(text);
  const m = norm.match(/(tang\s*[0-9]+|lau\s*[0-9]+|floor\s*[0-9]+|tang\s*tret|lau\s*tret|tang\s*lung|l[0-9]{1,2})/);
  if (m) {
    return m[1].replace(/\s+/g, "");
  }
  return "";
}

function checkClientAddressesMatch(addr1, addr2) {
  const c1 = normalizeClientText(addr1).replace(/[\s,]/g, "");
  const c2 = normalizeClientText(addr2).replace(/[\s,]/g, "");
  if (!c1 || !c2) return false;
  if (c1 === c2) return true;

  const { num: num1, street: street1 } = splitClientHouseNumberAndStreet(addr1);
  const { num: num2, street: street2 } = splitClientHouseNumberAndStreet(addr2);

  if (num1 && num2 && street1 && street2) {
    if (num1 === num2) {
      const st1 = street1.replace(/^(duong|d)\s+/, "").trim();
      const st2 = street2.replace(/^(duong|d)\s+/, "").trim();
      if (st1 === st2 || (st1.length >= 6 && st2.length >= 6 && (st1.includes(st2) || st2.includes(st1)))) {
        return true;
      }
    }
    return false;
  }

  if (c1.length >= 12 && c2.length >= 12) {
    if (c1.includes(c2) || c2.includes(c1)) return true;
    if (c1.length >= 16 && c2.length >= 16 && c1.slice(0, 16) === c2.slice(0, 16)) return true;
  }
  return false;
}

function checkClientBrandOverlap(name1, name2) {
  const c1 = normalizeClientText(name1).replace(/[\s,]/g, "");
  const c2 = normalizeClientText(name2).replace(/[\s,]/g, "");
  if (!c1 || !c2) return false;
  if (c1 === c2) return true;
  if (c1.length >= 4 && c2.length >= 4 && (c1.includes(c2) || c2.includes(c1))) return true;

  const t1 = c1.split(" ").filter(w => w.length >= 3 && !CLIENT_BRAND_STOPWORDS.has(w));
  const t2 = c2.split(" ").filter(w => w.length >= 3 && !CLIENT_BRAND_STOPWORDS.has(w));
  const set2 = new Set(t2);
  return t1.some(w => set2.has(w));
}

function findClientDuplicate(nameInput, addrInput, latInput, lonInput, mapsInput, catInput, currentId) {
  if (!Array.isArray(allPlacesCache) || allPlacesCache.length === 0) return null;

  const cleanName = normalizeClientText(nameInput).replace(/[\s,]/g, "");
  const cleanAddr = normalizeClientText(addrInput).replace(/[\s,]/g, "");
  const cleanMaps = (mapsInput || "").trim().toLowerCase();
  const newIsComplex = isClientCommercialComplex(addrInput, nameInput);
  const newFloor = extractClientFloorNumber(addrInput);

  for (const p of allPlacesCache) {
    if (currentId && String(p.id) === String(currentId)) continue;

    const pName = normalizeClientText(p.name).replace(/[\s,]/g, "");
    const pAddr = normalizeClientText(p.address).replace(/[\s,]/g, "");
    const pCat = p.category || "";
    const pMaps = (p.google_maps_url || "").trim().toLowerCase();
    const pLat = parseFloat(p.lat);
    const pLon = parseFloat(p.lon);
    const pIsComplex = isClientCommercialComplex(p.address, p.name);
    const pFloor = extractClientFloorNumber(p.address);

    // Lớp 1: Khớp tên chuẩn hóa 100%
    if (cleanName && pName && cleanName === pName) {
      return { place: p, reason: `Trùng tên 100% với quán <strong>"${p.name}"</strong> (ID: #${p.id})` };
    }

    // Lớp 2: Trùng link Google Maps
    if (cleanMaps && pMaps && cleanMaps === pMaps && !cleanMaps.includes("search/?api=1")) {
      return { place: p, reason: `Trùng liên kết Google Maps với quán <strong>"${p.name}"</strong> (ID: #${p.id})` };
    }

    // Lớp 3: Trùng địa chỉ (KỂ CẢ TÊN KHÁC NHAU HOẶC CHƯA NHẬP TÊN!)
    if (cleanAddr && pAddr) {
      // 3A. Khớp 100% chuỗi địa chỉ
      if (cleanAddr === pAddr) {
        return { place: p, reason: `Trùng 100% địa chỉ ("${p.address}") với quán <strong>"${p.name}"</strong> (ID: #${p.id})` };
      }

      // 3B. Khớp số nhà / tên đường qua checkClientAddressesMatch
      if (checkClientAddressesMatch(addrInput, p.address)) {
        if (!newIsComplex && !pIsComplex) {
          return { place: p, reason: `Trùng hoàn toàn địa chỉ ("${p.address}") với quán <strong>"${p.name}"</strong> (ID: #${p.id})` };
        } else {
          // Nếu trong TTTM/Phức hợp mà trùng cả số tầng
          if (newFloor && pFloor && newFloor === pFloor) {
            return { place: p, reason: `Trùng địa chỉ và cùng số tầng (${newFloor}) với quán <strong>"${p.name}"</strong> (ID: #${p.id})` };
          }
          // Nếu có thương hiệu tương đồng
          if (checkClientBrandOverlap(nameInput, p.name)) {
            return { place: p, reason: `Trùng địa chỉ và tên thương hiệu tương đồng với quán <strong>"${p.name}"</strong> (ID: #${p.id})` };
          }
        }
      }
    }

    // Phân biệt TTTM (di_choi) và quán ăn (an_uong) bên trong TTTM
    if ((newIsComplex || pIsComplex) && catInput && pCat && ((catInput === "di_choi" && pCat === "an_uong") || (catInput === "an_uong" && pCat === "di_choi"))) {
      continue;
    }

    // Lớp 4: Tọa độ GPS trùng sát (< 15m)
    if (!isNaN(latInput) && !isNaN(lonInput) && !isNaN(pLat) && !isNaN(pLon)) {
      const dLat = (latInput - pLat) * 111320;
      const dLon = (lonInput - pLon) * 111320 * Math.cos(latInput * (Math.PI / 180));
      const distM = Math.sqrt(dLat * dLat + dLon * dLon);
      if (distM < 15.0) {
        if (checkClientBrandOverlap(nameInput, p.name)) {
          return { place: p, reason: `Tọa độ GPS trùng sát (~${Math.round(distM)}m) và cùng thương hiệu với quán <strong>"${p.name}"</strong> (ID: #${p.id})` };
        }
        if (checkClientAddressesMatch(addrInput, p.address)) {
          return { place: p, reason: `Tọa độ GPS trùng sát (~${Math.round(distM)}m) và cùng địa chỉ với quán <strong>"${p.name}"</strong> (ID: #${p.id})` };
        }
        if (distM < 5.0 && !newIsComplex && !pIsComplex) {
          const { num: n1 } = splitClientHouseNumberAndStreet(addrInput);
          const { num: n2 } = splitClientHouseNumberAndStreet(p.address);
          if (!(n1 && n2 && n1 !== n2)) {
            return { place: p, reason: `Tọa độ GPS trùng sát (~${Math.round(distM)}m) với quán <strong>"${p.name}"</strong> (ID: #${p.id}) tại "${p.address}"` };
          }
        }
      }
    }

    // Lớp 5: Tên chứa nhau và trùng địa chỉ / đường
    if (checkClientBrandOverlap(nameInput, p.name) && cleanAddr && pAddr) {
      if (cleanAddr.includes(pAddr) || pAddr.includes(cleanAddr) || cleanAddr.slice(0, 15) === pAddr.slice(0, 15)) {
        return { place: p, reason: `Tên và địa chỉ rất tương đồng với quán <strong>"${p.name}"</strong> (${p.address})` };
      }
    }
  }

  return null;
}

function updateDuplicateWarningUI() {
  const warnBox = document.getElementById("formDuplicateWarning");
  const warnText = document.getElementById("formDuplicateWarningText");
  if (!warnBox || !warnText) return;

  const currentId = document.getElementById("formPlaceId")?.value;
  const nameInput = document.getElementById("formName")?.value?.trim() || "";
  const addrInput = document.getElementById("formAddress")?.value?.trim() || "";
  const latInput = parseFloat(document.getElementById("formLat")?.value);
  const lonInput = parseFloat(document.getElementById("formLon")?.value);
  const mapsInput = document.getElementById("formGoogleMapsUrl")?.value?.trim() || "";
  const catInput = document.getElementById("formCategory")?.value || "an_uong";

  // Nếu cả tên và địa chỉ đều chưa nhập hoặc quá ngắn thì ẩn
  if ((!nameInput || nameInput.length < 2) && (!addrInput || addrInput.length < 5)) {
    warnBox.classList.add("hidden");
    warnText.innerHTML = "";
    return;
  }

  const dup = findClientDuplicate(nameInput, addrInput, latInput, lonInput, mapsInput, catInput, currentId);
  if (dup) {
    warnText.innerHTML = `<strong>⚠️ CẢNH BÁO TRÙNG LẶP:</strong> ${dup.reason}. Vui lòng kiểm tra lại để tránh lưu trùng dữ liệu vào hệ thống!`;
    warnBox.classList.remove("hidden");
  } else {
    warnBox.classList.add("hidden");
    warnText.innerHTML = "";
  }
}

// BÓC TÁCH LINK GOOGLE MAPS (ĐÃ BỎ CHỨC NĂNG NHẬP TÊN QUÁN)
async function handleExtractGmaps() {
  const input = document.getElementById("gmapsExtractInput");
  const raw = input.value.trim();
  if (!raw) {
    alert("Vui lòng dán link Google Maps vào ô bên trên!");
    return;
  }
  const isUrl = raw.startsWith("http://") || raw.startsWith("https://") || raw.includes("maps.") || raw.includes("goo.gl") || raw.includes("google.com");
  if (!isUrl) {
    alert("Vui lòng dán đúng đường link Google Maps (bắt đầu bằng https://... hoặc https://maps.app.goo.gl/)!\n\n(Lưu ý: Chức năng này chỉ nhận liên kết Google Maps để định vị và lấy thông tin cơ bản, đã bỏ chức năng nhập tên quán để tránh dữ liệu sai lệch)");
    return;
  }

  const btn = document.getElementById("btnExtractGmaps");
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang bóc tách...`;
  btn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/admin/extract-gmaps`, {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ url_or_query: raw })
    });
    
    if (!res.ok) {
      let errDetail = "Không thể bóc tách link này.";
      try {
        const errJson = await res.json();
        errDetail = errJson.detail || errDetail;
      } catch (e) {}
      throw new Error(errDetail);
    }
    
    const data = await res.json();
    const p = data.place || {};
    let extractedCount = 0;

    // Tự động điền dữ liệu bóc tách THỰC TẾ từ URL vào form (Tên, Thể loại, Địa chỉ số nhà, Tọa độ GPS)
    if (p.name) {
      document.getElementById("formName").value = p.name;
      extractedCount++;
    }
    if (p.category) document.getElementById("formCategory").value = p.category;
    if (p.address && !p.address.includes("Mặc định")) {
      document.getElementById("formAddress").value = p.address;
      extractedCount++;
    }
    if (p.district) {
      document.getElementById("formDistrict").value = p.district;
      extractedCount++;
    }
    if (p.lat != null && p.lat !== "" && !isNaN(p.lat) && p.lat !== 0) {
      document.getElementById("formLat").value = p.lat;
      extractedCount++;
    }
    if (p.lon != null && p.lon !== "" && !isNaN(p.lon) && p.lon !== 0) {
      document.getElementById("formLon").value = p.lon;
      extractedCount++;
    }

    // Điền Số sao, Lượt review, Giờ hoạt động CHỈ KHI Google Maps CÓ THẬT (Tuyệt đối không điền số ảo)
    if (p.rating && p.rating > 0) {
      document.getElementById("formRating").value = p.rating;
    }
    if (p.reviews_count && p.reviews_count > 0) {
      document.getElementById("formReviewsCount").value = p.reviews_count;
    }
    if (p.open_time && p.open_time.includes(":")) {
      document.getElementById("formOpenTime").value = p.open_time;
    }
    if (p.close_time && p.close_time.includes(":")) {
      document.getElementById("formCloseTime").value = p.close_time;
    }

    // TUYỆT ĐỐI ĐỂ TRỐNG: Giá tối thiểu/tối đa, Giờ cao điểm
    // vì Google Maps không có tiền VNĐ, Admin tự nhập thực tế từ menu để đảm bảo 100% liêm chính dữ liệu
    const formGmapsUrl = document.getElementById("formGoogleMapsUrl");
    if (formGmapsUrl) {
      formGmapsUrl.value = raw.startsWith("http") ? raw : (p.google_maps_url || "");
    }
    const btnGmaps = document.getElementById("btnAdminOpenGmaps");
    if (btnGmaps) {
      btnGmaps.href = raw.startsWith("http") ? raw : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((p.name || '') + ' ' + (p.address || ''))}`;
      btnGmaps.classList.remove("hidden");
    }

    // Đổ dữ liệu phân tầng 2-Tier vào checkbox nếu có
    if (p.tags) {
      const { tier1: curT1, tier2: curT2 } = parsePlaceTiers(p.tags || "");
      ['di_1_minh', 'hen_ho', 'nhom_ban', 'gia_dinh'].forEach(t => {
        const c1 = document.getElementById(`chk_t1_${t}`);
        const c2 = document.getElementById(`chk_t2_${t}`);
        if (c1) c1.checked = curT1.includes(t);
        if (c2) c2.checked = curT2.includes(t);
      });
      syncAdminTagsInput();
    }

    if (p.best_review) document.getElementById("formBestReview").value = p.best_review;
    if (p.worst_review) document.getElementById("formWorstReview").value = p.worst_review;
    
    const imgEl = document.getElementById("formImageUrl");
    if (imgEl && p.image_url) {
      imgEl.value = p.image_url;
      updateImagePreview(p.image_url);
    }

    const chk = document.getElementById("formIsVerifiedReview");
    if (chk) chk.checked = true;

    // Kích hoạt kiểm tra trùng lặp ngay sau khi trích xuất
    updateDuplicateWarningUI();

    let extraRealInfo = [];
    if (p.rating) extraRealInfo.push(`⭐ Số sao thật trên Maps: ${p.rating} / 5.0`);
    if (p.open_time && p.close_time) extraRealInfo.push(`⏰ Giờ hoạt động thật trên Maps: ${p.open_time} - ${p.close_time}`);
    if (p.reviews_count) extraRealInfo.push(`📝 Lượt review thật: ${p.reviews_count}`);
    const realInfoText = extraRealInfo.length > 0 ? ("\n" + extraRealInfo.join("\n") + "\n") : "\n";

    alert(`✔ Đã bóc tách dữ liệu thật từ Google Maps cho "${p.name || 'địa điểm'}"!\n${realInfoText}\n📍 Địa chỉ số nhà & Tọa độ GPS: Đã trích xuất chính xác 100% từ Google Maps.\n\n⚠️ LƯU Ý LIÊM CHÍNH DỮ LIỆU (KHÔNG DÙNG SỐ LIỆU ẢO):\n- Khoảng giá tiền (VNĐ) và Giờ cao điểm được chủ động để trống vì Google Maps không cung cấp số tiền VNĐ. Admin vui lòng tự nhập theo menu thực tế!`);
  } catch (err) {
    if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
      alert("Không thể kết nối tới Backend! Vui lòng kiểm tra xem bạn đã chạy file MO_WEB_SGGO.bat chưa.");
    } else {
      alert("Lỗi bóc tách: " + err.message);
    }
  } finally {
    btn.innerHTML = `<i class="fa-solid fa-bolt"></i> Tự Động Điền`;
    btn.disabled = false;
  }
}

function updateImagePreview(url) {
  const img = document.getElementById("formImagePreview");
  const noImg = document.getElementById("formImageNoPreview");
  if (img && noImg) {
    if (url && url.trim()) {
      img.src = url;
      img.classList.remove("hidden");
      noImg.classList.add("hidden");
      img.onerror = () => {
        img.classList.add("hidden");
        noImg.classList.remove("hidden");
      };
    } else {
      img.src = "";
      img.classList.add("hidden");
      noImg.classList.remove("hidden");
    }
  }
}

function openAddPlaceModal() {
  document.getElementById("placeFormTitle").innerText = "Thêm Địa Điểm Mới";
  document.getElementById("placeFormSubtitle").innerText = "Nhập dữ liệu địa điểm tại Sài Gòn";
  document.getElementById("btnSubmitPlaceForm").innerText = "Lưu Địa Điểm Mới";
  const btnGmaps = document.getElementById("btnAdminOpenGmaps");
  if (btnGmaps) btnGmaps.classList.add("hidden");
  document.getElementById("gmapsExtractorBox").classList.remove("hidden");
  document.getElementById("gmapsExtractInput").value = "";
  document.getElementById("placeAdminForm").reset();
  document.getElementById("formPlaceId").value = "";
  document.getElementById("formName").value = "";
  document.getElementById("formCategory").value = "an_uong";
  document.getElementById("formDistrict").value = "";
  document.getElementById("formAddress").value = "";
  const formGmapsUrl = document.getElementById("formGoogleMapsUrl");
  if (formGmapsUrl) formGmapsUrl.value = "";
  document.getElementById("formLat").value = "";
  document.getElementById("formLon").value = "";
  document.getElementById("formReviewsCount").value = "";
  document.getElementById("formOpenTime").value = "";
  document.getElementById("formCloseTime").value = "";
  document.getElementById("formMinPrice").value = "";
  document.getElementById("formMaxPrice").value = "";
  const pDispEl = document.getElementById("formPriceDisplay");
  if (pDispEl) pDispEl.value = "";
  document.getElementById("formRating").value = "";
  document.getElementById("formPeakHours").value = "";
  ['di_1_minh', 'hen_ho', 'nhom_ban', 'gia_dinh'].forEach(t => {
    const c1 = document.getElementById(`chk_t1_${t}`);
    const c2 = document.getElementById(`chk_t2_${t}`);
    if (c1) c1.checked = false;
    if (c2) c2.checked = false;
  });
  syncAdminTagsInput();
  document.getElementById("formBestReview").value = "";
  document.getElementById("formWorstReview").value = "";
  const chkRev = document.getElementById("formIsVerifiedReview");
  if (chkRev) chkRev.checked = true;
  const chkAdmin = document.getElementById("formIsAdminChoice");
  if (chkAdmin) chkAdmin.checked = false;
  const chkHidden = document.getElementById("formIsHidden");
  if (chkHidden) chkHidden.checked = false;
  document.getElementById("formImageUrl").value = "";
  updateImagePreview("");
  const warnBox = document.getElementById("formDuplicateWarning");
  if (warnBox) warnBox.classList.add("hidden");
  document.getElementById("modalPlaceForm").classList.remove("hidden");
}

async function openEditPlaceModalById(id) {
  let p = allPlacesCache.find(x => Number(x.id) === Number(id));
  if (!p) {
    try {
      const res = await fetch(`${API_BASE}/places/${id}`);
      if (res.ok) p = await res.json();
    } catch (e) {}
  }
  if (!p) {
    alert("Không tìm thấy thông tin địa điểm #" + id);
    return;
  }
  openEditPlaceModal(p);
}

function handleDeletePlaceById(id) {
  const p = allPlacesCache.find(x => Number(x.id) === Number(id));
  const name = p ? p.name : `#${id}`;
  handleDeletePlace(id, name);
}

function openEditPlaceModal(p) {
  document.getElementById("placeFormTitle").innerHTML = `<i class="fa-solid fa-pen-to-square text-blue-600 mr-1.5"></i> Chỉnh Sửa Quán #${p.id} — ${p.name}`;
  document.getElementById("placeFormSubtitle").innerText = "Chỉnh sửa thông tin địa điểm";
  document.getElementById("btnSubmitPlaceForm").innerText = `Lưu Cập Nhật Cho Quán #${p.id}`;
  
  // Đồng bộ liên kết Google Maps đối chiếu cho Admin
  const formGmapsUrl = document.getElementById("formGoogleMapsUrl");
  if (formGmapsUrl) formGmapsUrl.value = p.google_maps_url || "";

  const btnGmaps = document.getElementById("btnAdminOpenGmaps");
  if (btnGmaps) {
    btnGmaps.href = p.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.name + ', ' + (p.address || p.district || 'TP.HCM'))}`;
    btnGmaps.classList.remove("hidden");
  }

  document.getElementById("gmapsExtractorBox").classList.add("hidden");
  document.getElementById("formPlaceId").value = p.id;
  document.getElementById("formName").value = p.name || "";
  document.getElementById("formCategory").value = p.category || "an_uong";
  document.getElementById("formDistrict").value = p.district || "";
  document.getElementById("formAddress").value = p.address || "";
  document.getElementById("formLat").value = (p.lat !== undefined && p.lat !== null && p.lat !== 0) ? p.lat : "";
  document.getElementById("formLon").value = (p.lon !== undefined && p.lon !== null && p.lon !== 0) ? p.lon : "";
  document.getElementById("formReviewsCount").value = (p.reviews_count !== undefined && p.reviews_count !== null && p.reviews_count > 0) ? p.reviews_count : "";
  document.getElementById("formOpenTime").value = p.open_time || "";
  document.getElementById("formCloseTime").value = p.close_time || "";
  document.getElementById("formMinPrice").value = (p.min_price !== undefined && p.min_price !== null && p.min_price > 0) ? p.min_price : "";
  document.getElementById("formMaxPrice").value = (p.max_price !== undefined && p.max_price !== null && p.max_price > 0) ? p.max_price : "";
  document.getElementById("formRating").value = (p.rating !== undefined && p.rating !== null && p.rating > 0) ? p.rating : "";
  document.getElementById("formPeakHours").value = p.peak_hours || "";
  const pDispEl = document.getElementById("formPriceDisplay");
  if (pDispEl) pDispEl.value = p.price_display || "";
  document.getElementById("formTags").value = p.tags || "nhom_ban";
  
  // Đổ dữ liệu phân tầng 2-Tier vào checkbox trên giao diện
  const { tier1: curT1, tier2: curT2 } = parsePlaceTiers(p.tags || "nhom_ban");
  ['di_1_minh', 'hen_ho', 'nhom_ban', 'gia_dinh'].forEach(t => {
    const c1 = document.getElementById(`chk_t1_${t}`);
    const c2 = document.getElementById(`chk_t2_${t}`);
    if (c1) c1.checked = curT1.includes(t);
    if (c2) c2.checked = curT2.includes(t);
  });
  syncAdminTagsInput();

  document.getElementById("formBestReview").value = p.best_review || "";
  document.getElementById("formWorstReview").value = p.worst_review || "";
  const chkRev = document.getElementById("formIsVerifiedReview");
  if (chkRev) chkRev.checked = (p.is_verified_review === 1);
  const chkAdmin = document.getElementById("formIsAdminChoice");
  if (chkAdmin) chkAdmin.checked = (p.is_admin_choice === 1);
  const chkHidden = document.getElementById("formIsHidden");
  if (chkHidden) chkHidden.checked = (p.is_hidden === 1);
  document.getElementById("formImageUrl").value = p.image_url || "";
  updateImagePreview(p.image_url || "");
  document.getElementById("modalPlaceForm").classList.remove("hidden");
}

function closePlaceFormModal() {
  document.getElementById("modalPlaceForm").classList.add("hidden");
}

async function handleSavePlace(e) {
  e.preventDefault();
  syncAdminTagsInput();
  const placeId = document.getElementById("formPlaceId").value;
  const isEdit = placeId !== "";
  const chkRev = document.getElementById("formIsVerifiedReview");
  const isRealReview = chkRev ? (chkRev.checked ? 1 : 0) : 1;
  const chkAdmin = document.getElementById("formIsAdminChoice");
  const isAdminChoice = chkAdmin ? (chkAdmin.checked ? 1 : 0) : 0;
  const chkHidden = document.getElementById("formIsHidden");
  const isHidden = chkHidden ? (chkHidden.checked ? 1 : 0) : 0;

  const rawName = document.getElementById("formName").value.trim();
  const rawCategory = document.getElementById("formCategory").value;
  const rawAddress = document.getElementById("formAddress").value.trim();
  const rawDistrict = document.getElementById("formDistrict").value.trim() || "TP.HCM";
  const rawImg = document.getElementById("formImageUrl").value.trim();
  const rawGmapsUrl = document.getElementById("formGoogleMapsUrl")?.value.trim() || null;
  const latVal = document.getElementById("formLat")?.value?.trim();
  const lonVal = document.getElementById("formLon")?.value?.trim();
  const ratingVal = document.getElementById("formRating")?.value?.trim();
  const revCountVal = document.getElementById("formReviewsCount")?.value?.trim();
  const minPriceVal = document.getElementById("formMinPrice")?.value?.trim();
  const maxPriceVal = document.getElementById("formMaxPrice")?.value?.trim();

  // 1. RÀNG BUỘC DỮ LIỆU CHẶT CHẼ TRÊN GIAO DIỆN
  if (rawName.length < 2) {
    alert("Tên địa điểm phải có ít nhất 2 ký tự!");
    document.getElementById("formName").focus();
    return;
  }

  if (!["an_uong", "di_choi"].includes(rawCategory)) {
    alert("Thể loại địa điểm không hợp lệ (phải là 'an_uong' hoặc 'di_choi')!");
    return;
  }

  if (rawAddress.length < 5) {
    alert("Địa chỉ phải cụ thể (ít nhất 5 ký tự, bao gồm số nhà hoặc tên đường)!");
    document.getElementById("formAddress").focus();
    return;
  }

  const latNum = parseFloat(latVal);
  const lonNum = parseFloat(lonVal);
  if (isNaN(latNum) || isNaN(lonNum) || latNum < 10.3 || latNum > 11.2 || lonNum < 106.3 || lonNum > 107.2) {
    alert("Tọa độ GPS không hợp lệ hoặc nằm ngoài phạm vi TP.HCM!\nVui lòng nhập: Vĩ độ (Lat: 10.3 - 11.2), Kinh độ (Lon: 106.3 - 107.2).");
    document.getElementById("formLat").focus();
    return;
  }

  const minPriceNum = (minPriceVal && !isNaN(parseInt(minPriceVal))) ? parseInt(minPriceVal) : 0;
  const maxPriceNum = (maxPriceVal && !isNaN(parseInt(maxPriceVal))) ? parseInt(maxPriceVal) : 0;
  if (minPriceNum < 0 || maxPriceNum < 0) {
    alert("Mức giá không được là số âm!");
    return;
  }
  if (maxPriceNum > 0 && maxPriceNum < minPriceNum) {
    alert("Mức giá tối đa không được nhỏ hơn mức giá tối thiểu!");
    document.getElementById("formMaxPrice").focus();
    return;
  }

  const ratingNum = (ratingVal && !isNaN(parseFloat(ratingVal))) ? parseFloat(ratingVal) : 0.0;
  if (ratingNum < 0.0 || ratingNum > 5.0) {
    alert("Điểm đánh giá phải từ 0.0 đến 5.0 sao!");
    document.getElementById("formRating").focus();
    return;
  }

  const reviewsCountNum = (revCountVal && !isNaN(parseInt(revCountVal))) ? parseInt(revCountVal) : 0;
  if (reviewsCountNum < 0) {
    alert("Số lượt đánh giá không được là số âm!");
    document.getElementById("formReviewsCount").focus();
    return;
  }

  // 2. CHẶN LƯU NẾU PHÁT HIỆN TRÙNG LẶP DỮ LIỆU ĐA LỚP (Tên, Địa chỉ, Link Maps, GPS)
  const dup = findClientDuplicate(rawName, rawAddress, latNum, lonNum, rawGmapsUrl, rawCategory, placeId);
  if (dup) {
    const rawReason = dup.reason.replace(/<[^>]*>/g, "");
    alert(`KHÔNG THỂ LƯU ĐỊA ĐIỂM:\n\n${rawReason}\n\nHệ thống chống trùng lặp đã chặn thao tác này để bảo vệ tính toàn vẹn của cơ sở dữ liệu!`);
    return;
  }

  const payload = {
    name: rawName,
    google_maps_url: rawGmapsUrl,
    category: rawCategory,
    address: rawAddress,
    district: rawDistrict,
    lat: latNum,
    lon: lonNum,
    reviews_count: reviewsCountNum,
    open_time: document.getElementById("formOpenTime").value.trim(),
    close_time: document.getElementById("formCloseTime").value.trim(),
    min_price: minPriceNum,
    max_price: maxPriceNum,
    rating: ratingNum,
    peak_hours: document.getElementById("formPeakHours").value.trim(),
    tags: document.getElementById("formTags").value.trim(),
    price_display: document.getElementById("formPriceDisplay")?.value.trim() || null,
    best_review: document.getElementById("formBestReview").value.trim(),
    worst_review: document.getElementById("formWorstReview").value.trim(),
    image_url: rawImg ? rawImg : null,
    is_verified: 1,
    is_verified_review: isRealReview,
    is_admin_choice: isAdminChoice,
    is_hidden: isHidden
  };

  const url = isEdit ? `${API_BASE}/admin/places/${placeId}` : `${API_BASE}/admin/places`;
  const method = isEdit ? "PUT" : "POST";

  try {
    const res = await fetch(url, {
      method: method,
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Không thể lưu dữ liệu.");
    }

    alert(isEdit 
      ? `Đã cập nhật thành công quán "${payload.name}" (#${placeId})!` 
      : `Đã thêm địa điểm mới "${payload.name}"!`
    );
    closePlaceFormModal();
    await preloadPlaces();
    const viewAdmin = document.getElementById("viewAdmin");
    if (viewAdmin && !viewAdmin.classList.contains("hidden")) {
      loadAdminDashboard();
    }
    const viewAll = document.getElementById("viewAll");
    if (viewAll && !viewAll.classList.contains("hidden")) {
      filterAllPlaces();
    }
  } catch (err) {
    alert("Lỗi: " + err.message);
  }
}

async function handleDeletePlace(placeId, name) {
  if (!confirm(`Bạn có chắc chắn muốn xóa địa điểm "${name}" không?`)) {
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/admin/places/${placeId}`, {
      method: "DELETE",
      headers: getAuthHeaders()
    });
    if (!res.ok) throw new Error("Không thể xóa địa điểm.");
    alert("Đã xóa địa điểm thành công!");
    preloadPlaces();
    loadAdminDashboard();
  } catch (err) {
    alert("Lỗi: " + err.message);
  }
}

// ==============================================================================
// 7. TẢI VÀ NHẬP CSV (IMPORT / EXPORT)
// ==============================================================================

let fileToUploadBase64 = "";
let uploadedFileName = "";

function downloadCSVTemplate() {
  window.location.href = `${API_BASE}/admin/sample-csv`;
}

function downloadExcelTemplate() {
  window.location.href = `${API_BASE}/admin/sample-excel`;
}

function openImportModal() {
  csvToUploadText = "";
  fileToUploadBase64 = "";
  uploadedFileName = "";
  const inp = document.getElementById("csvFileInput");
  if (inp) inp.value = "";
  document.getElementById("csvFileName").innerText = "Hỗ trợ định dạng .csv, .xlsx, .xls";
  document.getElementById("btnUploadCSV").disabled = true;
  const reportBox = document.getElementById("csvValidationReport");
  if (reportBox) reportBox.classList.add("hidden");
  document.getElementById("modalImportCSV").classList.remove("hidden");
}

function closeImportModal() {
  document.getElementById("modalImportCSV").classList.add("hidden");
}

function handleCSVFileSelected(e) {
  const file = e.target.files[0];
  if (!file) return;

  uploadedFileName = file.name;
  document.getElementById("csvFileName").innerText = `Đã chọn: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  const isExcel = file.name.toLowerCase().endsWith(".xlsx") || file.name.toLowerCase().endsWith(".xls");
  const reader = new FileReader();

  if (isExcel) {
    reader.onload = function(evt) {
      fileToUploadBase64 = evt.target.result; // Data URL containing base64
      csvToUploadText = "";
      document.getElementById("btnUploadCSV").disabled = false;
    };
    reader.readAsDataURL(file);
  } else {
    reader.onload = function(evt) {
      csvToUploadText = evt.target.result;
      fileToUploadBase64 = "";
      document.getElementById("btnUploadCSV").disabled = false;
    };
    reader.readAsText(file, "UTF-8");
  }
}

async function submitCSVImport() {
  if (!csvToUploadText && !fileToUploadBase64) return;
  const btn = document.getElementById("btnUploadCSV");
  const reportBox = document.getElementById("csvValidationReport");
  const errorListEl = document.getElementById("csvErrorList");
  const titleEl = document.getElementById("csvValidationTitle");

  btn.innerText = "Đang kiểm tra & nạp CSDL...";
  btn.disabled = true;

  try {
    const payload = {
      filename: uploadedFileName || "places_import.csv"
    };
    if (fileToUploadBase64) {
      payload.file_base64 = fileToUploadBase64;
    } else {
      payload.csv_content = csvToUploadText;
    }

    const res = await fetch(`${API_BASE}/admin/import-csv`, {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (data.error_count > 0) {
      if (reportBox) reportBox.classList.remove("hidden");
      if (titleEl) titleEl.innerText = `Đã nạp ${data.imported_count}/${data.total_rows} dòng. Phát hiện ${data.error_count} dòng lỗi:`;
      if (errorListEl) {
        errorListEl.innerHTML = "";
        data.errors.forEach(err => {
          errorListEl.innerHTML += `<li><strong>Dòng ${err.row}</strong> (Cột <code class="font-bold text-rose-700 bg-rose-100 px-1 py-0.5 rounded">${err.field}</code>): ${err.reason}</li>`;
        });
      }
      if (data.imported_count > 0) {
        preloadPlaces();
        loadAdminDashboard();
      }
    } else {
      if (reportBox) reportBox.classList.add("hidden");
      alert(`Toàn bộ ${data.imported_count} địa điểm hợp lệ và đã nạp thành công!`);
      closeImportModal();
      preloadPlaces();
      loadAdminDashboard();
    }
  } catch (e) {
    alert("Lỗi khi nạp file CSV: " + (e.message || "Không thể kết nối máy chủ."));
  } finally {
    btn.innerText = "Tiến Hành Nạp Dữ Liệu";
    btn.disabled = false;
  }
}

// ==============================================================================
// 8. XEM CHI TIẾT ĐỊA ĐIỂM CHUẨN GOOGLE MAPS (ẢNH, THÔNG TIN, COMMENT, BẢN ĐỒ)
// ==============================================================================

let currentDetailPlace = null;

function openPlaceDetailById(id) {
  let p = allPlacesCache.find(x => Number(x.id) === Number(id));
  if (!p) return;

  currentDetailPlace = p;

  // 1. Phân loại & Huy hiệu Admin Pick
  const isEat = p.category === "an_uong";
  const catLabel = document.getElementById("detailCategoryLabel");
  if (catLabel) catLabel.innerText = isEat ? "Ẩm thực Sài Gòn" : "Vui chơi & Di tích";

  const adminBadge = document.getElementById("detailAdminChoiceBadge");
  if (adminBadge) {
    if (p.is_admin_choice === 1) {
      adminBadge.classList.remove("hidden");
      adminBadge.classList.add("inline-flex");
    } else {
      adminBadge.classList.add("hidden");
      adminBadge.classList.remove("inline-flex");
    }
  }

  // 2. Banner Ảnh thực tế / Placeholder chuẩn
  const imgWrapper = document.getElementById("detailImageWrapper");
  if (imgWrapper) {
    if (p.image_url && p.image_url.trim()) {
      imgWrapper.innerHTML = `
        <img src="${p.image_url}" alt="${p.name}" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<div class=\\'w-full h-full flex flex-col items-center justify-center bg-slate-100 text-slate-400 font-bold text-xs gap-1.5\\'><i class=\\'fa-solid fa-camera text-2xl text-slate-300\\'></i> Chưa có ảnh thực tế</div>'" />
        <div class="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent pointer-events-none"></div>
        <div class="absolute bottom-3 left-4 right-4 flex justify-between items-center text-white text-xs font-bold drop-shadow">
          <span>#${p.id} • ${p.district || 'TP.HCM'}</span>
          <span class="bg-black/40 backdrop-blur-sm px-2 py-0.5 rounded-md text-[10px]"><i class="fa-solid fa-camera mr-1"></i> Ảnh thực tế</span>
        </div>
      `;
    } else {
      imgWrapper.innerHTML = `
        <div class="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-slate-100 via-slate-50 to-orange-50/40 text-slate-400 font-bold text-xs gap-1.5 p-4 text-center">
          <div class="w-12 h-12 rounded-2xl bg-white shadow-xs border border-slate-200 flex items-center justify-center text-slate-300 text-xl">
            <i class="fa-solid fa-camera"></i>
          </div>
          <span class="text-slate-600 font-extrabold text-sm">Chưa có ảnh thực tế</span>
          <span class="text-[11px] text-slate-400 font-normal">Hình ảnh đang được cập nhật</span>
        </div>
      `;
    }
  }

  // 3. Tên, Số sao & Mức giá
  const titleEl = document.getElementById("detailTitle");
  if (titleEl) titleEl.innerText = p.name;

  const ratingBadge = document.getElementById("detailRatingBadge");
  if (ratingBadge) {
    if (p.rating && p.rating > 0) {
      ratingBadge.innerHTML = `<i class="fa-solid fa-star text-amber-500 mr-1 text-xs"></i><span class="font-black text-amber-900">${p.rating}</span>`;
      ratingBadge.classList.remove("hidden");
    } else {
      ratingBadge.innerHTML = `<span class="text-xs text-slate-500 font-bold">Chưa có sao</span>`;
    }
  }

  // Đổ bóng sao vàng
  const starContainer = document.getElementById("detailStarIcons");
  if (starContainer) {
    if (p.rating && p.rating > 0) {
      const fullStars = Math.floor(p.rating);
      const halfStar = (p.rating % 1) >= 0.3;
      let starsHtml = "";
      for (let i = 0; i < fullStars; i++) starsHtml += `<i class="fa-solid fa-star"></i>`;
      if (halfStar) starsHtml += `<i class="fa-solid fa-star-half-stroke"></i>`;
      const emptyStars = 5 - Math.ceil(p.rating);
      for (let i = 0; i < emptyStars; i++) starsHtml += `<i class="fa-regular fa-star text-slate-300"></i>`;
      starContainer.innerHTML = starsHtml;
    } else {
      starContainer.innerHTML = "";
    }
  }

  const reviewsCountEl = document.getElementById("detailReviewsCount");
  if (reviewsCountEl) {
    reviewsCountEl.innerText = (p.reviews_count && p.reviews_count > 0)
      ? `${parseInt(p.reviews_count).toLocaleString()} đánh giá Google`
      : "Chưa có đánh giá Google";
  }

  const priceRangeEl = document.getElementById("detailPriceRange");
  if (priceRangeEl) {
    if (p.price_display && p.price_display.trim()) {
      priceRangeEl.innerText = p.price_display;
    } else if (p.min_price === 0 && p.max_price === 0) {
      priceRangeEl.innerText = "Miễn phí vé vào cổng";
    } else if (p.min_price != null && p.max_price != null && (p.min_price > 0 || p.max_price > 0)) {
      priceRangeEl.innerText = `${p.min_price.toLocaleString()}đ - ${p.max_price.toLocaleString()}đ`;
    } else {
      priceRangeEl.innerText = "Chưa cập nhật giá";
    }
  }

  // 4. Link Google Maps
  const queryEnc = encodeURIComponent(`${p.name} ${p.address}`);
  const gmapsRouteUrl = p.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${queryEnc}`;

  const realPageBtn = document.getElementById("detailGmapsRealPageBtn");
  if (realPageBtn) realPageBtn.href = gmapsRouteUrl;

  const routeBtn = document.getElementById("detailGmapsRouteBtn");
  if (routeBtn) routeBtn.href = gmapsRouteUrl;

  const extMapLink = document.getElementById("detailExternalMapLink");
  if (extMapLink) extMapLink.href = gmapsRouteUrl;

  // 5. Địa chỉ cụ thể
  const addrEl = document.getElementById("detailAddress");
  if (addrEl) addrEl.innerText = p.address;

  // 6. Trạng thái hoạt động
  const isOpen = (typeof p.is_currently_open === "boolean")
    ? p.is_currently_open
    : isPlaceCurrentlyOpen(p.open_time, p.close_time);
  const statusBadge = document.getElementById("detailStatusBadge");
  if (statusBadge) {
    statusBadge.className = isOpen
      ? "px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800"
      : "px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800";
    statusBadge.innerText = isOpen ? "🟢 Đang mở cửa" : "🔴 Đã đóng cửa";
  }

  const openHoursEl = document.getElementById("detailOpenHours");
  if (openHoursEl) openHoursEl.innerText = p.hours_display || `${p.open_time} - ${p.close_time}`;

  // 7. Giờ cao điểm
  const peakHoursEl = document.getElementById("detailPeakHours");
  if (peakHoursEl) {
    const rawPeak = (p.peak_hours && p.peak_hours !== 'Chưa rõ') ? p.peak_hours : '';
    const cleanPeak = rawPeak.replace(/\s*\([^\)]*đông[^\)]*\)/gi, '').trim();
    peakHoursEl.innerText = cleanPeak || "Chưa rõ (quán chưa cập nhật)";
  }

  // 8. Bối cảnh tags (Xếp trên/dưới tự nhiên, KHÔNG ghi chữ Tier 1/2, KHÔNG làm nổi bật lệch màu)
  const tagsContainer = document.getElementById("detailTagsList");
  if (tagsContainer) {
    tagsContainer.innerHTML = "";
    const tagMap = {
      di_1_minh: `<i class="fa-solid fa-user text-slate-500 mr-1.5 text-[11px]"></i>Đi 1 mình`,
      hen_ho: `<i class="fa-solid fa-heart text-rose-500 mr-1.5 text-[11px]"></i>Hẹn hò cặp đôi`,
      nhom_ban: `<i class="fa-solid fa-users text-sky-600 mr-1.5 text-[11px]"></i>Nhóm bạn`,
      gia_dinh: `<i class="fa-solid fa-people-roof text-amber-600 mr-1.5 text-[11px]"></i>Gia đình`
    };
    const { tier1, tier2 } = parsePlaceTiers(p.tags || "");

    let html = `<div class="w-full space-y-1.5 mt-1">`;
    if (tier1.length > 0) {
      html += `
        <div class="flex items-center gap-1.5 flex-wrap">
          ${tier1.map(t => `<span class="px-3 py-1 bg-slate-50 text-slate-700 border border-slate-200/90 rounded-xl text-xs font-semibold inline-flex items-center shadow-2xs">${tagMap[t] || t}</span>`).join("")}
        </div>
      `;
    }
    if (tier2.length > 0) {
      html += `
        <div class="flex items-center gap-1.5 flex-wrap">
          ${tier2.map(t => `<span class="px-3 py-1 bg-slate-50 text-slate-700 border border-slate-200/90 rounded-xl text-xs font-semibold inline-flex items-center shadow-2xs">${tagMap[t] || t}</span>`).join("")}
        </div>
      `;
    }
    html += `</div>`;
    tagsContainer.innerHTML = html;
  }

  // 9. Bình luận khen & lưu ý thực tế
  const bestRev = document.getElementById("detailBestReview");
  if (bestRev) {
    if (p.best_review && p.best_review.trim()) {
      bestRev.innerText = p.best_review;
    } else {
      bestRev.innerHTML = `<span class="text-slate-400 font-normal italic">Chưa có đánh giá 5 sao nào được ghi nhận trên Google Maps.</span>`;
    }
  }

  const worstRev = document.getElementById("detailWorstReview");
  if (worstRev) {
    if (p.worst_review && p.worst_review.trim()) {
      worstRev.innerText = p.worst_review;
    } else {
      worstRev.innerHTML = `<span class="text-slate-400 font-normal italic">Chưa có phản ánh hoặc góp ý tiêu cực nào trên Google Maps.</span>`;
    }
  }

  // 10. Bản đồ tương tác Leaflet (Không bị Google Maps chặn)
  const drawerMapContainer = document.getElementById("drawerLeafletMap");
  if (drawerMapContainer && typeof L !== "undefined") {
    if (p.lat && p.lon && !isNaN(p.lat) && !isNaN(p.lon) && (parseFloat(p.lat) !== 0 || parseFloat(p.lon) !== 0)) {
      drawerMapContainer.style.display = "block";
      const lat = parseFloat(p.lat);
      const lon = parseFloat(p.lon);
      if (!drawerMap) {
        drawerMap = L.map("drawerLeafletMap", {
          zoomControl: true,
          scrollWheelZoom: false
        }).setView([lat, lon], 16);

        initLeafletTileLayers(drawerMap);

        const pinIcon = L.divIcon({
          className: "custom-leaflet-marker",
          html: `<div style="background-color: #E11D48; color: white; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 2.5px solid white;"><i class="fa-solid fa-location-dot"></i></div>`,
          iconSize: [32, 32],
          iconAnchor: [16, 32],
          popupAnchor: [0, -32]
        });

        drawerMarker = L.marker([lat, lon], { icon: pinIcon }).addTo(drawerMap);
        drawerMarker.bindPopup(`<strong>${p.name}</strong><br><span style="font-size:11px;">${p.address}</span>`);
      } else {
        drawerMap.setView([lat, lon], 16);
        if (drawerMarker) {
          drawerMarker.setLatLng([lat, lon]);
          drawerMarker.bindPopup(`<strong>${p.name}</strong><br><span style="font-size:11px;">${p.address}</span>`);
        }
      }
      setTimeout(() => {
        if (drawerMap) drawerMap.invalidateSize();
      }, 350);
    } else {
      drawerMapContainer.style.display = "none";
    }
  }

  // 11. Nút sửa dành cho Admin
  const footerAdminBtn = document.getElementById("detailFooterAdminEditBtn");
  if (footerAdminBtn) {
    if (currentUser && currentUser.role === "admin") {
      footerAdminBtn.innerHTML = `
        <button onclick="closePlaceDetail(); openEditPlaceModalById(${p.id});" class="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-xs cursor-pointer">
          <i class="fa-solid fa-pen-to-square"></i> <span>Sửa quán này</span>
        </button>
      `;
    } else {
      footerAdminBtn.innerHTML = ``;
    }
  }

  // Mở ngăn kéo
  const backdrop = document.getElementById("placeDetailBackdrop");
  const drawer = document.getElementById("placeDetailDrawer");
  if (backdrop) backdrop.classList.remove("hidden");
  if (drawer) drawer.classList.remove("translate-x-full");
}

function closePlaceDetail() {
  const backdrop = document.getElementById("placeDetailBackdrop");
  const drawer = document.getElementById("placeDetailDrawer");

  if (drawer) drawer.classList.add("translate-x-full");
  if (backdrop) backdrop.classList.add("hidden");
  currentDetailPlace = null;
}

function copyDetailAddress() {
  if (!currentDetailPlace) return;
  const text = `${currentDetailPlace.name}, ${currentDetailPlace.address}`;
  navigator.clipboard.writeText(text).then(() => {
    alert(`Đã sao chép địa chỉ:\n"${text}"\nBạn có thể dán vào Grab, Be hoặc ứng dụng bản đồ!`);
  }).catch(() => {
    prompt("Sao chép địa chỉ:", text);
  });
}



// Giữ lại alias để tương thích các link cũ
function openSideMapById(id) {
  openPlaceDetailById(id);
}

function closeSideMap() {
  closePlaceDetail();
}

function copySideMapAddress() {
  copyDetailAddress();
}


// ==============================================================================
// CUSTOM LUXURY DROPDOWN SYSTEM (THAY THẾ HOÀN TOÀN DROPDOWN MẶC ĐỊNH CỦA WINDOWS)
// ==============================================================================
function initCustomSelects() {
  const targetIds = ["allCategoryFilter", "allTagFilter", "allPriceFilter", "allSortFilter", "allRadiusFilter"];
  
  targetIds.forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    
    // Tránh khởi tạo trùng lặp
    if (sel.nextElementSibling && sel.nextElementSibling.classList.contains("custom-dropdown-container")) {
      return;
    }
    
    // Ẩn select gốc (giữ nguyên DOM để kích hoạt event change và query value)
    sel.style.display = "none";
    
    // Tạo container bao ngoài
    const container = document.createElement("div");
    container.className = "custom-dropdown-container";
    container.dataset.forSelect = id;
    
    // Nút trigger
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "custom-dropdown-trigger";
    
    const labelSpan = document.createElement("span");
    labelSpan.className = "truncate pr-2 custom-dropdown-label";
    const selectedOpt = sel.options[sel.selectedIndex] || sel.options[0];
    labelSpan.textContent = selectedOpt ? selectedOpt.text : "";
    
    const arrowIcon = document.createElement("i");
    arrowIcon.className = "fa-solid fa-chevron-down text-[10px] text-slate-400 transition-transform duration-200 custom-dropdown-arrow";
    
    trigger.appendChild(labelSpan);
    trigger.appendChild(arrowIcon);
    
    // Menu thả xuống sang trọng (Render vào trong DOM web, hoàn toàn không dính UI Windows)
    const menu = document.createElement("div");
    menu.className = "custom-dropdown-menu hidden";
    
    function renderItems() {
      menu.innerHTML = "";
      Array.from(sel.options).forEach(opt => {
        const item = document.createElement("div");
        const isSelected = opt.value === sel.value;
        item.className = `custom-dropdown-item ${isSelected ? 'is-selected' : ''}`;
        item.dataset.val = opt.value;
        item.innerHTML = `
          <span class="truncate">${opt.text}</span>
          ${isSelected ? '<i class="fa-solid fa-check text-[10px] text-[#E11D48]"></i>' : ''}
        `;
        
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          sel.value = opt.value;
          labelSpan.textContent = opt.text;
          
          menu.classList.add("hidden");
          trigger.classList.remove("is-active");
          arrowIcon.classList.remove("rotate-180");
          
          renderItems();
          sel.dispatchEvent(new Event("change"));
        });
        
        menu.appendChild(item);
      });
    }
    
    renderItems();
    
    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isClosed = menu.classList.contains("hidden");
      
      // Đóng các dropdown khác
      document.querySelectorAll(".custom-dropdown-menu").forEach(m => {
        if (m !== menu) {
          m.classList.add("hidden");
          m.parentElement?.querySelector(".custom-dropdown-trigger")?.classList.remove("is-active");
          m.parentElement?.querySelector(".custom-dropdown-arrow")?.classList.remove("rotate-180");
        }
      });
      
      if (isClosed) {
        menu.classList.remove("hidden");
        trigger.classList.add("is-active");
        arrowIcon.classList.add("rotate-180");
      } else {
        menu.classList.add("hidden");
        trigger.classList.remove("is-active");
        arrowIcon.classList.remove("rotate-180");
      }
    });
    
    // Tự động đồng bộ khi code JS ngoài thay đổi select.value
    sel.addEventListener("change", () => {
      const curOpt = sel.options[sel.selectedIndex];
      if (curOpt) {
        labelSpan.textContent = curOpt.text;
        renderItems();
      }
    });
    
    container.appendChild(trigger);
    container.appendChild(menu);
    sel.parentNode.insertBefore(container, sel.nextSibling);
  });
}

// Đóng dropdown khi bấm ra ngoài
document.addEventListener("click", (e) => {
  if (!e.target.closest(".custom-dropdown-container")) {
    document.querySelectorAll(".custom-dropdown-menu").forEach(m => {
      m.classList.add("hidden");
      m.parentElement?.querySelector(".custom-dropdown-trigger")?.classList.remove("is-active");
      m.parentElement?.querySelector(".custom-dropdown-arrow")?.classList.remove("rotate-180");
    });
  }
});


