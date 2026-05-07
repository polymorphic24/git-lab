from flask import (
    Flask,
    render_template,
    request,
    redirect,
    jsonify,
    session,
    send_file
)

import sqlite3
import pandas as pd

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

# ================= APP =================
app = Flask(__name__)
app.secret_key = "secret123"

# ================= DATABASE =================
def get_db():

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    db = get_db()

    # ================= USERS =================
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE,

        password TEXT,

        role TEXT

    )
    """)

    # DEFAULT ADMIN
    hashed = generate_password_hash("admin123")

    db.execute("""
    INSERT OR IGNORE INTO users (
        id,
        username,
        password,
        role
    )
    VALUES (
        1,
        'admin',
        ?,
        'admin'
    )
    """, (hashed,))

    # ================= PRODUCTS =================
    db.execute("""
    CREATE TABLE IF NOT EXISTS products (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        code TEXT UNIQUE,

        name TEXT,

        price INTEGER,

        stock INTEGER

    )
    """)

    # ================= TRANSACTIONS =================
    db.execute("""
    CREATE TABLE IF NOT EXISTS transactions (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        total INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )
    """)

    # ================= DETAIL TRANSAKSI =================
    db.execute("""
    CREATE TABLE IF NOT EXISTS transaction_items (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        transaction_id INTEGER,

        product_id INTEGER,

        qty INTEGER,

        price INTEGER

    )
    """)

    db.commit()

# ================= AUTH =================
def is_logged_in():

    return "user" in session


def is_admin():

    return session.get("role") == "admin"

# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        db = get_db()

        user = db.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user"] = user["username"]
            session["role"] = user["role"]

            return redirect("/")

        else:

            return "Login gagal"

    return render_template("login.html")

# ================= LOGOUT =================
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")

# ================= DASHBOARD =================
@app.route("/")
def index():

    if not is_logged_in():
        return redirect("/login")

    db = get_db()

    omzet = db.execute("""
        SELECT COALESCE(SUM(total),0) as total
        FROM transactions
        WHERE date(created_at)=date('now')
    """).fetchone()

    transaksi = db.execute("""
        SELECT COUNT(*) as jumlah
        FROM transactions
        WHERE date(created_at)=date('now')
    """).fetchone()

    produk = db.execute("""
        SELECT COUNT(*) as jumlah
        FROM products
    """).fetchone()

    return render_template(
        "index.html",
        omzet=omzet,
        transaksi=transaksi,
        produk=produk
    )

# ================= PRODUK =================
@app.route("/produk")
def produk():

    if not is_logged_in():
        return redirect("/login")

    if not is_admin():
        return "Akses ditolak"

    db = get_db()

    data = db.execute("""
        SELECT * FROM products
        ORDER BY id DESC
    """).fetchall()

    return render_template(
        "produk.html",
        products=data
    )

# ================= TAMBAH PRODUK =================
@app.route("/add_produk", methods=["POST"])
def add_produk():

    if not is_logged_in():
        return redirect("/login")

    code = request.form["code"]
    name = request.form["name"]

    price = int(request.form["price"])

    stock = int(request.form["stock"])

    db = get_db()

    existing = db.execute(
        "SELECT * FROM products WHERE code=?",
        (code,)
    ).fetchone()

    # UPDATE JIKA SUDAH ADA
    if existing:

        db.execute("""
            UPDATE products
            SET

                name=?,

                price=?,

                stock = stock + ?

            WHERE code=?
        """, (

            name,
            price,
            stock,
            code

        ))

    # INSERT BARU
    else:

        db.execute("""
            INSERT INTO products (

                code,
                name,
                price,
                stock

            )
            VALUES (?, ?, ?, ?)
        """, (

            code,
            name,
            price,
            stock

        ))

    db.commit()

    return redirect("/produk")

# ================= KASIR =================
@app.route("/kasir")
def kasir():

    if not is_logged_in():
        return redirect("/login")

    db = get_db()

    products = db.execute("""
        SELECT * FROM products
        ORDER BY name ASC
    """).fetchall()

    return render_template(
        "kasir.html",
        products=products
    )

# ================= TRANSAKSI =================
@app.route("/transaksi", methods=["POST"])
def transaksi():

    if not is_logged_in():
        return jsonify({
            "status": "unauthorized"
        }), 401

    data = request.json

    items = data["items"]

    db = get_db()

    total = 0

    # VALIDASI STOK + HITUNG TOTAL
    for item in items:

        product = db.execute(
            "SELECT * FROM products WHERE id=?",
            (item["id"],)
        ).fetchone()

        if product["stock"] < item["qty"]:

            return jsonify({
                "status": "stok tidak cukup"
            }), 400

        total += (
            product["price"] * item["qty"]
        )

    # SIMPAN TRANSAKSI
    cursor = db.execute(
        "INSERT INTO transactions (total) VALUES (?)",
        (total,)
    )

    transaction_id = cursor.lastrowid

    # DETAIL TRANSAKSI
    for item in items:

        product = db.execute(
            "SELECT * FROM products WHERE id=?",
            (item["id"],)
        ).fetchone()

        # SIMPAN ITEM
        db.execute("""
            INSERT INTO transaction_items (

                transaction_id,
                product_id,
                qty,
                price

            )
            VALUES (?, ?, ?, ?)
        """, (

            transaction_id,
            item["id"],
            item["qty"],
            product["price"]

        ))

        # UPDATE STOK
        db.execute("""
            UPDATE products
            SET stock = stock - ?
            WHERE id=?
        """, (

            item["qty"],
            item["id"]

        ))

    db.commit()

    return jsonify({

        "status": "success",

        "transaction_id": transaction_id

    })

# ================= STRUK =================
@app.route("/struk/<int:id>")
def struk(id):

    db = get_db()

    transaksi = db.execute(
        "SELECT * FROM transactions WHERE id=?",
        (id,)
    ).fetchone()

    items = db.execute("""
        SELECT

            ti.*,
            p.name

        FROM transaction_items ti

        JOIN products p
        ON ti.product_id = p.id

        WHERE ti.transaction_id=?
    """, (id,)).fetchall()

    return render_template(

        "struk.html",

        transaksi=transaksi,

        items=items

    )

# ================= LAPORAN =================
@app.route("/laporan")
def laporan():

    if not is_logged_in():
        return redirect("/login")

    start = request.args.get("start")
    end = request.args.get("end")

    db = get_db()

    # FILTER TANGGAL
    if start and end:

        transactions = db.execute("""
            SELECT *
            FROM transactions

            WHERE date(created_at)
            BETWEEN ? AND ?

            ORDER BY created_at DESC
        """, (

            start,
            end

        )).fetchall()

    else:

        transactions = db.execute("""
            SELECT *
            FROM transactions

            ORDER BY created_at DESC
        """).fetchall()

    return render_template(
        "laporan.html",
        transactions=transactions
    )

# ================= DETAIL TRANSAKSI =================
@app.route("/transaksi/<int:id>")
def detail_transaksi(id):

    if not is_logged_in():
        return redirect("/login")

    db = get_db()

    transaksi = db.execute(
        "SELECT * FROM transactions WHERE id=?",
        (id,)
    ).fetchone()

    items = db.execute("""
        SELECT

            ti.*,
            p.name

        FROM transaction_items ti

        JOIN products p
        ON ti.product_id = p.id

        WHERE ti.transaction_id=?
    """, (id,)).fetchall()

    return render_template(

        "detail_transaksi.html",

        transaksi=transaksi,

        items=items

    )

# ================= EXPORT EXCEL =================
@app.route("/export")
def export_excel():

    if not is_logged_in():
        return redirect("/login")

    db = get_db()

    data = db.execute("""
        SELECT *
        FROM transactions
        ORDER BY id DESC
    """).fetchall()

    df = pd.DataFrame(data)

    file_name = "laporan.xlsx"

    df.to_excel(
        file_name,
        index=False
    )

    return send_file(
        file_name,
        as_attachment=True
    )

# ================= RUN =================
if __name__ == "__main__":

    init_db()

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True

    )
