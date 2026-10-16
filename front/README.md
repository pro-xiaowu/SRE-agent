# SRE-Agent 值班台（Vue 3）

目录：仓库根下的 `front/`（不是 `frontend-design`）。

先起后端，再起前端：

```bash
# 应用机，项目根目录，.env 已配好
unset VIRTUAL_ENV
uv run sre-agent serve
```

默认 API + `/metrics` 在 `http://127.0.0.1:9108`。

另开终端：

```bash
cd front
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。Vite 会把 `/api` 代理到 `:9108`。
