"""Render the one-pager to a paged A4 PDF (light theme, no split figures or rows)."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE = Path(__file__).resolve().parent.parent
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH")
PRINT_CSS = """
@page { size: A4; margin: 14mm 12mm 14mm 12mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-size: 12.5px; }
.page { max-width: none; padding: 0; gap: 22px; }
h1 { font-size: 27px; }
h2 { font-size: 18px; }
.lede { font-size: 14px; }
table { min-width: 0; font-size: 11.5px; }
th, td { padding: 7px 9px; }
tr, figure, .count, .col, .setup, .verdict, .notes { break-inside: avoid; }
section { break-inside: auto; }
section > h2 { break-after: avoid; }
.pairhead { break-after: avoid; }
.pair { break-inside: avoid; gap: 12px; }
figcaption { font-size: 11px; }
.counts { gap: 12px; }
:root { --paper: #ffffff; }
.setup { grid-template-columns: repeat(4, 1fr) !important; }
.setup span { font-size: 11.5px; }
.setup code { overflow-wrap: anywhere; }
.count { align-content: start; }
.pair, .shapes { grid-template-columns: 1fr 1fr !important; }
.scale { grid-template-columns: repeat(4, 1fr) !important; }
tr, .shape, .scale, .verdict, .limits li { break-inside: avoid; }
p { orphans: 3; widows: 3; }
section:has(.limits), section:has(.scale) { break-inside: avoid; }
.shape pre { white-space: pre-wrap; }
.shapes2 { grid-template-columns: 1fr 1fr !important; }
.shapes2 > div + div { border-left: 1px solid var(--rule) !important; border-top: 0 !important; }
.intent { break-inside: avoid; }
.intent > header h3 { font-size: 16px; }
.shapes2 pre { font-size: 11px; }
.calls { font-size: 12px; }
section.acs { break-before: page; }
.cols { grid-template-columns: repeat(3, 1fr) !important; }
section:has(.pair) { break-inside: avoid; }
"""
src = HERE / "report/_render.html"
src.write_text('<!doctype html><html><head><meta charset="utf-8"></head><body>'
               + (HERE / "report/index.html").read_text()
               + f"<style>{PRINT_CSS}</style></body></html>")
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROMIUM_PATH) if CHROMIUM_PATH else p.chromium.launch()
    page = b.new_page()
    page.emulate_media(media="print", color_scheme="light")
    page.goto(src.as_uri())
    page.wait_for_timeout(3000)
    page.pdf(path=str(HERE / "OpenBox-Policy-Granularity.pdf"), format="A4", print_background=True,
             prefer_css_page_size=True)
    b.close()
src.unlink()
