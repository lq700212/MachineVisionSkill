# MachineVisionSkill

机器视觉方向的 AI Skill 集合，兼容 ZCode / OpenCode 的 skills 机制。每个 skill 目录自包含（SKILL.md 使用说明 + 脚本 + 资产 + CHANGELOG 版本史），可独立安装使用。

## Skill 一览

| Skill | 说明 | 使用文档 |
|-------|------|----------|
| [视觉硬件选型](视觉硬件选型/) | 机器视觉选型专家：相机/镜头/光源自动选型计算、方案 PPT 生成、官网产品图自动获取 | [SKILL.md](视觉硬件选型/SKILL.md) |
| [视觉选型测试](视觉选型测试/) | 视觉硬件选型专用测试套件：回归 + 注入用例，开发迭代后一键全量验证 | [SKILL.md](视觉选型测试/SKILL.md) |
| [git自动提交推送](git自动提交推送/) | 本地工程一键 commit + push 到 GitHub，自动读 CHANGELOG 生成 commit message | [SKILL.md](git自动提交推送/SKILL.md) |
| [盖章专员](盖章专员/) | PDF 合同自动盖章：自动匹配现有印章的大小与位置 | [SKILL.md](盖章专员/SKILL.md) |

> 各 skill 的版本与变化记录见其目录内的 CHANGELOG.md。

## 安装

```bash
git clone https://github.com/lq700212/MachineVisionSkill.git
```

把需要的 skill 目录链接到客户端 skills 目录即可被识别（Windows 目录联接示例）：

```cmd
mklink /J "C:\Users\Administrator\.config\opencode\skills\视觉硬件选型" "D:\path\to\MachineVisionSkill\视觉硬件选型"
```

ZCode 用户也可链接到 `.agents\skills\`；直接复制目录同样可用。

## 版本管理约定

- **每个 skill 独立版本线**：版本与变化记录在各 skill 目录的 `CHANGELOG.md`（格式参考 Keep a Changelog），README 不标版本
- **本仓库不设仓库级 CHANGELOG**：集合仓库没有统一发版节奏，重复维护两份必然漂移；查"什么变了"直接看对应 skill 的 CHANGELOG
- commit message 以 skill 名开头，如 `视觉硬件选型: 新增三件套产品图替换`
- 需要发版语义时可用路径式 tag（monorepo 惯例）：`视觉硬件选型/v1.1.0`

## 仓库范围

本仓库按白名单跟踪 skill 目录（见 `.gitignore`）：当前只跟踪 `视觉硬件选型`、`视觉选型测试`、`git自动提交推送`、`盖章专员*`。新开发的 skill 需要入库时，在 `.gitignore` 加一行 `!目录名/` 并同步更新上表。
