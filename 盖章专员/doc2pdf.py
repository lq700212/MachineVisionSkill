#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Word(.doc/.docx)→PDF 转换（盖章专员 skill 内置脚本，v1.3.0 新增）。

定位：pdf_seal_stamper.py 只接受 PDF/图片/Excel，Word 合同先经本脚本转为
文本版 PDF，再走盖章管线（等价人工在 Word 中「另存为 PDF」）。

用法：
    python doc2pdf.py <Word文件.doc/.docx> [输出PDF]

    不指定输出时默认与源文件同目录的 `原名.pdf`；若该文件已存在则自动
    加后缀 `原名_转PDF.pdf`、`原名_转PDF2.pdf`……（永不覆盖已有文件，
    对齐本 skill"输出覆盖防护"的防线思想）。

实现要点（根因注释，写给下次排查的人）：
  - 必须走本机 Word COM（DispatchEx 独立进程 + SaveAs FileFormat=17），
    不用 python-docx/libreoffice 等第三方渲染——只有 Word 自己的导出能
    100% 还原分页/页眉页脚/文本框版式，且导出的 PDF 自带文字层。
  - COM 按 Office 进程默认目录解析相对路径：必须传 abspath，否则用户用
    相对路径调用时 Documents.Open 会打开失败（Excel 分支曾犯，见
    convert_excel_to_pdf 注释）。
  - COM 引用必须 finally 里 Close + Quit + 赋 None 三步缺一不可，否则
    WINWORD.EXE 进程残留锁住文件（Excel 分支事故档案）。
    注意 Word 的 Quit 偶发 RPC 错误（进程其实已退）：吞掉，不算失败。
  - 落盘判据必须用 pdfplumber 打开且页数>=1 才算写完——fitz(MuPDF) 对
    残缺 PDF 过度宽容（缺 /Root 也肯开），会把"没写完"误判成"写完了"
    （Excel 分支"No /Root object"事故教训）。
  - 模块顶部即把 stdout/stderr 重配为 utf-8：GBK 控制台打印中文/emoji
    会抛 UnicodeEncodeError 中断流程（v1.2.1 同类事故）。
