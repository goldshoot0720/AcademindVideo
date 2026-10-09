# Pi: The Practical Guide — 中英雙語動態字幕

為 [Academind 的《Pi - The Practical Guide》](https://pro.academind.com/courses/pi-the-practical-guide)
製作**中英雙語動態字幕**網站：課程影片在本機播放，英文字幕由 **AssemblyAI** 轉錄、
翻譯成繁體中文，並以詞級時間軸驅動卡拉OK／彈跳／淡入等動態效果。

課程規模：**5 個章節、47 課、總長 2 小時 36 分**。

## 產出清單

| 項目 | 數量 |
| --- | --- |
| 課程中介資料 `data/lessons.json` | 47 課 / 5 章節 |
| 影片 `video/*.mp4`（720p，本機） | 45 檔（鏡像缺 2 課） |
| ASR 音訊 `audio/*.m4a` | 45 檔 |
| 英文 SRT `data/srt/en/` | 45 檔 |
| 中英雙語 SRT `data/srt/bilingual/` | 45 檔 |
| 動態 ASS `data/ass/` | 45 檔 |
| 逐句雙語 JSON `data/bilingual/` | 45 檔 |
| 字幕總句數 | 3,942 句 |
| 翻譯覆蓋 | 45 / 45 課（100%） |

## 快速開始

```bash
python3 scripts/serve.py --open      # -> http://localhost:8788/
```

網站會列出全部 47 課；左側為章節分組的課程清單，右側可調整字幕動態效果、
字級、位置、背景遮罩與時間位移，並匯出 SRT／ASS。

> `player/standalone.html` 是**單檔自包含**版本（資料與 hls.js 都內嵌），
> 直接雙擊即可開啟，但因為瀏覽器不允許 `file://` 讀取同目錄影片，
> 影片播放仍需透過 `serve.py`。

## 影片來源

官方站台（Teachable + Hotmart 播放器）**只有前 3 課是免費試看**，其餘 44 課的
影片 ID 與簽章都必須帶入登入狀態才拿得到。因此本專案改用
[Bilibili 鏡像 BV1Bxbk64Ep6](https://www.bilibili.com/video/BV1Bxbk64Ep6)
作為片源：它是 45 段的完整重上傳（總長同為 2h36m），無需任何登入即可取得。

鏡像缺少 2 課（第 39 課 *Ideas For Extensions*、第 46 課 */tree Examples*），
網站仍會列出，只是標示為「無影片」。

## 字幕流程

```
data/bili.json ──► video/<slug>.mp4 + audio/<slug>.m4a   （yt-dlp + ffmpeg）
                            │
                            ├─ AssemblyAI 轉錄 ──► data/srt/en/<slug>.srt
                            │
                            ├─ parse_srt.py ────► data/segments/<slug>.json
                            │
                            ├─ translate.py ────► data/translations/zh-Hant/<slug>.json
                            │
                            └─ build.py ────────► data/bilingual/<slug>.json
                                                  data/srt/bilingual/<slug>.srt
                                                  data/ass/<slug>.ass
                                                  player/data.js
```

`scripts/build.py` 會套用**術語詞表**（`GLOSSARY`），把機翻的用語轉成台灣慣用語
（陣列／物件／函式／資料庫／伺服器／預設／專案／影片／檔案…），並補上 Pi 與
coding agent 相關詞彙（工作階段／沙箱／命令列／提示語…）。

## 一鍵跑完整流程

```bash
bash scripts/run_all.sh
```

每個階段都會跳過已經完成的產物，中斷後重跑很便宜。

## 專案結構

```
data/
  lessons.json            47 課的課程中介資料（章節、標題、長度）
  bili.json               Bilibili 鏡像的 45 個分段與課程對應
  srt/en/*.srt            英文 SRT（AssemblyAI 轉錄）
  segments/*.json         解析後的字幕分段（start/end/en）
  translations/zh-Hant/   繁體中文翻譯（與 segments 逐句對齊）
  bilingual/*.json        英+中 逐句資料，含詞級時間軸
  srt/bilingual/*.srt     雙語 SRT（英文一行、中文一行）
  ass/*.ass               動態 ASS（卡拉OK 掃動 + 淡入 + 縮放彈跳）
video/<slug>.mp4          課程影片（720p，由 serve.py 提供，支援 Range 分段請求）
audio/<slug>.m4a          16kHz 單聲道 AAC，供 AssemblyAI 轉錄
player/
  index.html              播放器（外部載入 data.js，開發用）
  standalone.html         單檔播放器（內嵌資料 + hls.js，可直接開啟）
  data.js                 由 build.py 產生，內嵌全部課程字幕資料
  vendor/hls.min.js       HLS 播放函式庫（本機內附，不依賴 CDN）
scripts/
  scrape.py               抓取課程側邊欄 -> data/lessons.json
  bili.py                 讀取鏡像分段並對應到課程 -> data/bili.json
  download.py             yt-dlp 下載影片 + ffmpeg 抽出 ASR 音訊
  asr.py                  AssemblyAI 轉錄 -> data/srt/en/
  parse_srt.py            SRT -> segments JSON
  translate.py            EN -> 繁中翻譯（多查詢批次，含重試/退避）
  fix_empty.py            補齊機翻漏譯的空句
  build.py                segments + 翻譯 -> bilingual / SRT / ASS / player data
  serve.py                本機伺服器（播放器 + 影片 Range 串流 + 字幕下載）
  preview.py              用 Pillow 產生字幕預覽圖
  burn.py                 用 ffmpeg 把 ASS 燒錄進影片（需含 libass 的 ffmpeg）
  run_all.sh              一鍵跑完整流程
  hotmart.py              （備用）官方 Hotmart HLS 字幕軌擷取
  fetch_en.py             （備用）官方站台英文字幕批次下載
```

## 官方來源備援（`hotmart.py` / `fetch_en.py`）

若你有 Academind 的登入狀態，也可以直接取用官方影片與官方英文字幕軌 ——
品質比 ASR 更好，而且不需下載影片。流程已實作並驗證：

1. 課程頁的 `<div class='hotmart_video_player' data-attachment-id=…>`
2. `GET /api/v2/hotmart/private_video?attachment_id=…` → `video_id` + `signature`
   （`v1` 路徑已失效，回 404；`v2` 才是現行的）
3. `https://player.hotmart.com/embed/<video_id>?signature=…&token=<app_key>`
   的 `__NEXT_DATA__` → `applicationData.mediaAssets[0].url`（帶簽章的 HLS master）
4. `master.m3u8` 內 `#EXT-X-MEDIA:TYPE=SUBTITLES` → 字幕 media playlist
   → 6 秒一段的 WebVTT → 合併成完整英文字幕

```bash
python3 scripts/fetch_en.py --cookie "你的 cookie"   # 47 課全抓
```

免費試看的 3 課（第 1、2、3 課）**不需登入**即可取得，本專案已納入。

## 播放器功能

- **動態效果**：卡拉OK（逐詞高亮）、彈跳、淡入、打字機、霓虹，共 5 種
- **雙語疊加**：上方為原英文字幕，下方為中文翻譯；可各自開關
- **字幕微調**：大小、位置（上／中／下）、背景遮罩、時間位移（±2s）
- **逐字稿面板**：整課雙語逐句對照，點擊即跳轉
- **匯出**：下載雙語 SRT、動態 ASS，或直接複製本課雙語字幕
- **鍵盤操作**：`空白` 播放／暫停、`←/→` ±5s、`↑/↓` 上下句、`E`/`C` 切換英／中

## 注意事項

- 影片與原始課程內容版權屬 Academind 與原作者所有；本專案僅作**個人學習用途**，
  請勿再散布。
- AssemblyAI 轉錄對技術名詞（Pi、Claude Code、Codex、AGENTS.md）辨識良好，
  但句界處偶有重複字（例如 "you can can configure"）。
- 機翻在句界處偶有不順（因逐句獨立翻譯），技術名詞已盡量校正。
- 本機 ffmpeg 若無 libass，`burn.py` 無法燒錄 ASS；ASS 可於 VLC / mpv 使用。
- AssemblyAI key 讀取順序：`--key` → `$ASSEMBLYAI_API_KEY` → `_scratch/assemblyai.key`。
