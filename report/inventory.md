# 每堂課素材盤點

產生時間：2026-10-10T01:03:36+08:00　|　15 門課 / 1082 堂課 / 總時長 69h 42m

## 總覽

| 階段 | 堂數 | 說明 | 待處理步驟 |
|---|---:|---|---|
| `done` | 365 | 完整（影片+音訊+英+中） | 無 |
| `translate` | 191 | 缺中文譯文 | translate → fix_empty → build |
| `asr` | 120 | 缺英文轉錄 | asr → parse_srt → translate → fix_empty → build |
| `audio` | 1 | 缺音訊 | ffmpeg_audio → asr → parse_srt → translate → fix_empty → build |
| `download` | 217 | 缺影片（鏡像可下載） | download → ffmpeg_audio → asr → parse_srt → translate → fix_empty → build |
| `blocked` | 188 | 缺影片（鏡像無對應） | find_source |

## 各課程

| course | series | 課數 | 鏡像對應 | done | translate | asr | audio | download | blocked | 時長 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ai-agents-workflows-the-practical-guide` | AI Agents & Workflows - The Practical Guide | 116 | 93 | 0 | 0 | 69 | 1 | 23 | 23 | 6h 48m |
| `ai-for-developers` | AI For Developers With GitHub Copilot, Cursor AI & ChatGPT | 146 | 74 | 0 | 74 | 0 | 0 | 0 | 72 | 7h 58m |
| `ai-key-concepts-terms-the-missing-guide` | AI Key Concepts & Terms - The Missing Guide | 60 | 59 | 0 | 57 | 1 | 0 | 1 | 1 | 1h 55m |
| `bun-the-practical-guide` | Bun - The Practical Guide | 58 | 56 | 0 | 56 | 0 | 0 | 0 | 2 | 4h 4m |
| `chatgpt-the-advanced-guide` | ChatGPT - The Advanced Guide | 37 | 37 | 37 | 0 | 0 | 0 | 0 | 0 | 1h 50m |
| `claude-code-the-practical-guide` | Claude Code - The Practical Guide | 61 | 35 | 35 | 0 | 0 | 0 | 0 | 26 | 3h 19m |
| `claude-cowork-the-practical-guide` | Claude Cowork - The Practical Guide | 33 | 32 | 32 | 0 | 0 | 0 | 0 | 1 | 2h 16m |
| `clean-code` | Clean Code | 95 | 85 | 72 | 4 | 4 | 0 | 5 | 10 | 6h 40m |
| `codex-the-practical-guide` | Codex - The Practical Guide | 67 | 48 | 0 | 0 | 27 | 0 | 21 | 19 | 3h 17m |
| `htmx-the-practical-guide` | HTMX - The Practical Guide | 64 | 60 | 60 | 0 | 0 | 0 | 0 | 4 | 4h 4m |
| `javascript-algorithms-the-fundamentals` | JavaScript Algorithms - The Fundamentals | 101 | 91 | 0 | 0 | 7 | 0 | 84 | 10 | 9h 22m |
| `javascript-data-structures-the-fundamentals` | JavaScript Data Structures - The Fundamentals | 104 | 95 | 0 | 0 | 12 | 0 | 83 | 9 | 9h 13m |
| `local-llms-via-ollama-lm-studio-the-practical-guide` | Local LLMs via Ollama & LM Studio - The Practical Guide | 56 | 51 | 51 | 0 | 0 | 0 | 0 | 5 | 3h 53m |
| `pi-the-practical-guide` | Pi - The Practical Guide | 47 | 45 | 45 | 0 | 0 | 0 | 0 | 2 | 2h 36m |
| `vps-essentials-the-practical-guide` | VPS Essentials - The Practical Guide | 37 | 33 | 33 | 0 | 0 | 0 | 0 | 4 | 2h 22m |

## 待處理清單（前 15 堂）

| course | # | title | 時長 | stage | 待處理步驟 |
|---|---:|---|---|---|---|
| `ai-agents-workflows-the-practical-guide` | 1 | Welcome To The Course! | 1:22 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 2 | What Is An AI Agent? | 2:13 | blocked | find_source |
| `ai-agents-workflows-the-practical-guide` | 3 | General vs Task-specific Agents | 2:39 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 4 | Where Agents Run / Execute | 2:07 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 5 | AI Agent Harnesses, LLMs & Limitations | 3:25 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 6 | How Agents Use Tools | 5:15 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 7 | Understanding Session Context | 2:17 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 8 | Core AI Agent Building Blocks - Overview | 2:25 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 9 | AI Agents vs AI Workflows | 2:18 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 10 | Module Introduction | 0:57 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 11 | Three Main Ways For Controlling AI Agents You Should Know | 0:49 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 12 | Managing Agent Tools & The Environment | 3:42 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 13 | Choosing The Right Model | 1:17 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 14 | Understanding Developer-provided System Instructions | 1:39 | asr | asr → parse_srt → translate → fix_empty → build |
| `ai-agents-workflows-the-practical-guide` | 15 | Providing Your Own Instructions & Understanding AGENTS.md / CLAUDE.md | 3:29 | asr | asr → parse_srt → translate → fix_empty → build |

完整清單共 1082 列，見 `lesson_inventory.csv` / `inventory.json`。
