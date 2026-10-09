# 貢獻指南

## 分支

- `feat/*`：新功能
- `fix/*`：修 bug
- `docs/*`：文件變更

## Commit

- 格式：`<type>: <摘要>`（摘要用繁體中文）
- `type` ∈ `feat | fix | docs | chore | refactor | test`

## Hook

```sh
git config core.hooksPath .githooks
```

## 併入規則

- 程式碼變更走 PR，且 CI `check` 綠才合併。
- docs-only 可直推 `main`。
- private 方案無 branch protection，CI 紅＝停併。
