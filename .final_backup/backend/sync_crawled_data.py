"""
Script tự động nạp kết quả cào từ Tampermonkey (sggo_targeted_real_data.json) vào CSDL SQLite & enriched_places.json
Cách dùng:
  python backend/sync_crawled_data.py [đường_dẫn_file_json]
  (Nếu không truyền tham số, script tự tìm trong thư mục Downloads hoặc Desktop)
"""

import os
import sys
import json
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(os.path.dirname(__file__), "sggo.db")
ENRICHED_PATH = os.path.join(os.path.dirname(__file__), "enriched_places.json")

def find_json_file(custom_path=None):
    if custom_path and os.path.exists(custom_path):
        return custom_path
    
    # Tìm trong Downloads hoặc Desktop
    user_home = os.path.expanduser("~")
    candidates = [
        os.path.join(user_home, "Downloads", "sggo_targeted_real_data.json"),
        os.path.join(user_home, "Downloads", "sggo_v6_enriched_places.json"),
        os.path.join(user_home, "Desktop", "sggo_targeted_real_data.json"),
        os.path.join(user_home, "OneDrive", "Desktop", "sggo_targeted_real_data.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def main():
    json_path = find_json_file(sys.argv[1] if len(sys.argv) > 1 else None)
    if not json_path:
        print("❌ Không tìm thấy file JSON kết quả cào (sggo_targeted_real_data.json).")
        print("💡 Hãy tải file từ Tampermonkey về thư mục Downloads hoặc truyền đường dẫn file: python backend/sync_crawled_data.py <path>")
        return

    print(f"📖 Đang đọc dữ liệu từ: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    if isinstance(raw_data, dict) and "places" in raw_data:
        crawled_items = raw_data["places"]
    elif isinstance(raw_data, list):
        crawled_items = raw_data
    else:
        print("❌ Định dạng file JSON không hợp lệ.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    updated_count = 0
    for item in crawled_items:
        pid = item.get("id")
        if not pid:
            continue

        # Cập nhật thông tin thực tế từ Google Maps
        cur.execute("""
        UPDATE places SET
            lat = COALESCE(?, lat),
            lon = COALESCE(?, lon),
            rating = COALESCE(?, rating),
            reviews_count = COALESCE(?, reviews_count),
            image_url = COALESCE(?, image_url),
            best_review = COALESCE(?, best_review),
            worst_review = COALESCE(?, worst_review),
            peak_hours = COALESCE(?, peak_hours),
            open_time = COALESCE(?, open_time),
            close_time = COALESCE(?, close_time),
            price_display = COALESCE(?, price_display),
            google_maps_url = COALESCE(?, google_maps_url)
        WHERE id = ?
        """, (
            item.get("lat"),
            item.get("lon"),
            item.get("rating"),
            item.get("reviews_count"),
            item.get("image_url"),
            item.get("best_review"),
            item.get("worst_review"),
            item.get("peak_hours"),
            item.get("open_time"),
            item.get("close_time"),
            item.get("price_display"),
            item.get("google_maps_url"),
            pid
        ))
        if cur.rowcount > 0:
            updated_count += 1
            print(f"  ✅ Đã cập nhật #{pid}: {item.get('name')}")

    conn.commit()
    conn.close()

    # Đồng bộ sang enriched_places.json
    from database import sync_db_to_json
    sync_db_to_json()

    print(f"\n🎉 HOÀN TẤT! Đã đồng bộ {updated_count} quán vào CSDL SQLite & enriched_places.json!")

if __name__ == "__main__":
    main()
