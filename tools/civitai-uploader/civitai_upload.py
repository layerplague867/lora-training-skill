"""Reusable Civitai model uploader (Playwright). Civitai has no upload API, so this
drives a logged-in browser through the 4-step Publish Wizard.

  login                 Log in ONCE (session persists in .profile/). Your password is
                        never handled here — you type it in the browser.
  upload <config.json>  Fill the wizard from a config, upload the model file + sample
                        images, and STOP before Publish (draft). --publish --yes to publish.

Every step is screenshotted into runs/<slug>/ and logged, so runs can be inspected.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / ".profile"
CREATE_URL = "https://civitai.com/models/create"
ACCOUNT_URL = "https://civitai.com/user/account"
TYPE_LABEL = {"LORA": "LoRA", "LoCon": "LoRA", "Checkpoint": "Checkpoint"}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def launch(p, headless):
    return p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        headless=headless,
        viewport={"width": 1500, "height": 1100},
        args=["--disable-blink-features=AutomationControlled"],
    )


def has_session_cookie(ctx):
    return any(
        any(
            h in c["name"].lower()
            for h in ("civ-token", "session-token", "civitai-token")
        )
        for c in ctx.cookies()
    )


def is_logged_in(page):
    page.goto(ACCOUNT_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    return "/user/account" in page.url.lower()


def clean_md(md):
    t = re.sub(r"```[^\n]*\n", "", md)
    t = t.replace("```", "")
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    return t.replace("**", "").replace("`", "").strip()


def pick_option(pg, text):
    for loc in (
        pg.get_by_role("option", name=text, exact=False),
        pg.locator("[role='option']", has_text=text),
        pg.locator("[data-combobox-option],.mantine-Select-item", has_text=text),
    ):
        try:
            loc.first.wait_for(state="visible", timeout=2500)
            loc.first.click()
            return True
        except Exception:
            continue
    return False


def add_pill_tags(pg, tags):
    """Civitai model Tags = a TagsInput; click its inner box then type + Enter per tag."""
    inner = pg.locator("[class*='TagsInput'][class*='inner']").first
    try:
        inner.click(timeout=5000)
    except Exception:
        return "no tags box"
    added = []
    for t in tags:
        try:
            pg.keyboard.type(t, delay=30)
            pg.wait_for_timeout(600)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(500)
            added.append(t)
        except Exception:
            pass
    return f"added {len(added)}/{len(tags)}"


def set_trigger_words(pg, words):
    """Version Trigger Words: turn OFF the 'no trigger words' toggle, then for each word
    type into #input_trainedWords and click the '+ Create <word>' autocomplete option."""
    lbl = pg.locator("label", has_text="doesn't require any trigger words")
    if lbl.count():
        cb = lbl.first.locator("input[type=checkbox]")
        try:
            if cb.count() and cb.is_checked():
                lbl.first.click()
                pg.wait_for_timeout(1200)
        except Exception:
            pass
    ti = pg.locator("#input_trainedWords").first
    done = []
    for w in words:
        try:
            ti.click()
            pg.wait_for_timeout(300)
            pg.keyboard.press("Control+A")
            pg.keyboard.press("Delete")
            pg.keyboard.type(w, delay=60)
            pg.wait_for_timeout(1000)  # '+ Create <w>' appears
            if pick_option(pg, f"Create {w}") or pick_option(pg, w):
                done.append(w)
                pg.wait_for_timeout(600)
        except Exception:
            pass
    return f"trigger {done}"


def wait_upload_done(pg, timeout=240):
    """Wait until a model file REALLY finishes uploading before advancing.

    The file row shows its size the moment the upload STARTS, so the size text alone
    is not a completion signal (that bug truncated a 447 MB upload). Completion =
    'Finished uploading' toast, or file row present with no progress UI for 4 polls.
    """
    end = time.time() + timeout
    stable = 0
    while time.time() < end:
        try:
            if pg.get_by_text("Finished uploading", exact=False).count():
                return True
            row = pg.locator("text=/\\d+(\\.\\d+)?\\s*(MB|GB)/").count() > 0
            busy = (
                pg.locator("[role='progressbar']").count() > 0
                or pg.get_by_text("Uploading", exact=False).count() > 0
            )
            if row and not busy:
                stable += 1
                if stable >= 4:
                    return True
            else:
                stable = 0
        except Exception:
            pass
        pg.wait_for_timeout(5000)
    return False


