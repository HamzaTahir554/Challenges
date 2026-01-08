import os
import sys
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

DB_NAME = "optics_pos.db"
APP_TITLE = "Noor Vision"  # Shop name
DATE_FMT = "%Y-%m-%d %H:%M:%S"

# Optional libraries
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    REPORTLAB_OK = True
except Exception:
    REPORTLAB_OK = False

try:
    from openpyxl import Workbook
    OPENPYXL_OK = True
except Exception:
    OPENPYXL_OK = False

try:
    import pywhatkit
    PYWHA_OK = True
except Exception:
    PYWHA_OK = False


# -------------------- UI THEME --------------------

def setup_theme(root: tk.Misc):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    base_font = ("Segoe UI", 10)
    heading_font = ("Segoe UI", 10, "bold")
    title_font = ("Segoe UI", 16, "bold")

    root.option_add("*Font", base_font)

    style.configure("TFrame", background="#f6f7fb")
    style.configure("TLabel", background="#f6f7fb")
    style.configure("TButton", padding=(10, 6))
    style.configure("TEntry", padding=5)
    style.configure("TCombobox", padding=5)
    style.configure("Title.TLabel", font=title_font, foreground="#1f2a44")
    style.configure("Section.TLabelframe", background="#f6f7fb", padding=10)
    style.configure("Section.TLabelframe.Label", font=heading_font, foreground="#1f2a44")

    style.configure(
        "Treeview",
        rowheight=26,
        font=base_font,
        background="#ffffff",
        fieldbackground="#ffffff",
    )
    style.configure(
        "Treeview.Heading",
        font=heading_font,
        background="#e8ecf7",
        foreground="#1f2a44",
    )
    style.map(
        "Treeview",
        background=[("selected", "#6d8cff")],
        foreground=[("selected", "#ffffff")],
    )


# -------------------- DATABASE --------------------

def db_connect():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def safe_add_column(conn, table, col_def):
    """Add column if it doesn't exist. col_def example: 'barcode TEXT'"""
    col_name = col_def.strip().split()[0]
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if col_name not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        conn.commit()


