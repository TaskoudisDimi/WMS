"""Outgoing email over SMTP. Templates are inline and bilingual (el/en)."""
import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from core.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER

log = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send(to: str | list[str], subject: str, text: str, html_body: str | None = None,
         attachments: list[tuple[str, bytes, str]] | None = None, reply_to: str | None = None) -> None:
    """attachments: (filename, content, mime type) tuples."""
    if not is_configured():
        raise RuntimeError("SMTP is not configured (SMTP_HOST / SMTP_USER / SMTP_PASSWORD)")
    msg = EmailMessage()
    name, addr = parseaddr(SMTP_FROM)
    msg["From"] = formataddr((name, addr))
    msg["To"] = ", ".join(to) if isinstance(to, list) else to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for filename, content, mime in attachments or []:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    ctx = ssl.create_default_context()
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20) as s:
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls(context=ctx)
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)


# ── Templates ─────────────────────────────────────────────────────────────────

_T = {
    "added_to_team": {
        "el": ("Προστέθηκες στην ομάδα «{business}»",
               "Σε πρόσθεσαν στην επιχείρηση «{business}» στο WMS.\n\nΣύνδεση: {url}"),
        "en": ("You were added to “{business}”",
               "You've been added to the business “{business}” on WMS.\n\nSign in: {url}"),
    },
}


def send_template(to: str, key: str, lang: str = "el", **params) -> None:
    subject, body = _T[key].get(lang, _T[key]["el"])
    subject, body = subject.format(**params), body.format(**params)
    send(to, subject, body, _wrap_html(subject, f"<p>{html.escape(body).replace(chr(10), '<br>')}</p>"))


def _wrap_html(title: str, inner: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#f5f7f7;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#152121">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border:1px solid #e1e6e6;border-radius:12px">
<tr><td style="padding:24px 28px 8px;font-weight:650;font-size:15px;color:#107d71">WMS</td></tr>
<tr><td style="padding:0 28px 8px"><h1 style="margin:0;font-size:20px;line-height:1.3">{html.escape(title)}</h1></td></tr>
<tr><td style="padding:8px 28px 28px;font-size:14px;line-height:1.6">{inner}</td></tr>
</table></td></tr></table></body></html>"""


def render_alert_digest(lang: str, business: str, reorder: list[dict], expiring: list[dict],
                        anomalies: list[dict], url: str) -> tuple[str, str, str]:
    """Daily digest: what to reorder, what expires soon, what looks unusual."""
    el = lang != "en"
    n = len(reorder) + len(expiring) + len(anomalies)
    subject = (f"{business}: {n} θέματα για σήμερα" if el else f"{business}: {n} things need attention today")

    def section(title: str, rows: list[str]) -> tuple[str, str]:
        if not rows:
            return "", ""
        txt = f"\n{title}\n" + "\n".join(f"  • {r}" for r in rows) + "\n"
        htm = f"<h2 style='font-size:15px;margin:20px 0 6px'>{html.escape(title)}</h2><ul style='padding-left:18px;margin:0'>" + \
              "".join(f"<li style='margin:3px 0'>{html.escape(r)}</li>" for r in rows) + "</ul>"
        return txt, htm

    r_rows = [(f"{p['name']} ({p['sku']}): απόθεμα {p['current_stock']}, παράγγειλε {p['suggested_qty']}"
               if el else f"{p['name']} ({p['sku']}): {p['current_stock']} in stock, order {p['suggested_qty']}")
              + (f" — τελειώνει σε ~{p['days_until_stockout']} ημ." if el and p.get('days_until_stockout') is not None
                 else f" — runs out in ~{p['days_until_stockout']} days" if p.get('days_until_stockout') is not None else "")
              for p in reorder]
    e_rows = [(f"{l['products']['name']}: {l['quantity']} τεμ. λήγουν {l['expiry_date']}" if el
               else f"{l['products']['name']}: {l['quantity']} units expire {l['expiry_date']}")
              + (f" (παρτίδα {l['lot_code']})" if el and l.get('lot_code') else f" (lot {l['lot_code']})" if l.get('lot_code') else "")
              for l in expiring]
    a_rows = [describe_anomaly(a, lang) for a in anomalies]

    parts = [section("Για παραγγελία" if el else "To reorder", r_rows),
             section("Λήγουν σύντομα" if el else "Expiring soon", e_rows),
             section("Ασυνήθιστες κινήσεις" if el else "Unusual activity", a_rows)]
    text = "".join(p[0] for p in parts) + f"\n{url}\n"
    cta = "Άνοιγμα WMS" if el else "Open WMS"
    inner = "".join(p[1] for p in parts) + \
        f"<p style='margin-top:24px'><a href='{html.escape(url)}' style='background:#107d71;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:600'>{cta}</a></p>"
    return subject, text, _wrap_html(subject, inner)


def describe_anomaly(a: dict, lang: str) -> str:
    el = lang != "en"
    name = a.get("name", "")
    k = a["kind"]
    if k == "sales_drop":
        return (f"{name}: {a['actual']} πωλήσεις τις τελευταίες 2 εβδομάδες αντί για ~{a['expected']}" if el
                else f"{name}: {a['actual']} sold in the last 2 weeks vs ~{a['expected']} usually")
    if k == "sales_spike":
        return (f"{name}: {a['actual']} πωλήσεις τις τελευταίες 2 εβδομάδες, πολύ πάνω από το συνηθισμένο (~{a['expected']})" if el
                else f"{name}: {a['actual']} sold in the last 2 weeks, well above the usual ~{a['expected']}")
    if k == "stock_loss":
        return (f"{name}: χάθηκαν {a['actual']} τεμ. σε απογραφές τις τελευταίες 30 ημέρες" if el
                else f"{name}: {a['actual']} units lost in recounts over the last 30 days")
    if k == "revenue_drop":
        return (f"Έσοδα εβδομάδας €{a['actual']:,.0f} αντί για ~€{a['expected']:,.0f}" if el
                else f"Revenue this week €{a['actual']:,.0f} vs ~€{a['expected']:,.0f} usually")
    return k
