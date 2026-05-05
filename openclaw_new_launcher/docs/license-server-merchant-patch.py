"""
OpenClaw License Server - Merchant & Theme Extension Patch
=========================================================
This file contains the incremental changes needed to add merchant/theme
support to the license server (d:\\Axiangmu\\AUSTART\\license_server\\server.py).

Apply these changes manually to server.py. Each section is marked with
a "PATCH N" comment indicating where in the original file the change goes.
"""

# ============================================================
# PATCH 1: Replace init_db() function
# ============================================================
# Replace the existing init_db() function with this version that adds
# the merchants table and merchant_id column to codes.

def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists merchants (
            merchant_id text primary key,
            name text not null,
            subtitle text not null default '',
            theme_json text not null default '{}',
            logo_url text not null default '',
            created_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists codes (
            code_hash text primary key,
            code_label text not null,
            full_code text not null default '',
            licensee text not null,
            edition text not null,
            features_json text not null,
            expires text not null,
            max_activations integer not null default 1,
            disabled integer not null default 0,
            merchant_id text default null,
            created_at text not null,
            foreign key (merchant_id) references merchants(merchant_id)
        )
        """
    )
    try:
        conn.execute("alter table codes add column merchant_id text default null")
    except Exception:
        pass
    conn.execute(
        """
        create table if not exists activations (
            id integer primary key autoincrement,
            code_hash text not null,
            install_id text not null,
            device_id text not null,
            license_json text not null,
            activated_at text not null,
            unique(code_hash, install_id)
        )
        """
    )
    conn.commit()


# ============================================================
# PATCH 2: Add merchant CRUD functions (after make_code function)
# ============================================================

def get_merchant_rows() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "select merchant_id, name, subtitle, theme_json, logo_url, created_at from merchants order by created_at desc"
        ).fetchall()
    return [
        {
            "merchantId": row["merchant_id"],
            "name": row["name"],
            "subtitle": row["subtitle"],
            "themeJson": json.loads(row["theme_json"]) if row["theme_json"] else {},
            "logoUrl": row["logo_url"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def create_merchant(body: dict[str, Any]) -> dict[str, Any]:
    merchant_id = str(body.get("merchantId", "")).strip()
    name = str(body.get("name", "")).strip()
    subtitle = str(body.get("subtitle", "")).strip()
    theme_json = body.get("themeJson", {})
    logo_url = str(body.get("logoUrl", "")).strip()

    if not merchant_id or not name:
        raise ValueError("merchantId 和 name 不能为空")

    with connect() as conn:
        existing = conn.execute("select merchant_id from merchants where merchant_id = ?", (merchant_id,)).fetchone()
        if existing:
            raise ValueError(f"商家 {merchant_id} 已存在")
        conn.execute(
            "insert into merchants (merchant_id, name, subtitle, theme_json, logo_url, created_at) values (?, ?, ?, ?, ?, ?)",
            (merchant_id, name, subtitle, json.dumps(theme_json, ensure_ascii=False), logo_url, utc_now()),
        )
        conn.commit()
    return {"merchantId": merchant_id, "name": name}


def update_merchant(merchant_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        existing = conn.execute("select merchant_id from merchants where merchant_id = ?", (merchant_id,)).fetchone()
        if not existing:
            raise ValueError(f"商家 {merchant_id} 不存在")
        fields = []
        values = []
        for key, col in [("name", "name"), ("subtitle", "subtitle"), ("themeJson", "theme_json"), ("logoUrl", "logo_url")]:
            if key in body:
                val = body[key]
                if key == "themeJson":
                    val = json.dumps(val, ensure_ascii=False)
                fields.append(f"{col} = ?")
                values.append(val)
        if not fields:
            return {"ok": True, "message": "无更新"}
        values.append(merchant_id)
        conn.execute(f"update merchants set {', '.join(fields)} where merchant_id = ?", values)
        conn.commit()
    return {"ok": True}


def delete_merchant(merchant_id: str) -> dict[str, Any]:
    with connect() as conn:
        conn.execute("delete from merchants where merchant_id = ?", (merchant_id,))
        conn.execute("update codes set merchant_id = null where merchant_id = ?", (merchant_id,))
        conn.commit()
    return {"ok": True}


# ============================================================
# PATCH 3: Update create_code_records to accept merchant_id
# ============================================================
# Add merchant_id parameter to create_code_records function signature
# and include it in the INSERT statement.

def create_code_records_v2(
    *,
    count: int,
    licensee: str,
    edition: str,
    features: list[str],
    expires: str,
    max_activations: int,
    merchant_id: str | None = None,
) -> list[str]:
    count = max(1, min(int(count), 100))
    max_activations = max(1, min(int(max_activations), 20))
    codes: list[str] = []
    with connect() as conn:
        for _ in range(count):
            code = make_code(edition)
            conn.execute(
                """
                insert into codes (code_hash, code_label, full_code, licensee, edition, features_json, expires, max_activations, disabled, merchant_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    code_hash(code),
                    code[-9:],
                    code,
                    licensee,
                    edition,
                    json.dumps(features, ensure_ascii=False),
                    expires,
                    max_activations,
                    merchant_id,
                    utc_now(),
                ),
            )
            codes.append(code)
        conn.commit()
    return codes


