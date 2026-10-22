# AcademindVideo

Academind 課程的中英雙語字幕課程庫：課程清單首頁 + 每門課的字幕播放器，
外加一個本地後台，用來取得影片來源、把長影片按單元分割。

## 啟動

| 平台 | 指令 | 說明 |
| --- | --- | --- |
| Windows | 雙擊 `start.bat` | 或 `start.bat 9000` 指定埠號 |
| Windows | `serve.bat` | 與 `start.bat` 同義 |
| Windows | 雙擊 `stop.bat` | 停止伺服器（或視窗內 Ctrl-C） |
| macOS | 雙擊 `start.command` / `./serve.sh` | 行為相同 |

預設網址 <http://localhost:8788/>。同埠已有服務時只會開瀏覽器，不會重複啟動。

## 後台

首頁右上角「⚙ 後台」進入，或直接開 <http://localhost:8788/admin/>。

- **課程清單**：16 門課，顯示每門課已完成單元數；可用 `#<slug>` 深連結直接打開某門課。
- **鏡像來源**：資訊卡上的欄位可手動輸入 BV 號或完整影片網址，按「儲存」寫回該課的
  `course.json`（BV → `bv`，其他網址 → `mirrorUrl`）。下載與探測都以此為準。
- **來源下載**：`yt-dlp` 抓鏡像（整門課全部分 P）、原始課程頁的單一單元，或臨時輸入自訂網址。
- **登入憑證**：Bilibili 對未登入請求會回 **HTTP 412 風控**，必須帶 cookies。
  後台可直接選「讀取 Firefox cookies」（此機可用）；Chrome／Edge 的 cookie 受 Windows
  應用程式綁定加密保護，`yt-dlp` 解不開（DPAPI 錯誤），需改用 Firefox 或匯出的 `cookies.txt`。
- **測試來源**：先跑一次 `--simulate`，確認來源可用與分 P 數量，再決定要不要真的下載。
- **並行下載**：可選 1／2／3／4／6 條連線，把分 P 平均分給多條連線同時抓。
  實測單連線約 200–300 KiB/s（伺服器逐連線限速），開 3 條可明顯縮短總時間；開太多容易被限流。
- **日誌**：任務卡的「查看日誌」開全螢幕檢視器——不折行、可水平捲動、可整份複製，
  執行中會自動跟隨最新一行。
- **分割影片**：`ffmpeg` 依 `data/lessons.json` 的單元時長，切出播放器需要的
  `video/<單元 slug>.mp4`；也可改成固定長度切段（輸出 `video/part_NNN.mp4`）。
  「精準切割」會重新編碼換取逐幀準確，預設則用 `-c copy` 快速切（關鍵幀對齊）。
- **任務面板**：背景一次跑一個，顯示整體百分比、第幾個分 P、當前檔案大小／速度／ETA，可取消。

外部工具需求：

```bat
winget install yt-dlp.FFmpeg
winget install yt-dlp.yt-dlp
```

## 目錄

```
index.html                 課程清單首頁（由 scripts/build_index.py 產生）
admin/index.html           後台頁面
courses/<slug>/            每門課自成一個資料夾
  course.json              課程 metadata（series / bv / seriesUrl …）
  data/lessons.json        單元清單與時長
  data/segments/           逐句字幕段落（start/end/en）
  player/index.html        播放器
  video/<單元>.mp4         播放器實際讀取的影片（預設不存在，需自行下載/分割）
scripts/serve.py           本地伺服器（含 Range 支援）
scripts/admin_api.py       後台 API 與任務佇列
```

## Windows 腳本注意事項

`.bat` 檔案必須保持**純 ASCII + CRLF 換行**：只要夾了非 ASCII 字元或使用 LF 換行，
`cmd.exe` 解析時就會錯位（`rem`／`findstr`／`if` 全被拆爛）。中文訊息一律放在
`start.ps1`（UTF-8 with BOM）裡，並由腳本自己切到 UTF-8 碼頁。
