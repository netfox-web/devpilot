# DevPilot 專案開發管家

這是一套給多專案、多電腦、多 AI 工具使用的「專案開發進度中控台」。

支援來源：

- Codex
- Claude / Claude Code
- Cursor
- GitHub
- 手動紀錄
- 部署紀錄

第一版功能：

- 專案列表 CRUD
- 專案詳情頁
- 階段進度管理
- 任務清單
- AI 交接紀錄
- 部署紀錄
- 驗收清單
- API Token 驗證
- Codex / Claude 完成後自動呼叫 API 回寫進度
- SQLite 資料庫
- Docker / Synology NAS 部署

---

## 一鍵複製 Claude / Codex / Cursor 回寫指令

每個專案詳情頁會顯示「一鍵複製 Claude / Codex / Cursor 回寫指令」卡片，提供四個按鈕：

- 複製 Claude PowerShell 回寫指令
- 複製 Codex PowerShell 回寫指令
- 複製 Cursor PowerShell 回寫指令
- 複製 Python 回寫指令

按下按鈕後，完整指令會複製到剪貼簿，不會跳轉頁面。PowerShell 指令會自動帶入目前專案 ID、API URL、source、agent_name、work_mode，以及從 Flask 環境設定讀取的 API Token。頁面不直接顯示 Token，但複製出來的指令會包含 Token，方便 Claude Code、Codex 或 Cursor 完成工作後直接回寫 DevPilot API。

### Cursor 除錯後回寫 DevPilot

- Cursor 適合在本機 Debug、修正程式後，將結果回寫到 DevPilot 交接紀錄。
- 請從專案詳情頁點選「複製 Cursor PowerShell 回寫指令」，貼到 PowerShell 執行。
- 產生的 JSON 會固定 `source=cursor`、`work_mode=debug`，你只要依實際狀況修改摘要、檔案、測試與 Git 等欄位。
- 與其他 PowerShell 範本相同，請務必使用 `ConvertTo-Json` 後再以 **UTF-8 bytes** 送出，避免中文亂碼。

使用流程：

1. 開啟 DevPilot 專案詳情頁。
2. 點選對應的複製按鈕。
3. 把指令貼到 Claude Code、Codex、Cursor 建議的終端機，或 Windows PowerShell。
4. 將 `summary`、`completed_phases`、`changed_files`、`test_result`、`git_status`、`repo_branch`、`commit_sha`、`next_steps`、`warnings` 改成本次實際結果（Cursor 範本已預填 debug 相關占位文字）。
5. 執行指令後，DevPilot 會寫入 `/api/projects/{project_id}/handoff`。

### 讓 Codex / Claude 完成後呼叫 DevPilot API

PowerShell 範本會呼叫：

```powershell
$body = $payload | ConvertTo-Json -Depth 5
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "$ApiUrl/api/projects/$ProjectId/handoff" -Method Post -Headers @{ Authorization = "Bearer $ApiToken" } -ContentType "application/json; charset=utf-8" -Body $bytes
```

Python 範本會使用：

```bash
python scripts/report_handoff.py --base-url "http://127.0.0.1:5000" --project-id 1 --source codex --agent-name "Codex" --work-mode code-change --summary "請填寫本次完成內容"
```

`scripts/report_handoff.py` 會從 `.env` 的 `API_TOKEN`，或環境變數 `DEV_PILOT_API_TOKEN` 讀取 Token；也可以手動傳入 `--token`。它會用 UTF-8 JSON 呼叫 `/api/projects/{project_id}/handoff`。

### PowerShell 中文亂碼與 UTF-8 bytes

PowerShell 直接送 JSON 字串時，中文內容可能因預設編碼或主控台編碼不同而變成亂碼。把 JSON 先轉成 UTF-8 bytes，再用 `Content-Type: application/json; charset=utf-8` 傳送，可以讓 Flask 正確解析中文欄位，例如 `summary`、`test_result`、`next_steps`。

---

## 交接紀錄隱藏與還原

專案詳情頁的 AI 交接紀錄支援軟刪除。按下每筆紀錄右側的「隱藏」按鈕並確認後，DevPilot 會將該筆 `handoff_logs` 標記為隱藏，不會永久刪除資料，也不會清空資料庫。

