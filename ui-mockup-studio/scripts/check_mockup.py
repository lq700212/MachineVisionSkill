#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_mockup.py —— UI 设计稿 HTML 的交付前核验（结构 + 完整性 + 离线可用）。

为什么要有这个脚本
------------------
设计稿最怕"看起来能打开、实际有坑"：编码坏了、div 没闭合、点了跳转目标不存在、
只有主界面没有弹窗、方案不足 4 套、引用了外网 CDN 到现场打不开。
这些用眼睛扫不出来，本脚本一次性断言完，全 PASS 才算交付。

检查清单
--------
  C1  文件存在且非空
  C2  严格 UTF-8 解码通过（不是 GBK / 不是混合编码）
  C3  无 U+FFFD 替换符（解码损坏的痕迹）
  C4  文件以 </html> 结尾（没被截断）
  C5  div 开闭标签平衡（剥离 script/style/注释后统计）
  C6  页面数 >= --min-pages（默认 1）
  C7  弹窗数 >= --min-dialogs（默认 0）
  C8  设计方案数 >= --min-variants（默认 4）
  C9  工作台核心结构存在（switchPage / openDialog / modal-layer / 视图按钮）
  C10 所有 data-go 目标都有对应 data-page（跳转不断链）
  C11 所有 data-open 目标都有对应 data-dialog
  C12 每个页面都有 data-title / data-group / data-w / data-h
  C13 动效关键帧存在（@keyframes sPageIn / sDlgIn）
  C14 无外链资源（script src / link href / @import / url(http...)）——保证离线可开
  C15 无未替换占位符（{{...}}）
  C16 弹窗 data-parent 指向存在的页面
  C17 data-stack 为 winforms / wpf（目标技术栈）
  C18 WinForms 与 WPF 两套落地映射卡都存在
  W1  页面缺 data-desc（右栏说明会空）
  W2  页面缺 data-galaxy（无法追溯 galaxy 参考来源）
  W3  页面声明了多状态但找不到对应 .state-block
  W4  文件带 UTF-8 BOM（可接受，仅提示）
  W5  页面级按钮 > 12 个（不含表格行内）——先合并/收纳
  W6  页面开关 > 5 个——检查是否该合并成模式选择
  W7  说明文字过长（data-desc > 60 字 / 单条要点 > 40 字）
  W8  图标按钮缺 title（用户猜不出图标含义）

用法
----
    python check_mockup.py Docs/ui_design_mockups.html
    python check_mockup.py Docs/ui_design_mockups.html --min-pages 8 --min-dialogs 5
    python check_mockup.py Docs/ui_design_mockups.html --json

