# TODO

## 高優先級

### 1. 端到端測試 ✅ 大部分完成
- [x] 在真實的 SD-Trainer 環境中測試完整流程(一個角色 Anima LoRA 全流程跑通)
- [x] 驗證 `/api/run` 請求能成功啟動訓練
- [x] 驗證 `/api/graphic_cards` 自動 VRAM 檢測
- [x] 驗證 WD14 打標(改用 sd-image-sorter `:8487` 而非 `/api/interrogate`,契約見 collect-and-tag.md)
- [x] 測試快速路徑的自動參數計算(repeats=clamp(round(150/imgs),1,10))
- [x] 測試 dataset-doctor 體檢與修復流程
- 註:實跑踩到的硬體/環境坑(高瓦數 GPU 的電源瞬變可用 `nvidia-smi -pl` 降功耗上限、
      SD-Trainer 的啟動方式、trainer 會忽略 `resume`)屬於各人環境差異,尚未寫成文檔。
- [ ] 把上述環境坑整理成 `references/troubleshooting.md`
- [ ] **驗證 `prefer_json_caption` / `.json` caption 是否真被訓練端讀取**：
      2026-06-11 排查發現該 flag 只存在於 UI schema（`mikazuki/schema/sd3-lora.ts`）
      與 `anima_backend/adapter.py` 的透傳清單，整個 v2.7.0 安裝中找不到任何讀
      `.json` sidecar 的程式碼（`read_caption` 只讀 `caption_extension` 文字檔）。
      驗證方法：放一張只有 `.json` 標註的圖開訓，在 log 裡核對 caption 是否為空。
      確認後更新 `caption-guide.md` 的「unverified」標註（坐實或移除）

**為什麼重要**: `.json` 仍未驗證，所以 doctor 預設只把 `.txt` 視為可訓練 caption；驗證成功前不改此預設。

### 2. 發布準備
- [x] 新增 LICENSE 文件（MIT）
- [x] 將 GitHub 倉庫設為公開
- [ ] 建立目前版本的 Git tag
- [ ] 發布 GitHub Release（附上 CHANGELOG）

## 中優先級

### 3. 持續整合
- [x] 新增 GitHub Actions workflow
- [x] 自動執行 dataset-doctor、pipeline 與 skill package 測試
- [x] Python 版本矩陣: 3.10, 3.11, 3.12, 3.13
- [ ] 測試失敗時阻止合併

### 4. 第三個 Skill: lora-tester（部分由 v0.3.0 `lora-pipeline` 覆蓋）
- [ ] 設計自動化快照選擇邏輯（目前靠人看 validation 圖判斷過擬合/弱 identity）
- [x] 實現批次生成測試圖片（`lora-pipeline/scripts/validate.py`,ComfyUI Anima+LoRA 樣圖）
- [ ] 開發評分機制（CLIP similarity / 用戶投票）→ 自動選最佳快照
- [x] 整合到完整流程: collect → tag → curate → doctor → trainer → **validate** → publish

### 5. 已知功能缺口
- [ ] 支援正則化圖片（reg images）
- [ ] 支援從 checkpoint 恢復訓練
- [ ] 多概念訓練的重複次數平衡策略
- [ ] 高級用戶的手動參數覆寫路徑
- [ ] 支援更多訓練器（OneTrainer, kohya_ss 原版）

## 低優先級

### 6. 開發體驗改進
- [x] 新增 `.gitattributes` 處理 CRLF 警告
- [ ] 新增 pre-commit hooks（Ruff、tests）
- [ ] 改進測試覆蓋率報告

## 文檔改進
- [ ] 新增故障排除流程圖
- [ ] 錄製演示視頻
- [ ] 社群貢獻指南（CONTRIBUTING.md）
- [ ] 常見問題 FAQ

## 未來探索
- [ ] 支援 LoRA 之外的微調技術（DoRA, LyCORIS）
- [ ] Web UI 介面（非必需，CLI-first 設計）
- [x] 與社群 LoRA 分享平台整合（Civitai 無上傳 API → 改用 civitai-uploader Playwright 填向導，
      契約見 `references/validate-and-publish.md`，`lora-pipeline` 第 7 階段；停在 Draft，人點 Publish）