def init_db():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('Admin','Manager','Sales'))
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        shop_name TEXT,
        customer_type TEXT NOT NULL CHECK(customer_type IN ('Retail','Dealer')),
        total_due REAL NOT NULL DEFAULT 0
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_type TEXT NOT NULL CHECK(product_type IN ('Frame','Lens','Accessory')),
        name TEXT NOT NULL,
        price REAL NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0
    )''')

    # Add barcode if missing
    safe_add_column(conn, "products", "barcode TEXT")

    cur.execute('''CREATE TABLE IF NOT EXISTS sales (
        sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        total_amount REAL NOT NULL,
        paid_amount REAL NOT NULL,
        remaining_amount REAL NOT NULL,
        sale_date TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('Paid','Partially Paid','Unpaid')),
        notes TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS sale_items (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        unit_price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        line_total REAL NOT NULL,
        FOREIGN KEY(sale_id) REFERENCES sales(sale_id) ON DELETE CASCADE,
        FOREIGN KEY(product_id) REFERENCES products(product_id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS payments (
        payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER NOT NULL,
        payment_amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        payment_method TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY(sale_id) REFERENCES sales(sale_id) ON DELETE CASCADE
    )''')

    # Default admin
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)", ("admin", "admin", "Admin"))

    conn.commit()
    conn.close()


# -------------------- PERMISSIONS --------------------

def can(role: str, feature: str) -> bool:
    """feature: Customers, Products, Sales, Payments, Reports, Users"""
    perms = {
        "Admin": {"Customers", "Products", "Sales", "Payments", "Reports", "Users"},
        "Manager": {"Customers", "Products", "Reports"},
        "Sales": {"Customers", "Sales", "Payments"},
    }
    return feature in perms.get(role, set())


# -------------------- HELPERS --------------------

def now_str():
    return datetime.now().strftime(DATE_FMT)


def money(x):
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return str(x)


def ensure_float(s, default=0.0):
    try:
        return float(str(s).strip())
    except Exception:
        return default


def ensure_int(s, default=0):
    try:
        return int(float(str(s).strip()))
    except Exception:
        return default


def center_window(win: tk.Misc, width: int, height: int):
    win.update_idletasks()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


def insert_tree_row(tree: ttk.Treeview, values, index: int):
    tag = "even" if index % 2 == 0 else "odd"
    tree.insert("", "end", values=values, tags=(tag,))


# -------------------- INVOICE / REPORTS --------------------

def generate_invoice_pdf(sale_id: int, out_path: str | None = None) -> str:
    if not REPORTLAB_OK:
        raise RuntimeError("reportlab is not installed. Run: pip install reportlab")

    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT s.sale_id, s.sale_date, s.total_amount, s.paid_amount, s.remaining_amount, s.status,
               c.name, c.phone, c.shop_name, c.customer_type
        FROM sales s
        JOIN customers c ON c.customer_id = s.customer_id
        WHERE s.sale_id=?
    """, (sale_id,))
    sale = cur.fetchone()
    if not sale:
        conn.close()
        raise RuntimeError("Sale not found")

    cur.execute("""
        SELECT product_name, unit_price, quantity, line_total
        FROM sale_items WHERE sale_id=?
    """, (sale_id,))
    items = cur.fetchall()
    conn.close()

    (sid, sdate, total, paid, due, status, cname, phone, shop, ctype) = sale

    if not out_path:
        out_path = os.path.join(os.getcwd(), f"invoice_{sid}.pdf")

    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "INVOICE")

    c.setFont("Helvetica", 10)
    y -= 25
    c.drawString(40, y, f"Shop: {APP_TITLE}")
    y -= 15
    c.drawString(40, y, f"Invoice #: {sid}")
    y -= 15
    c.drawString(40, y, f"Date: {sdate}")

    y -= 25
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Customer")
    c.setFont("Helvetica", 10)
    y -= 15
    c.drawString(40, y, f"Name: {cname}")
    y -= 15
    c.drawString(40, y, f"Phone: {phone or ''}")
    y -= 15
    c.drawString(40, y, f"Shop: {shop or ''}")
    y -= 15
    c.drawString(40, y, f"Type: {ctype}")

    y -= 25
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Items")

    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Name")
    c.drawString(310, y, "Qty")
    c.drawString(360, y, "Unit")
    c.drawString(450, y, "Total")

    c.setFont("Helvetica", 10)
    y -= 12
    c.line(40, y, width - 40, y)
    y -= 15

    for (pname, unit, qty, ltot) in items:
        if y < 120:
            c.showPage()
            y = height - 60
        c.drawString(40, y, str(pname)[:45])
        c.drawRightString(340, y, str(qty))
        c.drawRightString(430, y, money(unit))
        c.drawRightString(width - 40, y, money(ltot))
        y -= 16

    y -= 10
    c.line(40, y, width - 40, y)

    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 40, y, f"Total: {money(total)}")
    y -= 18
    c.drawRightString(width - 40, y, f"Paid: {money(paid)}")
    y -= 18
    c.drawRightString(width - 40, y, f"Due: {money(due)}")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 40, y, f"Status: {status}")

    y -= 35
    c.setFont("Helvetica", 9)
    c.drawString(40, y, "Thank you for your business.")

    c.save()
    return out_path


def print_file_windows(path: str):
    # Uses default associated app printing (works for PDF via installed PDF reader)
    if sys.platform.startswith("win"):
        try:
            os.startfile(path, "print")
        except Exception as e:
            raise RuntimeError(f"Print failed: {e}")
    else:
        raise RuntimeError("Printing is currently supported via os.startfile on Windows.")


# -------------------- THERMAL ESC/POS PRINT (80mm) --------------------
# Windows RAW printing using pywin32
try:
    import win32print  # type: ignore
    WIN32_OK = True
except Exception:
    WIN32_OK = False

RECEIPT_PRINTER_NAME = ""  # optional: set printer name, else uses Windows default


def _get_default_printer_name():
    if not WIN32_OK:
        return None
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return None


def _load_sale_for_receipt(sale_id: int):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.sale_id, s.sale_date, s.total_amount, s.paid_amount, s.remaining_amount, s.status,
               c.name, c.phone, c.shop_name
        FROM sales s
        JOIN customers c ON c.customer_id = s.customer_id
        WHERE s.sale_id=?
        """,
        (sale_id,),
    )
    sale = cur.fetchone()
    if not sale:
        conn.close()
        raise RuntimeError("Sale not found")

    cur.execute(
        """
        SELECT product_name, unit_price, quantity, line_total
        FROM sale_items
        WHERE sale_id=?
        """,
        (sale_id,),
    )
    items = cur.fetchall()
    conn.close()
    return sale, items


def _fit_line(left: str, right: str, width: int) -> str:
    left = left or ""
    right = right or ""
    space = width - len(left) - len(right)
    if space < 1:
        left = left[: max(0, width - len(right) - 1)]
        space = width - len(left) - len(right)
        if space < 1:
            space = 1
    return left + (" " * space) + right


def build_receipt_text(sale_id: int, width: int = 42) -> str:
    sale, items = _load_sale_for_receipt(sale_id)
    (sid, sdate, total, paid, due, status, cname, phone, shop_name) = sale

    lines = []
    lines.append(APP_TITLE.center(width))
    lines.append(("Invoice #" + str(sid)).center(width))
    lines.append(str(sdate)[:19].center(width))
    lines.append("-" * width)
    lines.append(("Customer: " + str(cname))[:width])
    if phone:
        lines.append(("Phone: " + str(phone))[:width])
    if shop_name:
        lines.append(("Shop: " + str(shop_name))[:width])
    lines.append("-" * width)
    lines.append(_fit_line("ITEM", "AMT", width))
    lines.append("-" * width)

    for (pname, unit, qty, ltot) in items:
        nm = str(pname)
        lines.append(nm[:width])
        left = f"{qty} x {money(unit)}"
        right = money(ltot)
        lines.append(_fit_line(left, right, width))

    lines.append("-" * width)
    lines.append(_fit_line("TOTAL", money(total), width))
    lines.append(_fit_line("PAID", money(paid), width))
    lines.append(_fit_line("DUE", money(due), width))
    lines.append(_fit_line("STATUS", str(status), width))
    lines.append("-" * width)
    lines.append("Thank you!".center(width))
    lines.append("\n")
    return "\n".join(lines)


def make_escpos_bytes(text: str) -> bytes:
    init = b"\x1b@"          # Initialize
    align_left = b"\x1ba\x00"
    align_center = b"\x1ba\x01"
    bold_on = b"\x1bE\x01"
    bold_off = b"\x1bE\x00"
    cut = b"\x1dV\x01"       # Partial cut

    lines = text.splitlines()
    out = bytearray()
    out += init

    # Header
    if len(lines) >= 1:
        out += align_center + bold_on + (lines[0] + "\n").encode("utf-8", "replace") + bold_off
    if len(lines) >= 2:
        out += align_center + (lines[1] + "\n").encode("utf-8", "replace")
    if len(lines) >= 3:
        out += align_center + (lines[2] + "\n").encode("utf-8", "replace")

    out += align_left
    for i in range(3, len(lines)):
        out += (lines[i] + "\n").encode("utf-8", "replace")

    out += b"\n\n\n"  # feed
    out += cut
    return bytes(out)


def print_escpos_windows(raw_bytes: bytes, printer_name: str = ""):
    if not WIN32_OK:
        raise RuntimeError("pywin32 not installed. Run: pip install pywin32")

    p = (printer_name or RECEIPT_PRINTER_NAME).strip() or _get_default_printer_name()
    if not p:
        raise RuntimeError("No printer found. Set RECEIPT_PRINTER_NAME or install a printer.")

    hPrinter = win32print.OpenPrinter(p)
    try:
        doc_info = (f"{APP_TITLE} Receipt", None, "RAW")
        _ = win32print.StartDocPrinter(hPrinter, 1, doc_info)
        try:
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, raw_bytes)
            win32print.EndPagePrinter(hPrinter)
        finally:
            win32print.EndDocPrinter(hPrinter)
    finally:
        win32print.ClosePrinter(hPrinter)


def thermal_print_sale(sale_id: int):
    text = build_receipt_text(sale_id, width=42)
    raw = make_escpos_bytes(text)
    print_escpos_windows(raw)


def export_due_report_excel(out_path: str):
    if not OPENPYXL_OK:
        raise RuntimeError("openpyxl is not installed. Run: pip install openpyxl")

    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT customer_id, name, phone, shop_name, customer_type, total_due FROM customers ORDER BY total_due DESC")
    rows = cur.fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Customer Due"
    ws.append(["Customer ID", "Name", "Phone", "Shop", "Type", "Total Due"])
    for r in rows:
        ws.append(list(r))
    wb.save(out_path)


def export_due_report_pdf(out_path: str):
    if not REPORTLAB_OK:
        raise RuntimeError("reportlab is not installed. Run: pip install reportlab")

    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT customer_id, name, phone, shop_name, customer_type, total_due FROM customers ORDER BY total_due DESC")
    rows = cur.fetchall()
    conn.close()

    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Customer Due Report")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Generated: {now_str()}")

    y -= 25
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "ID")
    c.drawString(70, y, "Name")
    c.drawString(240, y, "Phone")
    c.drawString(320, y, "Shop")
    c.drawString(450, y, "Type")
    c.drawRightString(width - 40, y, "Due")

    y -= 10
    c.line(40, y, width - 40, y)
    y -= 15
    c.setFont("Helvetica", 9)

    for (cid, name, phone, shop, ctype, due) in rows:
        if y < 60:
            c.showPage()
            y = height - 60
            c.setFont("Helvetica", 9)
        c.drawString(40, y, str(cid))
        c.drawString(70, y, str(name)[:28])
        c.drawString(240, y, str(phone or "")[:15])
        c.drawString(320, y, str(shop or "")[:20])
        c.drawString(450, y, str(ctype))
        c.drawRightString(width - 40, y, money(due))
        y -= 14

    c.save()


def send_whatsapp_reminder(phone_pk: str, message: str):
    """phone_pk should be like 3XXXXXXXXX (without +92) or full with country.
    pywhatkit uses WhatsApp Web. Must be logged in.
    """
    if not PYWHA_OK:
        raise RuntimeError("pywhatkit not installed. Run: pip install pywhatkit")
    phone = str(phone_pk).strip()
    if phone.startswith("+"):
        full = phone
    else:
        # Pakistan default
        full = "+92" + phone.lstrip("0")
    pywhatkit.sendwhatmsg_instantly(full, message, wait_time=10, tab_close=True)


# -------------------- UI COMPONENTS --------------------

class Login(tk.Tk):
    def __init__(self):
        super().__init__()
        setup_theme(self)
        self.title(f"{APP_TITLE} - Login")
        center_window(self, 380, 260)
        self.resizable(False, False)

        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=APP_TITLE, style="Title.TLabel").pack(pady=(0, 10))
        ttk.Label(frm, text="Sign in to continue", foreground="#5a647a").pack(pady=(0, 14))

        ttk.Label(frm, text="Username").pack(anchor="w")
        self.username = ttk.Entry(frm)
        self.username.pack(fill="x")

        ttk.Label(frm, text="Password").pack(anchor="w", pady=(12, 0))
        self.password = ttk.Entry(frm, show="*")
        self.password.pack(fill="x")

        ttk.Button(frm, text="Login", command=self.do_login).pack(pady=16, fill="x")

        ttk.Label(frm, text="Default: admin / admin", foreground="#6b7280").pack()

        self.bind("<Return>", lambda e: self.do_login())
        self.username.focus_set()

    def do_login(self):
        u = self.username.get().strip()
        p = self.password.get().strip()
        if not u or not p:
            messagebox.showwarning("Missing", "Enter username and password")
            return

        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT user_id, role FROM users WHERE username=? AND password=?", (u, p))
        row = cur.fetchone()
        conn.close()

        if row:
            user_id, role = row
            self.destroy()
            App(user_id=user_id, username=u, role=role).mainloop()
        else:
            messagebox.showerror("Login Failed", "Invalid credentials")


class App(tk.Tk):
    def __init__(self, user_id: int, username: str, role: str):
        super().__init__()
        setup_theme(self)
        self.user_id = user_id
        self.username = username
        self.role = role

        self.title(APP_TITLE)
        self.geometry("1180x700")

        top = ttk.Frame(self, padding=(16, 10))
        top.pack(fill="x")
        ttk.Label(top, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Label(top, text=f"User: {username}   Role: {role}", foreground="#4b5563").pack(side="right")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Tabs based on role
        if can(role, "Customers"):
            self.customers_tab = CustomersTab(self.tabs)
            self.tabs.add(self.customers_tab, text="Customers")
        if can(role, "Products"):
            self.products_tab = ProductsTab(self.tabs)
            self.tabs.add(self.products_tab, text="Products")
        if can(role, "Sales"):
            self.sales_tab = SalesTab(self.tabs)
            self.tabs.add(self.sales_tab, text="Sales")
        if can(role, "Payments"):
            self.payments_tab = PaymentsTab(self.tabs)
            self.tabs.add(self.payments_tab, text="Payments")
        if can(role, "Reports"):
            self.reports_tab = ReportsTab(self.tabs)
            self.tabs.add(self.reports_tab, text="Reports")
        if can(role, "Users"):
            self.users_tab = UsersTab(self.tabs)
            self.tabs.add(self.users_tab, text="Users")

        bottom = ttk.Frame(self, padding=(16, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Refresh All", command=self.refresh_all).pack(side="left")
        ttk.Button(bottom, text="Exit", command=self.destroy).pack(side="right")

    def refresh_all(self):
        for child in self.tabs.winfo_children():
            if hasattr(child, "load"):
                child.load()


class CustomersTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._build()
        self.load()

    def _build(self):
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill="x")
        ttk.Button(bar, text="Add Customer", command=self.add_customer).pack(side="left")
        ttk.Button(bar, text="Edit Selected", command=self.edit_customer).pack(side="left", padx=6)
        ttk.Button(bar, text="Delete Selected", command=self.delete_customer).pack(side="left")

        ttk.Label(bar, text="Search:").pack(side="left", padx=(20, 6))
        self.search_var = tk.StringVar()
        s = ttk.Entry(bar, textvariable=self.search_var)
        s.pack(side="left", fill="x", expand=True)
        s.bind("<KeyRelease>", lambda e: self.load())

        cols = ("ID", "Name", "Phone", "Shop", "Type", "Due")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=20)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=120 if c != "Shop" else 240)
        self.tree.column("ID", width=70)
        self.tree.column("Due", width=120, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree.tag_configure("even", background="#f4f6fc")
        self.tree.tag_configure("odd", background="#ffffff")

    def load(self):
        q = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        for i in self.tree.get_children():
            self.tree.delete(i)
        conn = db_connect()
        cur = conn.cursor()
        if q:
            cur.execute("""
                SELECT customer_id, name, phone, shop_name, customer_type, total_due
                FROM customers
                WHERE lower(name) LIKE ? OR lower(shop_name) LIKE ? OR phone LIKE ?
                ORDER BY customer_id DESC
            """, (f"%{q}%", f"%{q}%", f"%{q}%"))
        else:
            cur.execute("SELECT customer_id, name, phone, shop_name, customer_type, total_due FROM customers ORDER BY customer_id DESC")
        rows = cur.fetchall()
        conn.close()
        for idx, r in enumerate(rows):
            insert_tree_row(
                self.tree,
                (r[0], r[1], r[2] or "", r[3] or "", r[4], money(r[5])),
                idx,
            )

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def add_customer(self):
        CustomerForm(self, title="Add Customer")

    def edit_customer(self):
        cid = self._selected_id()
        if not cid:
            messagebox.showinfo("Select", "Select a customer")
            return
        CustomerForm(self, title="Edit Customer", customer_id=cid)

    def delete_customer(self):
        cid = self._selected_id()
        if not cid:
            messagebox.showinfo("Select", "Select a customer")
            return
        if not messagebox.askyesno("Confirm", "Delete this customer? (Only if no sales linked)"):
            return
        try:
            conn = db_connect()
            cur = conn.cursor()
            cur.execute("DELETE FROM customers WHERE customer_id=?", (cid,))
            conn.commit()
            conn.close()
            self.load()
        except Exception as e:
            messagebox.showerror("Error", str(e))


class CustomerForm(tk.Toplevel):
    def __init__(self, parent: CustomersTab, title: str, customer_id: int | None = None):
        super().__init__(parent)
        setup_theme(self)
        self.parent = parent
        self.customer_id = customer_id
        self.title(title)
        center_window(self, 440, 340)
        self.resizable(False, False)

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        self.name = tk.StringVar()
        self.phone = tk.StringVar()
        self.shop = tk.StringVar()
        self.ctype = tk.StringVar(value="Dealer")

        for label, var in [
            ("Name", self.name),
            ("Phone", self.phone),
            ("Shop Name", self.shop),
        ]:
            ttk.Label(frm, text=label).pack(anchor="w")
            ttk.Entry(frm, textvariable=var).pack(fill="x", pady=(0, 10))

        ttk.Label(frm, text="Customer Type").pack(anchor="w")
        ttk.Combobox(frm, textvariable=self.ctype, values=["Dealer", "Retail"], state="readonly").pack(fill="x", pady=(0, 10))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=10)
        ttk.Button(btns, text="Save", command=self.save).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=8, expand=True, fill="x")

        if customer_id:
            self._load_existing()

    def _load_existing(self):
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT name, phone, shop_name, customer_type FROM customers WHERE customer_id=?", (self.customer_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            self.name.set(row[0])
            self.phone.set(row[1] or "")
            self.shop.set(row[2] or "")
            self.ctype.set(row[3])

    def save(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Name is required")
            return
        phone = self.phone.get().strip()
        shop = self.shop.get().strip()
        ctype = self.ctype.get().strip() or "Dealer"

        conn = db_connect()
        cur = conn.cursor()
        if self.customer_id:
            cur.execute("UPDATE customers SET name=?, phone=?, shop_name=?, customer_type=? WHERE customer_id=?",
                        (name, phone, shop, ctype, self.customer_id))
        else:
            cur.execute("INSERT INTO customers (name, phone, shop_name, customer_type) VALUES (?,?,?,?)",
                        (name, phone, shop, ctype))
        conn.commit()
        conn.close()
        self.parent.load()
        self.destroy()


class ProductsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._build()
        self.load()

    def _build(self):
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill="x")
        ttk.Button(bar, text="Add Product", command=self.add_product).pack(side="left")
        ttk.Button(bar, text="Edit Selected", command=self.edit_product).pack(side="left", padx=6)
        ttk.Button(bar, text="Delete Selected", command=self.delete_product).pack(side="left")

        ttk.Label(bar, text="Search:").pack(side="left", padx=(20, 6))
        self.search_var = tk.StringVar()
        s = ttk.Entry(bar, textvariable=self.search_var)
        s.pack(side="left", fill="x", expand=True)
        s.bind("<KeyRelease>", lambda e: self.load())

        cols = ("ID", "Type", "Name", "Barcode", "Price", "Stock")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=20)
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("ID", width=70)
        self.tree.column("Type", width=90)
        self.tree.column("Name", width=340)
        self.tree.column("Barcode", width=180)
        self.tree.column("Price", width=110, anchor="e")
        self.tree.column("Stock", width=90, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree.tag_configure("even", background="#f4f6fc")
        self.tree.tag_configure("odd", background="#ffffff")

    def load(self):
        q = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        for i in self.tree.get_children():
            self.tree.delete(i)
        conn = db_connect()
        cur = conn.cursor()
        if q:
            cur.execute("""
                SELECT product_id, product_type, name, barcode, price, stock
                FROM products
                WHERE lower(name) LIKE ? OR barcode LIKE ? OR CAST(product_id AS TEXT) LIKE ?
                ORDER BY product_id DESC
            """, (f"%{q}%", f"%{q}%", f"%{q}%"))
        else:
            cur.execute("SELECT product_id, product_type, name, barcode, price, stock FROM products ORDER BY product_id DESC")
        rows = cur.fetchall()
        conn.close()
        for idx, r in enumerate(rows):
            insert_tree_row(
                self.tree,
                (r[0], r[1], r[2], r[3] or "", money(r[4]), r[5]),
                idx,
            )

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def add_product(self):
        ProductForm(self, title="Add Product")

    def edit_product(self):
        pid = self._selected_id()
        if not pid:
            messagebox.showinfo("Select", "Select a product")
            return
        ProductForm(self, title="Edit Product", product_id=pid)

    def delete_product(self):
        pid = self._selected_id()
        if not pid:
            messagebox.showinfo("Select", "Select a product")
            return
        if not messagebox.askyesno("Confirm", "Delete this product? (Only if not used in sales)"):
            return
        try:
            conn = db_connect()
            cur = conn.cursor()
            cur.execute("DELETE FROM products WHERE product_id=?", (pid,))
            conn.commit()
            conn.close()
            self.load()
        except Exception as e:
            messagebox.showerror("Error", str(e))


class ProductForm(tk.Toplevel):
    def __init__(self, parent: ProductsTab, title: str, product_id: int | None = None):
        super().__init__(parent)
        setup_theme(self)
        self.parent = parent
        self.product_id = product_id
        self.title(title)
        center_window(self, 470, 430)
        self.resizable(False, False)

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        self.ptype = tk.StringVar(value="Frame")
        self.name = tk.StringVar()
        self.barcode = tk.StringVar()
        self.price = tk.StringVar(value="0")
        self.stock = tk.StringVar(value="0")

        ttk.Label(frm, text="Product Type").pack(anchor="w")
        ttk.Combobox(frm, textvariable=self.ptype, values=["Frame", "Lens", "Accessory"], state="readonly").pack(fill="x", pady=(0, 10))

        ttk.Label(frm, text="Name").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.name).pack(fill="x", pady=(0, 10))

        ttk.Label(frm, text="Barcode (optional)").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.barcode).pack(fill="x", pady=(0, 10))

        ttk.Label(frm, text="Wholesale Price").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.price).pack(fill="x", pady=(0, 10))

        ttk.Label(frm, text="Stock Quantity").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.stock).pack(fill="x", pady=(0, 10))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=10)
        ttk.Button(btns, text="Save", command=self.save).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=8, expand=True, fill="x")

        if product_id:
            self._load_existing()

    def _load_existing(self):
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT product_type, name, barcode, price, stock FROM products WHERE product_id=?", (self.product_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            self.ptype.set(row[0])
            self.name.set(row[1])
            self.barcode.set(row[2] or "")
            self.price.set(str(row[3]))
            self.stock.set(str(row[4]))

    def save(self):
        ptype = self.ptype.get().strip()
        name = self.name.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Product name is required")
            return
        barcode = self.barcode.get().strip() or None
        price = ensure_float(self.price.get(), 0.0)
        stock = ensure_int(self.stock.get(), 0)

        conn = db_connect()
        cur = conn.cursor()
        if self.product_id:
            cur.execute("UPDATE products SET product_type=?, name=?, barcode=?, price=?, stock=? WHERE product_id=?",
                        (ptype, name, barcode, price, stock, self.product_id))
        else:
            cur.execute("INSERT INTO products (product_type, name, barcode, price, stock) VALUES (?,?,?,?,?)",
                        (ptype, name, barcode, price, stock))
        conn.commit()
        conn.close()
        self.parent.load()
        self.destroy()


class ProductSearchDialog(tk.Toplevel):
    def __init__(self, parent, on_add):
        super().__init__(parent)
        setup_theme(self)
        self.title("Find Product")
        center_window(self, 720, 420)
        self.resizable(False, False)
        self.on_add = on_add

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Search by name, ID, or barcode").pack(anchor="w")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.search_var)
        entry.pack(fill="x", pady=(4, 10))
        entry.bind("<KeyRelease>", lambda e: self.load())

        cols = ("ID", "Name", "Barcode", "Price", "Stock")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("ID", width=70)
        self.tree.column("Name", width=280)
        self.tree.column("Barcode", width=150)
        self.tree.column("Price", width=90, anchor="e")
        self.tree.column("Stock", width=80, anchor="e")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("even", background="#f4f6fc")
        self.tree.tag_configure("odd", background="#ffffff")

        qty_frame = ttk.Frame(frame)
        qty_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(qty_frame, text="Qty").pack(side="left")
        self.qty_var = tk.StringVar(value="1")
        qty_entry = ttk.Entry(qty_frame, textvariable=self.qty_var, width=8)
        qty_entry.pack(side="left", padx=(6, 12))

        ttk.Button(qty_frame, text="Add Selected", command=self.add_selected).pack(side="left")
        ttk.Button(qty_frame, text="Close", command=self.destroy).pack(side="right")

        entry.focus_set()
        self.load()

    def load(self):
        q = self.search_var.get().strip().lower()
        for i in self.tree.get_children():
            self.tree.delete(i)

        conn = db_connect()
        cur = conn.cursor()
        if q:
            cur.execute("""
                SELECT product_id, name, barcode, price, stock
                FROM products
                WHERE lower(name) LIKE ? OR barcode LIKE ? OR CAST(product_id AS TEXT) LIKE ?
                ORDER BY product_id DESC
            """, (f"%{q}%", f"%{q}%", f"%{q}%"))
        else:
            cur.execute("SELECT product_id, name, barcode, price, stock FROM products ORDER BY product_id DESC")
        rows = cur.fetchall()
        conn.close()

        for idx, r in enumerate(rows):
            insert_tree_row(self.tree, (r[0], r[1], r[2] or "", money(r[3]), r[4]), idx)

    def add_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a product to add")
            return
        pid = int(self.tree.item(sel[0], "values")[0])
        qty = ensure_int(self.qty_var.get(), 1)
        if qty <= 0:
            qty = 1
        self.on_add(pid, qty)
        self.destroy()


class SalesTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.cart = []  # dicts: {product_id,name,barcode,unit_price,qty,line_total}
        self._build()
        self.load()

    def _build(self):
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)

        # Left: sales list
        left = ttk.Frame(outer, padding=10)
        left.pack(side="left", fill="both", expand=True)

        bar = ttk.Frame(left)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="New Sale (Invoice)", command=self.new_sale).pack(side="left")
        ttk.Button(bar, text="View/Print Invoice", command=self.print_invoice).pack(side="left", padx=6)
        ttk.Button(bar, text="Thermal Print (80mm)", command=self.print_thermal).pack(side="left", padx=6)

        ttk.Label(bar, text="Search Sale ID / Customer:").pack(side="left", padx=(20, 6))
        self.search_var = tk.StringVar()
        s = ttk.Entry(bar, textvariable=self.search_var)
        s.pack(side="left", fill="x", expand=True)
        s.bind("<KeyRelease>", lambda e: self.load())

        cols = ("SaleID", "Customer", "Total", "Paid", "Due", "Status", "Date")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=20)
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("SaleID", width=70)
        self.tree.column("Customer", width=240)
        self.tree.column("Total", width=100, anchor="e")
        self.tree.column("Paid", width=100, anchor="e")
        self.tree.column("Due", width=100, anchor="e")
        self.tree.column("Status", width=120)
        self.tree.column("Date", width=160)
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("even", background="#f4f6fc")
        self.tree.tag_configure("odd", background="#ffffff")

        # Right: quick info
        right = ttk.Frame(outer, padding=10)
        right.pack(side="right", fill="y")
        ttk.Label(right, text="Tips", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            right,
            text=(
                "• Barcode scanner works like keyboard\n"
                "• Scan or search in invoice window\n"
                "• Stock auto-deducts on finalize\n"
                "• Print invoice as PDF / Thermal"
            ),
            justify="left",
        ).pack(anchor="w", pady=6)

    def load(self):
        q = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        for i in self.tree.get_children():
            self.tree.delete(i)

        conn = db_connect()
        cur = conn.cursor()
        if q:
            cur.execute("""
                SELECT s.sale_id, c.name, s.total_amount, s.paid_amount, s.remaining_amount, s.status, s.sale_date
                FROM sales s
                JOIN customers c ON c.customer_id = s.customer_id
                WHERE CAST(s.sale_id AS TEXT) LIKE ? OR lower(c.name) LIKE ?
                ORDER BY s.sale_id DESC
            """, (f"%{q}%", f"%{q}%"))
        else:
            cur.execute("""
                SELECT s.sale_id, c.name, s.total_amount, s.paid_amount, s.remaining_amount, s.status, s.sale_date
                FROM sales s
                JOIN customers c ON c.customer_id = s.customer_id
                ORDER BY s.sale_id DESC
            """)
        rows = cur.fetchall()
        conn.close()

        for idx, r in enumerate(rows):
            insert_tree_row(
                self.tree,
                (r[0], r[1], money(r[2]), money(r[3]), money(r[4]), r[5], r[6]),
                idx,
            )

    def _selected_sale_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def new_sale(self):
        SaleInvoiceWindow(self, on_saved=self._on_sale_saved)

    def _on_sale_saved(self):
        self.load()

    def print_invoice(self):
        sid = self._selected_sale_id()
        if not sid:
            messagebox.showinfo("Select", "Select a sale")
            return
        if not REPORTLAB_OK:
            messagebox.showerror(
                "Missing library",
                "Install reportlab first:\n\npip install reportlab",
            )
            return
        try:
            pdf = generate_invoice_pdf(sid)
            if messagebox.askyesno(
                "Invoice",
                f"Invoice generated:\n{pdf}\n\nPrint now?",
            ):
                print_file_windows(pdf)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def print_thermal(self):
        sid = self._selected_sale_id()
        if not sid:
            messagebox.showinfo("Select", "Select a sale")
            return
        try:
            thermal_print_sale(sid)
            messagebox.showinfo("Printed", "Thermal receipt printed successfully.")
        except Exception as e:
            messagebox.showerror("Thermal Print Error", str(e))


class SaleInvoiceWindow(tk.Toplevel):
    def __init__(self, parent: SalesTab, on_saved=None):
        super().__init__(parent)
        setup_theme(self)
        self.parent = parent
        self.on_saved = on_saved
        self.title("New Sale / Invoice")
        self.geometry("1020x660")

        self.cart = []

        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")

        ttk.Label(top, text="Customer").grid(row=0, column=0, sticky="w")
        self.customer_var = tk.StringVar()
        self.customer_cb = ttk.Combobox(top, textvariable=self.customer_var, state="readonly", width=45)
        self.customer_cb.grid(row=0, column=1, padx=8, sticky="w")

        ttk.Button(top, text="Refresh", command=self._load_customers).grid(row=0, column=2)

        ttk.Label(top, text="Scan Barcode / Enter Product ID").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.scan_var = tk.StringVar()
        scan_entry = ttk.Entry(top, textvariable=self.scan_var, width=45)
        scan_entry.grid(row=1, column=1, padx=8, sticky="w", pady=(10, 0))
        scan_entry.bind("<Return>", lambda e: self.add_by_scan())

        ttk.Label(top, text="Qty").grid(row=1, column=2, sticky="w", pady=(10, 0))
        self.qty_var = tk.StringVar(value="1")
        qty_entry = ttk.Entry(top, textvariable=self.qty_var, width=8)
        qty_entry.grid(row=1, column=3, sticky="w", pady=(10, 0))
        qty_entry.bind("<Return>", lambda e: self.add_by_scan())

        ttk.Button(top, text="Add Item", command=self.add_by_scan).grid(row=1, column=4, padx=8, pady=(10, 0))
        ttk.Button(top, text="Find Product", command=self.open_product_search).grid(row=1, column=5, padx=4, pady=(10, 0))

        ttk.Label(top, text="Note (optional)").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.note_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.note_var, width=70).grid(row=2, column=1, columnspan=5, padx=8, sticky="w", pady=(10, 0))

        # Cart
        mid = ttk.Frame(self, padding=12)
        mid.pack(fill="both", expand=True)

        cols = ("ProductID", "Name", "Barcode", "UnitPrice", "Qty", "LineTotal")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=16)
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("ProductID", width=90)
        self.tree.column("Name", width=360)
        self.tree.column("Barcode", width=160)
        self.tree.column("UnitPrice", width=110, anchor="e")
        self.tree.column("Qty", width=70, anchor="e")
        self.tree.column("LineTotal", width=120, anchor="e")
        self.tree.pack(fill="both", expand=True, side="left")
        self.tree.tag_configure("even", background="#f4f6fc")
        self.tree.tag_configure("odd", background="#ffffff")

        side = ttk.Frame(mid)
        side.pack(fill="y", side="right", padx=(10, 0))
        ttk.Button(side, text="Remove Selected", command=self.remove_selected).pack(fill="x")
        ttk.Button(side, text="Clear Cart", command=self.clear_cart).pack(fill="x", pady=6)

        ttk.Separator(side, orient="horizontal").pack(fill="x", pady=10)

        self.total_var = tk.StringVar(value="0")
        self.paid_var = tk.StringVar(value="0")
        self.due_var = tk.StringVar(value="0")

        ttk.Label(side, text="Total", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(side, textvariable=self.total_var, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))

        ttk.Label(side, text="Advance Paid").pack(anchor="w")
        paid_entry = ttk.Entry(side, textvariable=self.paid_var)
        paid_entry.pack(fill="x")
        paid_entry.bind("<KeyRelease>", lambda e: self.recalc())

        ttk.Label(side, text="Due", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
        ttk.Label(side, textvariable=self.due_var, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))

        ttk.Label(side, text="Payment Method").pack(anchor="w")
        self.pay_method = tk.StringVar(value="Cash")
        ttk.Combobox(side, textvariable=self.pay_method, values=["Cash", "Bank", "Online"], state="readonly").pack(fill="x")

        ttk.Separator(side, orient="horizontal").pack(fill="x", pady=10)

        ttk.Button(side, text="Finalize Sale", command=self.finalize_sale).pack(fill="x", pady=(0, 6))
        ttk.Button(side, text="Finalize + Print", command=lambda: self.finalize_sale(print_after=True)).pack(fill="x")

        self._load_customers()
        scan_entry.focus_set()

    def _load_customers(self):
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT customer_id, name, shop_name, customer_type FROM customers ORDER BY name")
        rows = cur.fetchall()
        conn.close()
        self.customer_map = {}
        values = []
        for (cid, name, shop, ctype) in rows:
            label = f"{cid} - {name} ({shop or ''} {ctype})"
            values.append(label)
            self.customer_map[label] = cid
        self.customer_cb["values"] = values
        if values and not self.customer_var.get():
            self.customer_var.set(values[0])

    def open_product_search(self):
        ProductSearchDialog(self, on_add=self.add_product_by_id)

    def add_product_by_id(self, product_id: int, qty: int):
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT product_id, name, barcode, price, stock FROM products WHERE product_id=?", (product_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            messagebox.showwarning("Not found", "Product not found")
            return

        pid, name, barcode, price, stock = row
        if stock < qty:
            messagebox.showwarning("Low Stock", f"Not enough stock. Available: {stock}")
            return
        self._add_to_cart(pid, name, barcode or "", float(price), qty, stock)

    def add_by_scan(self):
        code = self.scan_var.get().strip()
        qty = ensure_int(self.qty_var.get(), 1)
        if qty <= 0:
            qty = 1

        if not code:
            return

        conn = db_connect()
        cur = conn.cursor()

        # Try barcode first
        cur.execute("SELECT product_id, name, barcode, price, stock FROM products WHERE barcode=?", (code,))
        row = cur.fetchone()

        # If not found, try product_id
        if not row and code.isdigit():
            cur.execute("SELECT product_id, name, barcode, price, stock FROM products WHERE product_id=?", (int(code),))
            row = cur.fetchone()

        conn.close()

        if not row:
            messagebox.showwarning("Not found", "Product not found (barcode/product id)")
            return

        pid, name, barcode, price, stock = row
        if stock < qty:
            messagebox.showwarning("Low Stock", f"Not enough stock. Available: {stock}")
            return
        self._add_to_cart(pid, name, barcode or "", float(price), qty, stock)
        self.scan_var.set("")
        self.qty_var.set("1")

    def _add_to_cart(self, pid: int, name: str, barcode: str, price: float, qty: int, stock: int):
        # If already in cart, increase qty
        for item in self.cart:
            if item["product_id"] == pid:
                new_qty = item["qty"] + qty
                if stock < new_qty:
                    messagebox.showwarning("Low Stock", f"Not enough stock. Available: {stock}")
                    return
                item["qty"] = new_qty
                item["line_total"] = item["qty"] * item["unit_price"]
                self.refresh_cart()
                return

        self.cart.append({
            "product_id": pid,
            "name": name,
            "barcode": barcode,
            "unit_price": price,
            "qty": qty,
            "line_total": price * qty,
        })

        self.refresh_cart()

    def refresh_cart(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for idx, item in enumerate(self.cart):
            insert_tree_row(
                self.tree,
                (item["product_id"], item["name"], item["barcode"], money(item["unit_price"]), item["qty"], money(item["line_total"])),
                idx,
            )
        self.recalc()

    def recalc(self):
        total = sum(i["line_total"] for i in self.cart)
        paid = ensure_float(self.paid_var.get(), 0.0)
        if paid < 0:
            paid = 0
        if paid > total:
            paid = total
            self.paid_var.set(str(total))
        due = total - paid
        self.total_var.set(money(total))
        self.due_var.set(money(due))

    def remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        pid = int(self.tree.item(sel[0], "values")[0])
        self.cart = [x for x in self.cart if x["product_id"] != pid]
        self.refresh_cart()

    def clear_cart(self):
        self.cart = []
        self.refresh_cart()

    def finalize_sale(self, print_after=False):
        if not self.cart:
            messagebox.showwarning("Empty", "Add at least one item")
            return

        cust_label = self.customer_var.get().strip()
        if not cust_label or cust_label not in self.customer_map:
            messagebox.showwarning("Customer", "Select a customer")
            return
        customer_id = self.customer_map[cust_label]

        total = sum(i["line_total"] for i in self.cart)
        paid = ensure_float(self.paid_var.get(), 0.0)
        if paid < 0:
            paid = 0
        if paid > total:
            paid = total
        due = total - paid

        status = "Paid" if due == 0 else ("Unpaid" if paid == 0 else "Partially Paid")
        note = self.note_var.get().strip() or None

        # Save transaction (with stock deduction)
        conn = db_connect()
        cur = conn.cursor()
        try:
            # Validate stock again (avoid race)
            for it in self.cart:
                cur.execute("SELECT stock FROM products WHERE product_id=?", (it["product_id"],))
                st = cur.fetchone()[0]
                if st < it["qty"]:
                    raise RuntimeError(f"Low stock for {it['name']}. Available: {st}")

            cur.execute("""
                INSERT INTO sales (customer_id,total_amount,paid_amount,remaining_amount,sale_date,status,notes)
                VALUES (?,?,?,?,?,?,?)
            """, (customer_id, total, paid, due, now_str(), status, note))
            sale_id = cur.lastrowid

            # Insert items + deduct stock
            for it in self.cart:
                cur.execute("""
                    INSERT INTO sale_items (sale_id,product_id,product_name,unit_price,quantity,line_total)
                    VALUES (?,?,?,?,?,?)
                """, (sale_id, it["product_id"], it["name"], it["unit_price"], it["qty"], it["line_total"]))
                cur.execute("UPDATE products SET stock = stock - ? WHERE product_id=?", (it["qty"], it["product_id"]))

            # Update customer due
            cur.execute("UPDATE customers SET total_due = total_due + ? WHERE customer_id=?", (due, customer_id))

            # If paid > 0, store payment row
            if paid > 0:
                cur.execute("""
                    INSERT INTO payments (sale_id,payment_amount,payment_date,payment_method,note)
                    VALUES (?,?,?,?,?)
                """, (sale_id, paid, now_str(), self.pay_method.get(), "Advance"))

            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            messagebox.showerror("Error", str(e))
            return
        conn.close()

        # Generate invoice PDF
        pdf_path = None
        if REPORTLAB_OK:
            try:
                pdf_path = generate_invoice_pdf(sale_id)
            except Exception:
                pdf_path = None

        messagebox.showinfo("Saved", f"Sale saved. Invoice #: {sale_id}")

        if self.on_saved:
            self.on_saved()

        if print_after:
            if not REPORTLAB_OK:
                messagebox.showwarning("Missing", "Install reportlab for PDF invoice printing")
            elif pdf_path:
                try:
                    print_file_windows(pdf_path)
                except Exception as e:
                    messagebox.showerror("Print Error", str(e))

        self.destroy()


class PaymentsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._build()
        self.load()

    def _build(self):
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill="x")

        ttk.Button(bar, text="Receive Payment", command=self.add_payment).pack(side="left")
        ttk.Button(bar, text="View Payment History", command=self.view_history).pack(side="left", padx=6)

        ttk.Label(bar, text="Search Sale ID / Customer:").pack(side="left", padx=(20, 6))
        self.search_var = tk.StringVar()
        s = ttk.Entry(bar, textvariable=self.search_var)
        s.pack(side="left", fill="x", expand=True)
        s.bind("<KeyRelease>", lambda e: self.load())

        cols = ("SaleID", "Customer", "Total", "Paid", "Due", "Status", "Date")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=22)
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("SaleID", width=70)
        self.tree.column("Customer", width=250)
        self.tree.column("Total", width=100, anchor="e")
        self.tree.column("Paid", width=100, anchor="e")
        self.tree.column("Due", width=100, anchor="e")
        self.tree.column("Status", width=120)
        self.tree.column("Date", width=170)
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree.tag_configure("even", background="#f4f6fc")
        self.tree.tag_configure("odd", background="#ffffff")

    def load(self):
        q = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        for i in self.tree.get_children():
            self.tree.delete(i)

        conn = db_connect()
        cur = conn.cursor()
        if q:
            cur.execute("""
                SELECT s.sale_id, c.name, s.total_amount, s.paid_amount, s.remaining_amount, s.status, s.sale_date
                FROM sales s
                JOIN customers c ON c.customer_id = s.customer_id
                WHERE CAST(s.sale_id AS TEXT) LIKE ? OR lower(c.name) LIKE ?
                ORDER BY s.sale_id DESC
            """, (f"%{q}%", f"%{q}%"))
        else:
            cur.execute("""
                SELECT s.sale_id, c.name, s.total_amount, s.paid_amount, s.remaining_amount, s.status, s.sale_date
                FROM sales s
                JOIN customers c ON c.customer_id = s.customer_id
                ORDER BY s.sale_id DESC
            """)
        rows = cur.fetchall()
        conn.close()

        for idx, r in enumerate(rows):
            insert_tree_row(
                self.tree,
                (r[0], r[1], money(r[2]), money(r[3]), money(r[4]), r[5], r[6]),
                idx,
            )

    def _selected_sale_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def add_payment(self):
        sid = self._selected_sale_id()
        if not sid:
            messagebox.showinfo("Select", "Select a sale")
            return
        PaymentForm(self, sale_id=sid, on_saved=self.load)

    def view_history(self):
        sid = self._selected_sale_id()
        if not sid:
            messagebox.showinfo("Select", "Select a sale")
            return
        PaymentHistory(self, sale_id=sid)


class PaymentForm(tk.Toplevel):
    def __init__(self, parent: PaymentsTab, sale_id: int, on_saved=None):
        super().__init__(parent)
        setup_theme(self)
        self.parent = parent
        self.sale_id = sale_id
        self.on_saved = on_saved
        self.title(f"Receive Payment - Sale #{sale_id}")
        center_window(self, 430, 340)
        self.resizable(False, False)

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        # Load sale
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT s.total_amount, s.paid_amount, s.remaining_amount, c.customer_id, c.name
            FROM sales s JOIN customers c ON c.customer_id = s.customer_id
            WHERE s.sale_id=?
        """, (sale_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            messagebox.showerror("Error", "Sale not found")
            self.destroy()
            return

        total, paid, due, customer_id, cname = row
        self.customer_id = customer_id

        ttk.Label(frm, text=f"Customer: {cname}", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(frm, text=f"Total: {money(total)}   Paid: {money(paid)}   Due: {money(due)}").pack(anchor="w", pady=(4, 10))

        self.amount = tk.StringVar(value=str(due if due > 0 else 0))
        ttk.Label(frm, text="Payment Amount").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.amount).pack(fill="x", pady=(0, 10))

        self.method = tk.StringVar(value="Cash")
        ttk.Label(frm, text="Method").pack(anchor="w")
        ttk.Combobox(frm, textvariable=self.method, values=["Cash", "Bank", "Online"], state="readonly").pack(fill="x", pady=(0, 10))

        self.note = tk.StringVar()
        ttk.Label(frm, text="Note (optional)").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.note).pack(fill="x", pady=(0, 10))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=10)
        ttk.Button(btns, text="Save Payment", command=self.save).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=8, expand=True, fill="x")

    def save(self):
        amt = ensure_float(self.amount.get(), 0.0)
        if amt <= 0:
            messagebox.showwarning("Invalid", "Enter a valid payment amount")
            return

        conn = db_connect()
        cur = conn.cursor()
        try:
            # Get current due
            cur.execute("SELECT remaining_amount, paid_amount, customer_id FROM sales WHERE sale_id=?", (self.sale_id,))
            r = cur.fetchone()
            if not r:
                raise RuntimeError("Sale not found")
            remaining, paid, customer_id = r

            if amt > remaining:
                amt = remaining

            # Insert payment
            cur.execute("""
                INSERT INTO payments (sale_id,payment_amount,payment_date,payment_method,note)
                VALUES (?,?,?,?,?)
            """, (self.sale_id, amt, now_str(), self.method.get(), self.note.get().strip() or None))

            new_paid = paid + amt
            new_remaining = remaining - amt
            status = "Paid" if new_remaining == 0 else "Partially Paid"

            cur.execute("UPDATE sales SET paid_amount=?, remaining_amount=?, status=? WHERE sale_id=?",
                        (new_paid, new_remaining, status, self.sale_id))

            # Update customer due
            cur.execute("UPDATE customers SET total_due = total_due - ? WHERE customer_id=?", (amt, customer_id))

            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            messagebox.showerror("Error", str(e))
            return
        conn.close()

        messagebox.showinfo("Saved", "Payment saved")
        if self.on_saved:
            self.on_saved()
        self.destroy()


class PaymentHistory(tk.Toplevel):
    def __init__(self, parent, sale_id: int):
        super().__init__(parent)
        setup_theme(self)
        self.title(f"Payment History - Sale #{sale_id}")
        center_window(self, 740, 440)

        cols = ("PaymentID", "Amount", "Date", "Method", "Note")
        tree = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c)
        tree.column("PaymentID", width=90)
        tree.column("Amount", width=110, anchor="e")
        tree.column("Date", width=170)
        tree.column("Method", width=100)
        tree.column("Note", width=240)
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        tree.tag_configure("even", background="#f4f6fc")
        tree.tag_configure("odd", background="#ffffff")

        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT payment_id, payment_amount, payment_date, payment_method, note FROM payments WHERE sale_id=? ORDER BY payment_id", (sale_id,))
        rows = cur.fetchall()
        conn.close()

        for idx, r in enumerate(rows):
            insert_tree_row(tree, (r[0], money(r[1]), r[2], r[3], r[4] or ""), idx)


class ReportsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._build()

    def _build(self):
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Reports", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(frm, text="Export customer due to Excel/PDF, and send WhatsApp reminders.").pack(anchor="w", pady=(0, 10))

        box = ttk.LabelFrame(frm, text="Customer Due Report", style="Section.TLabelframe")
        box.pack(fill="x")

        ttk.Button(box, text="Export Due Report (Excel)", command=self.export_excel).pack(side="left")
        ttk.Button(box, text="Export Due Report (PDF)", command=self.export_pdf).pack(side="left", padx=8)

        remind = ttk.LabelFrame(frm, text="WhatsApp Reminder", style="Section.TLabelframe")
        remind.pack(fill="x", pady=12)

        self.cust_var = tk.StringVar()
        ttk.Label(remind, text="Customer").grid(row=0, column=0, sticky="w")
        self.cust_cb = ttk.Combobox(remind, textvariable=self.cust_var, state="readonly", width=60)
        self.cust_cb.grid(row=0, column=1, padx=8, sticky="w")
        ttk.Button(remind, text="Refresh", command=self.load_customers).grid(row=0, column=2)

        ttk.Label(remind, text="Message").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.msg = tk.Text(remind, height=4, width=60)
        self.msg.grid(row=1, column=1, padx=8, pady=(10, 0), sticky="w")

        ttk.Button(remind, text="Send WhatsApp", command=self.send_whatsapp).grid(row=1, column=2, padx=8, pady=(10, 0), sticky="n")

        ttk.Label(remind, text="Note: WhatsApp requires pywhatkit + WhatsApp Web logged in.", foreground="#555").grid(row=2, column=1, sticky="w", padx=8, pady=(8, 0))

        self.load_customers()

    def load_customers(self):
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT customer_id, name, phone, total_due FROM customers ORDER BY total_due DESC")
        rows = cur.fetchall()
        conn.close()

        self.cust_map = {}
        values = []
        for cid, name, phone, due in rows:
            label = f"{cid} - {name} | Phone: {phone or ''} | Due: {money(due)}"
            values.append(label)
            self.cust_map[label] = (cid, phone, due)

        self.cust_cb["values"] = values
        if values:
            self.cust_var.set(values[0])
            # Default message
            _, phone, due = self.cust_map[values[0]]
            self.msg.delete("1.0", "end")
            self.msg.insert("1.0", f"Assalam-o-Alaikum, reminder: your outstanding due is Rs {money(due)}. Kindly pay your installment. Thank you.")

    def export_excel(self):
        if not OPENPYXL_OK:
            messagebox.showerror(
                "Missing library",
                "Install openpyxl first:\n\npip install openpyxl",
            )
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], initialfile="customer_due_report.xlsx")
        if not path:
            return
        try:
            export_due_report_excel(path)
            messagebox.showinfo("Done", f"Saved: {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_pdf(self):
        if not REPORTLAB_OK:
            messagebox.showerror(
                "Missing library",
                "Install reportlab first:\n\npip install reportlab",
            )
            return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="customer_due_report.pdf")
        if not path:
            return
        try:
            export_due_report_pdf(path)
            messagebox.showinfo("Done", f"Saved: {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def send_whatsapp(self):
        label = self.cust_var.get().strip()
        if not label or label not in self.cust_map:
            messagebox.showwarning("Customer", "Select a customer")
            return
        cid, phone, due = self.cust_map[label]
        if not phone:
            messagebox.showwarning("Phone", "Customer phone is missing")
            return
        msg = self.msg.get("1.0", "end").strip()
        if not msg:
            msg = f"Reminder: your outstanding due is Rs {money(due)}."

        if not PYWHA_OK:
            messagebox.showerror(
                "Missing library",
                "Install pywhatkit first:\n\npip install pywhatkit",
            )
            return
        try:
            send_whatsapp_reminder(phone, msg)
            messagebox.showinfo("Sent", "WhatsApp reminder sent (check WhatsApp Web)")
        except Exception as e:
            messagebox.showerror("Error", str(e))


class UsersTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._build()
        self.load()

    def _build(self):
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill="x")
        ttk.Button(bar, text="Add User", command=self.add_user).pack(side="left")
        ttk.Button(bar, text="Reset Password", command=self.reset_password).pack(side="left", padx=6)
        ttk.Button(bar, text="Delete User", command=self.delete_user).pack(side="left")

        cols = ("ID", "Username", "Role")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=22)
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("ID", width=70)
        self.tree.column("Username", width=240)
        self.tree.column("Role", width=120)
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree.tag_configure("even", background="#f4f6fc")
        self.tree.tag_configure("odd", background="#ffffff")

    def load(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, role FROM users ORDER BY user_id")
        rows = cur.fetchall()
        conn.close()
        for idx, r in enumerate(rows):
            insert_tree_row(self.tree, r, idx)

    def _selected_user_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def add_user(self):
        UserForm(self, title="Add User")

    def reset_password(self):
        uid = self._selected_user_id()
        if not uid:
            messagebox.showinfo("Select", "Select a user")
            return
        newp = simple_prompt(self, "Reset Password", "Enter new password:")
        if not newp:
            return
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("UPDATE users SET password=? WHERE user_id=?", (newp, uid))
        conn.commit()
        conn.close()
        messagebox.showinfo("Done", "Password updated")

    def delete_user(self):
        uid = self._selected_user_id()
        if not uid:
            messagebox.showinfo("Select", "Select a user")
            return
        if uid == 1:
            messagebox.showwarning("Protected", "Default admin cannot be deleted")
            return
        if not messagebox.askyesno("Confirm", "Delete this user?"):
            return
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE user_id=?", (uid,))
        conn.commit()
        conn.close()
        self.load()


class UserForm(tk.Toplevel):
    def __init__(self, parent: UsersTab, title: str):
        super().__init__(parent)
        setup_theme(self)
        self.parent = parent
        self.title(title)
        center_window(self, 430, 310)
        self.resizable(False, False)

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.role = tk.StringVar(value="Sales")

        ttk.Label(frm, text="Username").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.username).pack(fill="x", pady=(0, 10))

        ttk.Label(frm, text="Password").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.password).pack(fill="x", pady=(0, 10))

        ttk.Label(frm, text="Role").pack(anchor="w")
        ttk.Combobox(frm, textvariable=self.role, values=["Admin", "Manager", "Sales"], state="readonly").pack(fill="x", pady=(0, 10))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=10)
        ttk.Button(btns, text="Save", command=self.save).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=8, expand=True, fill="x")

    def save(self):
        u = self.username.get().strip()
        p = self.password.get().strip()
        r = self.role.get().strip()
        if not u or not p:
            messagebox.showwarning("Missing", "Username and password required")
            return
        conn = db_connect()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)", (u, p, r))
            conn.commit()
        except Exception as e:
            conn.close()
            messagebox.showerror("Error", str(e))
            return
        conn.close()
        self.parent.load()
        self.destroy()


def simple_prompt(parent, title, label):
    win = tk.Toplevel(parent)
    setup_theme(win)
    win.title(title)
    center_window(win, 360, 170)
    win.resizable(False, False)
    var = tk.StringVar()

    frm = ttk.Frame(win, padding=12)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text=label).pack(anchor="w")
    ent = ttk.Entry(frm, textvariable=var)
    ent.pack(fill="x", pady=10)
    ent.focus_set()

    res = {"val": None}

    def ok():
        res["val"] = var.get().strip()
        win.destroy()

    def cancel():
        win.destroy()

    btns = ttk.Frame(frm)
    btns.pack(fill="x")
    ttk.Button(btns, text="OK", command=ok).pack(side="left", expand=True, fill="x")
    ttk.Button(btns, text="Cancel", command=cancel).pack(side="left", padx=8, expand=True, fill="x")

    win.bind("<Return>", lambda e: ok())
    win.grab_set()
    parent.wait_window(win)
    return res["val"]


# -------------------- ENTRYPOINT --------------------

if __name__ == "__main__":
    init_db()

    # Helpful console notes (won't show in EXE windowed mode)
    print("Starting Wholesale Optics POS...")
    print("Optional installs:")
    print("  pip install reportlab openpyxl pywhatkit")
    print("EXE build:")
    print("  pip install pyinstaller")
    print("  pyinstaller --onefile --windowed optics_pos.py")

    Login().mainloop()
