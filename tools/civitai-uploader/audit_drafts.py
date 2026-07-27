"""Audit every draft's Upload-files step: list the model file rows actually present.

Usage: audit_drafts.py <model_id> [<model_id> ...]
For each model, opens the wizard, clicks the "Upload files" stepper item (direct
?step=3 URL loads the post editor - known gotcha), and dumps the Model Files card
text + a screenshot to runs/audit/<id>.png. Read-only, never publishes.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from civitai_upload import launch, is_logged_in, log


def main():
    ids = sys.argv[1:]
    shots = Path(__file__).parent / "runs" / "audit"
    shots.mkdir(parents=True, exist_ok=True)
    results = {}

    with sync_playwright() as p:
        ctx = launch(p, headless=False)
        page = ctx.new_page()
        if not is_logged_in(page):
            log("NOT LOGGED IN")
            ctx.close()
            return 3
        for mid in ids:
            try:
                page.goto(
                    f"https://civitai.com/models/{mid}/wizard?step=3",
                    wait_until="domcontentloaded",
                )
                page.wait_for_timeout(5000)
                page.get_by_text("Upload files", exact=True).first.click()
                page.wait_for_timeout(4000)
                name = "?"
                try:
                    name = page.locator("h1, h2").first.inner_text()[:60]
                except Exception:
                    pass
                rows = []
                for el in page.locator("text=/\\.safetensors/").all():
                    try:
                        rows.append(el.inner_text().strip()[:80])
                    except Exception:
                        pass
                sizes = []
                for el in page.locator(
                    "text=/\\d+(\\.\\d+)?\\s*(MB|GB)\\s*[·•]/"
                ).all():
                    try:
                        sizes.append(el.inner_text().strip()[:40])
                    except Exception:
                        pass
                results[mid] = (sorted(set(rows)), sorted(set(sizes)))
                page.screenshot(path=str(shots / f"{mid}.png"), full_page=True)
                log(f"{mid}: files={sorted(set(rows))} sizes={sorted(set(sizes))}")
            except Exception as e:
                results[mid] = ([], [f"ERROR {e}"])
                log(f"{mid}: ERROR {e}")
        ctx.close()

    log("=== AUDIT SUMMARY ===")
    for mid, (rows, sizes) in results.items():
        status = "OK" if rows else "!! NO FILE"
        log(f"{status}  {mid}  {rows} {sizes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
