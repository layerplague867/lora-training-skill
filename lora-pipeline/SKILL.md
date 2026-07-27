---
name: lora-pipeline
description: End-to-end LoRA factory — go from just a character/concept NAME to a trained, validated LoRA staged as a ready-to-publish Civitai draft, Anima-first. Use when the user wants the WHOLE flow (not just training) — "make me a LoRA of X", "collect images and train a character LoRA", "train and upload to Civitai", "build a dataset from scratch and publish". Orchestrates seven phases: collect images (Danbooru), auto-tag (WD14 / sd-image-sorter, trigger-first), curate + build the kohya dataset, gate on dataset-doctor, train via lora-trainer, validate a sample gallery in ComfyUI, then package + fill the Civitai upload wizard and STOP at Draft for the user to click Publish. Delegates training to lora-trainer and quality to dataset-doctor; never trains without a confirm card and never auto-publishes.
---

# lora-pipeline — 从「角色名字」到「Civitai 草稿」的端到端流水线

把「帮我做一个 X 的 LoRA」变成一条受控流水线:**收图 → 打标 → 精修 → 体检 → 训练 → 验证 → 打包上传(停在 Draft)**。本 skill 是**总指挥**——真正的训练交给 [`lora-trainer`](../lora-trainer/SKILL.md),质量交给 [`dataset-doctor`](../dataset-doctor/SKILL.md),自己负责把两端(收集/打标/精修 和 验证/发布)接起来。默认 **Anima 优先**。

> **两道人类闸门,不可移动:**
> 1. **训练前必须出「确认卡」** 并取得明确同意(继承 `lora-trainer` 的规则)——训练慢、占显存、难回退。
> 2. **绝不自动发布。** 全流程可以自动到 **Draft(草稿)**为止;点 Publish 是公开行为、会被索引,**必须由用户亲自点**。没有用户当场明说「发布」,绝不传 `--publish`。

## 依赖的本地工具(环境相关)

这些是**这台机器上**的外部本地工具,路径/端口是默认值,脚本都可用 flag/env 覆盖。契约细节见两份参考文档。

| 工具 | 用途 | 默认位置 |
|---|---|---|
| DanbooruDownload | 按 tag 下载图 | `C:\tools\DanbooruDownload`(env `DANBOORU_DL_DIR`) |
| sd-image-sorter | WD14 打标 FastAPI | `http://127.0.0.1:8487`(env `SORTER_URL`),`run.bat` 启动 |
| SD-Trainer | 训练后端 mikazuki API | `http://127.0.0.1:28000`,`run_gui.bat` 启动 |
| ComfyUI | 验证出图 | `http://127.0.0.1:8188`(env `COMFY_URL`) |
| civitai-uploader | 填 Civitai 上传向导 | `<repo>\tools\civitai-uploader`(独立工具,自带 README) |

`<PY>` = 任意带 Pillow 的 Python 3.10+(如 `<DanbooruDownload>\.venv\Scripts\python.exe`)。管线脚本在 `scripts/`,纯 stdlib + Pillow。

## 工作目录布局

一个 `--work <dir>` 项目根,各阶段写入子目录:

```
<work>/
  raw/                       collect.py    → danbooru 图 + .txt sidecar
  curation_manifest.json     curate.py     → keep/drop 名单
  dataset/<R>_<concept>/     build_dataset.py → 精修后的 RGB 图（kohya 结构）
  dataset/<R>_<concept>/*.txt tag_dataset.py  → WD14 触发词优先 caption
  output/<name>/             lora-trainer  → safetensors 快照
  validation/                validate.py   → ComfyUI 样图
  civitai_upload/            make_civitai_pack.py → MODEL_CARD + *.civitai.json + samples/
```

## 七个阶段(精确步骤)

```
0  输入:角色/概念「名字」(必需)。目标:角色|画风(用户没说才问)。
   推导:danbooru tag(默认 name_(series))、trigger(小写去空格,常见词做变体 mychar→mych4r)、
        output_name = <concept>-anima-v1、work 目录。
1  COLLECT  scripts/collect.py --tag "<danbooru tag>" --work <work> --limit 200 --apply
            → raw/ 有 ≥30 张再继续(太少就换 tag / 提高 limit)。见 collect-and-tag.md 的 2-tag 坑。
2  CURATE   scripts/curate.py --work <work>                 → 丢多人/漫画/参考图/太小/坏图
   BUILD    scripts/build_dataset.py --work <work> --concept <c>  → dataset/<R>_<c>/(自动定 repeats)
3  TAG      scripts/tag_dataset.py --work <work> --concept <c> --trigger <t>
            → Anima 正确打标:干净 tagger(eva02/swinv2,不用 pixai 单跑、绝不用 toriigate 当 tagger)
              → `content_mode=template` + `preset_id=anima_tags_only`(官方段落顺序、@artist、
              safety 词表 questionable→nsfw、单行)→ **caption 悖论修剪**:把 ≥0.9 出现率的不变
              身份特征(髮色/瞳色/体征)加进 blacklist 让 trigger 吸收(会印出所有候选,可复审)。
              画风用 --style(改剪 style/artist、保留内容,不做特征修剪)。见 collect-and-tag.md。
4  DOCTOR   ../dataset-doctor/scripts/doctor.py "<work>/dataset" --trigger <t> --epochs 10 --report
            → 按 dataset-doctor 修复到 PASS(FAIL 挡下,WARN 让用户接受)。
5  TRAIN    交给 lora-trainer:选参(repeats×图×epochs≈1500)→【确认卡】→ POST /api/run → 监看 log。
            train_data_dir = "<work>/dataset";output_dir = "<work>/output/<name>"。
6  VALIDATE 把选定快照拷进 ComfyUI/models/loras/ → scripts/validate.py --work <work> --lora <file> --trigger <t>
            → 看 validation/:一致=好;同姿势/僵脸=过拟合,退更早快照;identity 弱=提 strength 或加 epoch。
7  PUBLISH  scripts/make_civitai_pack.py --work <work> --concept <c> --trigger <t> --name <name>
                --lora-file <...safetensors> --display "<title>" --series "<series>"
            → civitai_upload/。一次性 login.bat 后:
              <civitai-uploader>\upload.bat "<work>\civitai_upload\<name>.civitai.json"
            → 填满 4 步向导、传文件+样图、**停在 Draft**。报告草稿 URL,让用户点 Publish。
```

