#!/usr/bin/env python3
"""Publish The Bannerman contact card to thebannerman.ca/pages/card.

Replaces the rented QR-Code-Generator link (l.ead.me) with a page on our own
domain, so the printed business-card QR keeps working with no subscription.

Reuses the same Shopify Admin API path as generate_sports_tv.py, including its
hard-won gotcha: pages.json IGNORES a ?handle= filter, so we pull the list and
match the handle in code rather than blindly overwriting some other page.

Env:
    SHOPIFY_ADMIN_TOKEN   custom-app Admin API token (shpat_...)
    SHOPIFY_SHOP          e.g. 6c1e0f-fc.myshopify.com  (optional; default below)
    SHOPIFY_API_VERSION   optional
"""
import base64, json, os, sys, urllib.request, urllib.error

SHOP    = os.environ.get("SHOPIFY_SHOP", "6c1e0f-fc.myshopify.com").strip()
TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip()
API_VER = os.environ.get("SHOPIFY_API_VERSION", "2026-07").strip()

PAGE_HANDLE = "card"
PAGE_TITLE  = "Damon Dhanowa"

NAME   = "Damon Dhanowa"
ORG    = "The Bannerman"
TAG    = "Love thy team"
PHONE_DISPLAY = "250 884 7656"
PHONE_TEL     = "+12508847656"
EMAIL  = "ddhanowa@live.ca"
SITE   = "thebannerman.ca"
BLUE   = "#5C8DB8"          # sampled from the logo on thebannerman.ca
BLUE_D = "#4E7FA8"

USE_PHOTO   = False              # False -> show the triangle logo instead of the headshot
PHOTO_FILE  = "card-photo.jpg"   # binary, if present
PHOTO_B64   = "card-photo.b64"   # same image, base64 text (web-UI friendly)
LOGO_B64    = "card-logo.b64"    # triangle mark, used as the saved contact photo
TRIANGLE = ("M 0,741 L 1197,741 L 613,0 L 787,332 L 410,332 L 582,1 Z")

def _fold(line, width=74):
    """vCard lines wrap at 75 octets; continuation lines start with one space."""
    out = [line[:width]]
    i = width
    while i < len(line):
        out.append(" " + line[i:i + width - 1])
        i += width - 1
    return out


def build_vcard():
    lines = ["BEGIN:VCARD", "VERSION:3.0",
             "N:Dhanowa;Damon;;;", f"FN:{NAME}", f"ORG:{ORG}",
             f"TEL;TYPE=CELL,VOICE:{PHONE_TEL}",
             f"EMAIL;TYPE=INTERNET,PREF:{EMAIL}",
             f"URL:https://{SITE}", f"NOTE:{TAG}"]
    if os.path.exists(LOGO_B64):
        b64 = "".join(open(LOGO_B64).read().split())
        lines += _fold(f"PHOTO;ENCODING=b;TYPE=PNG:{b64}")
    else:
        log(f"  ! {LOGO_B64} not found — saved contact will have no photo")
    lines += ["END:VCARD", ""]
    return "\r\n".join(lines)


def log(m): print(m, flush=True)


def avatar_html():
    """Inline the photo so the page has no external image dependency."""
    b64 = ""
    if not USE_PHOTO:
        return logo_html()
    if os.path.exists(PHOTO_FILE):
        b64 = base64.b64encode(open(PHOTO_FILE, "rb").read()).decode()
    elif os.path.exists(PHOTO_B64):
        b64 = "".join(open(PHOTO_B64).read().split())
    if b64:
        return (f'<img src="data:image/jpeg;base64,{b64}" alt="{NAME}" '
                'style="width:132px;height:132px;border-radius:50%;object-fit:cover;'
                'display:block;margin:0 auto 18px;border:4px solid rgba(255,255,255,.35);">')
    log(f"  ! neither {PHOTO_FILE} nor {PHOTO_B64} found — using the logo mark")
    return logo_html()


def logo_html():
    """The Bannerman triangle, centred in the same circle the photo occupied."""
    return ('<div style="width:132px;height:132px;border-radius:50%;background:#fff;'
            'margin:0 auto 18px;border:4px solid rgba(255,255,255,.35);'
            'display:flex;align-items:center;justify-content:center;">'
            f'<svg width="78" height="48" viewBox="0 0 1197 741" role="img" '
            f'aria-label="The Bannerman"><path d="{TRIANGLE}" '
            f'fill="{BLUE}" fill-rule="evenodd"/></svg></div>')


def row(href, text, label, last=False):
    border = "border-top:1px solid #ececec;" + ("border-bottom:1px solid #ececec;" if last else "")
    return (f'<div style="{border}padding:15px 0;">'
            f'<a href="{href}" style="color:#232323;text-decoration:none;font-size:16px;">{text}</a>'
            f'<div style="font-size:12.5px;color:#8b8b8b;margin-top:3px;">{label}</div></div>')


