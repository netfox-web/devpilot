# DevPilot 專案開發管家

## Repo / Worktree / Deploy 三層架構

DevPilot 用 `project_repos` 記錄每個專案的三層路徑：

- `repo_path`：Git repo，例如 `/volume1/repos/{slug}`
- `worktree_path`：AI 實際修改程式的位置，例如 `/volume1/worktrees/{slug}`
- `deploy_path`：Docker runtime 位置，例如 `/volume1/docker/{slug}`

安全原則：

- AI 只能修改 `/volume1/worktrees/*`
- Docker 目錄是 runtime，不要直接在 `/volume1/docker/*` 寫 code
- 不要刪除或覆蓋 `data`、`uploads`、`output`、`backup`、`backups`
- 需要部署時，先在 worktree 修改、commit，之後再透過部署流程更新 Docker 目錄並執行 `docker compose up -d`

### 從 Docker 服務建立 Project + Repo + Worktree

在 `/docker-scan` 每個未綁定的 Docker service 可按「建立專案 + Repo」，或呼叫 API：

```bash
curl -X POST http://211.75.219.184:5010/api/docker-services/1/bootstrap-project \
  -H "Authorization: Bearer YOUR_TOKEN"
```

流程：

1. 從 `docker_services` 讀取 `container_name`、`deploy_path`、`compose_path`、`ports`、`image`
2. 以既有 project、`deploy_path` 最後一層資料夾或 container name 推 project name
3. 若尚未綁定 project，自動建立 DevPilot project
4. 建立 `/volume1/repos/{slug}` 與 `/volume1/worktrees/{slug}`
5. 若 `deploy_path` 內有 `app.py`、`package.json`、`requirements.txt`、`src/`、`public/`，會初始化本機 repo 並建立第一個 commit
6. 建立 worktree，更新 `project_repos`，並把 `docker_services.project_id` 綁到新專案

匯入時會排除 `.git`、`data`、`uploads`、`output`、`backup`、`backups`、`node_modules`、`.venv`、`*.db`，避免把 runtime 資料與資料庫放進 repo。

### Repo 狀態

```bash
curl http://211.75.219.184:5010/api/projects/1/repo-status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

此 API 會讀取 worktree/repo 的 `git status --porcelain`、目前 branch 與 `rev-parse HEAD`，更新 `repo_status`、`branch`、`last_commit`。

這是一套給多專案、多電腦、多 AI 工具使用的「專案開發進度中控台」。

支援來源：

- Codex
- Claude / Claude Code
- Cursor
- Antigravity（Google Agent）
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

## 一鍵複製 AI 工具回寫指令（DEV_PILOT_API_URL）

每個專案詳情頁會顯示「**一鍵複製 AI 工具回寫指令**」卡片，含 **Claude、Codex、Cursor、Antigravity** 的 PowerShell 範本與 Python 範本。卡片上會顯示目前 **回寫目標 API**，其來自環境變數 **`DEV_PILOT_API_URL`**（由執行 DevPilot（Flask）時載入的 `.env` 提供）；**有設定則優先使用該值**，未設定則預設 `http://127.0.0.1:5000`。

提供的按鈕包含：

- 複製 Claude PowerShell 回寫指令
- 複製 Codex PowerShell 回寫指令
- 複製 Cursor PowerShell 回寫指令
- 複製 Antigravity PowerShell 回寫指令
- 複製 Python 回寫指令（`scripts/report_handoff.py`）

按下按鈕後，完整指令會複製到剪貼簿，不會跳轉頁面。PowerShell 會帶入目前專案 ID、`$ApiUrl`（同上 `DEV_PILOT_API_URL`）、`source`、`agent_name`、`work_mode` 與 **API Token**（來自 `API_TOKEN`）。頁面不直接顯示 Token，但複製內容會含 Token。

### 部署到 NAS 後要打哪台 API？

DevPilot 若跑在 NAS（例如 **`http://211.75.219.184:5010`**），請在 **NAS 容器／主機的 `.env`** 以及 **每一台會執行 AI 回寫的開發機 `.env`** 皆設定：

```text
DEV_PILOT_API_URL=http://211.75.219.184:5010
```