class Shot:
    def __init__(s, page, d):
        s.page, s.dir, s.n = page, d, 0
        d.mkdir(parents=True, exist_ok=True)

    def __call__(s, name):
        s.n += 1
        p = s.dir / f"{s.n:02d}_{name}.png"
        try:
            s.page.screenshot(path=str(p), full_page=True)
            log(f"  shot {p.name}")
        except Exception as e:
            log(f"  shot fail {e}")


def advance(pg, names, want_url_part=None, timeout=180):
    """Click a Next/Continue-style button; wait until URL reflects the next step."""
    end = time.time() + timeout
    while time.time() < end:
        for nm in names:
            try:
                b = pg.get_by_role("button", name=nm, exact=False)
                if b.count() and b.first.is_enabled():
                    b.first.click()
                    pg.wait_for_timeout(3500)
                    if not want_url_part or want_url_part in pg.url:
                        return True
            except Exception:
                pass
        pg.wait_for_timeout(4000)
        if want_url_part and want_url_part in pg.url:
            return True
    return False


def cmd_login(args):
    with sync_playwright() as p:
        ctx = launch(p, headless=False)
        page = ctx.new_page()
        log("Log in in the browser (email/Google + 2FA). I will NOT touch the page.")
        page.goto("https://civitai.com/login", wait_until="domcontentloaded")
        end = time.time() + 360
        ok = False
        while time.time() < end:
            page.wait_for_timeout(3000)
            try:
                if has_session_cookie(ctx):
                    ok = True
                    break
            except Exception:
                pass
        log(
            "LOGIN SAVED ✓"
            if ok
            else "Login not detected — re-run and finish signing in."
        )
        ctx.close()
        return 0 if ok else 1


