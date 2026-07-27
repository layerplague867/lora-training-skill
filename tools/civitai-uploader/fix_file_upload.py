"""Re-upload a model file into an EXISTING Civitai draft whose step-3 upload was cut short.

Usage: fix_file_upload.py <model_id> <safetensors_path>

Gotchas this handles (learned the hard way):
- Opening /wizard?step=3 directly loads the POST editor, not the files step — you must
  click the "Upload files" stepper item on the page.
- The post editor contains the text "750 MB", so a generic "<N> MB" regex is a false
  positive for "file present". Presence is checked by the EXACT file name instead.
- Only the model-file input (accept contains 'safetensors') is used — never a generic
  input[type=file] fallback (that one belongs to the post image dropzone).
Never publishes.
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from civitai_upload import launch, is_logged_in, log


def goto_files_step(page, model_id):
    page.goto(
        f"https://civitai.com/models/{model_id}/wizard?step=3",
        wait_until="domcontentloaded",
    )
    page.wait_for_timeout(5000)
    try:
        page.get_by_text("Upload files", exact=True).first.click()
        page.wait_for_timeout(4000)
    except Exception as e:
        log(f"stepper click failed: {e}")
    return page.get_by_text("Model Files", exact=False).count() > 0


def file_present(page, fname):
    try:
        return page.get_by_text(fname, exact=False).count() > 0
    except Exception:
        return False


def busy(page):
    try:
        return (
            page.locator("[role='progressbar']").count() > 0
            or page.get_by_text("Uploading", exact=False).count() > 0
        )
    except Exception:
        return True


def main():
    model_id, file_path = sys.argv[1], sys.argv[2]
    fname = Path(file_path).name
    if not Path(file_path).exists():
        log(f"ABORT missing {file_path}")
        return 2
    shots = Path(__file__).parent / "runs" / f"fix2-{model_id}"
    shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = launch(p, headless=False)
        page = ctx.new_page()
        if not is_logged_in(page):
            log("NOT LOGGED IN - run login first")
            ctx.close()
            return 3

        on_files = goto_files_step(page, model_id)
        log(f"model {model_id}: files step reached = {on_files}")
        page.screenshot(path=str(shots / "01_files_step.png"), full_page=True)
        if not on_files:
            log("could not reach Model Files step - aborting")
            ctx.close()
            return 4

        if file_present(page, fname):
            log(f"{fname} already listed - verifying it persists...")
            if goto_files_step(page, model_id) and file_present(page, fname):
                log("file persisted across re-navigation ✓ nothing to do")
                page.screenshot(path=str(shots / "02_already_ok.png"), full_page=True)
                ctx.close()
                return 0
            log("file row did not persist - re-uploading")

        fi = page.locator("input[type='file'][accept*='safetensors']")
        if not fi.count():
            fi = page.locator("input[type='file'][accept*='ckpt']")
        if not fi.count():
            log("no model-file input found on files step - aborting (see screenshot)")
            page.screenshot(path=str(shots / "03_no_input.png"), full_page=True)
            ctx.close()
            return 5

        fi.first.set_input_files(file_path)
        size_mb = Path(file_path).stat().st_size / 1e6
        log(f"uploading {fname} ({size_mb:.0f} MB), waiting for real completion...")
        deadline = time.time() + max(1200, size_mb * 6)
        stable = 0
        while time.time() < deadline:
            page.wait_for_timeout(5000)
            try:
                if page.get_by_text("Finished uploading", exact=False).count():
                    log("finished-uploading toast seen")
                    break
            except Exception:
                pass
            if file_present(page, fname) and not busy(page):
                stable += 1
                if stable >= 4:
                    log("file row stable with no progress UI for 20s - assuming done")
                    break
            else:
                stable = 0
        else:
            log("TIMEOUT waiting for upload")
            page.screenshot(path=str(shots / "04_timeout.png"), full_page=True)
            ctx.close()
            return 6

        page.wait_for_timeout(5000)
        page.screenshot(path=str(shots / "05_uploaded.png"), full_page=True)
        ok = goto_files_step(page, model_id) and file_present(page, fname)
        page.screenshot(path=str(shots / "06_after_renav.png"), full_page=True)
        log(
            "file persisted after re-navigation ✓"
            if ok
            else "FILE NOT PERSISTED - check manually"
        )
        ctx.close()
        return 0 if ok else 7


if __name__ == "__main__":
    sys.exit(main())