如此一來，專案詳情頁一鍵複製的指令、以及 `report_handoff.py` 預設 `--base-url`，都會對 **NAS 上的 DevPilot** 送 `POST /api/projects/{id}/handoff`，**Claude、Codex、Cursor、Antigravity** 行為一致。

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
python scripts/report_handoff.py --project-id 1 --source codex --agent-name "Codex" --work-mode code-change --summary "請填寫本次完成內容"
```

`--base-url` **未指定時**優先使用 `.env` 的 **`DEV_PILOT_API_URL`**，再退回 `http://127.0.0.1:5000`。`scripts/report_handoff.py` 會從 `.env` 的 `API_TOKEN`，或環境變數 `DEV_PILOT_API_TOKEN` 讀取 Token；也可以手動傳入 `--token`。它會用 UTF-8 JSON 呼叫 `/api/projects/{project_id}/handoff`。

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
# 請將基底 URL 改為與 DEV_PILOT_API_URL 相同（NAS 例如 http://211.75.219.184:5010）
curl -X PATCH http://127.0.0.1:5000/api/handoffs/123/hide \
  -H "Authorization: Bearer YOUR_TOKEN"
```

還原交接紀錄：

```bash
# 請將基底 URL 改為與 DEV_PILOT_API_URL 相同（NAS 例如 http://211.75.219.184:5010）
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
# 一鍵複製回寫 / report_handoff 預設 API 基底；NAS 請填對外網址，例如：
# DEV_PILOT_API_URL=http://211.75.219.184:5010
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
http://NAS_IP:對外埠
```

對外埠依 `docker-compose.yml` 或反代設定（範例：`http://211.75.219.184:5010`）。**AI 回寫**請在 `.env` 設定 **`DEV_PILOT_API_URL`** 與該對外網址一致，勿仍用本機 `127.0.0.1`。

### NAS Docker 掃描匯入（唯讀）

主選單 **「NAS Docker 掃描」**（`/docker-scan`）可針對已在「部署主機」建好的目標（須填 `ssh_host` / `ssh_user`）經 **SSH** 拉取：

- `find {docker_root} -maxdepth 3 -name docker-compose.yml -print`
- `docker ps -a --format '{{json .}}'`
- （可選）對每個容器 `docker inspect <容器ID>` — 僅讀取 metadata

**設計上不包含** `rm`、`docker stop`、`docker restart`、`docker compose down`／`up` 等指令；**不會停止、刪除或變更 NAS 上任何容器**。

掃描結果寫入資料表 `docker_scan_runs`、`docker_services`。若容器目錄、`compose` 路徑或既有 `project_deployments` 記錄與專案相符，會**嘗試自動帶入 `project_id`**；否則為 **未綁定專案**，可在同一頁下拉選單手動綁定（會建立或更新 `project_deployments`）。

**API：**

- `POST /api/deployment-targets/{target_id}/scan-docker`（JSON 可選 `{ "docker_root": "/volume1/docker" }`，需 `Authorization: Bearer TOKEN`）
- `PATCH /api/docker-services/{service_id}/bind-project`（JSON：`project_id`、`environment`）

**建議：** 每個專案在 NAS 的目錄統一為 **`/volume1/docker/{project_name}`**，方便掃描與手動對應。**勿**讓自動化／AI 工具執行會刪除 **`/volume1/docker`**、清空 **data volume**，或刪除 **data / uploads / backup / output** 等目錄的命令。

---

## 四、API 清單

下列 `curl` 範例以 `http://127.0.0.1:5000` 表示**本機開發**；若 DevPilot 在 NAS，請將整段基底改為你的 **`DEV_PILOT_API_URL`**（例如 `http://211.75.219.184:5010`）。

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

把下面貼給 Claude Code（若 DevPilot 在 NAS，`127.0.0.1:5000` 請改成與 **`DEV_PILOT_API_URL`** 相同位址）：

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

## 八、AI 心跳追蹤串接

DevPilot 可接收 Codex / Claude / Cursor / Antigravity 或外部 AI 心跳追蹤系統送來的狀態，讓儀表板與專案詳情頁顯示 AI 是否在線、正在跑什麼任務。

### 1. 回報 AI 心跳

API：

```text
POST /api/ai-heartbeats
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json; charset=utf-8
```

範例：