預設畫面只會顯示未隱藏紀錄。若要清理或檢查測試交接紀錄：

1. 進入專案詳情頁。
2. 在「AI 交接紀錄」區塊按「顯示已隱藏紀錄」。
3. 已隱藏紀錄會出現「已隱藏」 badge，並顯示隱藏時間與原因。
4. 按「還原」即可將該筆紀錄恢復到一般列表。

首頁「最近 AI 交接紀錄」只會顯示未隱藏紀錄，因此測試資料可以先隱藏保留，不必刪除 DB。

### Hide / Restore API

隱藏交接紀錄：

```bash
curl -X PATCH http://127.0.0.1:5000/api/handoffs/123/hide \
  -H "Authorization: Bearer YOUR_TOKEN"
```

還原交接紀錄：

```bash
curl -X PATCH http://127.0.0.1:5000/api/handoffs/123/restore \
  -H "Authorization: Bearer YOUR_TOKEN"
```

成功時會回傳：

```json
{
  "ok": true,
  "handoff_id": 123,
  "message": "交接紀錄已隱藏"
}
```

---

## Google Antigravity 回寫支援

DevPilot 支援 Google Antigravity Agent 完成任務後回寫交接紀錄。專案詳情頁的「一鍵複製 AI 工具回寫指令」提供「複製 Antigravity PowerShell 回寫指令」按鈕，複製後可貼到 PowerShell 執行。

Antigravity 回寫欄位建議固定如下：

- `source=antigravity`
- `agent_name=Google Antigravity`
- `work_mode=agent-run`
- `summary` 填寫本次 Antigravity Agent 完成內容
- `completed_phases` 可先填 `["AI Agent 任務"]`

PowerShell 指令會使用 UTF-8 bytes 傳送 JSON，避免中文摘要、測試結果、下一步等欄位亂碼：

```powershell
$body = $payload | ConvertTo-Json -Depth 5
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "$ApiUrl/api/projects/$ProjectId/handoff" -Method Post -Headers @{ Authorization = "Bearer $ApiToken" } -ContentType "application/json; charset=utf-8" -Body $bytes
```

安全提醒：Antigravity / Agent 工具不可刪除 `.env`、不可刪除 `data/project_manager.db`、不可清空資料庫、不可動正式部署資料。完成後仍要回寫 handoff，讓 Codex / Claude / Cursor / Antigravity 的工作紀錄都留在 DevPilot。

## 一、本機啟動