阶段 1–4、6–7a 只动数据、可离线/本地;只有打标(2)、训练(5)、验证(6)、上传(7b)需要对应服务在线。任一服务连不上 ≠ 中止:先把能离线做的做完,再提示用户启动缺的服务(可建议在输入框 `! run.bat` / `! run_gui.bat` 直接在会话里起)。

## 委派导航

| 阶段 | 读取 / 执行 |
|---|---|
| 1–3 收集 / 打标 / 精修 的契约与坑 | [`../references/collect-and-tag.md`](../references/collect-and-tag.md) + `scripts/collect.py`·`curate.py`·`build_dataset.py`·`tag_dataset.py` |
| 4 体检 + 一行修复 | [`../dataset-doctor/SKILL.md`](../dataset-doctor/SKILL.md)(`doctor.py` / `fix_dataset.py`) |
| 5 选参 · 确认卡 · 开训 · 监看 | [`../lora-trainer/SKILL.md`](../lora-trainer/SKILL.md) + `../references/{trainer-api,anima-params,presets}.md` |
| caption 格式 / 触发词 / 官方推荐质量词 | [`../references/caption-guide.md`](../references/caption-guide.md) |
| 6–7 验证出图 + Civitai 上传的契约与坑 | [`../references/validate-and-publish.md`](../references/validate-and-publish.md) + `scripts/validate.py`·`make_civitai_pack.py` |

## 官方推荐质量词(caption 与出图都用)

Anima 官方 tag 顺序把质量/元信息放**最前**。**出图/样图 prompt** 用质量前缀
`masterpiece, best quality, newest, highres`;**caption 端** 的质量词表是
`masterpiece / best / good / normal / low / worst quality`(不是 Pony 的 `score_5`),
理想是按美学分数逐图给、没打分就省略。段落顺序、@artist、safety 词表、单行、以及角色的
caption 悖论修剪,全部由 `anima` preset + trait-candidates 处理——细节与「为什么」见
[`caption-guide.md`](../references/caption-guide.md) 的 *Anima tagging craft* 一节。

## 自检

1. 入口是「名字」时:已推导 danbooru tag / trigger / output_name / work,没让用户做这些机械推导。
2. 顺序是 **收集 → 精修 → 建库 → 打标 → 体检**(对**建好的** concept 文件夹打标,不是对 raw)。
3. 打标用 `content_mode="template"` + Anima preset(段落顺序、safety 词表、@artist、单行);角色做了 caption 悖论修剪(不变身份特征 → trigger),画风改剪 style/artist;tagger 选 eva02/swinv2,pixai 只在 consensus、toriigate 绝不当 tagger。
4. 过了 `dataset-doctor` 闸门:FAIL 没放行,WARN 已让用户接受;触发词一致率达标。
5. **训练前出了确认卡并取得同意**(委派 `lora-trainer`,未确认不 POST /api/run)。
6. 发布前**验证过样图**(至少让用户看过 validation/);base_model 用精确名 `Anima`。
7. **停在 Draft**:没有用户当场明说「发布」,绝不 `--publish`。报告了草稿 URL。

## 可验证案例(端到端)

用户:「帮我做一个 `my_character_(my_series)` 的角色 LoRA,用 Anima,收图打标训练完自动传 Civitai,我只点发布。」

1. 推导:tag=`my_character_(my_series)`、trigger=`mychar`、name=`mychar-anima-v1`、work=`D:/work/mychar`。
2. `collect.py --apply` → raw/ 126 张 → `curate.py` 丢多人/漫画/太小 → `build_dataset.py --concept mychar` → `dataset/5_mychar/`(~34 张,repeats 自动)。
3. `tag_dataset.py --trigger mychar` → 触发词优先 caption → `doctor.py ... --trigger mychar` → 修到 PASS。
4. 委派 `lora-trainer`:34 张→repeats/epochs≈1500 步 →【确认卡】→ 用户「确认」→ 开训 → 监看 → `output/mychar-anima-v1/`。
5. 拷贝快照 → `validate.py --lora mychar-anima-v1.safetensors --trigger mychar` → validation/ 一致 → OK。
6. `make_civitai_pack.py ...` → `civitai_upload/` → `upload.bat *.civitai.json` → **Draft**(LoRA/Character、tags、base_model Anima、trigger mychar、文件、样图都已填)→ 报告草稿 URL,等用户点 Publish。

## 执行交接

- 本 skill 只做**编排**:串起收集/打标/精修 与 验证/发布,并守住两道人类闸门(训练前确认卡、发布必须人点)。
- 训练细节 → `lora-trainer`;数据质量 → `dataset-doctor`;工具契约与坑 → 两份 `references/*.md`。
- 收尾归档(可选,本机约定):图片进 `D:\archive\done\<name>\`,产物/脚本/上传包进 `<skill>\lora-datasets\<name>\`(已 gitignore)。
