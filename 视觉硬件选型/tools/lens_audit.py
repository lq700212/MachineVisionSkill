#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""库外型号核查工具。

背景（2026-11-20 事故）：
选型时用"数据库里没有"排除用户/客户提出的型号，属于循环论证——
库是候选池，不是全集。任何被提出的库外型号，必须先按本工具清单
去官网核查，再写结论；查过的型号留档到 hardware_database.json
的 external_candidates，避免重复调研。

用法：
  # 库内型号：直接判定
  python lens_audit.py --model M7528-MP --wd 300 --fov 24x19.2 \
      --pixel-size 3.45 --sensor 2/3

  # 库外型号：必须补齐官网参数，缺项会拒绝判定
  python lens_audit.py --model MVL-KF7528M-12MP --wd 300 \
      --fov 24x19.2 --pixel-size 3.45 --sensor 2/3 \
      --mod 500 --mag 0.176 --distortion 0.75 --sensor-support 1 \
      --resolution-mp 12

退出码：0=可用，1=需工程处理/有风险，2=不可用或参数不足
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lens_selector import LensSelector, lens_wd_status, format_wd_requirement


def parse_fov(s: str):
    parts = s.lower().replace('*', 'x').split('x')
    if len(parts) != 2:
        raise argparse.ArgumentTypeError('--fov 格式应为 24x19.2')
    return float(parts[0]), float(parts[1])


SENSOR_DIMS = {
    '1/3': (4.8, 3.6), '1/2': (6.4, 4.8), '1/1.8': (7.2, 5.4),
    '2/3': (8.45, 7.07), '1': (12.8, 9.6), '1.1': (14.14, 10.35),
    '1.2': (14.6, 12.63), '4/3': (17.3, 13.0),
}


def parse_sensor(s: str):
    """返回 (宽, 高) mm；未知返回 (0, 0)。"""
    key = str(s).replace('"', '').replace('英寸', '').strip()
    return SENSOR_DIMS.get(key, (0.0, 0.0))


def sensor_diag(s: str) -> float:
    w, h = parse_sensor(s)
    return (w * w + h * h) ** 0.5


def build_from_db(model: str):
    sel = LensSelector()
    for lens in sel.lenses:
        if lens.get('model') == model:
            return lens, 'main'
    try:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '..', 'config', 'hardware_database.json')
        with open(db_path, encoding='utf-8') as f:
            db = json.load(f)
        for item in db.get('external_candidates', []):
            if item.get('model') == model:
                return item, 'external_record'
    except Exception:
        pass
    return None, 'missing'


