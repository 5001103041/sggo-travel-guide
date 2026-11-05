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
