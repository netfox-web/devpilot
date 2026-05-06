# 測試紀錄

已在產出環境做以下檢查：

- `python -m py_compile app.py scripts/report_handoff.py`
- Flask test client 呼叫：
  - `GET /api/projects`
  - `GET /api/projects/1/status`
  - `POST /api/projects/1/handoff`

結果：API Token 驗證、專案查詢、Claude 回寫交接紀錄皆可正常運作。

注意：ZIP 內不附正式資料庫。第一次啟動會自動建立 `data/project_manager.db` 並產生示範專案。
