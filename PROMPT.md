Buatkan base project backend FastAPI dari scratch dengan struktur modular monolith.

Stack:
- FastAPI
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Pydantic v2
- JWT authentication
- passlib/bcrypt untuk password hashing
- python-dotenv atau pydantic-settings
- pytest untuk testing dasar

Gunakan struktur project seperti ini:

backend/
├─ app/
│  ├─ main.py
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ database.py
│  │  ├─ security.py
│  │  └─ exceptions.py
│  ├─ api/
│  │  ├─ deps.py
│  │  └─ v1/
│  │     ├─ router.py
│  │     └─ auth/
│  │        └─ routes.py
│  ├─ modules/
│  │  └─ users/
│  │     ├─ models.py
│  │     ├─ schemas.py
│  │     ├─ repository.py
│  │     ├─ service.py
│  │     └─ router.py
│  └─ utils/
├─ migrations/
├─ tests/
├─ alembic.ini
├─ pyproject.toml
└─ README.md

Buat model user dasar dengan pendekatan:
- Satu tabel utama `users` untuk autentikasi dan role.
- Tabel detail terpisah berdasarkan tipe user jika field-nya berbeda.

Role user:
1. SUPERADMIN
   - superadmin level negara
2. BRANCH_ADMIN
   - admin untuk masing-masing cabang
3. SALES_OFFICER
   - petugas penjual
4. BUYER
   - pembeli

Schema database yang diinginkan:

Tabel `users`:
- id: UUID primary key
- name: string, required
- username: string, unique, indexed, required
- hashed_password: string, required
- role: enum [SUPERADMIN, BRANCH_ADMIN, SALES_OFFICER, BUYER]
- is_active: boolean, default true
- created_at: datetime
- updated_at: datetime

Tabel `employee_profiles`:
Untuk BRANCH_ADMIN dan SALES_OFFICER.
- id: UUID primary key
- user_id: FK ke users.id, unique
- no_induk_kar: string, unique, required
- created_at: datetime
- updated_at: datetime

Tabel `buyer_profiles`:
Untuk BUYER.
- id: UUID primary key
- user_id: FK ke users.id, unique
- nik: string, unique, required
- no_kk: string, required
- xendit_wallet_key: string, nullable dulu
- created_at: datetime
- updated_at: datetime

Catatan desain:
- Jangan taruh semua field di tabel users karena detail pembeli dan pegawai berbeda.
- `users` hanya untuk identitas umum, login, password, role, dan status.
- Detail khusus role disimpan di tabel profile.
- Untuk SUPERADMIN, tidak perlu profile tambahan dulu.
- Untuk BRANCH_ADMIN dan SALES_OFFICER, gunakan `employee_profiles`.
- Untuk BUYER, gunakan `buyer_profiles`.

Buat endpoint awal:

Auth:
- POST /api/v1/auth/login
  - input: username, password
  - output: access_token, token_type, user info
- GET /api/v1/auth/me
  - butuh JWT
  - output: current user

Users:
- POST /api/v1/users/superadmins
- POST /api/v1/users/branch-admins
- POST /api/v1/users/sales-officers
- POST /api/v1/users/buyers
- GET /api/v1/users
- GET /api/v1/users/{user_id}
- PATCH /api/v1/users/{user_id}/deactivate

Validasi:
- username harus unique
- no_induk_kar harus unique untuk employee profile
- nik harus unique untuk buyer profile
- role harus sesuai endpoint yang dipakai
- password harus di-hash sebelum disimpan
- jangan pernah return hashed_password di response

Tambahkan dependency authorization dasar:
- get_current_user
- require_roles(*roles)

Aturan permission awal:
- SUPERADMIN bisa membuat semua jenis user.
- BRANCH_ADMIN bisa membuat SALES_OFFICER dan BUYER.
- SALES_OFFICER hanya bisa membuat BUYER.
- BUYER tidak bisa membuat user.

Buat file:
- models SQLAlchemy
- schemas Pydantic
- repository layer
- service layer
- router layer
- Alembic migration pertama
- README berisi cara install, setup env, migrate database, dan run server

Gunakan style kode yang clean, type hints, async atau sync SQLAlchemy boleh, tapi konsisten. Prioritaskan implementasi yang mudah dikembangkan menjadi backend untuk 3 aplikasi berbeda.