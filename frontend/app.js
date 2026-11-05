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
