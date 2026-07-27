"""Publish the HIDDEN wizard showcase posts of models the user has ALREADY published.

Model publish and post publish are separate on Civitai: the wizard post stays
'hidden' unless published, so the model-page gallery and profile Images stay empty.
Route: a published model's /wizard?step=4 URL loads its showcase post editor
(the user posts listing does NOT show hidden posts). Only the model IDs passed on
the command line are touched; model drafts are never published by this script.

Usage: publish_posts.py <model_id> [<model_id> ...]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from civitai_upload import launch, is_logged_in, log


def main():
    model_ids = sys.argv[1:]
    shots = Path(__file__).parent / "runs" / "publish-posts"
    shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = launch(p, headless=False)
        page = ctx.new_page()
        if not is_logged_in(page):
            log("NOT LOGGED IN")
            ctx.close()
            return 3

        done = []
        for mid in model_ids:
            page.goto(
                f"https://civitai.com/models/{mid}/wizard?step=4",
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(7000)
            page.screenshot(path=str(shots / f"{mid}_before.png"), full_page=True)
            body = ""
            try:
                body = page.locator("body").inner_text()[:6000]
            except Exception:
                pass
            if "currently hidden" not in body:
                log(f"model {mid}: post not hidden (or editor not loaded) - skipping")
                continue
            try:
                page.get_by_role("button", name="Publish", exact=True).first.click()
                page.wait_for_timeout(4000)
                try:
                    page.get_by_role("button", name="Publish", exact=True).first.click()
                    page.wait_for_timeout(3000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)
                page.screenshot(path=str(shots / f"{mid}_after.png"), full_page=True)
                still = "currently hidden" in page.locator("body").inner_text()[:6000]
                log(
                    f"model {mid}: post published={'NO - still hidden' if still else 'YES ✓'}"
                )
                if not still:
                    done.append(mid)
            except Exception as e:
                log(f"model {mid}: publish click failed {e}")

        log(f"published showcase posts for models: {done}")
        ctx.close()
        return 0 if len(done) == len(model_ids) else 1


if __name__ == "__main__":
    sys.exit(main())
