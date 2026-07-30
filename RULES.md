# 项目规则

## 版本号规则

采用语义化版本号 `vMAJOR.MINOR.PATCH`，但本项目**只在末尾 (PATCH) 递增**：

- ✅ 新功能、修复、优化 → 升级 PATCH（末尾 +1）
- ❌ 不升级 MINOR（中间段）
- ❌ 不升级 MAJOR（首段）

示例：
```
v2.5.2 → v2.5.3   ← 新功能/修复，正确
v2.5.2 → v2.6.0   ← ❌ 错误，禁止
v2.5.2 → v3.0.0   ← ❌ 错误，禁止
```

查看当前最新版本：
```bash
git tag --sort=-v:refname | head -1
```

打新 tag：
```bash
# 1. 末尾 +1
NEW_TAG=$(git tag --sort=-v:refname | head -1 | awk -F. '{print $1"."$2"."$3+1}')
# 2. 推送 tag
git push origin $NEW_TAG
```