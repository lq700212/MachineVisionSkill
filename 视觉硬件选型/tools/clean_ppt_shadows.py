#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPT阴影清理工具
================
去除PPT中所有由外部工具误加的阴影效果（outerShdw等），恢复干净外观。

背景：历史版本流程中"母版合并"工具把源形状的阴影同步到了所有形状，
导致生成的PPT每个文本框都带阴影。本工具直接在XML层清除：
  - 幻灯片/版式/母版中所有 <a:effectLst> 内的效果
  - 主题样式不动（母版原生的样式保留）

用法：
  python clean_ppt_shadows.py 输入.pptx [-o 输出.pptx]
  不指定 -o 时覆盖原文件（先备份为 .bak）
"""

import os
import re
import shutil
import sys
import zipfile


def clean_pptx_shadows(input_path: str, output_path: str = None) -> dict:
    """清理pptx中的阴影效果，返回统计信息"""
    output_path = output_path or input_path
    stats = {'files_processed': 0, 'effects_removed': 0}

    if output_path == input_path:
        backup = input_path + '.bak'
        shutil.copy2(input_path, backup)
        print(f"已备份原文件: {backup}")

    tmp_path = output_path + '.tmp_clean'

    with zipfile.ZipFile(input_path, 'r') as zin:
        names = zin.namelist()
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                data = zin.read(name)
                # 幻灯片/版式/母版/备注才处理，主题和媒体不动
                if re.match(r'ppt/(slides|slideLayouts|slideMasters|notesSlides)/[^/]+\.xml$', name):
                    xml = data.decode('utf-8')
                    before = xml.count('outerShdw') + xml.count('innerShdw') + \
                             xml.count('prstShdw') + xml.count('reflection') + \
                             xml.count('glow')
                    if before > 0:
                        # 删除整个 <a:effectLst>...</a:effectLst> 块
                        xml = re.sub(r'<a:effectLst>.*?</a:effectLst>', '', xml, flags=re.S)
                        # 删除自闭合变体
                        xml = xml.replace('<a:effectLst/>', '')
                        after = xml.count('outerShdw') + xml.count('innerShdw') + \
                                xml.count('prstShdw') + xml.count('reflection') + \
                                xml.count('glow')
                        stats['effects_removed'] += before - after
                        stats['files_processed'] += 1
                    data = xml.encode('utf-8')
                zout.writestr(zin.getinfo(name), data)

    shutil.move(tmp_path, output_path)
    print(f"处理完成: {output_path}")
    print(f"  清理了 {stats['files_processed']} 个XML文件中的 "
          f"{stats['effects_removed']} 个阴影/发光/倒影效果")
    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description='PPT阴影清理工具')
    parser.add_argument('input', help='输入pptx路径')
    parser.add_argument('-o', '--output', help='输出路径（缺省覆盖原文件并备份）')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"文件不存在: {args.input}")
        sys.exit(1)

    clean_pptx_shadows(args.input, args.output)


if __name__ == '__main__':
    main()