退出码：0 = 全 PASS（WARN 不影响）；1 = 有 FAIL 或文件读不了。
"""

import argparse
import io
import json
import re
import sys


def strip_noise(html):
    """
    剥离注释 / script / style，只留真实 DOM 结构。
    为什么必须剥离：工作台 JS 里有大量 `<div class="...">` 字符串模板，
    直接数标签会把 JS 字符串算进去，造成假不平衡；注释里的示例属性也会造成假跳转。
    """
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", "", html, flags=re.S | re.I)
    return html


def parse_open_tags(html, tag):
    """提取指定标签的所有开标签（到第一个 '>' 为止），返回标签字符串列表。"""
    return re.findall(r"<" + tag + r"\b[^>]*>", html, flags=re.I)


def attrs(tag):
    """把开标签里的 key="value" 抽成 dict。"""
    return dict(re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', tag))


def main():
    ap = argparse.ArgumentParser(description="UI 设计稿 HTML 交付前核验")
    ap.add_argument("file", help="要检查的 HTML 文件")
    ap.add_argument("--min-pages", type=int, default=1, help="最少页面数（默认 1）")
    ap.add_argument("--min-dialogs", type=int, default=0, help="最少弹窗数（默认 0）")
    ap.add_argument("--min-variants", type=int, default=4, help="最少设计方案数（默认 4）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    results = []   # [(level, code, message)]
    def ok(code, msg): results.append(("PASS", code, msg))
    def fail(code, msg): results.append(("FAIL", code, msg))
    def warn(code, msg): results.append(("WARN", code, msg))

    # ---------- C1 文件存在 ----------
    try:
        with open(args.file, "rb") as f:
            raw = f.read()
    except OSError as ex:
        results.append(("FAIL", "C1", "文件读取失败：" + str(ex)))
        return emit(results, args.json)
    if not raw:
        fail("C1", "文件为空")
        return emit(results, args.json)
    ok("C1", "文件存在，%d 字节" % len(raw))

    # ---------- C2 严格 UTF-8 ----------
    try:
        text = raw.decode("utf-8")
        ok("C2", "严格 UTF-8 解码通过")
    except UnicodeDecodeError as ex:
        fail("C2", "不是合法 UTF-8（%s）；禁止用 GBK 保存" % ex)
        return emit(results, args.json)

    if raw.startswith(b"\xef\xbb\xbf"):
        warn("W4", "文件带 UTF-8 BOM（浏览器可识别，仅提示）")

    # ---------- C3 U+FFFD ----------
    n_bad = text.count("\ufffd")
    if n_bad:
        fail("C3", "存在 %d 个 U+FFFD 替换符，说明曾有编码损坏" % n_bad)
    else:
        ok("C3", "无 U+FFFD 替换符")

    # ---------- C4 结尾完整 ----------
    if text.rstrip().endswith("</html>"):
        ok("C4", "文件以 </html> 完整结尾")
    else:
        fail("C4", "文件未以 </html> 结尾，可能被截断")

    dom = strip_noise(text)

    # ---------- C5 div 平衡 ----------
    n_open = len(re.findall(r"<div\b", dom, flags=re.I))
    n_close = len(re.findall(r"</div\s*>", dom, flags=re.I))
    if n_open == n_close:
        ok("C5", "div 开闭平衡（%d / %d）" % (n_open, n_close))
    else:
        fail("C5", "div 不平衡：开 %d / 闭 %d" % (n_open, n_close))

    # ---------- 页面与弹窗元数据 ----------
    pages = []
    for tag in parse_open_tags(dom, "section"):
        a = attrs(tag)
        if "page" in a.get("class", "").split():
            pages.append(a)
    page_ids = [p.get("data-page", "") for p in pages if p.get("data-page")]

    dialogs = []
    for tag in parse_open_tags(dom, "div"):
        a = attrs(tag)
        if "data-dialog" in a:
            dialogs.append(a)
    dialog_ids = [d.get("data-dialog", "") for d in dialogs if d.get("data-dialog")]

    # ---------- C6 / C7 数量 ----------
    if len(page_ids) >= args.min_pages:
        ok("C6", "页面数 %d（要求 >= %d）" % (len(page_ids), args.min_pages))
    else:
        fail("C6", "页面数 %d < 要求 %d" % (len(page_ids), args.min_pages))

    if len(dialog_ids) >= args.min_dialogs:
        ok("C7", "弹窗数 %d（要求 >= %d）" % (len(dialog_ids), args.min_dialogs))
    else:
        fail("C7", "弹窗数 %d < 要求 %d" % (len(dialog_ids), args.min_dialogs))

    # ---------- C8 方案数 ----------
    variants = sorted(set(re.findall(r'data-variant="([a-z0-9]+)"', dom)))
    if len(variants) >= args.min_variants:
        ok("C8", "设计方案 %d 套：%s" % (len(variants), ", ".join(variants)))
    else:
        fail("C8", "设计方案只有 %d 套（%s），要求 >= %d 套且覆盖全部页面"
                  % (len(variants), ", ".join(variants) or "无", args.min_variants))

    # ---------- C9 核心结构 ----------
    core = {
        "switchPage": "function switchPage" in text,
        "openDialog": "function openDialog" in text,
        "modal-layer": 'id="modalLayer"' in text or "modal-layer" in text,
        "视图切换": 'data-view="overview"' in text and 'data-view="flow"' in text,
        "总览生成": "function buildOverview" in text,
        "跳转图生成": "function buildFlow" in text,
    }
    missing = [k for k, v in core.items() if not v]
    if not missing:
        ok("C9", "工作台核心结构齐全（页面/弹窗/总览/跳转图/视图切换）")
    else:
        fail("C9", "缺少核心结构：" + "、".join(missing))

    # ---------- C10 / C11 跳转完整性 ----------
    go_targets = [x for x in re.findall(r'data-go="([^"]*)"', dom)]
    bad_go = sorted(set(t for t in go_targets if t not in page_ids))
    if bad_go:
        fail("C10", "data-go 目标不存在：%s（已定义页面：%s）"
                    % ("、".join(bad_go), "、".join(page_ids)))
    else:
        ok("C10", "data-go 跳转全部有目标（%d 条）" % len(go_targets))

    open_targets = re.findall(r'data-open="([^"]*)"', dom)
    bad_open = sorted(set(t for t in open_targets if t not in dialog_ids))
    if bad_open:
        fail("C11", "data-open 目标不存在：%s（已定义弹窗：%s）"
                    % ("、".join(bad_open), "、".join(dialog_ids)))
    else:
        ok("C11", "data-open 弹窗全部有定义（%d 条）" % len(open_targets))

    # ---------- C12 页面元数据 ----------
    bad_meta = []
    for p in pages:
        pid = p.get("data-page", "(无id)")
        lack = [k for k in ("data-title", "data-group", "data-w", "data-h") if not p.get(k)]
        if lack:
            bad_meta.append("%s 缺 %s" % (pid, "/".join(lack)))
    if bad_meta:
        fail("C12", "页面元数据不全：" + "；".join(bad_meta))
    else:
        ok("C12", "每个页面都有 title/group/宽/高")

    # ---------- C13 动效 ----------
    lacks = [k for k in ("@keyframes sPageIn", "@keyframes sDlgIn") if k not in text]
    if lacks:
        fail("C13", "缺少动效关键帧：" + "、".join(lacks))
    else:
        ok("C13", "页面/弹窗入场动效关键帧存在")

    # ---------- C14 离线可用 ----------
    ext = []
    ext += re.findall(r'<script\b[^>]*\bsrc\s*=\s*"https?://[^"]+"', text, flags=re.I)
    ext += re.findall(r'<link\b[^>]*\bhref\s*=\s*"https?://[^"]+"', text, flags=re.I)
    ext += re.findall(r"@import\s+url\(\s*['\"]?https?://", text, flags=re.I)
    ext += re.findall(r"url\(\s*['\"]?https?://", text, flags=re.I)
    if ext:
        fail("C14", "存在 %d 处外链资源，离线环境会打不开：%s" % (len(ext), ext[0][:80]))
    else:
        ok("C14", "无外链资源，单文件离线可打开")

    # ---------- C15 占位符 ----------
    left = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if left:
        fail("C15", "占位符未替换：%s" % "、".join(sorted(set(left))))
    else:
        ok("C15", "无未替换占位符")

    # ---------- C16 弹窗父页 ----------
    bad_parent = []
    for d in dialogs:
        par = d.get("data-parent")
        if par and par not in page_ids:
            bad_parent.append("%s -> %s" % (d.get("data-dialog", "?"), par))
    if bad_parent:
        fail("C16", "弹窗 data-parent 指向不存在的页面：" + "；".join(bad_parent))
    else:
        ok("C16", "弹窗父页引用有效")

    # ---------- C17 / C18 两栈支持 ----------
    m_stack = re.search(r'data-stack="([^"]*)"', text)
    stack = (m_stack.group(1) if m_stack else "").strip()
    if stack in ("winforms", "wpf"):
        ok("C17", "目标技术栈声明有效：%s" % stack)
    else:
        fail("C17", "data-stack 缺失或非法（应为 winforms / wpf）：%r" % stack)

    miss_map = [k for k in ('id="mapWfList"', 'id="mapWpfList"') if k not in text]
    if miss_map:
        fail("C18", "缺少落地映射卡：" + "、".join(miss_map) + "（WinForms 与 WPF 两套必须同时内置）")
    else:
        ok("C18", "WinForms / WPF 两套落地映射卡都存在")

    # ---------- W1 / W2 / W3 ----------
    no_desc = [p.get("data-page", "?") for p in pages if not p.get("data-desc")]
    if no_desc:
        warn("W1", "页面缺 data-desc（右栏说明会空）：" + "、".join(no_desc))
    else:
        ok("W1", "每个页面都有一句话说明")

    no_galaxy = [p.get("data-page", "?") for p in pages if not p.get("data-galaxy")]
    if no_galaxy:
        warn("W2", "页面缺 data-galaxy（无法追溯设计参考）：" + "、".join(no_galaxy))
    else:
        ok("W2", "每个页面都标注了 galaxy 参考分类")

    bad_state = []
    for p in pages:
        states = [s.strip() for s in (p.get("data-states") or "").split(",") if s.strip()]
        if len(states) <= 1:
            continue
        pid = p.get("data-page", "?")
        # 页面 section 内部找 .state-block[data-for=...]
        m = re.search(r'<section\b[^>]*data-page="' + re.escape(pid) + r'".*?</section>',
                      dom, flags=re.S)
        seg = m.group(0) if m else ""
        for s in states:
            if ('data-for="' + s + '"') not in seg:
                bad_state.append("%s 缺 %s" % (pid, s))
    if bad_state:
        warn("W3", "声明了状态但没有对应 .state-block：" + "；".join(bad_state))
    else:
        ok("W3", "页面状态声明与 state-block 对应")

    # ---------- W5 / W6 信息预算：按钮与开关的减法护栏 ----------
    # 表格行内的"更多/编辑"不算页面级按钮，否则任何表格页都会误报；
    # 统计前先剥掉 <table>...</table>。
    over_btn, over_sw = [], []
    for p in pages:
        pid = p.get("data-page", "?")
        m = re.search(r'<section\b[^>]*data-page="' + re.escape(pid) + r'".*?</section>', dom, flags=re.S)
        seg = m.group(0) if m else ""
        seg = re.sub(r"<table\b.*?</table>", "", seg, flags=re.S | re.I)
        n_btn = len(re.findall(r"<button\b", seg, flags=re.I))
        n_sw = len(re.findall(r'class="[^"]*\bswitch\b[^"]*"', seg, flags=re.I))
        if n_btn > 12:
            over_btn.append("%s(%d)" % (pid, n_btn))
        if n_sw > 5:
            over_sw.append("%s(%d)" % (pid, n_sw))
    if over_btn:
        warn("W5", "页面级按钮超过 12 个，先合并/收纳再交付：" + "、".join(over_btn))
    else:
        ok("W5", "页面级按钮数量在预算内（<=12，不含表格行内）")
    if over_sw:
        warn("W6", "页面开关超过 5 个，检查是否该合并成模式选择：" + "、".join(over_sw))
    else:
        ok("W6", "页面开关数量在预算内（<=5）")

    # ---------- W7 说明文字预算：描述要言简意赅 ----------
    long_desc, long_pt = [], []
    for p in pages:
        pid = p.get("data-page", "?")
        desc = p.get("data-desc", "") or ""
        if len(desc) > 60:
            long_desc.append("%s(%d字)" % (pid, len(desc)))
        for pt in (p.get("data-points") or "").split("|"):
            pt = pt.strip()
            if len(pt) > 40:
                long_pt.append("%s: %s…" % (pid, pt[:16]))
                break
    if long_desc or long_pt:
        warn("W7", "说明文字偏长（desc<=60字、单条要点<=40字）：" + "；".join(long_desc + long_pt))
    else:
        ok("W7", "页面说明与要点言简意赅")

    # ---------- W8 图标按钮必须有 title，否则用户猜不出含义 ----------
    no_tip = []
    for tag in re.findall(r"<button\b[^>]*>", dom, flags=re.I):
        if "icon-btn" in tag and "title=" not in tag:
            no_tip.append(re.sub(r"\s+", " ", tag)[:70])
    if no_tip:
        warn("W8", "图标按钮缺 title（用户猜不出图标含义）：" + "；".join(no_tip[:3]))
    else:
        ok("W8", "图标按钮都有 title 提示")

    return emit(results, args.json)


def emit(results, as_json):
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    passes = [r for r in results if r[0] == "PASS"]

    if as_json:
        print(json.dumps({
            "ok": not fails,
            "pass": len(passes),
            "fail": len(fails),
            "warn": len(warns),
            "items": [{"level": l, "code": c, "message": m} for l, c, m in results],
        }, ensure_ascii=False, indent=2))
    else:
        for level, code, msg in results:
            print("[%s] %-4s %s" % (level, code, msg))
        print("")
        print("结果：PASS %d / FAIL %d / WARN %d" % (len(passes), len(fails), len(warns)))
        if fails:
            print("结论：不合格，逐条修复 FAIL 后复跑。")
        else:
            print("结论：合格。WARN 人工过目即可。" if warns else "结论：全部通过。")

    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
