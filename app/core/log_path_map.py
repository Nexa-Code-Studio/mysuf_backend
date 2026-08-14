"""
log_path_map.py
───────────────
Mapping statis dari (HTTP method, path prefix) → (deskripsi human-readable, kategori SPBU).

Digunakan oleh ActivityLoggingMiddleware untuk menghasilkan deskripsi yang bermakna
pada setiap request mutasi data.

Urutan pencocokan: dari yang paling spesifik (panjang path) ke yang paling umum.
"""

from app.modules.spbu_activities.models import SpbuActivityCategory

# Format: (method_upper, path_prefix_lower) → (deskripsi, SpbuActivityCategory)
# Path prefix dicocokan dengan startswith(), diurutkan dari yang paling panjang duluan.
PATH_ACTION_MAP: list[tuple[tuple[str, str], tuple[str, SpbuActivityCategory]]] = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    (("POST",   "/api/v1/auth/login"),              ("Login ke sistem SUBSIDIA",                           SpbuActivityCategory.Sistem)),
    (("POST",   "/api/v1/auth/logout"),             ("Logout dari sistem SUBSIDIA",                        SpbuActivityCategory.Sistem)),
    (("POST",   "/api/v1/auth/refresh"),            ("Perbarui sesi login",                             SpbuActivityCategory.Sistem)),

    # ── Cashier / Transaksi BBM ────────────────────────────────────────────────
    (("POST",   "/api/v1/cashier/transactions"),    ("Transaksi BBM diproses oleh kasir",               SpbuActivityCategory.Penjualan)),
    (("POST",   "/api/v1/cashier/scan"),            ("Pemindaian NIK/KTP warga oleh kasir",             SpbuActivityCategory.Penjualan)),

    # ── SPBU Transactions ─────────────────────────────────────────────────────
    (("POST",   "/api/v1/spbu/transactions"),       ("Memproses transaksi BBM baru",                    SpbuActivityCategory.Penjualan)),

    # ── SPBU Fraud Alert ──────────────────────────────────────────────────────
    (("POST",   "/api/v1/spbu/fraud-alert"),        ("Fraud alert diajukan",                            SpbuActivityCategory.Keamanan)),
    (("PATCH",  "/api/v1/spbu/fraud-alert"),        ("Status fraud alert diperbarui",                   SpbuActivityCategory.Keamanan)),
    (("PUT",    "/api/v1/spbu/fraud-alert"),        ("Fraud alert diperbarui",                          SpbuActivityCategory.Keamanan)),

    # ── SPBU Staff ────────────────────────────────────────────────────────────
    (("POST",   "/api/v1/spbu/staff"),              ("Menambahkan staf SPBU baru",                      SpbuActivityCategory.Sistem)),
    (("PUT",    "/api/v1/spbu/staff"),              ("Memperbarui data staf SPBU",                      SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/spbu/staff"),              ("Memperbarui data staf SPBU",                      SpbuActivityCategory.Sistem)),
    (("DELETE", "/api/v1/spbu/staff"),              ("Menghapus staf SPBU",                             SpbuActivityCategory.Sistem)),

    # ── SPBU Profile ──────────────────────────────────────────────────────────
    (("PUT",    "/api/v1/spbu/profile"),            ("Memperbarui profil SPBU",                         SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/spbu/profile"),            ("Memperbarui profil SPBU",                         SpbuActivityCategory.Sistem)),

    # ── SPBU Settings ─────────────────────────────────────────────────────────
    (("PUT",    "/api/v1/spbu/settings"),           ("Mengubah pengaturan SPBU",                        SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/spbu/settings"),           ("Mengubah pengaturan SPBU",                        SpbuActivityCategory.Sistem)),

    # ── Fraud Logs (general) ──────────────────────────────────────────────────
    (("POST",   "/api/v1/fraud-logs"),              ("Log fraud baru dicatat",                          SpbuActivityCategory.Keamanan)),
    (("PATCH",  "/api/v1/fraud-logs"),              ("Status log fraud diperbarui",                     SpbuActivityCategory.Keamanan)),
    (("PUT",    "/api/v1/fraud-logs"),              ("Log fraud diperbarui",                            SpbuActivityCategory.Keamanan)),

    # ── Kendaraan / Vehicles ──────────────────────────────────────────────────
    (("POST",   "/api/v1/vehicles"),                ("Mendaftarkan kendaraan baru",                     SpbuActivityCategory.Sistem)),
    (("PUT",    "/api/v1/vehicles"),                ("Memperbarui data kendaraan",                      SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/vehicles"),                ("Memperbarui data kendaraan",                      SpbuActivityCategory.Sistem)),
    (("DELETE", "/api/v1/vehicles"),                ("Menghapus kendaraan",                             SpbuActivityCategory.Sistem)),
    (("POST",   "/api/v1/vehicle-ownership-documents"), ("Dokumen kendaraan diunggah",                  SpbuActivityCategory.Sistem)),

    # ── Perusahaan / Companies ────────────────────────────────────────────────
    (("POST",   "/api/v1/companies"),               ("Mendaftarkan perusahaan baru",                    SpbuActivityCategory.Sistem)),
    (("PUT",    "/api/v1/companies"),               ("Memperbarui data perusahaan",                     SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/companies"),               ("Memperbarui data perusahaan",                     SpbuActivityCategory.Sistem)),
    (("DELETE", "/api/v1/companies"),               ("Menghapus perusahaan",                            SpbuActivityCategory.Sistem)),

    # ── Pengguna / Users ──────────────────────────────────────────────────────
    (("POST",   "/api/v1/users"),                   ("Menambah pengguna baru",                          SpbuActivityCategory.Sistem)),
    (("PUT",    "/api/v1/users"),                   ("Memperbarui data pengguna",                       SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/users"),                   ("Memperbarui data pengguna",                       SpbuActivityCategory.Sistem)),
    (("DELETE", "/api/v1/users"),                   ("Menghapus pengguna",                              SpbuActivityCategory.Sistem)),

    # ── Government ────────────────────────────────────────────────────────────
    (("POST",   "/api/v1/government"),              ("Aksi pemerintah dilakukan",                       SpbuActivityCategory.Sistem)),
    (("PUT",    "/api/v1/government"),              ("Data pemerintah diperbarui",                      SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/government"),              ("Data pemerintah diperbarui",                      SpbuActivityCategory.Sistem)),

    # ── Subsidi ───────────────────────────────────────────────────────────────
    (("POST",   "/api/v1/subsidy"),                 ("Data subsidi diperbarui",                         SpbuActivityCategory.Sistem)),
    (("PUT",    "/api/v1/subsidy"),                 ("Data subsidi diperbarui",                         SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/subsidy"),                 ("Data subsidi diperbarui",                         SpbuActivityCategory.Sistem)),

    # ── Wallet ────────────────────────────────────────────────────────────────
    (("POST",   "/api/v1/wallet"),                  ("Transaksi wallet dilakukan",                      SpbuActivityCategory.Penjualan)),

    # ── Registries / Seed ─────────────────────────────────────────────────────
    (("POST",   "/api/v1/seed"),                    ("Inisiasi data master sistem",                     SpbuActivityCategory.Sistem)),
    (("POST",   "/api/v1/registries"),              ("Data registri diperbarui",                        SpbuActivityCategory.Sistem)),

    # ── Mysuf Admin ───────────────────────────────────────────────────────────
    (("POST",   "/api/v1/subsidia-admin"),             ("Aksi super admin dilakukan",                      SpbuActivityCategory.Sistem)),
    (("PUT",    "/api/v1/subsidia-admin"),             ("Data super admin diperbarui",                     SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/subsidia-admin"),             ("Data super admin diperbarui",                     SpbuActivityCategory.Sistem)),
    (("DELETE", "/api/v1/subsidia-admin"),             ("Data dihapus oleh super admin",                   SpbuActivityCategory.Sistem)),

    # ── Fleet ─────────────────────────────────────────────────────────────────
    (("POST",   "/api/v1/fleet"),                   ("Aksi fleet dilakukan",                            SpbuActivityCategory.Sistem)),
    (("PUT",    "/api/v1/fleet"),                   ("Data fleet diperbarui",                           SpbuActivityCategory.Sistem)),
    (("PATCH",  "/api/v1/fleet"),                   ("Data fleet diperbarui",                           SpbuActivityCategory.Sistem)),
    (("DELETE", "/api/v1/fleet"),                   ("Data fleet dihapus",                              SpbuActivityCategory.Sistem)),
]

# Pre-sort by path prefix length descending for most-specific-first matching
PATH_ACTION_MAP.sort(key=lambda x: len(x[0][1]), reverse=True)


def resolve_action(method: str, path: str) -> tuple[str, SpbuActivityCategory]:
    """
    Kembalikan (deskripsi, kategori_spbu) berdasarkan method dan path.
    Fallback ke deskripsi generik jika tidak ada yang cocok.
    """
    method_upper = method.upper()
    path_lower = path.lower()

    for (m, prefix), (desc, category) in PATH_ACTION_MAP:
        if m == method_upper and path_lower.startswith(prefix.lower()):
            return desc, category

    # Fallback generik
    method_label = {
        "POST": "Menambahkan data baru",
        "PUT": "Memperbarui data",
        "PATCH": "Memperbarui data",
        "DELETE": "Menghapus data",
    }.get(method_upper, f"Aksi {method_upper}")

    return f"{method_label} pada {path}", SpbuActivityCategory.Sistem