def main():
    ap = argparse.ArgumentParser(description='镜头库外型号核查')
    ap.add_argument('--model', required=True)
    ap.add_argument('--wd', type=float, required=True, help='项目工作距离 mm')
    ap.add_argument('--fov', type=parse_fov, required=True, help='视野 WxH mm')
    ap.add_argument('--pixel-size', type=float, required=True, help='相机像元 μm')
    ap.add_argument('--sensor', required=True, help='相机靶面，如 2/3')
    ap.add_argument('--pixel-per-precision', type=float, default=3.0)
    ap.add_argument('--precision', type=float, default=None,
                    help='设备精度 mm；不填则按像素精度上限反推一致性')
    ap.add_argument('--mod', type=float, default=None, help='库外型号：最近摄距 mm')
    ap.add_argument('--mag', type=float, default=None, help='库外型号：WD 处倍率')
    ap.add_argument('--distortion', type=float, default=None, help='库外型号：畸变 %%')
    ap.add_argument('--sensor-support', default=None, help='库外型号：支持靶面，如 2/3')
    ap.add_argument('--resolution-mp', type=float, default=None)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    lens, source = build_from_db(args.model)
    if lens is None:
        lens = {
            'model': args.model,
            'mod': args.mod,
            'working_distance': args.wd,
            'magnification': args.mag,
            'distortion': args.distortion,
            'supported_sensor_size': args.sensor_support,
            'resolution_mp': args.resolution_mp,
            'wd_range': [args.mod, None] if args.mod is not None else None,
            'verified': False,
        }
        source = 'user_supplied'

    missing = [k for k in ('mod', 'magnification', 'distortion',
                           'supported_sensor_size')
               if lens.get(k) is None]
    verdict, reasons = [], []

    # 1. 工作距离
    wd_status, wd_detail = lens_wd_status(lens, args.wd)
    if wd_status == 'ok':
        reasons.append(f'WD {args.wd:g}mm 在镜头可用范围 {format_wd_requirement(wd_detail)}')
    elif wd_status == 'too_close':
        verdict.append('blocked')
        reasons.append(f'WD {args.wd:g}mm < 最近工作距离 {format_wd_requirement(wd_detail)}，'
                       f'原生不合焦；需接圈（超规格，须实测畸变/MTF）或改 WD')
    elif wd_status == 'too_far':
        verdict.append('blocked')
        reasons.append(f'WD {args.wd:g}mm > 可用上限 {format_wd_requirement(wd_detail)}')
    else:
        verdict.append('unverified')
        reasons.append('缺 mod/wd_range，工作距离无法判定')

    # 2. 倍率窗口（与选型器同口径）
    mag = lens.get('magnification')
    if mag:
        w, h = args.fov
        sw, sh = parse_sensor(args.sensor)
        if sw <= 0 or sh <= 0:
            verdict.append('unverified')
            reasons.append(f'无法识别靶面 {args.sensor}')
        else:
            mag_max = min(sw / w, sh / h)
            mag_min = args.pixel_size / (1e3 * (args.precision or 99) / args.pixel_per_precision) \
                if args.precision else 0
            if mag < mag_min * 0.98:
                verdict.append('blocked')
                reasons.append(f'倍率 {mag}x < 精度下限 {mag_min:.3f}x')
            elif mag > mag_max * 1.02:
                verdict.append('blocked')
                reasons.append(f'倍率 {mag}x > 视野上限 {mag_max:.3f}x')
            else:
                reasons.append(f'倍率 {mag}x 落在窗口 [{mag_min:.3f}, {mag_max:.3f}]')
            obj_res = args.pixel_size / mag
            reasons.append(f'像素精度 {obj_res:.2f}μm')
            if args.precision:
                limit = args.precision * 1000 / args.pixel_per_precision
                if obj_res > limit:
                    verdict.append('blocked')
                    reasons.append(f'像素精度超上限 {limit:.2f}μm')

    # 3. 靶面覆盖
    support_w, support_h = parse_sensor(str(lens.get('supported_sensor_size') or ''))
    camera_w, camera_h = parse_sensor(args.sensor)
    support_d = (support_w ** 2 + support_h ** 2) ** 0.5
    camera_d = (camera_w ** 2 + camera_h ** 2) ** 0.5
    if support_d and camera_d:
        if camera_d > support_d:
            verdict.append('blocked')
            reasons.append(f'镜头靶面 {lens.get("supported_sensor_size")} 盖不住相机 {args.sensor}')
        else:
            reasons.append(f'靶面 {lens.get("supported_sensor_size")} 覆盖 {args.sensor}')

    # 4. 分辨率匹配
    if lens.get('resolution_mp') and camera_w and camera_h:
        camera_mp = camera_w * camera_h / ((args.pixel_size / 1000) ** 2) / 1e6
        if lens['resolution_mp'] < camera_mp * 0.8:
            verdict.append('risk')
            reasons.append(f'镜头标称 {lens["resolution_mp"]}MP < 相机约 {camera_mp:.1f}MP，'
                           f'需实测中心 MTF')

    # 5. 畸变
    dist = lens.get('distortion')
    if dist is not None:
        w = args.fov[0]
        err = dist / 100 * w / 2
        reasons.append(f'畸变 {dist}% → {w:g}mm 视场约 {err:.3f}mm 偏差')
        if args.precision and err > args.precision * 0.5:
            verdict.append('risk')
            reasons.append(f'畸变偏差超过设备精度 {args.precision:g}mm 的 50%，须标定校正')

    if missing and 'blocked' not in verdict:
        verdict.append('unverified')
        reasons.append('缺官网字段：' + '、'.join(missing) + '（必须查官网补齐后重跑）')

    if 'blocked' in verdict:
        concl = 'rejected'
        code = 2
    elif 'unverified' in verdict:
        concl = 'unverified'
        code = 2
    elif 'risk' in verdict:
        concl = 'usable_with_risk'
        code = 1
    else:
        concl = 'usable'
        code = 0

    result = {
        'model': args.model,
        'source': source,
        'verdict': concl,
        'reasons': reasons,
        'missing_fields': missing,
        'db_entry': None if source == 'user_supplied' else lens,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"型号: {args.model}  (来源: {source})")
        print(f"结论: {concl}")
        for r in reasons:
            print(f"  - {r}")
        if missing and concl == 'unverified':
            print("必查官网字段: 型号 / 焦距 / MOD / WD-倍率表 / 畸变 / 靶面 / 分辨率 / 接口")
    return code


if __name__ == '__main__':
    sys.exit(main())