```bash
cd devpilot_project_manager
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

瀏覽器開：

```text
http://127.0.0.1:5000
```

第一次啟動會自動建立：

```text
data/project_manager.db
```

並產生示範專案。

---

## 二、設定 API Token

請複製 `.env.example` 成 `.env`，修改：

```text
API_TOKEN=請改成很長的隨機Token
SECRET_KEY=請改成另一組隨機字串
DATABASE_PATH=data/project_manager.db
HOST=0.0.0.0
PORT=5000
FLASK_DEBUG=0
```

所有 `/api/*` 都必須帶：

```text
Authorization: Bearer YOUR_TOKEN
```

---

## 三、Synology NAS Docker 部署

把整個資料夾放到 NAS，例如：

```bash
/volume1/docker/devpilot-project-manager
```

SSH 進 NAS：

```bash
cd /volume1/docker/devpilot-project-manager
cp .env.example .env
vi .env
mkdir -p data
docker compose up -d --build
docker compose ps
docker compose logs -f
```

瀏覽器開：

```text
http://NAS_IP:5000
```

---

## 四、API 清單

### 1. 查所有專案

```bash
curl -s http://127.0.0.1:5000/api/projects \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 2. 查單一專案狀態

```bash
curl -s http://127.0.0.1:5000/api/projects/1/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3. Codex 回寫交接紀錄

```bash
curl -X POST http://127.0.0.1:5000/api/projects/1/handoff \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "codex",
    "agent_name": "Codex",
    "work_mode": "code-change",
    "summary": "完成第六階段 matches API",
    "completed_phases": ["第六階段"],
    "changed_files": ["app.py", "templates/matches.html"],
    "test_result": "測試通過",
    "git_status": "clean",
    "repo_branch": "main",
    "commit_sha": "none",
    "next_steps": "進行第七階段前端串接",
    "warnings": "未部署正式環境"
  }'
```

### 4. Claude 回寫交接紀錄

```bash
curl -X POST http://127.0.0.1:5000/api/projects/1/handoff \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "claude",
    "agent_name": "Claude Code",
    "work_mode": "review",
    "summary": "完成資料表設計審查，建議新增租金帳單模型",
    "completed_phases": ["資料庫設計"],
    "changed_files": [],
    "test_result": "設計審查完成，未修改程式碼",
    "git_status": "read-only",
    "repo_branch": "main",
    "commit_sha": "none",
    "next_steps": "由 Codex 建立 rent_billing_cycles、rent_invoices、rent_payments",
    "warnings": "此輪為架構建議，尚未實作"
  }'
```

### 5. 貼純文字交接紀錄並自動解析

```bash
curl -X POST http://127.0.0.1:5000/api/projects/1/handoff/parse \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "codex",
    "agent_name": "Codex",
    "raw_text": "第六階段 matches API：完成\n第七階段前端接正式 API：完成\n測試結果：console error = 0\n下一步：明天驗收"
  }'
```

---

## 五、給 Claude Code 的固定指令

把下面貼給 Claude Code：

```text
你是這個專案的開發助手。

每次開始前，請先呼叫專案管理系統 API 查詢目前狀態：

curl -s http://127.0.0.1:5000/api/projects/1/status \
  -H "Authorization: Bearer YOUR_TOKEN"

完成本次任務後，請呼叫專案管理系統 API 回寫交接紀錄：

curl -X POST http://127.0.0.1:5000/api/projects/1/handoff \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "claude",
    "agent_name": "Claude Code",
    "work_mode": "code-change",
    "summary": "請填寫本次完成內容",
    "completed_phases": ["請填寫完成階段"],
    "changed_files": ["請填寫修改檔案"],
    "test_result": "請填寫測試結果",
    "git_status": "請填寫 git status 結果",
    "repo_branch": "請填寫目前分支",
    "commit_sha": "請填寫 commit sha，若無則填 none",
    "next_steps": "請填寫下一步",
    "warnings": "請填寫注意事項"
  }'

規則：
1. source 固定填 claude。
2. 如果只是審查，work_mode 填 review。
3. 如果有修改程式，work_mode 填 code-change。
4. 如果只有測試，work_mode 填 test。
5. 如果有部署，work_mode 填 deploy。
6. 不要把 API Token 寫進 Git。
7. 完成後一定要回報 API 是否成功。
```

---

## 六、給 Codex 的固定指令

```text
之後這個專案請遵守以下規則：

1. 開工前先呼叫 DevPilot API 查詢專案狀態。
2. 開工前執行 git status、git pull、git log --oneline -5。
3. 不要修改 .env、正式資料庫、正式上傳資料。
4. 每完成一個階段，先備份 DB，再測試功能。
5. 每次收尾都要呼叫 DevPilot API 回寫交接紀錄。
6. 回寫內容需包含：source、agent_name、work_mode、summary、completed_phases、changed_files、test_result、git_status、repo_branch、commit_sha、next_steps、warnings。
7. 若 git status 有殘留 modified 或 untracked，不可直接覆蓋，要先回報。
8. 完成後 commit / push 前，先確認是否允許。
```

---

## 七、用 Python 小工具回寫

專案內附：

```text
scripts/report_handoff.py
```

範例：

```bash
python scripts/report_handoff.py \
  --base-url http://127.0.0.1:5000 \
  --token YOUR_TOKEN \
  --project-id 1 \
  --source claude \
  --agent-name "Claude Code" \
  --work-mode code-change \
  --summary "完成第三階段 API 串接" \
  --phase "第三階段" \
  --changed-file app.py \
  --test-result "測試通過" \
  --next-steps "進行前端串接" \
  --warnings "未部署正式環境"
```

這支工具會自動抓：

- git status
- branch
- commit sha

再送到 DevPilot API。

---

## 八、目前第一版限制

- 尚未做登入帳密，內網 / NAS 使用建議先靠防火牆與 API Token。
- SQLite 適合單人或小團隊使用；多人高併發後可升級 PostgreSQL。
- Claude / Codex 是否能真的執行 curl，取決於你當下使用的工具權限。
- API Token 請不要 commit 到 GitHub。