def cmd_upload(args):
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    base = Path(args.config).resolve().parent
    desc = ""
    if cfg.get("description_file"):
        f = (base / cfg["description_file"]).resolve()
        desc = clean_md(f.read_text(encoding="utf-8")) if f.exists() else ""
    files = [str((base / x).resolve()) for x in cfg.get("files", [])]
    idir = (
        (base / cfg.get("images_dir", "")).resolve() if cfg.get("images_dir") else None
    )
    images = (
        sorted(str(x) for x in idir.glob("*.png")) if idir and idir.exists() else []
    )
    for f in files:
        if not Path(f).exists():
            log(f"ABORT missing file {f}")
            return 2
    run = ROOT / "runs" / cfg.get("slug", "model")
    log(
        f"{cfg['name']} | files={len(files)} images={len(images)} | publish={args.publish}"
    )

    with sync_playwright() as p:
        ctx = launch(p, headless=args.headless)
        page = ctx.new_page()
        shot = Shot(page, run)
        if not is_logged_in(page):
            log("NOT LOGGED IN — run `login` first.")
            ctx.close()
            return 3
        log("Logged in ✓")
        page.goto(CREATE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4500)

        # ===== STEP 1: model card =====
        log("Step 1: model card")
        try:
            page.fill("#input_name", cfg["name"])
            log("  name ✓")
        except Exception as e:
            log(f"  name fail {e}")
        page.click("#input_type")
        page.wait_for_timeout(700)
        log(
            f"  type={TYPE_LABEL.get(cfg.get('type', 'LORA'), 'LoRA')}: "
            + (
                "✓"
                if pick_option(page, TYPE_LABEL.get(cfg.get("type", "LORA"), "LoRA"))
                else "MISS"
            )
        )
        page.wait_for_timeout(400)
        if cfg.get("category"):
            page.click("#input_category")
            page.wait_for_timeout(700)
            log(
                f"  category={cfg['category']}: "
                + ("✓" if pick_option(page, cfg["category"]) else "MISS")
            )
        # tags (Mantine TagsInput: click inner box, type + Enter per tag)
        if cfg.get("tags"):
            log("  tags: " + add_pill_tags(page, cfg["tags"]))
        # description
        if desc:
            try:
                ed = page.locator("[contenteditable='true']").first
                ed.click()
                ed.type(desc[:6000], delay=1)
                log("  description ✓")
            except Exception:
                log("  description MISS")
        # POI = No (required) + attestation (required)
        try:
            page.get_by_role("radio", name="No", exact=True).first.check()
            log("  POI=No ✓")
        except Exception:
            try:
                page.get_by_text("No", exact=True).first.click()
                log("  POI=No (fallback)")
            except Exception:
                log("  POI=No MISS")
        try:
            page.check("#input_attestation")
            log("  attestation ✓")
        except Exception:
            log("  attestation MISS")
        if cfg.get("nsfw"):
            try:
                page.check("#input_nsfw")
            except Exception:
                pass
        shot("step1")
        log("  advancing to version...")
        if not advance(page, ["Next"], "wizard?step=2", 60):
            shot("step1_stuck")
            log("  !! could not advance past step 1 — review screenshot")
        page.wait_for_timeout(2000)
        shot("step2")

        # ===== STEP 2: version =====
        log("Step 2: version")
        if cfg.get("base_model"):
            try:
                page.get_by_label("Base Model", exact=False).first.click()
                page.wait_for_timeout(800)
                ok = pick_option(page, cfg["base_model"]) or pick_option(page, "Other")
                log(
                    f"  base model={cfg['base_model'] if ok else 'Other/MISS'}: {'✓' if ok else 'MISS'}"
                )
            except Exception:
                log("  base model MISS (set it manually)")
        if cfg.get("trigger_words"):
            log("  " + set_trigger_words(page, cfg["trigger_words"]))
        for key, sel in (("epochs", "#input_epochs"), ("steps", "#input_steps")):
            if cfg.get(key):
                try:
                    page.fill(sel, str(cfg[key]))
                except Exception:
                    pass
        shot("step2_filled")
        log("  advancing to files...")
        advance(page, ["Next"], "wizard?step=3", 60)
        page.wait_for_timeout(2000)
        shot("step3")

        # ===== STEP 3: upload model file =====
        log("Step 3: upload model file")
        try:
            fi = page.locator("input[type='file'][accept*='safetensors']")
            (
                fi.first if fi.count() else page.locator("input[type='file']").first
            ).set_input_files(files)
            log(f"  uploading {[Path(f).name for f in files]} ...")
        except Exception as e:
            log(f"  file upload MISS {e}")
        # wait for the upload to FINISH before advancing (avoids the 'No files uploaded' modal)
        upload_timeout = max(
            600, int(sum(Path(f).stat().st_size for f in files) / 1e6) * 6
        )
        log(
            "  upload finished ✓"
            if wait_upload_done(page, upload_timeout)
            else "  upload wait timed out"
        )
        shot("step3_uploading")
        advance(page, ["Next", "Continue"], "wizard?step=4", 120)
        page.wait_for_timeout(2500)
        shot("step4")

        # ===== STEP 4: image post =====
        log("Step 4: image post")
        if images:
            try:
                page.locator(
                    "input[type='file'][accept*='image']"
                ).first.set_input_files(images)
                log(f"  uploading {len(images)} images ...")
                page.wait_for_timeout(min(8000 + 1500 * len(images), 60000))
            except Exception as e:
                log(f"  image upload MISS {e}")
        shot("step4_images")

        if args.publish and args.yes:
            if advance(page, ["Publish"], None, 30):
                log("PUBLISHED ✓")
            else:
                log("Publish button not found — left as draft.")
            shot("after_publish")
        else:
            log("Left as DRAFT (not published). Review, then click Publish yourself.")
        log(f"Draft URL: {page.url}")
        if args.keep_open:
            log("Keeping browser open 10 min for review...")
            page.wait_for_timeout(600000)
        ctx.close()
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    up = sub.add_parser("upload")
    up.add_argument("config")
    up.add_argument("--publish", action="store_true")
    up.add_argument("--yes", action="store_true")
    up.add_argument("--keep-open", action="store_true")
    up.add_argument("--headless", action="store_true")
    a = ap.parse_args()
    sys.exit(cmd_login(a) if a.cmd == "login" else cmd_upload(a))


if __name__ == "__main__":
    main()