```powershell
$payload = @{
  source = "codex"
  agent_name = "Codex"
  project_id = 1
  project_name = "DevPilot 專案開發管家"
  machine_name = $env:COMPUTERNAME
  status = "running"
  current_task = "部署 DevPilot 到 NAS"
  last_message = "正在執行 docker compose up -d --build"
  pid = "$PID"
  session_id = "codex-$PID"
}
$body = $payload | ConvertTo-Json -Depth 5
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/ai-heartbeats" -Method Post -Headers @{ Authorization = "Bearer YOUR_TOKEN" } -ContentType "application/json; charset=utf-8" -Body $bytes
```

狀態欄位支援：

- `idle`：閒置
- `running`：執行中
- `error`：錯誤
- `offline`：工具主動回報離線
- `done`：任務完成

### 2. 查詢心跳

```bash
curl http://127.0.0.1:5000/api/ai-heartbeats \
  -H "Authorization: Bearer YOUR_TOKEN"
```

可用 query 篩選：

```text
/api/ai-heartbeats?project_id=1
/api/ai-heartbeats?source=codex
/api/ai-heartbeats?status=running
```

### 3. 顯示規則

- 首頁「AI 心跳狀態」會顯示最近 10 筆心跳。
- 專案詳情頁會顯示「此專案 AI 活動」。
- 超過 5 分鐘沒有回報時，畫面會顯示 `offline` badge；資料庫原本的 `status` 不一定會被改寫。

### 4. 與外部 AI 心跳系統串接

外部系統只要定期呼叫 `POST /api/ai-heartbeats` 即可。建議同一個 AI 執行階段固定帶入 `session_id`，DevPilot 會用 `source + agent_name + machine_name + session_id` 更新同一筆；若沒有 `session_id`，則使用 `source + agent_name + machine_name + project_id` 更新。

專案詳情頁提供「複製 AI 心跳回報指令」，可直接複製 Codex / Claude / Cursor / Antigravity 的 PowerShell 範本。PowerShell 請使用 UTF-8 bytes 送出 JSON，避免中文任務名稱或最後訊息亂碼。

安全提醒：AI Agent 工具不可刪除 `.env`、不可刪除 `data/project_manager.db`、不可清空資料庫、不可動正式部署資料。

---

## 九、目前第一版限制

- 尚未做登入帳密，內網 / NAS 使用建議先靠防火牆與 API Token。
- SQLite 適合單人或小團隊使用；多人高併發後可升級 PostgreSQL。
- Claude / Codex 是否能真的執行 curl，取決於你當下使用的工具權限。
- API Token 請不要 commit 到 GitHub。
## 服務端點掃描 / 前後台網址探測

DevPilot 可在 **NAS Docker 掃描**（`/docker-scan`）頁面，針對已掃入的 `docker_services` 解析對外 port，產生例如 `http://211.75.219.184:5010` 的 base URL，並探測固定少量候選路徑。

- 前台：`/`、`/home`、`/index`
- 後台：`/admin`、`/dashboard`、`/backend`、`/manage`、`/console`
- 登入：`/login`、`/admin/login`
- API / Health：`/api`、`/api/projects`、`/api/health`、`/health`
- 文件：`/docs`、`/swagger`、`/openapi.json`

探測會優先使用 `HEAD`，必要時才用 `GET`，timeout 3 秒，redirect 最多 3 次。它只記錄狀態碼、final URL 與 HTML title，不送帳密、不登入、不提交表單、不爆破、不做高頻掃描。

API：

