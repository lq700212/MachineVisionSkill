# AGENTS.md — skills 仓库开发规范（改任何 skill 前必读）

本目录是 opencode 各 skill 的集中存放地，同时是一个**独立的 git 仓库**
（`.git` 就在 `C:\Users\Administrator\.config\opencode\skills\`）。只要改动其中
任何一个 skill（代码/文档/测试），就是在改这个仓库，**收尾时必须保证仓库内
文档一致**。

## ⛔ 铁律（每次改动都必须执行，无需用户提醒）

**改完 skill 后，必须在根目录 `CHANGELOG.md` 顶部追加本次记录**，内容固定为
"给 git commit 用"的总览：

1. **改动了哪些 skill**（本次涉及的所有 skill，一个不漏地列出）
2. **每个 skill 改了什么**：版本号 + 要点（一句话到几行，够写 commit message）
3. **验证结论**：测试/回归是否通过、验收基线
4. **可直接用的 commit message 建议**

追加位置：根目录 `CHANGELOG.md` 的顶部（时间倒序，最新的在最上面）。详细版本
历史仍写在各 skill 目录自己的 `CHANGELOG.md`，根目录文件只做总览——两者都要更。

自检口诀：**"git log 只能看到这行 commit，后人能不能看出我改了哪个 skill、改
了什么？"** 不能 → 把要点补进根目录 CHANGELOG.md。

## .gitignore 白名单机制（新增文件/目录极易漏进 git）

- 根 `.gitignore` 是**白名单模式**：`/*` 忽略所有根条目，再逐个 `!` 放行
  需跟踪的 skill 目录与根文件。
- **新增的根目录文件（如新的 CHANGELOG 类文档）或新 skill 目录，必须手动在
  `.gitignore` 加 `!路径` 放行**，否则 `git status` 完全不显示、提交时静默漏掉
  （CHANGELOG.md 就踩过：创建后曾因未放行而不可见）。
- 当前已放行的根文件：`README.md`、`CHANGELOG.md`；已放行的 skill 目录：
  视觉硬件选型 / 视觉选型测试 / git自动提交推送 / 盖章专员。
- `盖章专员/**/*.png|jpg|jpeg|gif|bmp` 被忽略（防误传公司公章），新增同类图片注意。

## 历史教训（每次提交前扫一眼）

| 教训 | 根因 | 正确做法 |
|------|------|----------|
| commit message 不能只写日期+范围（如"2026-09-03（本次·视觉选型）"） | 没有遵循 CHANGELOG 中已有的 commit message 建议，信息量低 | **必须使用 CHANGELOG 中的"建议 commit message"**，或以此为基础提炼出实质摘要 |

## 收尾清单（每次改完 skill 后检查一遍）

- [ ] 各 skill 目录内：代码/文档/测试已改，`CHANGELOG.md` 已更新
- [ ] 根目录 `CHANGELOG.md` 顶部已追加本次记录（哪些 skill + 各改了什么 + 验证 + commit message）
- [ ] 新增文件/目录已检查 `git status` 是否可见（`.gitignore` 白名单放行）
- [ ] 无需用户提醒即可执行以上三条（本文件即固化规则，任何会话开始即载入）