def footer_mark():
    """Small mark at the foot of the card — dropped when the logo is already the avatar,
    so the triangle does not appear twice on one card."""
    if not USE_PHOTO:
        return ""
    return ('<div style="text-align:center;margin-top:22px;"><svg width="42" height="26" '
            f'viewBox="0 0 1197 741" aria-hidden="true"><path d="{TRIANGLE}" '
            f'fill="{BLUE}" fill-rule="evenodd"/></svg></div>')


def build_html():
    vcf_b64 = base64.b64encode(build_vcard().encode("utf-8")).decode()
    return f'''<div style="max-width:460px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#232323;">
<div style="background:{BLUE};padding:36px 24px 28px;text-align:center;border-radius:10px 10px 0 0;">
{avatar_html()}
<div style="font-size:25px;font-weight:600;color:#fff;letter-spacing:.2px;">{NAME}</div>
<div style="font-size:14px;color:rgba(255,255,255,.82);margin-top:5px;">{ORG}</div>
</div>
<table role="presentation" style="width:100%;border-collapse:collapse;background:{BLUE_D};"><tr>
<td style="width:50%;text-align:center;padding:15px 0;border-right:1px solid rgba(255,255,255,.22);"><a href="tel:{PHONE_TEL}" style="color:#fff;text-decoration:none;font-size:13px;font-weight:600;letter-spacing:1.1px;">&#9742;&nbsp; CALL</a></td>
<td style="width:50%;text-align:center;padding:15px 0;"><a href="mailto:{EMAIL}" style="color:#fff;text-decoration:none;font-size:13px;font-weight:600;letter-spacing:1.1px;">&#9993;&nbsp; EMAIL</a></td>
</tr></table>
<div style="background:#fff;padding:24px 26px 30px;border:1px solid #e6e6e6;border-top:none;border-radius:0 0 10px 10px;">
<div style="font-size:15px;font-weight:600;color:#3f3f3f;margin-bottom:20px;">{TAG}</div>
{row(f"tel:{PHONE_TEL}", PHONE_DISPLAY, "Mobile")}
{row(f"mailto:{EMAIL}", EMAIL, "Email")}
{row(f"https://{SITE}", SITE, "Website", last=True)}
<a href="data:text/vcard;charset=utf-8;base64,{vcf_b64}" download="damon-dhanowa.vcf" style="display:block;margin-top:26px;background:{BLUE};color:#fff;text-align:center;padding:16px 12px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600;letter-spacing:.9px;">SAVE TO MY PHONE</a>
{footer_mark()}
</div></div>'''


def shopify(method, path, body=None):
    url = f"https://{SHOP}/admin/api/{API_VER}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json",
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:500]}


def upsert_page(html):
    status, res = shopify("GET", "pages.json?limit=250&fields=id,handle,title")
    if status != 200:
        raise SystemExit(f"Shopify GET pages failed ({status}): {res}")
    existing = [p for p in res.get("pages", []) if p.get("handle") == PAGE_HANDLE]
    payload = {"page": {"title": PAGE_TITLE, "handle": PAGE_HANDLE,
                        "body_html": html, "published": True}}
    if existing:
        pid = existing[0]["id"]
        status, res = shopify("PUT", f"pages/{pid}.json", payload); action = "updated"
    else:
        status, res = shopify("POST", "pages.json", payload); action = "created"
        pid = (res.get("page") or {}).get("id")
    if status not in (200, 201):
        raise SystemExit(f"Shopify {action} page failed ({status}): {res}")
    log(f"  page {action}: /pages/{PAGE_HANDLE} (id {pid})")
    for key, val in (("title_tag", f"{NAME} — {ORG}"),
                     ("description_tag", f"Contact card for {NAME} of {ORG}. "
                                         f"Call {PHONE_DISPLAY}, email {EMAIL}.")):
        st, _ = shopify("POST", f"pages/{pid}/metafields.json",
                        {"metafield": {"namespace": "global", "key": key,
                                       "type": "single_line_text_field", "value": val}})
        if st not in (200, 201):
            log(f"  ! could not set {key} ({st}) — page still fine")
    return pid


def main():
    if not TOKEN:
        raise SystemExit("SHOPIFY_ADMIN_TOKEN is not set (add it as a GitHub secret).")
    html = build_html()
    log(f"built page HTML ({len(html):,} bytes)")
    upsert_page(html)
    log(f"  live at https://{SITE}/pages/{PAGE_HANDLE}")


if __name__ == "__main__":
    sys.exit(main())