# ============================================================
# PATCH 4: Update get_code_rows to include merchant_id
# ============================================================

def get_code_rows_v2() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            select c.code_hash, c.code_label, c.full_code, c.licensee, c.edition, c.features_json, c.expires, c.max_activations,
                   c.disabled, c.merchant_id, c.created_at, count(a.id) as activations
            from codes c
            left join activations a on a.code_hash = c.code_hash
            group by c.code_hash
            order by c.created_at desc
            """
        ).fetchall()
    return [
        {
            "codeHash": row["code_hash"],
            "codeLabel": row["code_label"],
            "fullCode": row["full_code"] or ("OC-" + row["edition"].upper() + "-" + row["code_label"]),
            "licensee": row["licensee"],
            "edition": row["edition"],
            "features": json.loads(row["features_json"]),
            "expires": row["expires"],
            "maxActivations": row["max_activations"],
            "activations": row["activations"],
            "disabled": bool(row["disabled"]),
            "merchantId": row["merchant_id"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


# ============================================================
# PATCH 5: Update activate_code to return theme from merchant
# ============================================================
# Replace the existing activate_code function with this version
# that looks up the merchant's theme_json and includes it in the response.

def activate_code_v2(body: dict[str, Any]) -> dict[str, Any]:
    code = str(body.get("code", "")).strip().upper()
    install_id = str(body.get("installId", "")).strip()
    device_id = str(body.get("deviceId", "")).strip()
    if not code or not install_id:
        raise ActivationError("缺少授权码或安装 ID")

    hashed = code_hash(code)
    with connect() as conn:
        code_row = conn.execute("select * from codes where code_hash = ?", (hashed,)).fetchone()
        if not code_row:
            raise ActivationError("授权码不存在", 404)
        if code_row["disabled"]:
            raise ActivationError("授权码已停用", 403)
        existing = conn.execute("select * from activations where code_hash = ? and install_id = ?", (hashed, install_id)).fetchone()
        if existing:
            conn.execute("delete from activations where code_hash = ? and install_id = ?", (hashed, install_id))
        used_count = conn.execute("select count(*) as count from activations where code_hash = ?", (hashed,)).fetchone()["count"]
        if used_count >= code_row["max_activations"]:
            raise ActivationError("授权码已被其他设备激活", 403)
        payload = {
            "licenseId": secrets.token_hex(12),
            "licensee": code_row["licensee"],
            "edition": code_row["edition"],
            "features": json.loads(code_row["features_json"]),
            "expires": code_row["expires"],
            "installId": install_id,
            "deviceId": device_id,
            "activatedAt": utc_now(),
        }
        license_data = sign_license(payload)
        conn.execute(
            """
            insert into activations (code_hash, install_id, device_id, license_json, activated_at)
            values (?, ?, ?, ?, ?)
            """,
            (hashed, install_id, device_id, json.dumps(license_data, ensure_ascii=False), utc_now()),
        )
        conn.commit()

        result: dict[str, Any] = {"license": license_data}

        merchant_id = code_row["merchant_id"]
        if merchant_id:
            merchant_row = conn.execute("select * from merchants where merchant_id = ?", (merchant_id,)).fetchone()
            if merchant_row and merchant_row["theme_json"]:
                try:
                    theme = json.loads(merchant_row["theme_json"])
                    if isinstance(theme, dict):
                        theme["merchantId"] = merchant_id
                        result["theme"] = theme
                except json.JSONDecodeError:
                    pass

        return result


# ============================================================
# PATCH 6: Add merchant API routes to Handler.do_GET
# ============================================================
# Add these routes inside Handler.do_GET(), before the final 404:

# In do_GET, add before the final 404:
#     if path == "/admin/api/merchants":
#         if not self.require_admin():
#             return
#         self.send_json(200, {"merchants": get_merchant_rows()})
#         return

# In do_POST, add before the "if path != '/activate'" check:
#     if path == "/admin/api/merchants":
#         if not self.require_admin():
#             return
#         try:
#             body = self.read_json()
#             result = create_merchant(body)
#             self.send_json(200, result)
#         except Exception as error:
#             self.send_json(400, {"error": str(error)})
#         return
#     if path.startswith("/admin/api/merchants/"):
#         if not self.require_admin():
#             return
#         merchant_id = path.split("/")[-1]
#         try:
#             body = self.read_json()
#             result = update_merchant(merchant_id, body)
#             self.send_json(200, result)
#         except Exception as error:
#             self.send_json(400, {"error": str(error)})
#         return

# Also update the /activate POST handler to use activate_code_v2:
#     result = activate_code_v2(body)
#     self.send_json(200, result)

# And update /admin/api/codes POST to pass merchant_id:
#     merchant_id = body.get("merchantId") or None
#     codes = create_code_records_v2(
#         ...,
#         merchant_id=merchant_id,
#     )

# And update /admin/api/codes GET to use get_code_rows_v2:
#     self.send_json(200, {"codes": get_code_rows_v2()})
