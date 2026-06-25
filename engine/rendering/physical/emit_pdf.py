"""PDF emitter for printable HTML (headless Chromium via Playwright).

Chromium is the chosen production engine: highest-fidelity HTML/CSS rendering and
self-contained — no system GTK/Pango install (which WeasyPrint required on Windows).
The browser is provisioned per-machine via `py -m playwright install chromium`.
"""

from __future__ import annotations

from pathlib import Path


def html_to_pdf(html: str, css_path: str, out_path: str) -> str:
    """Render HTML to a print-final PDF with headless Chromium.

    Playwright is imported lazily so importing the engine never requires the
    browser stack. ``css_path`` is accepted for signature compatibility; the HTML
    already inlines the print CSS, so Chromium needs no external stylesheet.
    """

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install it and the Chromium browser:\n"
            "  py -m pip install playwright\n"
            "  py -m playwright install chromium"
        ) from exc

    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                page.pdf(
                    path=str(output),
                    prefer_css_page_size=True,  # honor @page size + 0.75in margins
                    print_background=True,      # render the stimulus box fill
                )
            finally:
                browser.close()
    except RuntimeError:
        raise
    except Exception as exc:  # browser missing, launch failure, render error
        raise RuntimeError(
            "Headless Chromium could not render the PDF. Ensure the browser is "
            "installed: py -m playwright install chromium"
        ) from exc

    return str(output)