"""

import os
import subprocess
import sys

# GBK 控制台打印中文/emoji 保命（v1.2.1 同类事故：UnicodeEncodeError 中断）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WORD_INPUT_EXTS = (".doc", ".docx")
PIP_MIRROR = "https://mirrors.aliyun.com/pypi/simple/"


def ensure_pywin32():
    """保证 win32com 可用。缺失则自动 pip 安装（阿里镜像），仍失败返回 False。

    约束：只在"确实缺失"时装；安装失败不阻塞报错链，调用方给手动兜底。
    """
    try:
        import win32com.client  # noqa: F401
        return True
    except Exception:
        pass
    print("  缺少 pywin32（Word COM 需要），自动安装中（阿里镜像源）...")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pywin32",
             "-i", PIP_MIRROR, "--quiet"],
            capture_output=True, timeout=300)
        if r.returncode != 0:
            print("  ⚠️  pywin32 自动安装失败："
                  + (r.stderr or b"").decode("utf-8", "replace")[-500:])
            return False
    except Exception as e:
        print(f"  ⚠️  pywin32 自动安装异常: {e}")
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except Exception as e:
        print(f"  ⚠️  pywin32 安装后仍不可用: {e}")
        return False


def pick_output_path(word_path, explicit):
    """确定转换输出路径。显式输出必须 .pdf 结尾；默认输出撞名自动加后缀。"""
    if explicit:
        if os.path.splitext(explicit)[1].lower() != ".pdf":
            print(f"❌ 输出必须是 .pdf 结尾，收到: {explicit}")
            return None
        return os.path.abspath(explicit)
    base = os.path.splitext(os.path.abspath(word_path))[0]
    cand = base + ".pdf"
    if not os.path.exists(cand):
        return cand
    i = 1
    while True:
        suffix = "_转PDF" if i == 1 else f"_转PDF{i}"
        cand = base + suffix + ".pdf"
        if not os.path.exists(cand):
            print(f"  ℹ️  默认输出已存在，改用: {cand}")
            return cand
        i += 1


def convert_word_to_pdf(word_path, out_pdf_path, wait_sec=60):
    """调用本机 Word COM 导出 PDF。失败抛 RuntimeError（信息即下一步指引）。"""
    if not ensure_pywin32():
        raise RuntimeError(
            "缺少 pywin32 且自动安装失败，请先手动执行：\n"
            f"  pip install pywin32 -i {PIP_MIRROR}\n"
            "或手动用 Word 打开该文档「另存为 PDF」，再把 PDF 交给盖章流程。")
    import time as _time

    import pdfplumber  # 判据用 pdfplumber（严格校验 xref，见模块 docstring）
    import win32com.client

    word = None
    doc = None
    try:
        # abspath：COM 按进程默认目录解析相对路径，相对路径必失败（曾犯）
        word_path_abs = os.path.abspath(word_path)
        out_pdf_abs = os.path.abspath(out_pdf_path)
        try:
            word = win32com.client.DispatchEx("Word.Application")
        except Exception as e:
            raise RuntimeError(
                "Word COM 不可用（可能本机未安装 Microsoft Word）："
                f"{e}\n兜底方案：请手动用 Word/WPS 打开该文档，执行"
                "「另存为 PDF」，再把生成的 PDF 交给盖章流程。")
        word.Visible = False
        word.DisplayAlerts = 0  # wdAlertsNone：防弹窗阻塞自动化
        try:
            # ConfirmConversions=False 防格式转换确认框；ReadOnly=True 防改源文件
            doc = word.Documents.Open(word_path_abs, False, True)
        except Exception as e:
            raise RuntimeError(f"Word 打开文档失败（文件损坏/加密/被占用？）: {e}")
        # 17 = wdFormatPDF，等价人工「另存为 PDF」
        doc.SaveAs(out_pdf_abs, 17)
        # 落盘防御性等待：正常同步写完；保留探针防杀软/慢磁盘锁
        ok, pages = False, 0
        deadline = _time.time() + wait_sec
        while _time.time() < deadline:
            if os.path.exists(out_pdf_abs) and os.path.getsize(out_pdf_abs) > 0:
                try:
                    with pdfplumber.open(out_pdf_abs) as probe:
                        pages = len(probe.pages)
                        if pages >= 1:
                            ok = True
                            break
                except Exception:
                    pass
            _time.sleep(0.5)
        if not ok:
            raise RuntimeError(
                f"Word 导出 PDF 超时未完成（{wait_sec}s），文件可能仍在写入: "
                f"{out_pdf_abs}")
        doc.Close(False)
        doc = None
        return pages
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Word COM 转换失败: {e}")
    finally:
        # 三步缺一不可，否则 WINWORD.EXE 残留锁文件（Excel 分支事故档案）；
        # Quit 的偶发 RPC 错误吞掉（进程其实已退，不算失败）
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass
            doc = None
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
            word = None


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("用法: python doc2pdf.py <Word文件.doc/.docx> [输出PDF]")
        print("  不指定输出时默认与源文件同目录的 原名.pdf（撞名自动加 _转PDF 后缀）")
        return 0 if len(argv) >= 2 else 1
    word_path = argv[1]
    explicit = argv[2] if len(argv) > 2 else None
    if not os.path.exists(word_path):
        print(f"❌ 文件不存在: {word_path}")
        return 1
    if os.path.splitext(word_path)[1].lower() not in WORD_INPUT_EXTS:
        print(f"❌ 本脚本只转换 Word 文档（.doc/.docx），收到: {word_path}")
        return 1
    out_path = pick_output_path(word_path, explicit)
    if out_path is None:
        return 1
    try:
        pages = convert_word_to_pdf(word_path, out_path)
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1
    print(f"转换成功: {out_path}")
    print(f"  页数: {pages}，大小: {os.path.getsize(out_path)} bytes")
    print("  后续可直接把该 PDF 交给 seal_workflow.py / pdf_seal_stamper.py 盖章")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