```bash
curl -X POST http://211.75.219.184:5010/api/docker-services/1/scan-endpoints \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X POST http://211.75.219.184:5010/api/docker-services/scan-endpoints-all \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## AI 派工（dispatch）

DevPilot 支援從專案頁把任務派給 AI 工具，第一版先提供安全的 demo pipeline：

1. DevPilot 讀取 `project_repos` 的 `worktree_path` 與 `deploy_path`。
2. 模擬派工給 `codex` 或 `cursor`。
3. 在 worktree 寫入 `.devpilot_last_task.txt`，記錄任務與時間。
4. 若 `auto_deploy=true`，使用 `rsync -av` 從 worktree 同步到 deploy path，並執行 `docker compose up -d`。

API：

```bash
curl -X POST http://211.75.219.184:5010/api/projects/1/dispatch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent":"codex","task":"修正 API /api/orders 500 錯誤","auto_deploy":false}'
```

安全規則：

- AI 修改範圍應限制在 `worktree_path`。
- `rsync` 不使用 `--delete`。
- `rsync` 固定排除 `.env`、`data/`、`uploads/`、`output/`、`backup/`、`backups/` 與 `*.db`。
- 不執行 `docker compose down`，不刪除 deploy path，不清空資料庫。
- 部署前請確認 container 有權限存取 worktree、deploy path，且環境具備 `rsync` 與 `docker compose`。

掃描結果會寫入 `service_endpoints`。在 `/docker-scan` 可將端點標記為前台、後台、API 或忽略；專案詳情頁會顯示已綁定 Docker 服務的未忽略網址，已確認的網址會優先排序。首頁「服務網址狀態」會統計已偵測網址數、`200 OK`、需要確認與無法連線數量。
---

## 多環境部署（Production / Staging / Backup）

DevPilot 以同一台 disney NAS 模擬三個環境：

- Production：`/volume1/docker`
- Staging：`/volume1/docker-staging`
- Backup：`/volume1/backups`

專案頁會顯示每個 project 推導出的 Production / Staging / Backup 路徑。Production 優先使用 `project_repos.deploy_path`，Staging 與 Backup 會用同一個 project slug 產生對應路徑。

部署 API：

```bash
curl -X POST http://211.75.219.184:5010/api/projects/1/deploy-staging \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source":"codex","task":"AI 完成 worktree 修改後部署 staging"}'

curl -X POST http://211.75.219.184:5010/api/deployment-jobs/123/approve \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes":"人工驗收通過"}'

curl -X POST http://211.75.219.184:5010/api/projects/1/deploy-production \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id":123}'
```

規則：

- AI 只能直接 deploy staging。
- `deploy-production` 必須帶入狀態為 `approved` 的 production deployment job，否則 API 會回 403。
- Staging 部署成功後，DevPilot 會建立一筆 pending production job，等人工核准。
- 預設只同步檔案到目標環境；若確定不會與既有 container name / port 衝突，可傳 `run_compose=true` 才執行 `docker compose up -d`。
- 部署使用 `rsync -av`，不使用 `--delete`，並固定排除 `.env`、`data/`、`uploads/`、`output/`、`backup/`、`backups/` 與 `*.db`。
- 若設定 `TELEGRAM_BOT_TOKEN` 與 `TELEGRAM_CHAT_ID`，部署完成後會送 Telegram 通知；未設定時會安全略過。

建議流程：

```text
AI 修改 worktree
↓
deploy staging
↓
health check
↓
Telegram 通知
↓
人工核准 production job
↓
deploy production
```

---

## Gemini reviewer / tester

DevPilot 支援在 dispatch job 指定 Gemini：

```bash
curl -X POST http://211.75.219.184:5010/api/dispatch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id":1,"provider":"google","task_role":"reviewer","task":"分析 API log 並產生測試案例"}'
```

Gemini 只允許 `task_role=reviewer` 或 `task_role=tester`。任務內容只能是 API 分析、log 分析、測試案例產生與驗收結果整理。禁止 Gemini 任務執行 SSH、Docker、deploy、刪除或修改檔案。

環境變數：

```text
GEMINI_API_KEY=
GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent
```

不要把 `.env` commit 到 Git，也不要把 repo、DB、密鑰或完整 source code 傳給 Gemini。

---

## Gemini staging 驗收與 rollback

Staging 部署完成後，DevPilot 會建立 validation report，並可呼叫：

```bash
curl -X POST http://211.75.219.184:5010/api/deployment-jobs/123/validate-staging \
  -H "Authorization: Bearer YOUR_TOKEN"
```

驗收只傳 HTTP / endpoint 摘要給 Gemini，不傳整個 repo、DB 或機密。若未設定 `GEMINI_API_KEY`，DevPilot 會用精簡 HTTP 檢查做 fallback，仍會寫入 `validation_reports`。

結果：

- `pass`：job 進入 `waiting_approval`，可人工核准 production。
- `fail`：job 標記 `failed`，若有 snapshot 則嘗試 rollback。

Production deploy 前會建立 snapshot：

```text
/volume1/backups/{project}/snapshot_YYYYMMDD_HHMMSS
```

Rollback API：

```bash
curl -X POST http://211.75.219.184:5010/api/deployment-jobs/123/rollback \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Rollback 只允許操作該 project 的 deploy path，snapshot 必須位於 `/volume1/backups`。不允許刪除 `/volume1/docker`，且會保留 `.env`、`data`、`uploads`、`output`、`backup`、`backups` 等資料夾。
---

