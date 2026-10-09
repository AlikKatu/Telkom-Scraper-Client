import os
import sys
import time
import sqlite3
import json
import csv
import hashlib
from datetime import datetime
from pathlib import Path

os.system('color')
C, G, Y, R, M, W, B, Gr = '\033[96m', '\033[92m', '\033[93m', '\033[91m', '\033[95m', '\033[0m', '\033[1m', '\033[90m'

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DB_FILE = ROOT / "database" / "scraper.db"
REGION_FILE = ROOT / "input" / "daftar kota dan kabupaten.xlsx"
KEYWORD_FILE = ROOT / "input" / "keyword.xlsx"
EXPORT_DIR = ROOT / "exports"

from app.license_guard import get_machine_id, get_license_status, consume_quota, apply_activation_token

def get_db():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("CREATE TABLE IF NOT EXISTS projects (project_id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kategori TEXT NOT NULL,
            keyword TEXT NOT NULL, kota_kab TEXT NOT NULL, provinsi TEXT NOT NULL,
            witel TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scrape_candidates (
            candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL, name TEXT NOT NULL, place_url TEXT,
            phones_json TEXT, address_json TEXT, decision TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wifi_tasks (
            candidate_id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, place_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(candidate_id) REFERENCES scrape_candidates(candidate_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wifi_results (
            candidate_id INTEGER PRIMARY KEY, job_id TEXT NOT NULL,
            has_wifi INTEGER NOT NULL DEFAULT 0, wifi_provider TEXT, evidence TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(candidate_id) REFERENCES scrape_candidates(candidate_id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    return conn

def play_success_sound():
    try:
        import winsound
        winsound.Beep(523, 200)
        winsound.Beep(659, 200)
        winsound.Beep(784, 200)
        winsound.Beep(1046, 400)
    except Exception:
        print("\a")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def format_time(seconds):
    m, s = int(seconds // 60), int(seconds % 60)
    return f"{m} menit {s} detik" if m > 0 else f"{s} detik"

def get_active_witel():
    conn = get_db()
    try:
        row = conn.execute("SELECT witel FROM jobs WHERE witel IS NOT NULL AND witel != '' LIMIT 1").fetchone()
        if row and row[0]:
            return row[0].upper()
        return "WITEL BELUM DISET"
    except Exception:
        return "WITEL BELUM DISET"
    finally:
        conn.close()

def menu_license():
    clear_screen()
    print(C + B + "="*80 + W)
    print("               🔑 STATUS LISENSI & AKTIVASI KUOTA")
    print(C + B + "="*80 + W)
    lic = get_license_status()
    print(f" ID Perangkat Laptop  : {Y}{B}{lic['machine_id']}{W}")
    print(f" Kuota Terpakai       : {lic['used_jobs']:,} Job")
    print(f" Total Kuota Lisensi  : {lic['total_quota']:,} Job")
    if lic['is_locked']:
        print(f" Status Kuota         : {R}{B}HABIS / TERKUNCI (0 Job Tersisa){W}")
    else:
        print(f" Sisa Kuota Aktif     : {G}{B}{lic['remaining']:,} Job Tersisa{W}")
    print(C + "-"*80 + W)
    print(" Untuk menambah kuota, kirimkan ID Perangkat di atas ke Admin Telkom.")
    token = input(f"\nMasukkan Kode Aktivasi (Enter untuk kembali): ").strip()
    if token:
        ok, msg = apply_activation_token(token)
        if ok:
            print(f"\n{G}{B}✅ {msg}{W}")
            play_success_sound()
        else:
            print(f"\n{R}{B}❌ {msg}{W}")
        input(f"\n{Y}Tekan Enter untuk kembali...{W}")

def show_progress():
    clear_screen()
    conn = get_db()
    try:
        active_witel = get_active_witel()
        lic = get_license_status()
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='PENDING'").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='RUNNING'").fetchone()[0]
        done = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='DONE'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='FAILED_FINAL'").fetchone()[0]
        candidates = conn.execute("SELECT COUNT(*) FROM scrape_candidates").fetchone()[0]
        accepted = conn.execute("SELECT COUNT(*) FROM scrape_candidates WHERE decision='ACCEPT'").fetchone()[0]
        try:
            wifi_total = conn.execute("SELECT COUNT(*) FROM wifi_tasks").fetchone()[0]
            wifi_pending = conn.execute("SELECT COUNT(*) FROM wifi_tasks WHERE status IN ('PENDING', 'RETRY_WAIT')").fetchone()[0]
        except Exception:
            wifi_total, wifi_pending = 0, 0
        
        print(C + B + "="*80 + W)
        print("               📊 LIVE PROGRESS MONITOR")
        print(C + B + "="*80 + W)
        print(f" {B}WITEL AKTIF{W}       : {Y}{active_witel}{W}")
        if lic['is_locked']:
            print(f" {B}STATUS LISENSI{W} : {R}HABIS / TERKUNCI{W}")
            print(f" {B}ID PERANGKAT{W}   : {Y}{lic['machine_id']}{W}")
        print(f" {B}TOTAL DATABASE{W}    : {total:,} Target Kota/Keyword")
        print(f" {G}SELESAI (DONE){W}    : {done:,} Job")
        print(f" {R}GAGAL (FAILED){W}    : {failed:,} Job")
        print(f" {B}SISA PENDING{W}      : {M}{pending:,} Job Menunggu Eksekusi{W}")
        print(f" {B}AKTIF (RUNNING){W}   : {C}{running:,} Worker Sedang Berjalan{W}")
        print(C + "-" * 80 + W)
        print(f" {B}PROFIL TERKUMPUL{W}  : {candidates:,} Tempat")
        print(f" {G}PROFIL VALID{W}      : {accepted:,} Tempat {G}(Siap Export/Wi-Fi){W}")
        print(C + "-" * 80 + W)
        print(f" {B}TUGAS WI-FI{W}       : {wifi_total:,} Total | {Y}{wifi_pending:,} Sisa (PENDING){W}")
        print(C + B + "="*80 + W)
        input(f"\n{Y}>> Tekan Enter untuk kembali ke Menu Utama...{W}")
    finally:
        conn.close()

def get_next_pending_job_preview():
    conn = get_db()
    try:
        row = conn.execute("SELECT keyword, kota_kab FROM jobs WHERE status IN ('PENDING', 'RETRY_WAIT') ORDER BY created_at ASC, job_id ASC LIMIT 1").fetchone()
        if row:
            return row[0], row[1]
        return "Unknown", "Unknown"
    except Exception:
        return "Unknown", "Unknown"
    finally:
        conn.close()

def run_main_scraper():
    conn = get_db()
    try:
        total_in_db = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        pending_in_db = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'PENDING'").fetchone()[0]
    finally:
        conn.close()

    if total_in_db == 0:
        print(f"\n{R}[!] Database masih kosong! Belum ada target wilayah yang dimuat.{W}")
        print(f"    👉 Silakan pilih {Y}Menu 7{W} terlebih dahulu untuk inisialisasi Witel dari file Excel.")
        try:
            input(f"\n{Y}Tekan Enter untuk kembali ke menu utama...{W}")
        except KeyboardInterrupt:
            pass
        return

    if pending_in_db == 0:
        print(f"\n{G}[SELESAI] Hore! Tidak ada lagi job PENDING di database.{W}")
        try:
            input(f"\n{Y}Tekan Enter untuk kembali ke menu utama...{W}")
        except KeyboardInterrupt:
            pass
        return

    lic = get_license_status()
    if lic["is_locked"]:
        print(f"\n{R}{B}[!] MASA TRIAL / KUOTA LISENSI ANDA TELAH HABIS!{W}")
        print(f"    ID Perangkat Laptop Anda : {Y}{B}{lic['machine_id']}{W}")
        print("    Silakan hubungi Admin untuk mendapatkan Kode Aktivasi perpanjangan.")
        try:
            choice = input(f"\nMasukkan Kode Aktivasi sekarang? (y/n): ").strip().lower()
        except KeyboardInterrupt:
            return
        if choice == 'y':
            try:
                token = input(f"Masukkan Kode Aktivasi: ").strip()
            except KeyboardInterrupt:
                return
            ok, msg = apply_activation_token(token)
            if ok:
                print(f"\n{G}{B}✅ {msg}{W}")
                play_success_sound()
                time.sleep(2)
            else:
                print(f"\n{R}{B}❌ {msg}{W}")
                time.sleep(2)
        return

    print(f"\n{C}{B}🚀 PERSIAPAN MESIN SCRAPING UTAMA{W}")
    try:
        target = int(input(f"{Y}Berapa job yang ingin dieksekusi di sesi ini? (Misal: 50, 500): {W}"))
    except (ValueError, KeyboardInterrupt):
        return
        
    if target > lic["remaining"]:
        target = lic["remaining"]

    from app.region_mapper import read_first_sheet, build_region_mapping
    from app.worker_runner import run_worker_once_with_context
    from playwright.sync_api import sync_playwright
    
    rows = read_first_sheet(REGION_FILE)
    mapping = build_region_mapping(rows)
    known_regions = list(dict.fromkeys(item["Kota/Kab"] for item in mapping))
    
    total_processed, start_time = 0, time.time()
    session_target_details = []
    interrupted = False
    
    print(f"\n{G}[MEMULAI] Mesin berjalan untuk target {target} Job...{W}")
    print(f" {Gr}(Tips: Anda dapat menekan Ctrl+C kapan saja untuk berhenti secara aman tanpa merusak database){W}\n")
    
    browser_launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage"
    ]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=browser_launch_args)
            jobs_in_current_browser = 0
            consecutive_zero_count = 0
            try:
                while total_processed < target and not interrupted:
                    conn = get_db()
                    pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'PENDING'").fetchone()[0]
                    conn.close()
                    if pending == 0:
                        print(f"\n{G}[SELESAI] Hore! Tidak ada lagi job PENDING di database.{W}")
                        break
                    
                    if jobs_in_current_browser >= 100:
                        print(f"\n{C}-> [PENYEGARAN RAM] Hard Recycling Browser Chromium...{W}")
                        browser.close()
                        browser = p.chromium.launch(headless=True, args=browser_launch_args)
                        jobs_in_current_browser = 0
                        
                    batch_size = min(50, target - total_processed)
                    print(f"{C}-> Mendaur ulang Context (Batch {batch_size} Job)...{W}")
                    context = browser.new_context(viewport={"width": 1280, "height": 800}, locale="id-ID", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", locale="id-ID")
                    
                    def block_heavy_assets(route):
                        if route.request.resource_type in ["image", "media", "font"]:
                            route.abort()
                        else:
                            route.continue_()
                    context.route("**/*", block_heavy_assets)
                    
                    try:
                        count = 0
                        for _ in range(batch_size):
                            kw_preview, kota_preview = get_next_pending_job_preview()
                            print(f"   [{total_processed + 1}/{target}] ⏳ Sedang menyedot data: {kw_preview} di {kota_preview}...", end="", flush=True)

                            try:
                                temp_conn = get_db()
                                r = run_worker_once_with_context(temp_conn, known_regions, context, max_attempts=3)
                                temp_conn.close()
                            except KeyboardInterrupt:
                                print(f"\r   [{total_processed + 1}/{target}] {Y}⚠️ Interupsi Ctrl+C diterima!                                    {W}")
                                interrupted = True
                                break
                            
                            if r is None:
                                print(f"\r   [{total_processed + 1}/{target}] ❌ Batal (Tidak ada data)                      ")
                                break
                            
                            count += 1
                            total_processed += 1
                            jobs_in_current_browser += 1
                            consume_quota(1)
                            
                            kw, kota = kw_preview, kota_preview
                            current_job_id = None
                            try:
                                if isinstance(r, dict) and r.get("job_id"):
                                    current_job_id = r["job_id"]
                                    temp_conn2 = get_db()
                                    row_data = temp_conn2.execute("SELECT keyword, kota_kab FROM jobs WHERE job_id=?", (current_job_id,)).fetchone()
                                    temp_conn2.close()
                                    if row_data:
                                        kw, kota = row_data[0], row_data[1]
                            except Exception:
                                pass
                            session_target_details.append(f"{kw} di {kota}")

                            places_this_job = 0
                            if current_job_id:
                                try:
                                    temp_conn3 = get_db()
                                    places_this_job = temp_conn3.execute("SELECT COUNT(*) FROM scrape_candidates WHERE job_id=?", (current_job_id,)).fetchone()[0]
                                    temp_conn3.close()
                                except Exception:
                                    pass
                                    
                            if places_this_job == 0:
                                consecutive_zero_count += 1
                            else:
                                consecutive_zero_count = 0

                            print(f"\r   [{total_processed}/{target}] ✅ Ekstrak Selesai: {kw} di {kota} ({places_this_job} Tempat)            ")

                            if consecutive_zero_count >= 6:
                                print(f"\n   {Y}⚠️ [SENSOR GHOST-BLOCK] Terdeteksi 6 Job beruntun bernilai 0 tempat.")
                                print(f"      Mengaktifkan Auto-Cooldown 30 detik untuk penyegaran koneksi...{W}")
                                time.sleep(30)
                                consecutive_zero_count = 0
                                        
                        if count == 0 or interrupted:
                            break
                    except KeyboardInterrupt:
                        interrupted = True
                        break
                    finally:
                        try:
                            context.close()
                        except Exception:
                            pass
            except KeyboardInterrupt:
                interrupted = True
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except KeyboardInterrupt:
        interrupted = True
        
    # MEKANISME GRACEFUL RECOVERY: Rollback job RUNNING yang terputus kembali ke PENDING
    if interrupted:
        print(f"\n{Y}🛡️  [GRACEFUL SHUTDOWN] Mengamankan integritas database & browser...{W}")
        conn_cleanup = get_db()
        try:
            cur = conn_cleanup.cursor()
            cur.execute("UPDATE jobs SET status='PENDING' WHERE status='RUNNING'")
            reverted = cur.rowcount
            conn_cleanup.commit()
            print(f"   {G}✅ Berhasil mengembalikan {reverted} job yang terpotong ke status PENDING (Data 100% aman).{W}")
        finally:
            conn_cleanup.close()
    
    elapsed = time.time() - start_time
    avg_speed = elapsed / total_processed if total_processed > 0 else 0
    
    db_places, db_accepts, db_no_phone, db_no_address = 0, 0, 0, 0
    try:
        conn_diag = get_db()
        cur_diag = conn_diag.cursor()
        cur_diag.execute(f"SELECT job_id FROM jobs WHERE status='DONE' ORDER BY updated_at DESC LIMIT {total_processed}")
        done_ids = [f"'{r[0]}'" for r in cur_diag.fetchall()]
        if done_ids:
            in_clause = ",".join(done_ids)
            q = f"""
                SELECT 
                    COUNT(*),
                    SUM(CASE WHEN decision = 'ACCEPT' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN (phones_json IS NULL OR phones_json = '[]' OR trim(phones_json) = '') AND decision = 'ACCEPT' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN (address_json IS NULL OR address_json = '[]' OR trim(address_json) = '') AND decision = 'ACCEPT' THEN 1 ELSE 0 END)
                FROM scrape_candidates 
                WHERE job_id IN ({in_clause})
            """
            cur_diag.execute(q)
            row_diag = cur_diag.fetchone()
            if row_diag:
                db_places = row_diag[0] or 0
                db_accepts = row_diag[1] or 0
                db_no_phone = row_diag[2] or 0
                db_no_address = row_diag[3] or 0
        conn_diag.close()
    except Exception:
        pass

    header_status = "⚠️ LAPORAN SESI (DIHENTIKAN AMAN)" if interrupted else "📈 LAPORAN SESI SCRAPING UTAMA"
    print(f"\n{C}{B}" + "="*55 + f"{W}")
    print(f" {B}{header_status}{W}")
    print(f"{C}{B}" + "="*55 + f"{W}")
    print(f" Total Job Berhasil   : {total_processed} Job")
    print(f" Lama Waktu           : {format_time(elapsed)}")
    print(f" Kecepatan Rata2      : {avg_speed:.2f} detik / Job")
    print(C + "-"*55 + W)
    if session_target_details:
        print(f" 🎯 {B}Daftar Target Selesai:{W}")
        for idx, detail in enumerate(session_target_details[:10], 1):
            print(f"    {Y}{idx}. {detail}{W}")
        if len(session_target_details) > 10:
            print(f"    {M}... dan {len(session_target_details) - 10} area target lainnya.{W}")
        print(C + "-"*55 + W)
    print(f" 🏠 Profil Terkumpul  : {db_places:,} Tempat")
    print(f" ✅ Profil VALID      : {G}{db_accepts:,} Tempat (ACCEPT){W}")
    print(C + "-"*55 + W)
    play_success_sound()
    try:
        input(f"\n{Y}>> Tekan Enter untuk kembali ke menu utama...{W}")
    except KeyboardInterrupt:
        pass

def setup_wifi_tasks(silent=False):
    if not silent:
        print(f"\n{C}⚙️  Menyusun Antrean Wi-Fi dari data VALID...{W}")
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO wifi_tasks (candidate_id, job_id, place_url)
            SELECT MIN(candidate_id), job_id, place_url
            FROM scrape_candidates
            WHERE decision = 'ACCEPT' AND place_url IS NOT NULL AND place_url != ''
              AND place_url NOT IN (SELECT place_url FROM wifi_tasks)
            GROUP BY place_url
        """)
        inserted = cursor.rowcount
        conn.commit()
        if not silent:
            print(f"{G}[SUKSES] Berhasil memasukkan {inserted:,} tugas Wi-Fi baru unik!{W}")
    finally:
        conn.close()
    if not silent:
        time.sleep(2)

def run_wifi_scraper():
    setup_wifi_tasks(silent=True)
    
    print(f"\n{C}{B}📡 PERSIAPAN MESIN PENCARI WI-FI (MULTI-LAYER){W}")
    try:
        target = int(input(f"{Y}Berapa tempat yang ingin dicek Wi-Fi-nya? (Misal: 100, 500): {W}"))
    except (ValueError, KeyboardInterrupt):
        return
    from playwright.sync_api import sync_playwright
    
    def claim_task(conn):
        conn.execute("BEGIN IMMEDIATE")
        task = conn.execute("SELECT candidate_id, job_id, place_url, attempts FROM wifi_tasks WHERE status IN ('PENDING', 'RETRY_WAIT') ORDER BY created_at ASC LIMIT 1").fetchone()
        if task:
            conn.execute("UPDATE wifi_tasks SET status='RUNNING', attempts=attempts+1, updated_at=CURRENT_TIMESTAMP WHERE candidate_id=?", (task[0],))
            conn.commit()
            return {"candidate_id": task[0], "job_id": task[1], "place_url": task[2], "attempts": task[3] + 1}
        conn.commit()
        return None

    def check_wifi(page, url):
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        try:
            tabs = page.locator('button[role="tab"]:has-text("Tentang"), button[role="tab"]:has-text("About")')
            if tabs.count() > 0:
                tabs.first.click(timeout=3000)
                page.wait_for_timeout(1000)
        except Exception:
            pass
        text = page.locator("body").inner_text(timeout=15000).lower()
        kws = ['wi-fi', 'wifi', 'indihome', 'astinet', 'telkom', 'wms', 'internet']
        found = list(set([k for k in kws if k in text]))
        try:
            amenities = page.locator('[aria-label*="Wi-Fi" i], [aria-label*="wifi" i], [aria-label*="Internet" i]').count()
            if amenities > 0 and 'wi-fi (ikon/label)' not in found:
                found.append('wi-fi (ikon/label)')
        except Exception:
            pass
        has_wifi = 1 if found else 0
        provider = "Telkom/IndiHome" if any(k in text for k in ['indihome', 'astinet', 'telkom', 'wms']) else ("Unknown" if has_wifi else None)
        return {"has_wifi": has_wifi, "wifi_provider": provider, "evidence": ", ".join(found) if found else None}

    total_processed, start_time = 0, time.time()
    session_has_wifi, session_no_wifi, session_failed = 0, 0, 0
    interrupted = False
    
    browser_launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage"
    ]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=browser_launch_args)
            urls_in_browser = 0
            try:
                while total_processed < target and not interrupted:
                    conn = get_db()
                    pending = conn.execute("SELECT COUNT(*) FROM wifi_tasks WHERE status IN ('PENDING', 'RETRY_WAIT')").fetchone()[0]
                    if pending == 0:
                        print(f"\n{G}[SELESAI] Semua tugas Wi-Fi telah habis dikerjakan.{W}")
                        conn.close()
                        break
                    
                    if urls_in_browser >= 100:
                        print(f"\n{C}-> [PENYEGARAN RAM] Hard Recycling Browser Chromium Wi-Fi...{W}")
                        browser.close()
                        browser = p.chromium.launch(headless=True, args=browser_launch_args)
                        urls_in_browser = 0
                    
                    batch_size = min(50, target - total_processed)
                    print(f"{C}-> Mendaur ulang Context (Cek {batch_size} Target)...{W}")
                    context = browser.new_context(viewport={"width": 1280, "height": 800}, locale="id-ID", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", locale="id-ID")
                    
                    def block_wifi_assets(route):
                        if route.request.resource_type in ["image", "media", "font"]:
                            route.abort()
                        else:
                            route.continue_()
                    context.route("**/*", block_wifi_assets)
                    
                    processed = 0
                    try:
                        for _ in range(batch_size):
                            task = claim_task(conn)
                            if not task:
                                break
                            try:
                                page = context.new_page()
                                res = check_wifi(page, task['place_url'])
                                page.close()
                                
                                conn.execute("INSERT OR REPLACE INTO wifi_results (candidate_id, job_id, has_wifi, wifi_provider, evidence) VALUES (?, ?, ?, ?, ?)", (task["candidate_id"], task["job_id"], res["has_wifi"], res["wifi_provider"], res["evidence"]))
                                conn.execute("UPDATE wifi_tasks SET status='DONE', updated_at=CURRENT_TIMESTAMP WHERE candidate_id=?", (task["candidate_id"],))
                                conn.commit()
                                
                                if res['has_wifi']:
                                    session_has_wifi += 1
                                    print(f"   {G}[V] ADA WI-FI{W} | Provider: {res['wifi_provider']} | {task['place_url'][:30]}...")
                                else:
                                    session_no_wifi += 1
                                    print(f"   {R}[X] TIDAK ADA{W} | Provider: {res['wifi_provider']} | {task['place_url'][:30]}...")
                            except KeyboardInterrupt:
                                print(f"\n   {Y}⚠️ Interupsi Ctrl+C diterima! Menghentikan pengecekan Wi-Fi...{W}")
                                conn.execute("UPDATE wifi_tasks SET status='PENDING' WHERE candidate_id=?", (task["candidate_id"],))
                                conn.commit()
                                interrupted = True
                                break
                            except Exception as e:
                                session_failed += 1
                                new_status = "RETRY_WAIT" if task['attempts'] < 3 else "FAILED_FINAL"
                                conn.execute("UPDATE wifi_tasks SET status=?, last_error=?, updated_at=CURRENT_TIMESTAMP WHERE candidate_id=?", (new_status, str(e)[:100], task["candidate_id"]))
                                conn.commit()
                                if new_status == "RETRY_WAIT":
                                    backoff = 3 * (2 ** task['attempts'])
                                    print(f"   {M}[!] Gagal Jaringan. Backoff {backoff} detik -> {new_status}{W}")
                                    time.sleep(backoff)
                                else:
                                    print(f"   {R}[!] Gagal Permanen -> {new_status}{W}")
                            processed += 1
                            urls_in_browser += 1
                    except KeyboardInterrupt:
                        interrupted = True
                        break
                    finally:
                        try:
                            context.close()
                        except Exception:
                            pass
                    conn.close()
                    total_processed += processed
                    if processed == 0 or interrupted:
                        break
            except KeyboardInterrupt:
                interrupted = True
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except KeyboardInterrupt:
        interrupted = True
        
    if interrupted:
        print(f"\n{Y}🛡️  [GRACEFUL SHUTDOWN] Mengamankan antrean tugas Wi-Fi...{W}")
        conn_cleanup = get_db()
        try:
            cur = conn_cleanup.cursor()
            cur.execute("UPDATE wifi_tasks SET status='PENDING' WHERE status='RUNNING'")
            reverted = cur.rowcount
            conn_cleanup.commit()
            print(f"   {G}✅ Berhasil mengembalikan {reverted} tugas Wi-Fi ke status PENDING.{W}")
        finally:
            conn_cleanup.close()
            
    elapsed = time.time() - start_time
    avg_speed = elapsed / total_processed if total_processed > 0 else 0
    header_status = "⚠️ LAPORAN SESI WI-FI (DIHENTIKAN AMAN)" if interrupted else "📡 LAPORAN SESI PENCARIAN WI-FI"
    print(f"\n{C}{B}" + "="*55 + f"{W}")
    print(f" {B}{header_status}{W}")
    print(f"{C}{B}" + "="*55 + f"{W}")
    print(f" Total URL Diperiksa  : {total_processed} Tempat")
    print(f" Lama Waktu           : {format_time(elapsed)}")
    print(f" Kecepatan Rata2      : {avg_speed:.2f} detik / Tempat")
    print(C + "-"*55 + W)
    print(f" {G}✅ Memiliki Wi-Fi   : {session_has_wifi} Tempat{W}")
    print(f" {R}❌ Tidak Ada Wi-Fi  : {session_no_wifi} Tempat{W}")
    if session_failed > 0:
        print(f" {M}⚠️ Gagal Pengecekan : {session_failed} Tempat (Bisa di-reset){W}")
    play_success_sound()
    try:
        input(f"\n{Y}>> Tekan Enter untuk kembali...{W}")
    except KeyboardInterrupt:
        pass

def export_data():
    clear_screen()
    print(f"\n{C}{B}" + "="*65 + f"{W}")
    print(f" 📝 EXPORT LAPORAN ENTERPRISE (PROSPEK + LOG AUDIT)")
    print(f"{C}{B}" + "="*65 + f"{W}")
    try:
        from app.excel_exporter import export_enterprise_data
        ok, msg, stats = export_enterprise_data(DB_FILE, EXPORT_DIR)
        if ok:
            print(f"\n {G}✅ EKSPOR BERHASIL DISELESAIKAN!{W}")
            print(f" -------------------------------------------------------------")
            print(f"  🏢 Prospek VALID (Sheet 1)    : {G}{B}{stats['total_valid']:,} Tempat (Siap Tindak Lanjut Sales){W}")
            print(f"  🛡️  Log Karantina (Sheet 2)   : {Y}{B}{stats['total_karantina']:,} Tempat (Audit Data Ditolak){W}")
            print(f"  🟢 Siap Chat WhatsApp Langsung: {G}{stats['wa_count']:,} Kontak (Link wa.me Aktif){W}")
            print(f"  📡 Fasilitas Wi-Fi Terdeteksi : {C}{stats['wifi_count']:,} Tempat{W}")
            print(f" -------------------------------------------------------------")
            print(f"  📁 File Excel Resmi Telkom    : {G}{Path(stats['xlsx_path']).name}{W}")
            print(f"  📁 File Backup CSV            : {Path(stats['csv_path']).name}")
            print(f"  📂 Tersimpan di Folder        : {EXPORT_DIR.resolve()}")
            play_success_sound()
        else:
            print(f"\n {Y}ℹ️  {msg}{W}")
    except Exception as e:
        print(f"\n {R}❌ Gagal mengekspor: {e}{W}")
    input(f"\n{Y}>> Tekan Enter untuk kembali ke Menu Utama...{W}")

def reset_failed_jobs():
    print(f"\n{C}♻️  MENCARI DATA YANG GAGAL / TERTINGGAL (AKIBAT DI-CLOSE [X])...{W}")
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE jobs SET status='PENDING' WHERE status IN ('FAILED_FINAL', 'RUNNING')")
        job_res = cur.rowcount
        cur.execute("UPDATE wifi_tasks SET status='PENDING', attempts=0 WHERE status IN ('FAILED_FINAL', 'RUNNING')")
        wifi_res = cur.rowcount
        conn.commit()
        if job_res == 0 and wifi_res == 0:
            print(f"{G}[INFO] Tidak ada data job yang menggantung. Database bersih!{W}")
        else:
            print(f"{G}[SUKSES] Antrean Database Dipulihkan!{W}")
            print(f" -> {job_res} Job Tempat menggantung dikembalikan ke status PENDING")
            print(f" -> {wifi_res} Job Wi-Fi menggantung dikembalikan ke status PENDING")
    finally:
        conn.close()
        
    print(f"\n{C}🧹 Memeriksa sisa proses Chromium zombie di RAM Windows...{W}")
    try:
        from app.process_guard import clean_orphan_chromium
        k, m = clean_orphan_chromium(verbose=True)
        if k > 0:
            print(f" {G}✅ Berhasil mematikan {k} proses zombie tak bertuan ({m:.1f} MB RAM dibebaskan){W}")
        else:
            print(f" {G}✅ RAM Bersih. Tidak ada browser zombie tertinggal.{W}")
    except Exception as e:
        print(f" {Y}Catatan pembersih: {e}{W}")
        
    input(f"\n{Y}>> Tekan Enter untuk kembali ke menu...{W}")

def parse_sheet_to_dicts(raw_rows):
    if not raw_rows:
        return []
    if isinstance(raw_rows[0], dict):
        return raw_rows
    headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(raw_rows[0])]
    records = []
    for row in raw_rows[1:]:
        if not any(row):
            continue
        row_dict = {}
        for i, h in enumerate(headers):
            val = row[i] if i < len(row) else ""
            row_dict[h] = str(val).strip() if val is not None else ""
        records.append(row_dict)
    return records

def sync_new_witel_project():
    clear_screen()
    print(C + B + "="*80 + W)
    print("      🔄 SINKRONISASI / INISIALISASI WITEL BARU DARI EXCEL INPUT")
    print(C + B + "="*80 + W)
    
    if not REGION_FILE.exists() or not KEYWORD_FILE.exists():
        print(f"{R}[!] File input tidak lengkap di folder input/:{W}")
        print(f"    - {REGION_FILE.name}: {'ADA' if REGION_FILE.exists() else 'TIDAK DITEMUKAN'}")
        print(f"    - {KEYWORD_FILE.name}: {'ADA' if KEYWORD_FILE.exists() else 'TIDAK DITEMUKAN'}")
        input(f"\n{Y}Tekan Enter untuk kembali...{W}")
        return

    from app.region_mapper import read_first_sheet
    from app.witel_registry import detect_witel_from_cities
    
    print(f"{C}-> Membaca file kota: {REGION_FILE.name}...{W}")
    raw_sheet_cities = read_first_sheet(REGION_FILE)
    city_rows = parse_sheet_to_dicts(raw_sheet_cities)
    
    def extract_val(row, keys, default=""):
        if isinstance(row, dict):
            for k in row.keys():
                if any(cand in k.lower().strip() for cand in keys):
                    val = str(row[k]).strip()
                    if val:
                        return val
        elif isinstance(row, (list, tuple)) and row:
            return str(row[0]).strip()
        return default

    raw_cities = []
    for r in city_rows:
        c_val = extract_val(r, ["kota", "kab", "kabupaten", "daerah", "wilayah"])
        if c_val and c_val not in raw_cities:
            raw_cities.append(c_val)
            
    if not raw_cities and city_rows:
        for r in city_rows:
            first_v = list(r.values())[0] if isinstance(r, dict) and r.values() else ""
            if first_v and str(first_v).strip() not in raw_cities:
                raw_cities.append(str(first_v).strip())

    if not raw_cities:
        print(f"{R}[!] Tidak ditemukan data kota/kabupaten di dalam {REGION_FILE.name}.{W}")
        input(f"\n{Y}Tekan Enter untuk kembali...{W}")
        return
        
    detected_witel, matched_items = detect_witel_from_cities(raw_cities)
    
    print(f"{C}-> Membaca file keyword: {KEYWORD_FILE.name}...{W}")
    raw_sheet_kw = read_first_sheet(KEYWORD_FILE)
    kw_rows = parse_sheet_to_dicts(raw_sheet_kw)
    
    parsed_keywords = []
    for r in kw_rows:
        kw = extract_val(r, ["keyword", "kata kunci", "kata", "key", "pencarian"])
        kat = extract_val(r, ["kategori", "category", "sektor", "bidang"], default="UMUM")
        if not kw and isinstance(r, dict) and r.values():
            vals = [str(v).strip() for v in r.values() if str(v).strip()]
            if vals:
                kw = vals[-1]
                kat = vals[0] if len(vals) > 1 else "UMUM"
        if kw and (kat, kw) not in parsed_keywords:
            parsed_keywords.append((kat, kw))
            
    if not parsed_keywords:
        print(f"{R}[!] Tidak ditemukan kata kunci di dalam {KEYWORD_FILE.name}.{W}")
        input(f"\n{Y}Tekan Enter untuk kembali...{W}")
        return
        
    total_combinations = len(matched_items) * len(parsed_keywords)
    
    print(f"\n{G}[ANALISIS INPUT BERHASIL]{W}")
    print(f" 🏢 Witel Terdeteksi : {Y}{B}{detected_witel}{W}")
    print(f" 📍 Total Kota/Kab   : {len(matched_items)} Daerah")
    print(f" 🔑 Total Keyword    : {len(parsed_keywords)} Kata Kunci")
    print(f" 🎯 Total Target Job : {B}{total_combinations:,}{W} Kombinasi Job")
    print(C + "-"*80 + W)
    print(" Pilih Metode Sinkronisasi:")
    print(" [1] Tambahkan ke Database yang Berjalan (Tanpa hapus data lama)")
    print(" [2] Mulai Project Baru Bersih (Database lama di-backup ke database/backups/)")
    print(" [0] Batal")
    
    choice = input(f"\n{B}Pilihan Anda (0/1/2): {W}").strip()
    if choice not in ["1", "2"]:
        print(f"{Y}Operasi dibatalkan.{W}")
        time.sleep(1)
        return
        
    conn = get_db()
    try:
        if choice == "2":
            import shutil
            conn.close()
            backup_dir = ROOT / "database" / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            old_witel = get_active_witel().replace(" ", "_")
            backup_file = backup_dir / f"scraper_backup_{old_witel}_{stamp}.db"
            
            if DB_FILE.exists():
                shutil.copy2(DB_FILE, backup_file)
                print(f"{G}[BACKUP] Database lama diamankan ke: {backup_file.name}{W}")
            
            conn = get_db()
            for tbl in ["wifi_results", "wifi_tasks", "scrape_candidates", "job_business", "jobs", "projects"]:
                try:
                    conn.execute(f"DELETE FROM {tbl};")
                except Exception:
                    pass
            try:
                conn.execute("VACUUM;")
            except Exception:
                pass
            
        project_id = f"PRJ-{detected_witel.replace(' ', '_').upper()}"
        conn.execute("INSERT OR IGNORE INTO projects (project_id, name) VALUES (?, ?)", (project_id, detected_witel))
        
        jobs_to_insert = []
        for city_info in matched_items:
            kota = city_info["kota_kab"]
            prov = city_info["provinsi"]
            for kat, kw in parsed_keywords:
                seed = f"{detected_witel}_{kota}_{kw}_{kat}".lower()
                jid = f"JOB-{hashlib.sha256(seed.encode()).hexdigest()[:16].upper()}"
                jobs_to_insert.append((jid, project_id, kat, kw, kota, prov, detected_witel))
                
        conn.executemany("""
            INSERT OR IGNORE INTO jobs (job_id, project_id, kategori, keyword, kota_kab, provinsi, witel, status, attempts)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', 0)
        """, jobs_to_insert)
        
        conn.commit()
        print(f"\n{G}[SUKSES] Berhasil memproses antrean target untuk {detected_witel}!{W}")
        play_success_sound()
    finally:
        conn.close()
        
    input(f"\n{Y}>> Tekan Enter untuk kembali ke Menu Utama...{W}")

def main_menu():
    try:
        from app.process_guard import clean_orphan_chromium
        clean_orphan_chromium(verbose=False)
    except Exception:
        pass

    while True:
        clear_screen()
        active_witel = get_active_witel()
        lic = get_license_status()
        
        print(C + B + "="*80 + W)
        print(R + r"              @@@              " + W)
        print(R + r"       )@    @@@@    _@@@      " + W)
        print(R + r"      |@@|  @@@@/  ,@@@@/      " + R + B + r"  _____    _ _                  " + W)
        print(R + r'      @@@@ @@@@@ _@@@@@"       ' + R + B + r" |_   _|__| | |_____ _ __       " + W)
        print(R + r"      @@@@@@@@@@@@@@@@   _.@@@ " + R + B + r"   | |/ -_) | / / _ \ '  \      " + W)
        print(Gr+ r"    /@/" + R + r'    ^\@@@@@@@_/@@@@@@"  ' + R + B + r"   |_|\___|_|_\_\___/_|_|_|     " + W)
        print(Gr+ r"  @@@@|~@@~." + R + r"    \@@@@@@@@@@^   " + W)
        print(Gr+ r'_@@@"' + R + r"  @@@@@@@   ^@@@@@@/      " + W + B + r"  ___         _                   _       " + W)
        print(Gr+ r"@@@^" + R + r"    @@@@@@@   )@@@^        " + W + B + r" |_ _|_ _  __| |___ _ _  ___ ___ (_)__ _  " + W)
        print(Gr+ r"@@@" + R + r"      ^@@@@@    @@\,,,_     " + W + B + r"  | || ' \/ _` / _ \ ' \/ -_)_-< | / _` | " + W)
        print(Gr+ r"@@@\       " + R + r"^@@/   |@@@@@@@@/   " + W + B + r" |___|_||_\__,_\___/_||_\___/__/ |_\__,_| " + W)
        print(Gr+ r"^@@@@\     _/@@@@" + R + r"|@@@@@@~^     " + W + r"                                   the world in your hand" + W)
        print(Gr+ r"  @@@@@@@@@@@@@@@              " + W)
        print(Gr+ r'    "@@@@@@@@@"                ' + W)
        print(C + B + "="*80 + W)
        print("                        🤖 " + B + "TELKOM SCRAPER " + Y + "ENTERPRISE DASHBOARD V3" + W)
        print(f"                   🏢 {B}WILAYAH AKTIF :{W} {G}{B}{active_witel}{W}")
        if lic['is_locked']:
            print(f"                   ⚠️ {R}{B}STATUS        : MASA TRIAL HABIS / TERKUNCI{W}")
        print(C + B + "="*80 + W)
        print(" " + C + "1." + W + " 📊 Monitor Progress Saat Ini")
        print(" " + C + "2." + W + " 🚀 Jalankan / Lanjutkan Scraping Tempat (Utama)")
        print(" " + C + "3." + W + " ⚙️  Sinkronisasi Data Baru untuk Target Wi-Fi")
        print(" " + C + "4." + W + " 📡 Jalankan / Lanjutkan Scraping Wi-Fi")
        print(" " + C + "5." + W + " 📝 Export Laporan Akhir (Excel Native / CSV)")
        print(" " + M + "6." + W + " ♻️  Ulangi Job Gagal (Reset FAILED ke PENDING)")
        print(" " + Y + "7." + W + " 🔄 Inisialisasi / Ganti Witel Baru (Dari Excel Input)")
        if lic['is_locked']:
            print(" " + R + B + "8." + W + f" 🔑 {R}{B}Aktivasi Lisensi / Perpanjang Kuota (Wajib Kode Admin){W}")
        print(" " + R + "0." + W + " ❌ Keluar Program")
        print(C + B + "="*80 + W)
        
        prompt_txt = "Pilih Menu (0-8): " if lic['is_locked'] else "Pilih Menu (0-7): "
        try:
            p = input(B + prompt_txt + W).strip()
        except KeyboardInterrupt:
            print(f"\n{G}Sampai jumpa! Sistem dimatikan dengan aman via Ctrl+C.{W}")
            break

        if p == '1':
            show_progress()
        elif p == '2':
            run_main_scraper()
        elif p == '3':
            setup_wifi_tasks()
        elif p == '4':
            run_wifi_scraper()
        elif p == '5':
            export_data()
        elif p == '6':
            reset_failed_jobs()
        elif p == '7':
            sync_new_witel_project()
        elif p == '8' and lic['is_locked']:
            menu_license()
        elif p == '0':
            print(f"\n{G}Sampai jumpa! Sistem dimatikan dengan aman.{W}")
            break
        else:
            time.sleep(1)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n\033[92mSampai jumpa! Sistem dimatikan dengan aman.\033[0m")
        try:
            from app.process_guard import clean_orphan_chromium
            clean_orphan_chromium(verbose=False)
        except Exception:
            pass
        sys.exit(0)
