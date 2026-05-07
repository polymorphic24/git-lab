from flask import Flask, render_template, request, redirect, jsonify, session
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"

# ================= DB =================
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()

    # USERS
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    db.execute("""
    INSERT OR IGNORE INTO users (id, username, password)
    VALUES (1, 'admin', 'admin123')
    """)

    # PRODUCTS (PAKAI CODE)
    db.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        name TEXT,
        price INTEGER,
        stock INTEGER
    )
    """)

    # TRANSACTIONS
    db.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # DETAIL TRANSAKSI (INI YANG BARU)
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

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()

        if user:
            session["user"] = user["username"]
            return redirect("/")
        else:
            return "Login gagal"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

# ================= ROUTES =================
@app.route("/")
def index():
    if not is_logged_in():
        return redirect("/login")
    return render_template("index.html")

# ===== PRODUK =====
@app.route("/produk")
def produk():
    if not is_logged_in():
        return redirect("/login")

    db = get_db()
    data = db.execute("SELECT * FROM products").fetchall()
    return render_template("produk.html", products=data)

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

    if existing:
        db.execute("""
            UPDATE products
            SET name=?, price=?, stock = stock + ?
            WHERE code=?
        """, (name, price, stock, code))
    else:
        db.execute("""
            INSERT INTO products (code, name, price, stock)
            VALUES (?, ?, ?, ?)
        """, (code, name, price, stock))

    db.commit()
    return redirect("/produk")

# ===== KASIR =====
@app.route("/kasir")
def kasir():
    if not is_logged_in():
        return redirect("/login")

    db = get_db()
    products = db.execute("SELECT * FROM products").fetchall()
    return render_template("kasir.html", products=products)

@app.route("/transaksi", methods=["POST"])
def transaksi():
    if not is_logged_in():
        return jsonify({"status": "unauthorized"}), 401

    data = request.json
    items = data["items"]

    db = get_db()

    total = 0

    # validasi + hitung total
    for item in items:
        product = db.execute(
            "SELECT * FROM products WHERE id=?",
            (item["id"],)
        ).fetchone()

        if product["stock"] < item["qty"]:
            return jsonify({"status": "stok tidak cukup"}), 400

        total += product["price"] * item["qty"]

    # simpan transaksi
    cursor = db.execute(
        "INSERT INTO transactions (total) VALUES (?)",
        (total,)
    )
    transaction_id = cursor.lastrowid

    # simpan detail + update stok
    for item in items:
        product = db.execute(
            "SELECT * FROM products WHERE id=?",
            (item["id"],)
        ).fetchone()

        db.execute("""
            INSERT INTO transaction_items (transaction_id, product_id, qty, price)
            VALUES (?, ?, ?, ?)
        """, (transaction_id, item["id"], item["qty"], product["price"]))

        db.execute("""
            UPDATE products
            SET stock = stock - ?
            WHERE id=?
        """, (item["qty"], item["id"]))

    db.commit()

    return jsonify({"status": "success"})

# ===== LAPORAN =====
@app.route("/laporan")
def laporan():
    if not is_logged_in():
        return redirect("/login")

    start = request.args.get("start")
    end = request.args.get("end")

    db = get_db()

    if start and end:
        transactions = db.execute("""
            SELECT * FROM transactions
            WHERE date(created_at) BETWEEN ? AND ?
            ORDER BY created_at DESC
        """, (start, end)).fetchall()
    else:
        transactions = db.execute("""
            SELECT * FROM transactions
            ORDER BY created_at DESC
        """).fetchall()

    return render_template("laporan.html", transactions=transactions)

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
        SELECT ti.*, p.name 
        FROM transaction_items ti
        JOIN products p ON ti.product_id = p.id
        WHERE ti.transaction_id=?
    """, (id,)).fetchall()

    return render_template("detail_transaksi.html", transaksi=transaksi, items=items)

# ================= RUN =================
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