## Codex CLI dispatch worker

DevPilot can queue real AI dispatch jobs and let a background worker run Codex in the configured project worktree. The first supported executable agent is `codex`.

Start the worker:

```bash
python orchestrator_worker.py
```

For local verification without invoking the real Codex CLI:

```bash
DEVPILOT_CODEX_MOCK=1 python orchestrator_worker.py
```

Create a dispatch job:

```bash
curl -X POST http://211.75.219.184:5010/api/dispatch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id":1,"agent":"codex","task_prompt":"Fix the failing API test","risk_level":"low"}'
```

Worker flow:

1. Polls queued `dispatch_jobs` every 10 seconds.
2. Runs only inside `project_repos.worktree_path`.
3. Calls `codex --help` before choosing CLI flags.
4. Records command output in `agent_runs`.
5. Runs `npm test`, `npm run build`, or `python -m py_compile app.py` when applicable.
6. Sets the job to `waiting_approval` after passing tests, or `failed` after errors.

Deploy staging after the worker passes:

```bash
curl -X POST http://211.75.219.184:5010/api/dispatch-jobs/123/deploy-staging \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Approve production:

```bash
curl -X POST http://211.75.219.184:5010/api/dispatch-jobs/123/approve-production \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Production deploy creates a snapshot first:

```text
/volume1/backups/{project_slug}/snapshot_YYYYMMDD_HHMMSS
```

Rollback:

```bash
curl -X POST http://211.75.219.184:5010/api/dispatch-jobs/123/rollback \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Safety rules:

- Codex may edit only the worktree.
- Do not edit `/volume1/docker` directly.
- Do not overwrite `.env`.
- Do not delete `data`, `uploads`, `output`, `backup`, or `backups`.
- Do not run `docker compose down`, `docker rm`, `docker rmi`, or `rm -rf /`.
- Staging and production deploy use rsync excludes for `.git`, `.env`, `data`, `uploads`, `backups`, `node_modules`, `.venv`, and `*.db`.

---

## API Key 管理中心

DevPilot 提供 `/api-keys` 後台頁面集中管理 AI、部署、Webhook 與第三方服務 Key。

功能：

- 新增 Key 名稱、分類、provider、狀態與版本，例如 `v1` / `v2`。
- 權限標籤支援 `read`、`write`、`deploy`、`ai`、`webhook`。
- Key value 使用 AES-256 加密後存入 SQLite，不以明文存放。
- 列表只顯示遮罩，例如 `sk-****abcd`。
- 只有 owner 可點「顯示值」，完整值顯示 10 秒後自動遮罩，並寫入 `api_key_audit_logs`。
- 「複製」不會把完整值顯示在 UI，但一樣會寫入 audit log。
- `revoke` 只把狀態改為 `revoked`，不會永久刪除資料。
- `api_key_usage` 可統計最近 7 日調用數。
- `.env` 匯入只讀取目前 `.env` 的 Key/Token/Secret/Webhook 類變數，加密匯入資料庫，不會覆蓋或修改 `.env`。

建議設定獨立加密金鑰：

```text
MASTER_KEY=
```

若未設定 `MASTER_KEY`，DevPilot 會相容讀取 `API_KEY_ENCRYPTION_KEY`；兩者都未設定時，才會用既有 `SECRET_KEY + API_TOKEN` 派生加密金鑰。正式環境建議固定設定 `MASTER_KEY`，避免日後更換 `SECRET_KEY` 或 `API_TOKEN` 後無法解密既有 Key。

安全注意：

- 不要把 Key value 貼到 handoff。
- 不要把 Key value 印到 log。
- 不要把 `.env` commit 到 Git。
- audit log 只記錄 action、key 名稱、版本、IP、User-Agent，不記錄 Key value。

### Enterprise lifecycle

Key lifecycle:

```text
create -> use -> rotate -> revoke
```

Additional controls:

- `environment`: `staging` or `production`.
- `rotation_days`: default 30 days.
- `last_rotated_at`: updated after each rotation.
- `usage_limit`: optional soft limit for monitoring.
- `ai_allowed`: AI agents may use only keys with `ai_allowed=1` and `environment=staging`.

Automatic rotation:

- DevPilot starts a background scheduler every 10 minutes.
- Active keys with `now - last_rotated_at > rotation_days` are rotated.
- Old versions in `api_key_versions` become `revoked`.
- New key material is encrypted with AES-256 and is not printed to logs or written to handoff.
- Rotation writes an audit log entry.

Anomaly detection:

- More than 100 requests per minute creates a `high_rate` alert.
- Hourly usage above 5x the 7-day hourly average creates a `volume_spike` alert.
- A new IP after previous known IPs creates an `unexpected_ip` alert.
- Reaching `usage_limit` creates a `usage_limit` alert.

Environment separation:

- Staging keys are allowed only for staging deploy and test/validation API paths.
- Production keys are allowed only for production/formal API paths.
- AI token role cannot create, rotate, reveal, or revoke API keys.
- AI token usage recording is allowed only for staging keys with `ai_allowed=1`.
- AI agents must never receive or use production keys.

---

## AI 成本控管與 fallback

DevPilot 提供 `/ai-costs` 後台頁面集中查看 OpenAI / Gemini / Claude 的估算用量、成本、budget 與 fallback 規則。成本欄位是 `estimated_cost`，用於控管與預警，不等於正式帳單。

資料表：

- `ai_providers`：provider 狀態、優先順序、預設模型、每 1k token 成本、每日/月 budget。
- `ai_usage_logs`：provider、model、project、dispatch job、task_role、token 數、估算成本、成功/失敗與錯誤摘要。
- `ai_fallback_rules`：依 task_role 設定 primary provider 與 fallback provider。

API：

```bash
curl http://211.75.219.184:5010/api/ai-costs \
  -H "Authorization: Bearer YOUR_TOKEN"

