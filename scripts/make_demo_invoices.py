#!/usr/bin/env python3
"""Generate demo invoice PDFs in demo_invoices/ for the FinFlow walkthrough.

Suppliers are invented and seeded for Acme Corp by scripts/seed_database.py.

    a_clean_kestrel_ridge.pdf       ~$10.4k, every field present  -> approver
    b_scanned_ambervolt.pdf         image-only scan, no due date   -> human review
    c_threshold_northpine.pdf       just under the $5,000 limit    -> THRESHOLD_GAMING flag, controller
    d_large_halvorsen_teague.pdf    over $25,000                   -> controller

Run from the repo root (reportlab is not a project dependency):

    uv run --no-project --with reportlab --with pillow python scripts/make_demo_invoices.py
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "demo_invoices"
TAX_RATE = Decimal("0.0825")
CENT = Decimal("0.01")

BILL_TO = ["Acme Corp", "Accounts Payable", "1400 Commerce Blvd", "Dallas, TX 75201"]


@dataclass
class Line:
    sku: str
    description: str
    qty: int
    unit: str
    unit_price: Decimal

    @property
    def total(self) -> Decimal:
        return (self.unit_price * self.qty).quantize(CENT, ROUND_HALF_UP)


@dataclass
class DemoInvoice:
    filename: str
    supplier: str
    address: list[str]
    email: str
    phone: str
    invoice_number: str
    invoice_date: date
    terms_days: int | None
    job_number: str
    po_number: str
    lines: list[Line]
    notes: str
    show_due_date: bool = True
    expected_range: tuple[Decimal, Decimal] = field(default=(Decimal("0"), Decimal("1e9")))

    @property
    def subtotal(self) -> Decimal:
        return sum((line.total for line in self.lines), Decimal("0.00"))

    @property
    def tax(self) -> Decimal:
        return (self.subtotal * TAX_RATE).quantize(CENT, ROUND_HALF_UP)

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax

    @property
    def due_date(self) -> date | None:
        if self.terms_days is None:
            return None
        return self.invoice_date + timedelta(days=self.terms_days)


def money(value: Decimal) -> str:
    return f"${value:,.2f}"


def build_invoices(today: date) -> list[DemoInvoice]:
    return [
        DemoInvoice(
            filename="a_clean_kestrel_ridge.pdf",
            supplier="Kestrel Ridge Electrical Supply",
            address=["2210 Foundry Road", "Fort Worth, TX 76106"],
            email="ar@kestrelridge-electric.example",
            phone="(817) 555-0142",
            invoice_number="KRES-240518",
            invoice_date=today - timedelta(days=3),
            terms_days=30,
            job_number="J-2611 Cedar Park Medical Office Bldg",
            po_number="PO-ACME-77412",
            lines=[
                Line("THHN12-BK-500", "12 AWG THHN copper wire, black, 500 ft spool", 8, "spool", Decimal("142.75")),
                Line("THHN12-WH-500", "12 AWG THHN copper wire, white, 500 ft spool", 6, "spool", Decimal("142.75")),
                Line("EMT-075-10", '3/4" EMT conduit, 10 ft stick', 120, "ea", Decimal("9.48")),
                Line("EMT-075-CPL", '3/4" EMT set-screw couplings, box of 50', 6, "box", Decimal("38.90")),
                Line("PNL-200A-42", "200A main breaker panelboard, 42 circuit, NEMA 1", 2, "ea", Decimal("1486.00")),
                Line("TRF-2X4-40K", "LED 2x4 troffer, 4000K, 0-10V dimming", 36, "ea", Decimal("89.50")),
            ],
            notes="Delivered to jobsite gate 2. Thank you for your business.",
            expected_range=(Decimal("5000"), Decimal("23750")),
        ),
        DemoInvoice(
            filename="b_scanned_ambervolt.pdf",
            supplier="Ambervolt Wire & Conduit",
            address=["88 Switchyard Lane", "Garland, TX 75041"],
            email="billing@ambervolt-wire.example",
            phone="(972) 555-0187",
            invoice_number="AV-30917",
            invoice_date=today - timedelta(days=6),
            terms_days=None,
            job_number="J-2604 Lakeview Elementary Reno",
            po_number="PO-ACME-77388",
            lines=[
                Line("W12THHN500", "12 AWG THHN copper wire, 500 ft spool", 12, "spool", Decimal("144.20")),
                Line("EMT34-10", '3/4" EMT conduit, 10 ft', 200, "ea", Decimal("9.55")),
                Line("PB200A", "200A panelboard, 30 circuit", 1, "ea", Decimal("1498.00")),
            ],
            notes="",
            show_due_date=False,
            expected_range=(Decimal("5000"), Decimal("23750")),
        ),
        DemoInvoice(
            filename="c_threshold_northpine.pdf",
            supplier="Northpine Electric Distributors",
            address=["5120 Riverbend Pkwy, Suite 300", "Irving, TX 75039"],
            email="invoices@northpine-electric.example",
            phone="(469) 555-0119",
            invoice_number="NPED-118204",
            invoice_date=today - timedelta(days=2),
            terms_days=45,
            job_number="J-2611 Cedar Park Medical Office Bldg",
            po_number="PO-ACME-77420",
            lines=[
                Line("CU-THHN-12-RD", "12 AWG THHN copper wire, red, 500 ft spool", 10, "spool", Decimal("139.90")),
                Line("EMT-3/4-10FT", '3/4" EMT conduit, 10 ft stick', 150, "ea", Decimal("9.35")),
                Line("LT-TROF-24-LED", "LED 2x4 troffer, 4000K, 5000 lm", 20, "ea", Decimal("86.75")),
            ],
            notes="Partial shipment. Remaining items to be invoiced separately.",
            expected_range=(Decimal("4750"), Decimal("5000")),
        ),
        DemoInvoice(
            filename="d_large_halvorsen_teague.pdf",
            supplier="Halvorsen-Teague Lighting & Power",
            address=["940 Industrial Circle", "Arlington, TX 76011"],
            email="ar@halvorsen-teague.example",
            phone="(682) 555-0163",
            invoice_number="HTLP-2026-04471",
            invoice_date=today - timedelta(days=4),
            terms_days=30,
            job_number="J-2598 Northgate Distribution Center",
            po_number="PO-ACME-77301",
            lines=[
                Line("HT-PNL200-42", "200A main breaker panelboard, 42 circuit, NEMA 1", 6, "ea", Decimal("1512.00")),
                Line("HT-TRF24-40", "LED 2x4 troffer, 4000K, 0-10V dimming", 140, "ea", Decimal("88.25")),
                Line("HT-THHN12-500", "12 AWG THHN copper wire, 500 ft spool", 24, "spool", Decimal("141.30")),
                Line("HT-EMT34-10", '3/4" EMT conduit, 10 ft stick', 400, "ea", Decimal("9.42")),
                Line("HT-EMT34-CON", '3/4" EMT set-screw connectors, box of 50', 10, "box", Decimal("41.60")),
            ],
            notes="Phase 2 lighting and distribution package per approved submittal.",
            expected_range=(Decimal("25000"), Decimal("1e9")),
        ),
    ]


def check_math(inv: DemoInvoice) -> None:
    for line in inv.lines:
        assert line.total == (line.unit_price * line.qty).quantize(CENT), line
    assert inv.subtotal == sum(line.total for line in inv.lines)
    assert inv.total == inv.subtotal + inv.tax
    low, high = inv.expected_range
    assert low <= inv.total < high, f"{inv.filename}: total {inv.total} outside {low}-{high}"


def draw_clean_pdf(inv: DemoInvoice, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    left, right = 54, width - 54

    c.setFillColor(colors.HexColor("#1F3A5F"))
    c.rect(0, height - 96, width, 96, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(left, height - 48, inv.supplier)
    c.setFont("Helvetica", 9.5)
    c.drawString(left, height - 66, " | ".join(inv.address))
    c.drawString(left, height - 80, f"{inv.phone} | {inv.email}")
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(right, height - 52, "INVOICE")

    c.setFillColor(colors.black)
    y = height - 130
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Bill To")
    c.setFont("Helvetica", 10)
    for i, text in enumerate(BILL_TO):
        c.drawString(left, y - 14 * (i + 1), text)

    meta = [
        ("Invoice Number", inv.invoice_number),
        ("Invoice Date", inv.invoice_date.isoformat()),
        ("Due Date", inv.due_date.isoformat() if inv.due_date else ""),
        ("Payment Terms", f"Net {inv.terms_days}" if inv.terms_days else ""),
        ("PO Number", inv.po_number),
        ("Job Number", inv.job_number),
        ("Currency", "USD"),
    ]
    for i, (label, value) in enumerate(meta):
        row_y = y - 14 * i
        c.setFont("Helvetica-Bold", 10)
        c.drawString(310, row_y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(410, row_y, value)

    y = height - 250
    cols = [left, 140, 380, 420, 465, right]
    c.setFillColor(colors.HexColor("#E8EEF5"))
    c.rect(left - 4, y - 5, right - left + 8, 18, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(cols[0], y, "Item")
    c.drawString(cols[1], y, "Description")
    c.drawRightString(cols[3] - 8, y, "Qty")
    c.drawString(cols[3], y, "Unit")
    c.drawRightString(cols[4] + 40, y, "Unit Price")
    c.drawRightString(cols[5], y, "Line Total")

    c.setFont("Helvetica", 9)
    for line in inv.lines:
        y -= 20
        c.drawString(cols[0], y, line.sku)
        c.drawString(cols[1], y, line.description)
        c.drawRightString(cols[3] - 8, y, str(line.qty))
        c.drawString(cols[3], y, line.unit)
        c.drawRightString(cols[4] + 40, y, money(line.unit_price))
        c.drawRightString(cols[5], y, money(line.total))
    y -= 12
    c.setStrokeColor(colors.HexColor("#9AA7B5"))
    c.line(left, y, right, y)

    totals = [
        ("Subtotal", money(inv.subtotal)),
        (f"Sales Tax ({TAX_RATE * 100:.2f}%)", money(inv.tax)),
        ("Total Due (USD)", money(inv.total)),
    ]
    for i, (label, value) in enumerate(totals):
        row_y = y - 20 - 16 * i
        bold = i == len(totals) - 1
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(right - 110, row_y, label)
        c.drawRightString(right, row_y, value)

    y -= 100
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, "Notes")
    c.setFont("Helvetica", 9)
    c.drawString(left, y - 13, f"{inv.notes} Job {inv.job_number.split(' ')[0]}, {inv.po_number}.")
    c.drawString(left, y - 26, f"Remit to {inv.email}. Please reference the invoice number with payment.")

    c.showPage()
    c.save()


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "DejaVuSansMono.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def draw_scanned_pdf(inv: DemoInvoice, path: Path, seed: int = 7) -> None:
    """Render the invoice as a skewed, noisy, low-contrast scan embedded as an image-only PDF."""
    rng = random.Random(seed)
    dpi = 110
    w, h = int(8.5 * dpi), int(11 * dpi)
    page = Image.new("L", (w, h), 236)
    d = ImageDraw.Draw(page)
    body, small, big = _font(15), _font(13), _font(24)
    ink = 70

    # Supplier name sits under a smeared, faded letterhead.
    d.text((60, 60), inv.supplier.upper(), font=big, fill=150)
    d.text((60, 92), "  ".join(inv.address), font=small, fill=120)
    d.text((60, 110), f"{inv.phone}   {inv.email}", font=small, fill=140)
    d.text((w - 250, 60), "INVOICE", font=big, fill=ink)

    y = 160
    d.text((60, y), "SOLD TO: " + ", ".join(BILL_TO[:1] + BILL_TO[2:]), font=body, fill=ink)
    d.text((60, y + 24), f"Inv #: {inv.invoice_number}", font=body, fill=ink)
    d.text((60, y + 48), f"Date: {inv.invoice_date.strftime('%m/%d/%y')}", font=body, fill=ink)
    d.text((420, y + 24), f"Cust PO: {inv.po_number}", font=body, fill=ink)
    d.text((420, y + 48), f"Job: {inv.job_number}", font=small, fill=ink)

    y = 260
    d.line((55, y - 6, w - 55, y - 6), fill=110, width=1)
    d.text((60, y), "QTY  ITEM        DESCRIPTION                          PRICE      AMOUNT", font=small, fill=ink)
    y += 26
    for line in inv.lines:
        desc = line.description[:34].ljust(34)
        row = f"{line.qty:>3}  {line.sku:<10}  {desc}  {line.unit_price:>8,.2f}  {line.total:>10,.2f}"
        d.text((60, y), row, font=small, fill=ink)
        y += 24
    d.line((55, y + 4, w - 55, y + 4), fill=110, width=1)
    y += 18
    for label, value in (("SUBTOTAL", inv.subtotal), ("TAX 8.25%", inv.tax), ("TOTAL", inv.total)):
        d.text((w - 330, y), f"{label:<10}{value:>14,.2f}", font=body, fill=ink)
        y += 26
    total_y = y - 26

    # Rubber stamp overlapping the total, coffee ring, and a smudge across the letterhead.
    stamp = Image.new("L", (300, 90), 0)
    sd = ImageDraw.Draw(stamp)
    sd.rectangle((4, 4, 295, 85), outline=255, width=4)
    sd.text((22, 14), "RECEIVED", font=_font(30), fill=255)
    sd.text((40, 52), "AP DEPT - PENDING", font=_font(15), fill=255)
    stamp = stamp.rotate(14, expand=True)
    page.paste(150, (w - 360, total_y - 50), stamp.point(lambda p: int(p * 0.55)))
    d.ellipse((w - 300, 120, w - 130, 290), outline=175, width=9)
    d.rectangle((40, 54, 470, 84), fill=205)
    d.text((70, 60), inv.supplier.upper()[:9], font=big, fill=160)

    d.text((60, h - 140), "Terms: per agreement", font=small, fill=ink)

    # Scanner artifacts: rotation, noise, blur, uneven exposure, JPEG compression.
    page = page.rotate(-1.8, resample=Image.BICUBIC, expand=False, fillcolor=40)
    page = Image.blend(page, Image.effect_noise((w, h), 40), 0.18)
    px = page.load()
    for _ in range(int(w * h * 0.012)):
        x, yy = rng.randrange(w), rng.randrange(h)
        px[x, yy] = rng.choice((25, 60, 200, 255))
    page = page.filter(ImageFilter.GaussianBlur(0.9))
    gradient = Image.linear_gradient("L").resize((w, h)).point(lambda p: int(p * 0.18))
    page = Image.composite(page, Image.new("L", (w, h), 150), Image.eval(gradient, lambda p: 255 - p))

    jpeg = io.BytesIO()
    page.convert("RGB").save(jpeg, format="JPEG", quality=38)
    jpeg.seek(0)

    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawImage(ImageReader(jpeg), 0, 0, width=letter[0], height=letter[1])
    c.showPage()
    c.save()


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    for inv in build_invoices(date.today()):
        check_math(inv)
        path = OUTPUT_DIR / inv.filename
        if inv.show_due_date:
            draw_clean_pdf(inv, path)
        else:
            draw_scanned_pdf(inv, path)
        print(f"{inv.filename:<32} {inv.supplier:<34} total {money(inv.total):>12}")


if __name__ == "__main__":
    main()
