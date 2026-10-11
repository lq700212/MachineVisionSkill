# -*- coding: utf-8 -*-
"""quote_check：内部报价文档核验。交付/发出前必跑，全 PASS 才算完。

检查项（任一 FAIL 即打回）：
  1) 必备节：项目输入/工价/工作量/报价/利润/风险/待决策/纪律
     +（转换理由｜复用说明）：有参考程序写前者，纯新写后者（--scope 决定不了，靠关键字二选一）
  2) 工价有据：含“置信度/来源/样本”或“本地验证”字样（防编工价）
  3) 两本账：含“现场”天数表述且“两本账/纯代码/不可控/二次进场”纠偏（防 9 天式乐观）
  4) 范围排他：含“不含”+ 范围关键字（--scope：plc=PLC，vision=相机/视觉，
     mes=MES/接口，general=范围/边界）（防范围蔓延）
  5) 对外禁语：标题含“对外”且不含“对内”的节内不得出现 AI转/用AI/prompt/行对行
  6) 数字一致：报价节内表行金额之和 == 合计（排除合计行自身；防加总错误）
  7) 编码：文件必须是严格 UTF-8 可解码

用法：python quote_check.py "内部报价_xxx.md" [--scope plc]
退出码 0=全过，1=有 FAIL。
"""
import argparse
import re
import sys

NEED_SECTIONS = ["项目输入", "工价", "工作量", "报价", "利润", "风险", "待决策", "纪律"]
NEED_ONE_OF = ["转换理由", "复用说明"]
BANNED_IN_PUBLIC = ["AI转", "用AI", "用 AI", "prompt", "Prompt", "行对行"]
SCOPE_KEYS = {
    "plc": ["PLC"],
    "vision": ["相机", "视觉", "镜头", "光源"],
    "mes": ["MES", "接口", "CIM"],
    "general": ["范围", "边界", "不含"],
}


def section_of(lines, idx):
    """找到第 idx 行所属的节标题（最近的上方 # 标题）"""
    for j in range(idx, -1, -1):
        if lines[j].startswith("#"):
            return lines[j]
    return ""


def main():
    ap = argparse.ArgumentParser(description="内部报价文档核验")
    ap.add_argument("doc", help="内部报价文档 .md 路径")
    ap.add_argument("--scope", default="plc", choices=list(SCOPE_KEYS),
                    help="项目范围类型（决定排他关键字）")
    args = ap.parse_args()
    try:
        with open(args.doc, encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        print("FAIL 编码：非严格 UTF-8（终端 GBK 显示是假象，以此为准）")
        return 1
    except OSError as e:
        print(f"FAIL 读文件：{e}")
        return 1

    fails = []

    def check(name, ok, hint=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"：{hint}" if hint and not ok else ""))
        if not ok:
            fails.append(name)

    check("必备节齐全", all(k in text for k in NEED_SECTIONS),
          "缺：" + "、".join(k for k in NEED_SECTIONS if k not in text))
    check("重构或复用说明", any(k in text for k in NEED_ONE_OF),
          "既无转换理由又无复用说明：有参考写前者，纯新写后者")
    check("工价有据", any(k in text for k in ["置信度", "来源", "样本", "本地验证"]),
          "工价节无来源/置信度/样本字样=编工价嫌疑")
    check("两本账", ("现场" in text) and any(k in text for k in ["两本账", "纯代码", "不可控", "二次进场"]),
          "无现场拆分=9天式乐观重犯")
    check("范围排他", ("不含" in text) and any(k in text for k in SCOPE_KEYS[args.scope]),
          f"无‘不含…{ '/'.join(SCOPE_KEYS[args.scope])}…’排他条款=范围蔓延等着被白嫖")

    lines = text.split("\n")
    public_chunks = []
    cur_public = False
    buf = []
    for ln in lines:
        if ln.startswith("#"):
            if cur_public and buf:
                public_chunks.append("\n".join(buf))
                buf = []
            cur_public = ("对外" in ln) and ("对内" not in ln)
        elif cur_public:
            buf.append(ln)
    if cur_public and buf:
        public_chunks.append("\n".join(buf))
    bad = [w for w in BANNED_IN_PUBLIC if w in "\n".join(public_chunks)]
    check("对外无禁语", not bad, "对外节出现禁语：" + "、".join(bad))

    # 数字一致：报价节内“|…| N.N 万”表行求和（排除含“合计”的行），对合计 **X万**
    quote_rows = []
    for i, ln in enumerate(lines):
        m = re.match(r"^\|.*\|\s*([\d.]+)\s*万", ln)
        if m and "报价" in section_of(lines, i):
            if "合计" not in ln:
                quote_rows.append(float(m.group(1)))
    total_m = re.search(r"合计[^0-9]*\*\*([\d.]+)\s*万\*\*", text)
    if total_m and quote_rows:
        total = float(total_m.group(1))
        s = round(sum(quote_rows), 2)
        check("数字一致", abs(total - s) < 0.05, f"合计 {total}万 vs 分项和 {s}万")
    else:
        check("数字一致", False, "没找到合计/报价节分项数字，格式跑偏")

    print(f"结论：{len(fails)} FAIL" if fails else "结论：全 PASS，可发出")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