curl http://211.75.219.184:5010/api/ai-providers \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X PATCH http://211.75.219.184:5010/api/ai-providers/1 \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"active","default_model":"codex-cli","cost_input_per_1k":0.001,"cost_output_per_1k":0.003,"daily_budget":5,"monthly_budget":100}'

curl -X POST http://211.75.219.184:5010/api/ai-fallback-rules \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"primary_provider":"gemini","fallback_provider":"claude","task_role":"reviewer","enabled":true}'
```

模型選擇策略：

- `planner`：優先 Claude，fallback Gemini。
- `reviewer` / `tester`：優先 Gemini，fallback Claude。
- `executor`：優先 OpenAI / Codex，不自動 fallback 到低信任 provider。
- provider 若為 `disabled`、`error`、近期失敗或超過 `daily_budget`，會依規則選擇可用 fallback。
- `risk_level=high` 時，不會自動 fallback 到較低信任 provider，需人工確認。

安全限制：

- 不顯示 API key。
- 不存 prompt 全文，只存短摘要、token 數與錯誤摘要。
- 不把 key 寫進 handoff 或 log。
- 成本是估算值，請以各 provider 帳務後台為正式帳單依據。

---

## 商品影片 + 貼文發佈（安全版）

DevPilot 可在專案詳情頁建立商品內容工作流：

```text
商品資料
↓
Claude 產短影音 script（hook / 商品亮點 / CTA）
↓
Claude 產貼文文案（開頭吸引句 / 商品特色 3 點 / 優惠 / CTA）
↓
DevPilot 組 Kling prompt（場景 / 角色 / 語氣 / 字幕）
↓
Kling 生成 video_url
↓
寫入 content_jobs，專案頁顯示影片與文案預覽
↓
使用者手動按鈕發佈到 Facebook / LINE
```

資料表：

- `content_jobs.type=product_video`
- `title`：商品名稱
- `script`：Claude 產生或 fallback 產生的短影音腳本
- `prompt`：送給 Kling 的影片 prompt
- `provider=kling`
- `status`：`queued` / `running` / `done` / `failed`
- `output_url`：Kling 回傳的 `video_url`
- `post_text`：Claude 產生或 fallback 產生的貼文
- `post_status`：`draft` / `ready` / `published`
- `post_platform`：`facebook` / `line`
- `post_id`：平台回傳的貼文 ID

API：

```bash
curl -X POST http://211.75.219.184:5010/api/content/product-video \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "project_id": 1,
    "product_name": "濕紙巾",
    "features": ["台灣製", "80抽", "RO純水"],
    "target": "媽媽族群",
    "style": "促銷 / 溫馨 / 快速"
  }'
```

手動發佈：

```bash
curl -X POST http://211.75.219.184:5010/api/content/123/publish/facebook \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X POST http://211.75.219.184:5010/api/content/123/publish/line \
  -H "Authorization: Bearer YOUR_TOKEN"
