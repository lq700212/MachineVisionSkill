# AGENTS.md — winforms-ui-debug skill 维护规范（改本 skill 前必读）

## 改动流程

1. 改 SKILL.md 前先确认改的是"通用方法论"还是"项目案例"：通用方法（harness、
   三大工具、DPI）直接改正文；单个项目的血泪/对照窗体/路径一律下沉到对应小节
   或附录 A，不许把某项目的硬编码写进正文（V1.0.0 合并时修过三份全写
   AgingTestSystem 的旧坑，见 SKILL 附录 B）。
2. 改完必须同步两处文档：本目录 `CHANGELOG.md`（`[Unreleased]` 或新版本节）、
   skills 根目录 `CHANGELOG.md` 顶部（本次总览 + 建议 commit message，
   见根 `AGENTS.md` 收尾清单）；
3. 版本号：新增通用章节/脚本 → 升 minor；修 bug/补案例 → 升 patch；
   新增适用项目 → 升 minor 并在附录 A 加一行。
4. 附录 A 保鲜：凡改动涉及某项目构建输出/对照窗体，同步改附录 A 对应行；
   新项目开工发现附录 A 无本行时按表头补一行（SKILL §十二有同样约定；
   各项目 AGENTS 里也各有一句同步责任，三处互为备份）。

## 改脚本后必跑的验证（无需用户提醒）

1. Python 版：`python -m py_compile scripts/*.py`；
2. PowerShell 版：必须 **UTF-8 带 BOM**（PS 5.1 无 BOM 按 ANSI 解析中文会语法错误）——
   写完后断言头三字节 `EF BB BF`；另跑 `powershell -NoProfile -Command` 做语法解析
   （`[Parser]::ParseFile` 无报错）；
3. 参数校验三态：启动模式缺 `--exe` 必报错、附加模式缺 `--process` 必报错、
   `--help` 正常打印（无需真启动 exe，用不存在的 `--exe` 看报错文案即可）。

## 分工红线（防职责漂移）

- 本 skill 只管"界面渲染/布局问题定位"；回归测试归各项目自己的测试 skill
  （AgingTestSystem 的 agingtest-regression、CommandCenter 的 commandcenter-test），
  两边互相引用不抢活。
- `scripts/` 只放"取证工具"（矩形枚举/截图），不放断言式回归探针——后者跟项目版本走，
  放各项目自己的测试目录。
- PrintWindow 与真实截图是互补关系（选用表在 SKILL §十末尾），不要删掉任何一边，
  也不要把"一律用某一种"的绝对化表述写回来。
