"""Screenshot the OpenBox views for the report.

    ./capture/open_chrome.sh                 # sign in, leave the window open
    uv run --with playwright python capture/openbox.py --session-id <session uuid>

The session is the `tool-and-input` run (scripts/find_session.sh prints it).
Attaches to the Chrome window on :9333 once you are past the login page.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOTS = Path(os.environ.get("SCREENSHOT_DIR", ROOT / "screenshots"))
DASHBOARD = os.environ.get("OPENBOX_DASHBOARD_URL", "http://localhost:3233")
CDP = "http://localhost:9333"


def shot(page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    print("saved", SHOTS / f"{name}.png", flush=True)


def scroll_to(locator, block: str = "start") -> None:
    """Scroll the element itself into place; the dashboard scrolls an inner container."""
    locator.evaluate(f"e => e.scrollIntoView({{block: '{block}'}})")
    locator.page.wait_for_timeout(1500)


def wait_for_sign_in() -> None:
    while True:
        try:
            tabs = json.load(urllib.request.urlopen(f"{CDP}/json", timeout=3))
        except OSError:
            tabs = []
        if any(t.get("type") == "page" and t.get("url", "").startswith(DASHBOARD)
               and "/login" not in t["url"] and "/sso" not in t["url"] for t in tabs):
            return
        time.sleep(2)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--only", choices=["shapes"], help="take only the six-rule shapes view")
    args = parser.parse_args()
    agent = f"{DASHBOARD}/agents/{os.environ['PROCUREMENT_AGENT_ID']}"

    wait_for_sign_in()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        page = [pg for pg in browser.contexts[0].pages if pg.url.startswith(DASHBOARD)][-1]
        page.set_viewport_size({"width": 1600, "height": 1000})

        if args.only == "shapes":
            # All six rules expanded: each intent's broad and precise shape.
            page.goto(f"{agent}?tab=authorize&subtab=policies")
            page.wait_for_timeout(6000)
            names = ["Purchase orders over 500", "Email only inside the tenant", "No outbound email",
                     "No purchase orders", "No Globex documents", "No document reads"]
            for rule in names:
                page.get_by_text(rule, exact=True).first.click()
                page.wait_for_timeout(1200)
            scroll_to(page.get_by_placeholder("Search rules...").first)
            shot(page, "openbox-6-shapes-top")
            scroll_to(page.get_by_text("No purchase orders", exact=True).first)
            shot(page, "openbox-7-shapes-bottom")
            return

        # The agent's rules, each expanded to show its conditions.
        page.goto(f"{agent}?tab=authorize&subtab=policies")
        page.wait_for_timeout(6000)
        for rule in ("No outbound email", "Purchase orders over 500"):
            page.get_by_text(rule, exact=True).first.click()
            page.wait_for_timeout(1500)
        scroll_to(page.get_by_placeholder("Search rules...").first)
        shot(page, "openbox-1-rules")

        # The run: one verdict per call in the Verify event log.
        page.goto(f"{agent}?tab=verify&sessionId={args.session_id}")
        page.wait_for_timeout(7000)
        scroll_to(page.get_by_text("Event Log Timeline", exact=True).first)
        shot(page, "openbox-2-event-log")
        page.get_by_role("button", name="2", exact=True).click()
        page.wait_for_timeout(2500)
        scroll_to(page.get_by_text("Event Log Timeline", exact=True).first)
        shot(page, "openbox-3-event-log-page2")

        # The execution tree with every node expanded: block reasons inline.
        page.get_by_text("Tree View", exact=True).first.click()
        page.wait_for_timeout(2500)
        # Centre on the first email: the 501 purchase order and both emails sit around it.
        scroll_to(page.get_by_text("send_email", exact=True).first, "center")
        shot(page, "openbox-4-tree")

        # Two orders either side of the limit, expanded to show the amount next to the verdict.
        started = page.locator("div").filter(has_text="create_purchase_order").filter(
            has_text="ActivityStarted").filter(has_not_text="ActivityCompleted")
        rows = [r for r in started.all() if r.inner_text().count("create_purchase_order") == 1]
        # The filter matches each row's outer and inner element, so rows[2:4] are the
        # first two orders: 120 (ALLOW) and 2,400 (BLOCK).
        for row in rows[2:4]:
            row.click()
            page.wait_for_timeout(1500)
        scroll_to(rows[2], "start")
        shot(page, "openbox-5-boundary")


if __name__ == "__main__":
    main()
