# GUIDE — LoRA Training Skill Suite

**English** (this half) · **[简体中文](#指南--lora-训练技能套件)** (second half)

A hands-on guide for two audiences:

- **Users** — what to say, what to expect, what to check before you hit "confirm".
- **Agents** (Claude Code / OpenCode / Codex / OpenClaw / any LLM agent) — the
  contract you must follow when executing these skills.

---

## 1. Setup in two minutes

1. **Install the trainer**: grab `SD-Trainer-vX.Y.Z.7z` from
   [lora-scripts-next releases](https://github.com/wochenlong/lora-scripts-next/releases),
   extract anywhere, run `run_gui.bat`. The backend serves `http://127.0.0.1:28000`.
2. **Install the skills**: place `lora-pipeline/`, `lora-trainer/`,
   `dataset-doctor/`, and `references/` directly inside your agent's skills folder
   (see [Using outside Claude Code](#5-using-outside-claude-code) for per-agent paths).
   Keep them as siblings because they cross-reference by relative path.
3. **Python**: the doctor/fixer scripts need any Python 3.10+ with Pillow. The
   trainer's own `python_embeded\python.exe` works with zero setup.

With the trainer's bundled Python, no additional pip install is needed, and the checking
tools never touch the GPU. Other Python environments need Pillow.

## 2. For users

### The only thing you really need

A folder of images. Say:

> **"Train a character LoRA from `D:/data/mychar`."**

The agent will then, in order — asking you before anything changes on disk:

1. Check the trainer is running and read your GPU's VRAM (it won't ask you).
2. Propose a **trigger word** (e.g. `mych4r`) — a rare token that will summon your
   character at generation time. You can swap it on the confirm card.
3. Organize loose images into the `<repeats>_<concept>` folder the trainer expects.
4. Auto-caption Anima datasets with the shared sd-image-sorter pipeline, then review
   its non-blocking semantic/trait audit.
5. Run **dataset-doctor** and fix what it finds (duplicates, broken files, caption
   problems) — every fix is shown as a plan first, and removed files go to
   `_quarantine/`, never deleted.
6. Pick an initial repeats/epochs budget (about 1500 steps) and a preset that fits VRAM.
7. Show **one confirm card**. Nothing trains until you say so.

Other useful prompts:

| You say | What happens |
|---|---|
| "Check my dataset at `<path>` before training" | Doctor report only — PASS / WARN / FAIL + fixes |
| "Fix the duplicates / captions in `<path>`" | Dry-run plan → your OK → applied |
| "Tag these images, trigger is `zkz`" | Anima-sectioned WD14 captions + audit |
| "Train a **style** LoRA from `<path>`" | Style path: rank 32 and an `@style` trigger |
| "Train on SDXL / SD1.5 / Flux" | Same flow, different base model |
| "Use dim 32, lr 1e-4, 20 epochs" | Expert path — your numbers, still gated + confirmed |

### The full pipeline — from just a name

If you don't even have images yet, use **`lora-pipeline`** and give it a *name*:

> **"Make me a LoRA of `my_character_(my_series)` on Anima — collect, tag, train, and
> upload to Civitai; I'll click Publish."**

It runs seven phases — collect (Danbooru) → curate & build → tag + semantic review →
dataset-doctor gate → train (the confirm card still appears here) → validate a sample
gallery (ComfyUI) → package and fill the Civitai upload wizard — and **stops at a Draft**.
You review it and click Publish; it never publishes for you. Details and the exact tool
contracts: `lora-pipeline/SKILL.md`, `references/collect-and-tag.md`,
`references/validate-and-publish.md`.

### Reading the confirm card

```
📋 Training confirm card
- What:    character LoRA "zkz" · trigger: zkz   ← the word you'll type in prompts
- Data:    32 images × 5 repeats × 10 epochs = 1600 steps   ← initial budget
- GPU:     RTX 4070 12GB → low-VRAM preset (LoKr)
- Output:  ./output/zkz-anima-v1/ · a snapshot every 2 epochs
- Model:   Anima (dim32/alpha16 · bf16 · unet_lr 2e-5)
Reply "confirm" to start, or say what to change.
```

Worth a glance before confirming: is the **image count** what you expected (a wrong
count usually means a wrong path), and is the **trigger** a word you're happy typing
in every prompt from now on.

### While it trains

The agent tails the live log. Loss bouncing around (e.g. 0.3 → 0.05 with noise) is
normal. The agent watches for the two real problems — `loss=nan` (precision issue)
and CUDA out-of-memory — and proposes fixes. TensorBoard runs at `:6006`, the
monitor dashboard at `:6008`.

### After training — picking your LoRA

The output folder holds several snapshots (`zkz-anima-v1-000002.safetensors`, …,
plus the final file). Procedure:

1. Copy the **final** file into your generator (ComfyUI: `models/loras/`).
2. Generate a few images **with the trigger word**.
3. Looks overfitted (same pose everywhere, stiff face, training images leaking
   through)? Step back to an earlier snapshot and retry.
4. Too weak? Raise the LoRA weight first (1.0 → 1.2) before retraining.

### Troubleshooting

| Symptom | Fix |
|---|---|
| "Trainer not reachable" | Start `run_gui.bat`; wait for `http://127.0.0.1:28000` to answer |
| Doctor says **FAIL** | Something would crash training (corrupt images / no images). Let the agent quarantine the offenders, then re-check |
| Doctor says **WARN** | Training would *work*, just worse than it could. Fixes are one command each — usually worth it |
| A fix removed a file you wanted | It's in `<dataset>/_quarantine/` — move it back, done |
| `loss=nan` in the log | Use bf16 (not fp16), or switch optimizer; the agent knows this rule |
| CUDA out of memory | Lower-VRAM preset: gradient checkpointing, `blocks_to_swap`, LoKr |
| LoRA does nothing in ComfyUI | Trigger word missing from the prompt, or wrong base-model family |

## 3. For agents — the contract

If you are an LLM agent executing these skills, these rules are **non-negotiable**:

1. **Never launch without confirmation.** Assemble the config, show the confirm
   card, wait for an explicit yes. No confirmation → no `POST /api/run`.
2. **Never skip the doctor gate.** FAIL blocks training. WARN requires the user to
   explicitly accept the remaining issues.
3. **Never modify files without a dry-run first.** Every `fix_dataset.py` command
   prints a plan by default. Show the plan, get one confirmation, then re-run with
   `--apply`. Never hand-roll `rm`/`del` — the fixer quarantines instead of deleting.
4. **Don't ask what the API can tell you.** VRAM → `GET /api/graphic_cards`;
   trainer alive → `GET /api/version`. The only question a beginner should face is
   "character or style?" Character runs also need `1girl`, `1boy`, or `1other`.
5. **Re-run the doctor after fixing**, until PASS (or a user-accepted WARN).

### Quick-path pipeline (exact steps)

```
0  GET /api/version            → trainer alive?  GET /api/graphic_cards → VRAM
1  inputs: image folder (required) · goal: character|style (ask only if unsaid)
   character count: 1girl|1boy|1other · derive trigger (mychar → mych4r)
           output_name = <concept>-anima-v1
2  prepare data (each: dry-run → confirm once → --apply):
     loose images?    fix_dataset.py organize <dir> --repeats R --concept <name>
     no captions?     Anima: tag_dataset.py --dataset-dir <concept-dir> --trigger T
                              --subject-tag <count>  (style: --style and @trigger)
                       other bases: POST /api/interrogate
     doctor.py <dir> --trigger T --epochs N --json   → fix per table below → re-check
3  params: repeats = clamp(round(150 / images), 1, 10)
           epochs  = 10 (character) | 12 (style)     → initial total_steps ≈ 1500
           preset  = #1 char / #2 style (≥16GB) | #3 LoKr+blocks_to_swap (≤12GB)
4  confirm card → wait for explicit "confirm"
5  POST /api/run (flat JSON body from references/presets.md)
   check resp.status == "success" → keep data.task_id
6  poll GET /api/train/log/tail/{task_id}?limit=240
   watch: loss=nan → bf16/optimizer · OOM → ckpt/blocks_to_swap/resolution
7  compare early/final checkpoints with a strength-0 baseline at fixed seeds
```

### Issue code → fix command

Run with the same Python as `doctor.py`. All dry-run by default; `--apply` only
after user confirmation. Quarantined files go to `<dataset>/_quarantine/`.

| Doctor issue code | One-line fix |
|---|---|
| `no_concept_folders` | `fix_dataset.py organize <dir> --repeats <R> --concept <name>` |
| `corrupt_images` | `fix_dataset.py quarantine-corrupt <dir>` |
| `exact_duplicates` | `fix_dataset.py dedupe <dir>` |
| `near_duplicates` | `fix_dataset.py dedupe <dir> --near` |
| `non_rgb_mode` | `fix_dataset.py to-rgb <dir>` |
| `trigger_inconsistent` | `fix_dataset.py add-trigger <dir> --trigger <T>` |
| `artifact_tags` / `duplicate_tags` | `fix_dataset.py strip-tags <dir> [--tags "a,b"]` |
| `multiline_caption` | No auto-fix — merge each caption into ONE line (the trainer reads only line 1); preserve Anima section order and use `. ` before natural language |
| `missing_captions` / `empty_captions` | Anima: `tag_dataset.py`; other bases: `/api/interrogate` |
| `below_target_resolution` / `tiny_images` | No auto-fix — needs better source images |

### API quick reference

| Call | Purpose |
|---|---|
| `GET /api/version` | Trainer alive check |
| `GET /api/graphic_cards` | GPU + VRAM autodetect |
| `POST /api/run` | Launch training (flat JSON config) |
| `GET /api/train/log/tail/{task_id}` | Poll training log |
| `GET /api/tasks/terminate/{task_id}` | Stop a run |
| `POST /api/interrogate` | WD14 auto-captioning |
| `GET /api/tagger/status` | Tagging progress |

Full contract with request/response bodies: `references/trainer-api.md`.
Parameter semantics: `references/anima-params.md`. Templates: `references/presets.md`.

## 4. Manual CLI reference

Works without any agent. `<PY>` = any Python 3.10+ with Pillow
(e.g. `<SD-Trainer>\python_embeded\python.exe`).

```powershell
# Full audit → PASS/WARN/FAIL + prioritized fixes (read-only)
& <PY> dataset-doctor\scripts\doctor.py "D:\data\mychar" --trigger mych4r --epochs 10 --report

# Machine-readable variant (exit code 2 on FAIL — usable as a CI/hook gate)
& <PY> dataset-doctor\scripts\doctor.py "D:\data\mychar" --trigger mych4r --json

# Image-only / caption-only scans
& <PY> dataset-doctor\scripts\scan_dataset.py "D:\data\mychar"
& <PY> dataset-doctor\scripts\check_captions.py "D:\data\mychar" --trigger mych4r

# Fixes — ALWAYS dry-run first, then add --apply
& <PY> dataset-doctor\scripts\fix_dataset.py organize "D:\data\mychar" --repeats 5 --concept mych4r
& <PY> dataset-doctor\scripts\fix_dataset.py dedupe "D:\data\mychar" --near
& <PY> dataset-doctor\scripts\fix_dataset.py to-rgb "D:\data\mychar"
& <PY> dataset-doctor\scripts\fix_dataset.py add-trigger "D:\data\mychar" --trigger mych4r
& <PY> dataset-doctor\scripts\fix_dataset.py strip-tags "D:\data\mychar" --tags "watermark"
& <PY> dataset-doctor\scripts\fix_dataset.py quarantine-corrupt "D:\data\mychar" --apply
```

## 5. Using outside Claude Code

These skills follow the open **Agent Skills** convention (`SKILL.md` with `name` +
`description` frontmatter), which all four major agents now read natively:

| Agent | Install location | Invocation |
|---|---|---|
| **Claude Code** | `~/.claude/skills/` or project `.claude/skills/` | Auto-triggers on intent; or ask for the skill by name |
| **[OpenCode](https://opencode.ai/docs/skills/)** | Reads `.claude/skills/` & `~/.claude/skills/` directly; also `.opencode/skills/` | Native skill tool; loads on demand |
| **[Codex CLI](https://developers.openai.com/codex/skills)** | `~/.codex/skills/` or repo `.codex/skills/` | `$lora-trainer` mention, `/skills`, or implicit by description |
| **[OpenClaw](https://docs.openclaw.ai/tools/skills)** | `<workspace>/skills/` or `~/.openclaw/skills/` | Loaded with the agent's skill snapshot |

Two rules apply everywhere:

1. **Keep the suite intact.** `lora-pipeline/`, `lora-trainer/`, `dataset-doctor/`,
   and `references/` must remain sibling folders — the SKILL.md files use relative paths.
2. **The agent needs shell + HTTP.** Any agent that can run a command line and make
   local HTTP requests can execute the full flow. For agents with *no* skill support
   at all, just say: *"Read `lora-trainer/SKILL.md` and follow it."* — the skills are
   plain instructions; nothing in them is Claude-specific.

---

---

# 指南 — LoRA 训练技能套件

**[English](#guide--lora-training-skill-suite)**(上半部分)· **简体中文**(本部分)

本指南面向两类读者:

- **用户** — 该说什么、会发生什么、按「确认」之前看哪几项。
- **Agent**(Claude Code / OpenCode / Codex / OpenClaw / 任何 LLM agent)— 执行这套
  技能时必须遵守的契约。

---

## 1. 两分钟装好

1. **装训练器**:从 [lora-scripts-next releases](https://github.com/wochenlong/lora-scripts-next/releases)
   下载 `SD-Trainer-vX.Y.Z.7z`,解压,运行 `run_gui.bat`。后端跑在 `http://127.0.0.1:28000`。
2. **装技能**:把仓库中的 `lora-pipeline/`、`lora-trainer/`、`dataset-doctor/`、
   `references/` 直接放进 agent 的技能根目录(各 agent 路径见
   [在 Claude Code 之外使用](#5-在-claude-code-之外使用))。四者必须同级——它们用相对路径互相引用。
3. **Python**:体检/修复脚本只需要任意 Python 3.10+ 加 Pillow。直接用训练器自带的
   `python_embeded\python.exe`,零配置。

使用训练器自带的 Python 时无需额外 pip 安装,检查工具也不占 GPU。其他 Python 环境需要 Pillow。

## 2. 用户篇

### 你真正需要准备的只有一样

一个图片文件夹。直接说:

> **「用 `D:/data/mychar` 练一个角色 LoRA。」**

agent 会按顺序做下面的事——**动你文件之前一定先问你**:

1. 确认训练器在跑、自动读显卡显存(不会问你显存多大)。
2. 提议一个**触发词**(如 `mych4r`)——生成时用来召唤角色的稀有 token,确认卡上可改。
3. 把散图整理成训练器要求的 `<重复次数>_<概念名>` 文件夹结构。
4. Anima 数据统一用 sd-image-sorter 生成分段 WD14 caption,再复查语义/特征审计。
5. 跑 **dataset-doctor** 体检并修复发现的问题(重复图、坏图、标注问题)——每个修复
   先展示计划,移走的文件进 `_quarantine/`,**绝不删除**。
6. 自动给 repeats/epochs 首轮预算(约 1500 步)、按显存选配置。
7. 给你**一张确认卡**。你不点头,不开训。

其他常用说法:

| 你说 | 会发生什么 |
|---|---|
| 「训练前帮我检查 `<路径>` 的数据集」 | 只出体检报告——PASS / WARN / FAIL + 修复建议 |
| 「把 `<路径>` 里的重复图/标注修一下」 | dry-run 计划 → 你确认 → 执行 |
| 「给这些图打标,触发词是 `zkz`」 | Anima 分段 WD14 caption + 审计 |
| 「练一个**画风** LoRA」 | 画风路线:rank 32、使用 `@画风` trigger |
| 「用 SDXL / SD1.5 / Flux 练」 | 同样流程,换底模 |
| 「dim 32、lr 1e-4、20 epochs」 | 进阶路线——按你的数,但照样过体检 + 确认 |

### 完整流水线 — 只给一个名字

如果连图都还没有,用 **`lora-pipeline`**,直接给它一个*名字*:

> **「用 Anima 帮我做一个 `my_character_(my_series)` 的 LoRA——收图、打标、训练、传 Civitai,
> 我只点发布。」**

它会跑七个阶段——收图(Danbooru)→ 精修建库 → 打标与语义复查 → dataset-doctor 闸门 →
训练(这里仍会出确认卡)→ 验证样图(ComfyUI)→ 打包并填 Civitai 上传向导——然后**停在
Draft(草稿)**。你看过再点 Publish,它绝不替你发布。细节与工具契约见
`lora-pipeline/SKILL.md`、`references/collect-and-tag.md`、`references/validate-and-publish.md`。

### 怎么看确认卡

```
📋 训练确认卡
- 练什么:角色 LoRA「zkz」 · 触发词: zkz   ← 以后写提示词要用的词
- 数据:  32 张图 × 5 重复 × 10 轮 = 1600 步   ← 首轮预算
- 显卡:  RTX 4070 12GB → 省显存配置(LoKr)
- 输出:  ./output/zkz-anima-v1/ · 每 2 轮存一个快照
- 模型:  Anima(dim32/alpha16 · bf16 · unet_lr 2e-5)
回复「确认」开训;想改哪项直接说。
```

确认前值得扫一眼的两处:**图片数量**对不对(数量不对通常是路径给错了)、
**触发词**你是否愿意以后一直打它。

### 训练中

agent 会盯实时日志。loss 上下波动(如 0.3 → 0.05 带噪声)是正常的。真正要管的
只有两种:`loss=nan`(精度问题)和 CUDA 显存不足(OOM),agent 会给出对策。
TensorBoard 在 `:6006`,监控面板在 `:6008`。

### 训练完 — 挑出能用的那个文件

输出文件夹里有多个快照(`zkz-anima-v1-000002.safetensors` …… 加最终档)。流程:

1. 把**最终档**复制到生成端(ComfyUI:`models/loras/`)。
2. **带触发词**出几张图。
3. 过拟合了(姿势全一样、脸僵、训练图穿帮)→ 往前换更早的快照再试。
4. 效果太弱 → 先把 LoRA 权重调高(1.0 → 1.2),再考虑重练。

### 排障

| 现象 | 处理 |
|---|---|
| 「连不上训练器」 | 启动 `run_gui.bat`,等 `http://127.0.0.1:28000` 有响应 |
| 体检 **FAIL** | 有东西会让训练直接崩(坏图/没有图)。让 agent 把问题文件隔离后重检 |
| 体检 **WARN** | 能训,但效果会打折。修复都是一行命令,通常值得修 |
| 修复移走了你想要的文件 | 在 `<数据集>/_quarantine/` 里,移回原位即可 |
| 日志出现 `loss=nan` | 用 bf16(别用 fp16)或换优化器;agent 知道这条规则 |
| CUDA 显存不足 | 更省显存的配置:gradient checkpointing、`blocks_to_swap`、LoKr |
| ComfyUI 里 LoRA 没效果 | 提示词里没写触发词,或底模家族不对 |

## 3. Agent 篇 — 执行契约

如果你是执行这套技能的 LLM agent,以下规则**没有商量余地**:

1. **未确认不开训。** 组装好配置 → 出确认卡 → 等明确同意。没有确认就没有 `POST /api/run`。
2. **不绕过体检闸门。** FAIL 一律挡下;WARN 必须让用户明确接受残留问题才放行。
3. **改文件前必须先 dry-run。** 每条 `fix_dataset.py` 命令默认只打印计划——展示计划、
   拿到一次确认、再加 `--apply` 重跑。**禁止手写 `rm`/`del`**——修复器用隔离区代替删除。
4. **API 能查的不要问用户。** 显存 → `GET /api/graphic_cards`;训练器是否在跑 →
   `GET /api/version`。新手只应该被问一个问题:「练角色还是画风?」
5. **修完重跑体检**,直到 PASS(或用户接受的 WARN)。

### 快速通道流水线(精确步骤)

```
0  GET /api/version            → 训练器活着?  GET /api/graphic_cards → 显存
1  输入:图片文件夹(必需) · 目标:角色|画风(用户没说才问)
   角色还需 1girl|1boy|1other · 推导触发词(mychar → mych4r)
         output_name = <概念名>-anima-v1
2  准备数据(每步:dry-run → 确认一次 → --apply):
     散图?       fix_dataset.py organize <dir> --repeats R --concept <名>
     没标注?     Anima:tag_dataset.py --dataset-dir <concept-dir> --trigger T
                       --subject-tag <count>(画风传 --style 和 @trigger)
                   其他底模:POST /api/interrogate
     doctor.py <dir> --trigger T --epochs N --json  → 按下表修 → 重检
3  选参:repeats = clamp(round(150 / 图片数), 1, 10)
         epochs  = 10(角色)| 12(画风)      → 首轮总步数 ≈ 1500
         preset  = ①角色 / ②画风(≥16GB)| ③LoKr+blocks_to_swap(≤12GB)
4  确认卡 → 等用户明确「确认」
5  POST /api/run(flat JSON,模板见 references/presets.md)
   检查 resp.status == "success" → 记下 data.task_id
6  轮询 GET /api/train/log/tail/{task_id}?limit=240
   盯:loss=nan → bf16/换优化器 · OOM → ckpt/blocks_to_swap/降分辨率
7  固定 seed 对比 strength-0 baseline、早期和最终快照
```

### issue code → 修复命令

与 `doctor.py` 用同一个 Python 运行。全部默认 dry-run;用户确认后加 `--apply`。
被移走的文件进 `<数据集>/_quarantine/`。

| 体检 issue code | 一行修复 |
|---|---|
| `no_concept_folders` | `fix_dataset.py organize <dir> --repeats <R> --concept <名>` |
| `corrupt_images` | `fix_dataset.py quarantine-corrupt <dir>` |
| `exact_duplicates` | `fix_dataset.py dedupe <dir>` |
| `near_duplicates` | `fix_dataset.py dedupe <dir> --near` |
| `non_rgb_mode` | `fix_dataset.py to-rgb <dir>` |
| `trigger_inconsistent` | `fix_dataset.py add-trigger <dir> --trigger <T>` |
| `artifact_tags` / `duplicate_tags` | `fix_dataset.py strip-tags <dir> [--tags "a,b"]` |
| `multiline_caption` | 无自动修复——把每个 caption 合并成**单行**（训练端只读第一行）；保留 Anima 分段顺序，并用 `. ` 接自然语言 |
| `missing_captions` / `empty_captions` | Anima:`tag_dataset.py`;其他底模:`/api/interrogate` |
| `below_target_resolution` / `tiny_images` | 无自动修复——需要更高分辨率的源图 |

### API 速查

| 调用 | 用途 |
|---|---|
| `GET /api/version` | 训练器存活检查 |
| `GET /api/graphic_cards` | 自动检测 GPU + 显存 |
| `POST /api/run` | 开训(flat JSON 配置) |
| `GET /api/train/log/tail/{task_id}` | 轮询训练日志 |
| `GET /api/tasks/terminate/{task_id}` | 停止训练 |
| `POST /api/interrogate` | WD14 自动打标 |
| `GET /api/tagger/status` | 打标进度 |

完整契约(请求/响应体)见 `references/trainer-api.md`;参数语义见
`references/anima-params.md`;模板见 `references/presets.md`。

## 4. 手动 CLI 速查

不需要任何 agent 也能用。`<PY>` = 任意带 Pillow 的 Python 3.10+
(如 `<SD-Trainer>\python_embeded\python.exe`)。

```powershell
# 完整体检 → PASS/WARN/FAIL + 按优先级的修复建议(只读)
& <PY> dataset-doctor\scripts\doctor.py "D:\data\mychar" --trigger mych4r --epochs 10 --report

# 机器可读(FAIL 时退出码 2——可当 CI/hook 闸门用)
& <PY> dataset-doctor\scripts\doctor.py "D:\data\mychar" --trigger mych4r --json

# 只扫图像 / 只查标注
& <PY> dataset-doctor\scripts\scan_dataset.py "D:\data\mychar"
& <PY> dataset-doctor\scripts\check_captions.py "D:\data\mychar" --trigger mych4r

# 修复 — 永远先 dry-run,看完计划再加 --apply
& <PY> dataset-doctor\scripts\fix_dataset.py organize "D:\data\mychar" --repeats 5 --concept mych4r
& <PY> dataset-doctor\scripts\fix_dataset.py dedupe "D:\data\mychar" --near
& <PY> dataset-doctor\scripts\fix_dataset.py to-rgb "D:\data\mychar"
& <PY> dataset-doctor\scripts\fix_dataset.py add-trigger "D:\data\mychar" --trigger mych4r
& <PY> dataset-doctor\scripts\fix_dataset.py strip-tags "D:\data\mychar" --tags "watermark"
& <PY> dataset-doctor\scripts\fix_dataset.py quarantine-corrupt "D:\data\mychar" --apply
```

## 5. 在 Claude Code 之外使用

这套技能遵循开放的 **Agent Skills** 约定(带 `name` + `description` frontmatter 的
`SKILL.md`),目前四大 agent 都原生支持:

| Agent | 安装位置 | 触发方式 |
|---|---|---|
| **Claude Code** | `~/.claude/skills/` 或项目 `.claude/skills/` | 按意图自动触发;也可点名调用 |
| **[OpenCode](https://opencode.ai/docs/skills/)** | 直接读 `.claude/skills/` 和 `~/.claude/skills/`;也支持 `.opencode/skills/` | 原生 skill 工具,按需加载 |
| **[Codex CLI](https://developers.openai.com/codex/skills)** | `~/.codex/skills/` 或仓库内 `.codex/skills/` | `$lora-trainer` 提及、`/skills`,或按描述隐式触发 |
| **[OpenClaw](https://docs.openclaw.ai/tools/skills)** | `<workspace>/skills/` 或 `~/.openclaw/skills/` | 随 agent 的技能快照加载 |

两条通用规则:

1. **仓库保持完整。** `lora-pipeline/`、`lora-trainer/`、`dataset-doctor/`、`references/` 必须是同级
   文件夹——SKILL.md 里用的是 `../references/…` 相对路径。
2. **agent 需要 shell + HTTP 能力。** 只要能跑命令行、能发本地 HTTP 请求,就能执行
   完整流程。完全不支持 skills 的 agent 也行——直接告诉它:
   *「读 `lora-trainer/SKILL.md`,照着执行。」* 技能内容是纯指令,没有任何
   Claude 专属的东西。
