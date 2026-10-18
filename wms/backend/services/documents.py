"""PDF documents (purchase orders) with Greek text support (bundled DejaVu fonts)."""
import unicodedata
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"

T = {
    "el": {"title": "Παραγγελία αγοράς", "no": "Αρ.", "date": "Ημερομηνία", "to": "Προς", "from": "Από",
           "sku": "Κωδικός", "item": "Περιγραφή", "qty": "Ποσότητα", "price": "Τιμή μον.", "total": "Σύνολο",
           "net": "Σύνολο (χωρίς ΦΠΑ)", "notes": "Σημειώσεις", "vat": "ΑΦΜ",
           "footer": "Παρακαλούμε επιβεβαιώστε τη διαθεσιμότητα και την ημερομηνία παράδοσης απαντώντας σε αυτό το email."},
    "en": {"title": "Purchase order", "no": "No.", "date": "Date", "to": "To", "from": "From",
           "sku": "SKU", "item": "Description", "qty": "Qty", "price": "Unit price", "total": "Total",
           "net": "Total (excl. VAT)", "notes": "Notes", "vat": "VAT",
           "footer": "Please confirm availability and delivery date by replying to this email."},
}


def _caps(s: str) -> str:
    """Greek capitals drop their accents (ΑΠΌ → ΑΠΟ)."""
    return "".join(c for c in unicodedata.normalize("NFD", s.upper()) if unicodedata.category(c) != "Mn")


def _money(v: float | None) -> str:
    if v is None:
        return "—"
    return f"€{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def purchase_order_pdf(order: dict, items: list[dict], business: dict, supplier: dict | None,
                       contact: dict, lang: str = "el") -> bytes:
    t = T.get(lang, T["el"])
    pdf = FPDF(format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.add_font("DejaVu", "", str(FONTS / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    teal = (16, 125, 113)

    # Header
    pdf.set_font("DejaVu", "B", 18)
    pdf.set_text_color(*teal)
    pdf.cell(0, 9, t["title"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(60, 60, 60)
    pdf.set_font("DejaVu", "", 9.5)
    created = datetime.fromisoformat(order["created_at"].replace("Z", "+00:00")).strftime("%d/%m/%Y")
    pdf.cell(0, 6, f'{t["no"]} {order["id"][:8].upper()}   ·   {t["date"]}: {created}', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # From / To
    col = (pdf.w - 36) / 2
    y = pdf.get_y()

    def block(x: float, title: str, lines: list[str]):
        pdf.set_xy(x, y)
        pdf.set_font("DejaVu", "B", 8.5)
        pdf.set_text_color(130, 130, 130)
        pdf.cell(col, 5, _caps(title), new_x="LEFT", new_y="NEXT")
        pdf.set_text_color(25, 25, 25)
        for i, line in enumerate(l for l in lines if l):
            pdf.set_font("DejaVu", "B" if i == 0 else "", 10 if i == 0 else 9)
            pdf.set_x(x)
            pdf.multi_cell(col - 4, 5, line, new_x="LEFT", new_y="NEXT")
        return pdf.get_y()

    s = supplier or {}
    end1 = block(18, t["from"], [business.get("name"), contact.get("name"), contact.get("email")])
    end2 = block(18 + col, t["to"], [s.get("name") or order.get("party_name") or "—", s.get("contact_name"),
                                     s.get("address"), s.get("email"), s.get("phone"),
                                     f'{t["vat"]}: {s["vat_number"]}' if s.get("vat_number") else None])
    pdf.set_y(max(end1, end2) + 8)

    # Lines
    pdf.set_font("DejaVu", "", 9)
    total = 0.0
    with pdf.table(col_widths=(20, 64, 26, 24, 24), text_align=("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"),
                   line_height=6.5, borders_layout="HORIZONTAL_LINES",
                   headings_style=FontFace(emphasis="BOLD", color=(110, 110, 110)),
                   first_row_as_headings=True) as table:
        head = table.row()
        for h in (t["sku"], t["item"], t["qty"], t["price"], t["total"]):
            head.cell(h)
        for it in items:
            p = it.get("products") or {}
            price = it.get("unit_price")
            line_total = (price or 0) * it["quantity"]
            total += line_total
            r = table.row()
            r.cell(p.get("sku") or "")
            r.cell(p.get("name") or "")
            r.cell(f'{it["quantity"]} {p.get("unit") or ""}'.strip())
            r.cell(_money(price))
            r.cell(_money(line_total) if price is not None else "—")

    pdf.ln(3)
    pdf.set_font("DejaVu", "B", 10.5)
    pdf.cell(0, 7, f'{t["net"]}: {_money(total)}', align="R", new_x="LMARGIN", new_y="NEXT")

    if order.get("notes"):
        pdf.ln(4)
        pdf.set_font("DejaVu", "B", 9)
        pdf.cell(0, 5, t["notes"], new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 9)
        pdf.multi_cell(0, 5, order["notes"])

    pdf.ln(8)
    pdf.set_font("DejaVu", "", 8.5)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(0, 4.5, t["footer"])
    return bytes(pdf.output())