```

環境變數：

```text
CLAUDE_API_URL=
CLAUDE_API_KEY=
KLING_API_URL=
KLING_API_KEY=
FACEBOOK_PUBLISH_API_URL=
FACEBOOK_ACCESS_TOKEN=
LINE_PUBLISH_API_URL=
LINE_NOTIFY_TOKEN=
```

若 Claude 未設定，DevPilot 會使用安全的本機模板產生 script；若 Kling 未設定，工作會停在 `queued`，方便先驗證 UI 與資料流程。
Facebook / LINE token 未設定時，發佈 API 會回錯誤，不會自動改用其他方式發文。

安全限制：

- 不會自動發文，必須按「發佈到 Facebook」或「發佈到 LINE」。
- 不顯示 Claude / Kling / Facebook / LINE API key。
- 不把 key 寫入 `content_jobs`、`api_logs` 或 handoff。
- `api_logs` 只記錄 action、job id、平台與狀態，不記錄完整商品 prompt、文案或 access token。

---

## AI 客服：產業限制 + 知識庫 + 拒答

DevPilot 提供安全客服聊天 API：`POST /api/chat`。流程是先找 tenant 設定，再做 tenant 知識庫關鍵字檢索；找到知識才回答，找不到或命中產業禁答主題就回 fallback，不讓 AI 自由發揮。

資料表：

- `tenant_knowledge`
  - `tenant_id`
  - `type`: `faq` / `product` / `policy`
  - `content`
- `tenant_settings`
  - `tenant_id`
  - `industry`
  - `strict_mode`: `1` 時必須依知識庫回答
  - `fallback_message`
- `industry_templates`
  - `industry`: `retail` / `restaurant` / `clinic` / `legal`
  - `allowed_topics`
  - `blocked_topics`

聊天 API：

```bash
curl -X POST http://211.75.219.184:5010/api/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "tenant_id": 1,
    "tenant_name": "濕紙巾商城",
    "message": "濕紙巾有 RO 純水嗎？"
  }'
```

固定 prompt 模板：

```text
你是 {tenant_name} 客服。

你只能回答以下內容：

{knowledge}

如果問題不在範圍內：
請回：
「不好意思，這個問題我無法回答，請聯繫客服人員」
```

安全規則：

- `strict_mode=1` 時，沒有命中 `tenant_knowledge` 就拒答。
- 命中 `industry_templates.blocked_topics` 就拒答。
- 回答內容只取自命中的 knowledge，不組合未知資訊。
- `api_logs` 只記錄 tenant、是否拒答與原因，不記錄完整對話內容。

---

## 今日早報 / 每日任務早報

DevPilot 可產生每日任務早報，彙整專案數、待處理任務、逾期任務、AI 心跳、Docker 服務與最近交接紀錄。

API：

```bash
curl -X POST http://211.75.219.184:5010/api/reports/daily/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{}'

curl http://211.75.219.184:5010/api/reports/daily/latest \
  -H "Authorization: Bearer YOUR_TOKEN"
```

首頁會顯示「今日早報」卡片；尚未產生時會提示可呼叫 `POST /api/reports/daily/generate`。

若 `TELEGRAM_BOT_TOKEN` 或 `TELEGRAM_CHAT_ID` 未設定，產生早報仍會成功，Telegram 傳送結果會標記為 skipped，不會讓 API 報錯。所有時間使用 DevPilot 的 `now_str()`，在 NAS Docker 內應為 `Asia/Taipei`。
# Cloudflare Batch Domain Setup Tool

`cf_batch.py` is a standalone Cloudflare API Token based batch tool for managing an AI service provider domain matrix from `domains.csv`.

Safety status:

- Default mode is dry-run. Omitting `--apply` will not write to Cloudflare.
- Real execution requires separate approval and both `--apply` and `--confirm-real-write` for write-capable commands.
- Do not run this tooling as part of a production deploy flow.
- `all` is highest-risk because it can create zones, DNS records, redirect rules, and SSL setting changes.
- Generated CSV files must follow `docs/generated_artifacts_policy.md` and must not be committed from the repo root.
- `domains.csv` is not yet approved as a commit-ready source of truth; fix encoding and CSV quoting in a separate review first.

## Files

- `cf_batch.py`: batch CLI tool
- `domains.csv`: domain matrix
- `.env.example`: environment variable template
- `cloudflare-result.csv`: generated execution or dry-run report
- `nameserver-update-list.csv`: registrar nameserver change checklist
- `requirements.txt`: Python dependencies

## Install

```bash
python -m pip install -r requirements.txt
```

Required packages for this tool:

```txt
requests
python-dotenv
pandas
dnspython
```

## Configure environment values

The tool reads system environment variables first. If those values are already set in the shell, CI, or host environment, no `.env` file is required.

Use `.env` only as a local fallback. To use it, copy `.env.example` to `.env` and fill only the Cloudflare API Token values needed for real execution:

```env
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=

DEFAULT_MAIN_TARGET=
DEFAULT_APP_TARGET=
DEFAULT_API_TARGET=

DEFAULT_PARKING_TARGET=aioffice.com.tw
DEFAULT_SSL_MODE=full
DEFAULT_PROXIED=true
```

Use a Cloudflare API Token, not a Global API Key. The token should be scoped for zone creation, DNS edit, zone settings edit, and rulesets edit as needed. If required values are missing from both system environment variables and `.env`, real execution stops with a configuration error.

At startup, the CLI prints an environment preflight summary. It shows only `present` / `missing` and masks `CLOUDFLARE_ACCOUNT_ID`; it never prints the Cloudflare API Token.

## Edit `domains.csv`

CSV columns:

```csv
domain,type,target,main_target,app_target,api_target,proxied,ssl_mode,category,note
```

`type` can be:

- `main`: creates or updates `@`, `www`, `app`, and `api` CNAME records.
- `redirect`: creates basic DNS and a 301 redirect to `target`.
- `parking`: same as redirect; if `target` is empty, uses `DEFAULT_PARKING_TARGET`.

`category` is optional and backward compatible. It is used only for the AI Office Brand Matrix classification and report visibility; it does not change Cloudflare API behavior.

## Dry-run

Dry-run is the default and never writes to Cloudflare:

```bash
python cf_batch.py all
```

Other dry-run commands:

```bash
python cf_batch.py add-zone
python cf_batch.py setup-dns
python cf_batch.py setup-redirects
python cf_batch.py setup-ssl
python cf_batch.py verify
```

`--dry-run` may still be passed explicitly for clarity.

## Real execution

Real execution is not part of production deploy. It requires a separate approval for the exact command and target domains.

After reviewing `cloudflare-result.csv`, run real commands explicitly with both `--apply` and `--confirm-real-write`:

```bash
python cf_batch.py add-zone --apply --confirm-real-write
python cf_batch.py setup-dns --apply --confirm-real-write
python cf_batch.py setup-redirects --apply --confirm-real-write
python cf_batch.py setup-ssl --apply --confirm-real-write
python cf_batch.py verify --apply
```

Or run everything:

```bash
python cf_batch.py all --apply --confirm-real-write
```

`all` is highest-risk and can create Cloudflare zones, create or update DNS records, create or update redirect rules, and update SSL mode. The tool does not delete DNS records by default. Existing matching records are updated; missing records are created.

## Report

`cloudflare-result.csv` columns:

```csv
domain,category,type,target,zone_id,zone_status,cloudflare_nameserver_1,cloudflare_nameserver_2,cloudflare_nameservers,current_nameservers,nameserver_status,dns_status,redirect_status,ssl_status,proxied_status,error_message
```

The tool also writes `nameserver-update-list.csv` for registrar work:

```csv
domain,cloudflare_nameserver_1,cloudflare_nameserver_2,status,note
```

If `nameserver_status=pending_nameserver_update`, Cloudflare has not yet become authoritative for that domain. Update nameservers at the registrar to the Cloudflare assigned nameservers shown in `cloudflare_nameserver_1` and `cloudflare_nameserver_2`, then re-run:

```bash
python cf_batch.py verify
```

## Safety

- API Token is read from system environment variables or `.env`; it is never hard-coded.
- Real-write commands require both `--apply` and `--confirm-real-write`.
- `verify --apply` is read-only against Cloudflare but still uses a token and writes local report CSV files.
- Dry-run writes only the local result CSV files.
- Generated CSV files should not be committed directly; follow `docs/generated_artifacts_policy.md`.
- No DNS record deletion is implemented.
- Cloudflare API errors are recorded in `cloudflare-result.csv`.
- Missing required environment values stop real execution.
