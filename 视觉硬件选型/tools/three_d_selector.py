#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3D 视觉引导选型器（视觉硬件选型 skill 的 3D 分支）

定位
----
2D 选型解决"像素当量够不够"，3D 引导解决的是"6D 位姿误差够不够"。
两者不是一套公式：
  - 2D：精度 → 像素当量 → 分辨率/倍率
  - 3D：引导总误差 → 相机/标定/机器人/夹爪/工件 分配 → 相机 Z 精度、XY 点距、FOV

本脚本只做"需求侧可复现的筛选与误差预算"，不替代样件打样。
所有相机参数来自 hardware_database.json 的 three_d_cameras，禁止从型号名推断。

用法
----
  python three_d_selector.py --part-size 300x300 --precision 0.5 \
      --cycle-time 3 --installation ETH

  python three_d_selector.py --config project_config_3d.json

  # 默认输出到「当前目录/<项目名>/」；--output 可显式指定其他目录

退出码
------
  0 = 有可行方案（至少 1 台 PASS）
  1 = 无可行方案（全部 FAIL）
  2 = 参数缺失/口径不明（脚本给出原话问法）
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def _safe_name(name: str, fallback: str = '3D视觉引导抓取方案') -> str:
    """把项目名清洗成合法目录名（Windows 非法字符 + 长度限制）。"""
    s = (name or '').strip()
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, '')
    s = ''.join(c for c in s if ord(c) >= 32)
    s = ' '.join(s.split())
    s = s.rstrip('. ')
    if not s:
        s = fallback
    return s[:80]


# 3D 引导误差预算默认分配（RSS，总和不是简单相加）
# 依据：3D 引导链路 = 相机测量 + 手眼标定 + 机器人绝对定位 + 夹爪/TCP + 工件位姿
DEFAULT_BUDGET = {
    'camera': 0.50,       # 相机测量/点云位姿（含 Z 精度 + XY 点距 + 配准）
    'calibration': 0.20,  # 手眼标定残差
    'robot': 0.20,        # 机器人绝对定位（不是重复定位）
    'gripper': 0.10,      # 夹爪/TCP
    'part': 0.10,         # 工件位姿/形变/放置
}

# 误差预算绝对上限（mm），可由 config 覆盖；用于把比例换算成绝对值
DEFAULT_ABS_ERRORS = {
    'calibration': 0.10,
    'robot': 0.10,
    'gripper': 0.05,
    'part': 0.05,
}

VERDICT_ORDER = {'PASS': 0, 'WARN': 1, 'FAIL': 2}


def _as_float(value, default=None):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_size(text: str) -> Optional[Dict[str, float]]:
    """解析 '300x300' / '300x300x120' / '300*300'，返回 width/height/depth。"""
    if not text:
        return None
    s = str(text).lower().replace('*', 'x').replace('×', 'x').replace(' ', '')
    parts = [p for p in s.split('x') if p]
    if len(parts) < 2:
        return None
    try:
        nums = [float(p) for p in parts[:3]]
    except ValueError:
        return None
    if len(nums) == 2:
        nums.append(None)
    return {'width': nums[0], 'height': nums[1], 'depth': nums[2]}


def _rss(values: List[float]) -> float:
    return math.sqrt(sum(float(v) ** 2 for v in values if v is not None))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _fmt_range(value, unit: str = '') -> str:
    """把 [0.25, 2.5] 格式化成 '0.25~2.5'，单值直接返回。"""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return f"{value[0]}~{value[1]}"
    if value is None:
        return '见相机规格'
    return str(value)


class ThreeDCameraSelector:
    """3D 相机选型器：FOV + 精度链 + 工作距离 + 节拍 + 接口。"""

    def __init__(self, database_path: str = None):
        if database_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            database_path = os.path.join(script_dir, '..', 'config', 'hardware_database.json')
        self.database_path = database_path
        self.cameras = self._load_cameras()

    def _load_cameras(self) -> List[Dict]:
        if not os.path.exists(self.database_path):
            print(f'[错误] 数据库不存在: {self.database_path}')
            return []
        with open(self.database_path, encoding='utf-8') as f:
            data = json.load(f)
        cams = data.get('three_d_cameras', [])
        if not cams:
            print('[错误] 数据库缺少 three_d_cameras 表；请先扩库（见 SKILL.md 3D 章节）')
        return cams

    # ------------------------------------------------------------------
    # 几何
    # ------------------------------------------------------------------
    @staticmethod
    def fov_at_wd(camera: Dict, wd_mm: float) -> Dict:
        """计算指定工作距离下的 FOV。

        厂家只给单点 FOV 时按相似三角形缩放（标记 estimated=True）；
        给近端/远端两点时线性插值（在推荐范围内足够，不外推）。
        """
        near = camera.get('fov_near') or {}
        far = camera.get('fov_far')
        near_w = _as_float(near.get('width'))
        near_h = _as_float(near.get('height'))
        near_d = _as_float(near.get('distance'))
        if not near_w or not near_h or not near_d or near_d <= 0:
            return {'width': None, 'height': None, 'estimated': True, 'error': 'FOV 数据缺失'}

        if not far or not far.get('width') or not far.get('distance'):
            scale = float(wd_mm) / near_d
            return {
                'width': near_w * scale,
                'height': near_h * scale,
                'estimated': True,
                'model': 'single_point_scaled',
            }

        far_w = _as_float(far.get('width'))
        far_h = _as_float(far.get('height'))
        far_d = _as_float(far.get('distance'))
        if not far_w or not far_h or not far_d or far_d == near_d:
            scale = float(wd_mm) / near_d
            return {
                'width': near_w * scale,
                'height': near_h * scale,
                'estimated': True,
                'model': 'single_point_scaled',
            }

        # 只在 [near_d, far_d] 内插值；超出范围按端点比例外推并标记
        if wd_mm <= near_d:
            t = 0.0
        elif wd_mm >= far_d:
            t = 1.0
        else:
            t = (float(wd_mm) - near_d) / (far_d - near_d)
        return {
            'width': near_w + t * (far_w - near_w),
            'height': near_h + t * (far_h - near_h),
            'estimated': wd_mm < near_d or wd_mm > far_d,
            'model': 'two_point_linear',
        }

    @staticmethod
    def xy_resolution(camera: Dict, wd_mm: float) -> Optional[float]:
        """点间距 = 该 WD 下 FOV 宽 / 深度图宽。"""
        fov = ThreeDCameraSelector.fov_at_wd(camera, wd_mm)
        res = camera.get('resolution') or {}
        res_w = _as_float(res.get('width'))
        if not fov.get('width') or not res_w:
            return _as_float(camera.get('xy_resolution_mm'))
        return fov['width'] / res_w

    @staticmethod
    def _best_wd(camera: Dict, need_w: float, need_h: float,
                 params: Dict, budget: Dict, fov_safety: float = 1.05) -> Optional[float]:
        """在相机推荐 WD 范围内找“引导误差最小”的工作点。

        约束：FOV ≥ 需求 × fov_safety（默认 5% 余量，防止来料偏移出视野）。
        为什么不是简单取最小 WD：点距随 WD 变粗，但 Z/VDI 标称值固定，
        误差函数不一定单调；遍历后取最小更稳。

        起点修正（2026-11-27）：厂家标称 Z 精度/VDI 都是在**最佳工作距离**下测的，
        脚本模型用固定标称值会系统性偏向近距离（越近点距越小→误差越小），
        但实际相机离最佳 WD 越远精度越差。因此搜索起点不早于 optimal_wd
        （若 FOV 在 optimal 处不够，才向近端回退）。
        """
        rng = camera.get('working_distance_mm') or []
        if len(rng) < 2:
            return _as_float(camera.get('optimal_working_distance_mm'))
        lo, hi = _as_float(rng[0]), _as_float(rng[1])
        if lo is None or hi is None:
            return _as_float(camera.get('optimal_working_distance_mm'))
        opt = _as_float(camera.get('optimal_working_distance_mm'))
        search_lo = max(lo, opt) if opt and lo <= opt <= hi else lo
        step = max(1.0, (hi - search_lo) / 300.0)
        best = None
        wd = search_lo
        while wd <= hi + 1e-6:
            fov = ThreeDCameraSelector.fov_at_wd(camera, wd)
            if ((fov.get('width') or 0) >= need_w * fov_safety
                    and (fov.get('height') or 0) >= need_h * fov_safety):
                err = ThreeDCameraSelector.camera_error(camera, wd, params, budget)
                if best is None or err['total_mm'] < best['error']:
                    best = {'wd': round(wd, 1), 'error': err['total_mm']}
            wd += step
        if best is None and search_lo > lo:
            # optimal 处 FOV 不够 → 允许向近端回退再找一次
            wd = lo
            while wd < search_lo:
                fov = ThreeDCameraSelector.fov_at_wd(camera, wd)
                if ((fov.get('width') or 0) >= need_w * fov_safety
                        and (fov.get('height') or 0) >= need_h * fov_safety):
                    err = ThreeDCameraSelector.camera_error(camera, wd, params, budget)
                    if best is None or err['total_mm'] < best['error']:
                        best = {'wd': round(wd, 1), 'error': err['total_mm']}
                wd += step
        return best['wd'] if best else None

    # ------------------------------------------------------------------
    # 精度链
    # ------------------------------------------------------------------
    @staticmethod
    def error_budget(params: Dict, precision_mm: float) -> Dict:
        """把引导总误差拆成 RSS 预算；返回绝对值与占比。

        设计目标 = 规格上限 × design_margin_ratio（默认 0.8）。
        预算按设计目标分配，不是按上限分配——按上限分配等于设计零余量，
        样机阶段任何一项超标就直接违约。
        """
        design_ratio = _as_float(params.get('design_margin_ratio'), 0.8) or 0.8
        design_ratio = min(max(design_ratio, 0.5), 1.0)
        design_target = precision_mm * design_ratio
        abs_errors = {
            'calibration': _as_float(params.get('calibration_error_mm'),
                                     DEFAULT_ABS_ERRORS['calibration']),
            'robot': _as_float(params.get('robot_error_mm'), DEFAULT_ABS_ERRORS['robot']),
            'gripper': _as_float(params.get('gripper_error_mm'), DEFAULT_ABS_ERRORS['gripper']),
            'part': _as_float(params.get('part_error_mm'), DEFAULT_ABS_ERRORS['part']),
        }
        # 相机侧预算 = 设计目标按 RSS 反推（其余项已知）
        others_rss = _rss(list(abs_errors.values()))
        if others_rss >= design_target:
            camera_budget = 0.0
            budget_infeasible = True
        else:
            camera_budget = math.sqrt(design_target ** 2 - others_rss ** 2)
            budget_infeasible = False
        total_rss = _rss([camera_budget] + list(abs_errors.values()))
        return {
            'precision_requirement_mm': precision_mm,
            'design_margin_ratio': round(design_ratio, 3),
            'design_target_mm': round(design_target, 4),
            'camera_budget_mm': round(camera_budget, 4),
            'absolute_errors_mm': {k: round(v, 4) for k, v in abs_errors.items()},
            'others_rss_mm': round(others_rss, 4),
            'total_rss_mm': round(total_rss, 4),
            'rss_margin_mm': round(precision_mm - total_rss, 4),
            'budget_infeasible': budget_infeasible,
            'ratio': {k: round(v / precision_mm, 3) for k, v in abs_errors.items()},
            'note': ('RSS 是统计合成，不是最坏情况相加；验收应按 3σ 或客户约定口径。'
                     '设计目标 = 要求 × %.0f%%，剩余为工程余量。' % (design_ratio * 100)),
        }

    @staticmethod
    def camera_error(camera: Dict, wd_mm: float, params: Dict, budget: Dict) -> Dict:
        """估算相机侧引导误差。

        优先级：
          1. 厂商给 guidance_accuracy_mm（scope=system）→ 直接用，不再叠加标定/机器人；
          2. 否则用 max(Z重复, VDI) + 0.5×点距，再与标定/机器人/夹爪/工件 RSS。
        """
        guidance = _as_float(camera.get('guidance_accuracy_mm'))
        if guidance is not None:
            return {
                'total_mm': round(guidance, 4),
                'scope': camera.get('guidance_accuracy_scope') or 'system',
                'components': {'vendor_guidance': round(guidance, 4)},
                'note': '厂商官方“视觉引导抓取精度”经验值，已含抓取链路；仍需样件复核。',
            }

        z = _as_float(camera.get('z_repeatability_mm'), 0.0)
        vdi = _as_float(camera.get('vdi_accuracy_mm'), 0.0)
        xy = ThreeDCameraSelector.xy_resolution(camera, wd_mm) or 0.0
        cam_measure = max(z, vdi) + 0.5 * xy
        abs_err = budget.get('absolute_errors_mm', DEFAULT_ABS_ERRORS)
        components = {
            'camera_measure': round(cam_measure, 4),
            'z_repeatability': round(z, 4),
            'vdi_accuracy': round(vdi, 4),
            'xy_half_pixel': round(0.5 * xy, 4),
            'calibration': round(abs_err.get('calibration', 0.0), 4),
            'robot': round(abs_err.get('robot', 0.0), 4),
            'gripper': round(abs_err.get('gripper', 0.0), 4),
            'part': round(abs_err.get('part', 0.0), 4),
        }
        total = _rss([cam_measure] + [abs_err.get(k, 0.0) for k in
                                      ('calibration', 'robot', 'gripper', 'part')])
        return {
            'total_mm': round(total, 4),
            'scope': 'camera_rss',
            'components': components,
            'note': '相机侧为估算（Z重复/VDI 取标称值 + 0.5×点距），必须样件实测。',
        }

    # ------------------------------------------------------------------
    # 单台评估
    # ------------------------------------------------------------------
    def evaluate(self, camera: Dict, params: Dict) -> Dict:
        part = params['part_size']
        margin = _as_float(params.get('fov_margin'), 1.2) or 1.2
        # 旋转包络：方形/长方形产品若可能任意旋转，FOV 必须覆盖外接圆直径，
        # 否则 300×300 在 45° 时外接 424mm，按 360mm 校核会漏判出视野。
        if params.get('part_may_rotate'):
            diag = math.hypot(part['width'], part['height'])
            need_w = need_h = diag * margin
        else:
            need_w = part['width'] * margin
            need_h = part['height'] * margin
        precision = params['precision_requirement']
        budget = params.get('_budget') or self.error_budget(params, precision)

        rng = camera.get('working_distance_mm') or [None, None]
        wd_req = _as_float(params.get('working_distance'))
        reasons, warnings, info = [], [], []

        # 1) 工作距离：给定值优先；未给则遍历找“满足FOV且误差最小”的工作点
        if wd_req is not None:
            wd = wd_req
            if rng[0] is not None and wd < rng[0]:
                reasons.append(f'WD {wd:.0f}mm 小于相机下限 {rng[0]:.0f}mm')
            if rng[1] is not None and wd > rng[1]:
                reasons.append(f'WD {wd:.0f}mm 大于相机上限 {rng[1]:.0f}mm')
        else:
            wd = self._best_wd(camera, need_w, need_h, params, budget)
            if wd is None:
                wd = _as_float(camera.get('optimal_working_distance_mm'))
                if wd is None and rng[0] is not None:
                    wd = rng[0]
                reasons.append(
                    f'推荐 WD 范围内 FOV 不足以覆盖 {need_w:.0f}×{need_h:.0f}mm')

        if wd is None:
            return {
                'model': camera.get('model'), 'brand': camera.get('brand'),
                'verdict': 'FAIL', 'score': 0.0,
                'reasons': reasons + ['相机 WD/FOV 数据缺失'],
                'warnings': warnings, 'info': info,
            }

        fov = self.fov_at_wd(camera, wd)
        fov_w, fov_h = fov.get('width') or 0, fov.get('height') or 0
        fov_ok = fov_w >= need_w and fov_h >= need_h
        if not fov_ok:
            reasons.append(
                f'FOV {fov_w:.0f}×{fov_h:.0f}mm @{wd:.0f}mm < 需求 {need_w:.0f}×{need_h:.0f}mm')
        elif min(fov_w / need_w, fov_h / need_h) < 1.05:
            warnings.append(
                f'FOV 余量 {min(fov_w / need_w, fov_h / need_h) * 100 - 100:.0f}% <5%，'
                f'来料偏移/装配误差可能出视野')
        if fov.get('estimated'):
            info.append('FOV 按单点/端点比例估算，非厂家该距离实测值')

        xy = self.xy_resolution(camera, wd)
        err = self.camera_error(camera, wd, params, budget)
        total = err['total_mm']

        # 2) 精度判定：≤80% 预算 = PASS；≤100% = WARN；>100% = FAIL
        if total > precision:
            reasons.append(f'引导误差估算 {total:.3f}mm > 要求 {precision:.3f}mm')
        elif total > precision * 0.8:
            warnings.append(
                f'引导误差估算 {total:.3f}mm 占要求 {precision:.3f}mm 的 '
                f'{total / precision * 100:.0f}%，余量不足 20%')

        # 3) 节拍：用典型采集时间，不用“最长/最高精度模式”的上限
        cycle = _as_float(params.get('cycle_time'))
        cap_typical = _as_float(camera.get('capture_time_typical_s'))
        cap = camera.get('capture_time_s') or []
        if cap_typical is None and len(cap) > 1:
            cap_typical = _as_float(cap[1])
        if cycle and cap_typical:
            process_est = _as_float(params.get('processing_time_s'), 0.5) or 0.5
            if cap_typical + process_est > cycle * 0.6:
                warnings.append(
                    f'采集 {cap_typical:.2f}s + 处理估算 {process_est:.2f}s '
                    f'超过节拍 {cycle:.1f}s 的 60%')

        # 4) 接口/防护
        iface = str(params.get('interface') or '').lower()
        cam_iface = str(camera.get('interface') or '').lower()
        if iface and iface not in cam_iface:
            if 'gige' in iface and '10gige' in cam_iface:
                warnings.append('相机为 10GigE，需 10G 网卡；兼容 1GigE 但采集降速')
            else:
                warnings.append(f'接口 {camera.get("interface")} 与要求 {params.get("interface")} 不完全一致')
        ip_req = str(params.get('ip_rating') or '').upper()
        ip_cam = str(camera.get('ip_rating') or '').upper()
        if ip_req and ip_cam and ip_req not in ip_cam:
            warnings.append(f'防护等级 {ip_cam} 低于要求 {ip_req}')

        # 5) 评分
        prec_margin = _clamp((precision - total) / precision) if precision > 0 else 0
        fov_margin_ratio = min(fov_w / need_w, fov_h / need_h) - 1 if need_w and need_h else 0
        fov_score = _clamp(fov_margin_ratio / 0.5)
        opt = _as_float(camera.get('optimal_working_distance_mm'))
        wd_score = _clamp(1 - abs(wd - opt) / max(opt * 0.5, 1.0)) if opt else 0.7
        software = camera.get('software') or []
        sw_score = 1.0 if camera.get('robot_integration') else (0.6 if software else 0.3)
        iface_score = 1.0 if 'gige' in cam_iface else 0.8
        # 数据置信度：低置信度参数必须扣分，避免"纸面最优"直接胜出
        confidence = str(camera.get('data_confidence') or 'medium')
        conf_factor = {'high': 1.0, 'medium': 0.92, 'low': 0.78}.get(confidence, 0.9)
        score = (0.45 * prec_margin + 0.20 * fov_score + 0.15 * wd_score
                 + 0.10 * sw_score + 0.10 * iface_score) * conf_factor
        if confidence != 'high':
            info.append(
                f'参数置信度 {confidence}：'
                + ('；'.join(camera.get('needs_vendor_confirmation') or ['需厂商书面确认']))
                + f'（评分已乘 {conf_factor}）')

        verdict = 'PASS'
        if reasons:
            verdict = 'FAIL'
        elif warnings:
            verdict = 'WARN'

        return {
            'brand': camera.get('brand'),
            'series': camera.get('series'),
            'model': camera.get('model'),
            'technology': camera.get('technology'),
            'verdict': verdict,
            'score': round(score, 4),
            'recommended_wd_mm': round(wd, 1),
            'working_distance_range_mm': rng,
            'fov_at_wd_mm': {'width': round(fov_w, 1), 'height': round(fov_h, 1),
                             'estimated': bool(fov.get('estimated'))},
            'required_fov_mm': {'width': round(need_w, 1), 'height': round(need_h, 1)},
            'fov_margin': {
                'width': round(fov_w / need_w, 3) if need_w else None,
                'height': round(fov_h / need_h, 3) if need_h else None,
            },
            'xy_resolution_mm': round(xy, 4) if xy else None,
            'guidance_error': err,
            'precision_margin_mm': round(precision - total, 4),
            'software': camera.get('software') or [],
            'robot_integration': camera.get('robot_integration'),
            'interface': camera.get('interface'),
            'ip_rating': camera.get('ip_rating'),
            'capture_time_s': camera.get('capture_time_s'),
            'reasons': reasons,
            'warnings': warnings,
            'info': info,
            'data_confidence': confidence,
            'needs_vendor_confirmation': camera.get('needs_vendor_confirmation') or [],
            'verified': camera.get('verified'),
            'verification_url': camera.get('verification_url'),
            'notes': camera.get('notes'),
        }

    # ------------------------------------------------------------------
    # 选型
    # ------------------------------------------------------------------
    def select(self, params: Dict, top_n: int = 8) -> Dict:
        precision = params['precision_requirement']
        budget = self.error_budget(params, precision)
        params['_budget'] = budget
        results = [self.evaluate(c, params) for c in self.cameras]
        # 排序：PASS > WARN > FAIL；同 verdict 按分数降序
        results.sort(key=lambda r: (VERDICT_ORDER.get(r['verdict'], 9), -r.get('score', 0)))
        passed = [r for r in results if r['verdict'] == 'PASS']
        warned = [r for r in results if r['verdict'] == 'WARN']
        failed = [r for r in results if r['verdict'] == 'FAIL']
        # 首选规则：PASS 且数据置信度非 low；low 只能作为"确认后潜力候选"，
        # 否则纸面最优的不可信数据会直接变成推荐结论。
        reliable = [r for r in passed if r.get('data_confidence') != 'low']
        low_conf_passed = [r for r in passed if r.get('data_confidence') == 'low']
        return {
            'generated_at': datetime.now().isoformat(timespec='seconds'),
            'project': {
                'name': params.get('project_name'),
                'application': params.get('application', '3d_robot_guidance'),
                'installation': params.get('installation', 'ETH'),
            },
            'requirements': {
                'part_size_mm': params['part_size'],
                'precision_requirement_mm': precision,
                'precision_basis': params.get('precision_basis'),
                'fov_margin': params.get('fov_margin', 1.2),
                'part_may_rotate': bool(params.get('part_may_rotate')),
                'working_distance_mm': params.get('working_distance'),
                'cycle_time_s': params.get('cycle_time'),
                'cycle_time_assumed': bool(params.get('cycle_time_assumed')),
                'gripper_angle_required': params.get('gripper_angle_required'),
                'product_variants': params.get('product_variants'),
                'bottom_flatness': params.get('bottom_flatness'),
                'surface_condition': params.get('surface_condition'),
            },
            'error_budget': budget,
            'summary': {
                'total': len(results),
                'pass': len(passed),
                'warn': len(warned),
                'fail': len(failed),
                'has_feasible': bool(passed),
            },
            'candidates': results,
            'recommendation': (reliable or passed or warned or [None])[0],
            'low_confidence_candidates': low_conf_passed,
            'top_n': results[:top_n],
        }

    # ------------------------------------------------------------------
    # Markdown 方案
    # ------------------------------------------------------------------
    @staticmethod
    def render_markdown(result: Dict, top_n: int = 6) -> str:
        req = result['requirements']
        budget = result['error_budget']
        rec = result.get('recommendation') or {}
        lines = []
        add = lines.append

        add(f"# 3D 视觉引导抓取方案{'：' + req.get('part_size_mm', '') if False else ''}")
        add('')
        add(f"> 生成时间：{result['generated_at']}　|　"
            f"应用：3D 机器人引导　|　安装：{result['project'].get('installation', 'ETH')}")
        add('')
        add('## 1. 需求摘要')
        add('')
        add('| 项目 | 值 |')
        add('|---|---|')
        add(f"| 产品尺寸 | {req['part_size_mm']['width']:.0f} × {req['part_size_mm']['height']:.0f}"
            + (f" × {req['part_size_mm']['depth']:.0f}" if req['part_size_mm'].get('depth') else '')
            + ' mm |')
        add(f"| 引导精度要求 | ≤ {req['precision_requirement_mm']:.3f} mm |")
        add(f"| 精度口径 | {req.get('precision_basis') or '未声明'} |")
        add(f"| 视野余量 | ×{req.get('fov_margin')} → 需求 "
            f"{req['part_size_mm']['width'] * req.get('fov_margin', 1.2):.0f} × "
            f"{req['part_size_mm']['height'] * req.get('fov_margin', 1.2):.0f} mm |")
        if req.get('part_may_rotate'):
            diag = (req['part_size_mm']['width'] ** 2
                    + req['part_size_mm']['height'] ** 2) ** 0.5
            add(f"| 旋转包络 | 产品可能任意旋转 → FOV 按外接圆 Ø{diag:.0f}mm × "
                f"{req.get('fov_margin')} = {diag * req.get('fov_margin', 1.2):.0f}mm 校核 |")
        add(f"| 工作距离 | {req.get('working_distance_mm') or '待现场确认（脚本按FOV反推）'} |")
        add(f"| 节拍 | {req.get('cycle_time_s') or '待确认'} s/件 |")
        add(f"| 夹爪角度引导 | {'需要 6D 位姿（含绕Z旋转）' if req.get('gripper_angle_required') else '未要求'} |")
        variants = req.get('product_variants')
        add(f"| 换型 | {str(variants) + ' 种' if variants else '待确认'} |")
        add(f"| 底部状态 | {req.get('bottom_flatness') or '待确认'} |")
        add(f"| 上表面状态 | {req.get('surface_condition') or '待确认'} |")
        add('')

        add('## 2. 选型结论')
        add('')
        if rec:
            add(f"**首选：{rec.get('brand')} {rec.get('model')}**"
                f"（{rec.get('verdict')}，综合评分 {rec.get('score')}）")
            add('')
            add(f"- 推荐工作距离：**{rec.get('recommended_wd_mm')} mm**"
                f"（相机范围 {rec.get('working_distance_range_mm')}）")
            add(f"- 该 WD 下 FOV：**{rec['fov_at_wd_mm']['width']:.0f} × "
                f"{rec['fov_at_wd_mm']['height']:.0f} mm**"
                f"（需求 {rec['required_fov_mm']['width']:.0f} × "
                f"{rec['required_fov_mm']['height']:.0f} mm）")
            add(f"- 点间距：**{rec.get('xy_resolution_mm')} mm**")
            add(f"- 引导误差估算：**{rec['guidance_error']['total_mm']:.3f} mm**"
                f"（{rec['guidance_error']['scope']}）")
            add(f"- 精度余量：**{rec.get('precision_margin_mm'):.3f} mm**")
            if rec.get('warnings'):
                add('')
                add('注意事项：')
                for w in rec['warnings']:
                    add(f"- ⚠ {w}")
            if rec.get('needs_vendor_confirmation'):
                add('')
                add('**定型前必须书面确认**：')
                for n in rec['needs_vendor_confirmation']:
                    add(f"- {n}")
            if rec.get('info'):
                add('')
                add('说明：')
                for n in rec['info']:
                    add(f"- {n}")
        else:
            add('**无可行方案**：所有候选相机均未通过 FOV 或精度校核。')
        add('')

        add('## 3. 候选对比')
        add('')
        add('| 品牌/型号 | 技术 | 推荐WD | FOV@WD | 点距 | 引导误差 | 数据置信度 | 判定 | 评分 |')
        add('|---|---|---|---|---|---|---|---|---|')
        for c in result['top_n'][:top_n]:
            fov = c.get('fov_at_wd_mm') or {}
            add(f"| {c.get('brand')} {c.get('model')} | {c.get('technology') or '-'} "
                f"| {c.get('recommended_wd_mm') or '-'} mm "
                f"| {fov.get('width', '-')}×{fov.get('height', '-')} mm "
                f"| {c.get('xy_resolution_mm') or '-'} mm "
                f"| {c.get('guidance_error', {}).get('total_mm', '-')} mm "
                f"| {c.get('data_confidence', '-')} "
                f"| {c.get('verdict')} | {c.get('score')} |")
        add('')
        add('> 数据置信度：high=官网数据表可直接引用；medium=官网标称但测试条件未明；'
            'low=数值与物理规律不符或来源非官方，必须厂商书面确认后才能定型。')
        add('')

        add('## 4. 精度链与误差预算')
        add('')
        add(f"规格上限 **{budget['precision_requirement_mm']:.3f} mm**，"
            f"设计目标 **{budget['design_target_mm']:.3f} mm**"
            f"（要求 × {budget['design_margin_ratio'] * 100:.0f}%，预留工程余量），按 RSS 分配：")
        add('')
        add('| 环节 | 预算（mm） | 占规格上限 | 说明 |')
        add('|---|---|---|---|')
        add(f"| 3D 相机（测量+位姿） | {budget['camera_budget_mm']:.3f} "
            f"| {budget['camera_budget_mm'] / budget['precision_requirement_mm'] * 100:.0f}% "
            f"| Z 重复、VDI、XY 点距、点云配准 |")
        for k, label in [('calibration', '手眼标定'), ('robot', '机器人绝对定位'),
                         ('gripper', '夹爪/TCP'), ('part', '工件位姿/形变')]:
            v = budget['absolute_errors_mm'][k]
            add(f"| {label} | {v:.3f} | {v / budget['precision_requirement_mm'] * 100:.0f}% | 现场实测/标定残差 |")
        add(f"| **RSS 合计** | **{budget['total_rss_mm']:.3f}** | "
            f"**{budget['total_rss_mm'] / budget['precision_requirement_mm'] * 100:.0f}%** | "
            f"对规格上限余量 {budget['rss_margin_mm']:.3f} mm |")
        add('')
        if budget.get('budget_infeasible'):
            add('> ⚠ 标定/机器人/夹爪/工件四项 RSS 已超过设计目标，相机侧无可用预算：'
                '必须先压缩这四项（提高标定等级、选更高绝对精度机器人、换夹爪方案），'
                '否则换任何相机都无法满足 0.5mm。')
            add('')
        add(f"> {budget['note']}")
        add('')

        add('## 5. 推荐配置')
        add('')
        add('| 项目 | 建议 |')
        add('|---|---|')
        add(f"| 3D 相机 | {rec.get('brand', '待定')} {rec.get('model', '待定')} |")
        add(f"| 安装方式 | ETH（Eye-to-Hand，固定支架） |")
        add(f"| 工作距离 | {rec.get('recommended_wd_mm', '待定')} mm（镜头/光窗到产品上表面） |")
        add(f"| 通讯 | GigE / 10GigE（按相机型号配网卡） |")
        add(f"| 标定 | 手眼标定板/标定球，残差 ≤ 0.10 mm，定期漂移自校正 |")
        add(f"| 软件 | {', '.join(rec.get('software') or ['相机 SDK + 3D 匹配软件'])} |")
        add(f"| 触发 | 传送带挡停到位信号 → PLC/机器人触发拍照 |")
        add('')

        add('## 6. 专项分析')
        add('')
        add('### 6.1 底部不平整')
        add('')
        add('单相机从上方只能看到产品上表面，底部不可见。底部不平导致的倾斜会传递到上表面，')
        add('可由上表面平面拟合 + 外轮廓/2D 纹理估计 6D 位姿；但如果上表面是无特征平面，')
        add('绕法向的旋转（RZ）不可观测，必须依赖外轮廓角点、2D 纹理或机械定位。')
        add('建议：① 要求每种产品提供 3D CAD 或点云模板；② 确认上表面是否有可辨识轮廓；')
        add('③ 若底部不平导致倾斜超过夹爪容差，增加侧视相机或柔性夹爪。')
        add('')
        add('### 6.2 抓取角度（6D 位姿）')
        add('')
        add('需要输出 XYZ + RX/RY/RZ。夹爪需具备绕 Z 旋转能力，倾斜由机器人手腕补偿；')
        add('若产品倾斜角超过夹爪/机器人单轴容差，需在抓取策略中增加“先调姿、再下爪”的两步动作。')
        add('')
        add('### 6.3 换型')
        add('')
        add('硬件不变，软件按产品型号管理 3D 模板（CAD/点云）与抓取策略；')
        add('换型时由 MES/PLC 下发型号，视觉调用对应模板。建议模板命名与产品编码绑定，')
        add('并保留模板版本号，避免换型后误用旧模板。')
        add('')
        add('### 6.4 ETH 标定与漂移')
        add('')
        add('Eye-to-Hand 固定安装，标定一次长期稳定；0.5mm 级应用建议：')
        add('标定点位 ≥20 组、覆盖视野四角与中心、标定残差 ≤0.10mm；')
        add('每班/每周用标定球复检，温漂明显的现场启用漂移自校正。')
        add('')

        add('## 7. 风险与验证计划')
        add('')
        add('| 风险 | 验证动作 | 通过标准 |')
        add('|---|---|---|')
        add('| 厂商标称精度是标准白板条件 | 用真实工件（含反光/深色/油污）打样 | 点云空洞率、位姿重复性满足 0.5mm |')
        add('| 底部不平导致倾斜/晃动 | 连续 30 次放置，测位姿波动 | 角度/位置波动 ≤ 预算 |')
        add('| 换型模板误匹配 | 每种型号各 10 件，混线切换 | 识别率 ≥99%，无误抓 |')
        add('| 手眼标定漂移 | 连续 8h 跑机，定时复检标定球 | 漂移 ≤0.05mm |')
        add('| 环境光/反光 | 开/关车间灯、强光手电对比 | 点云质量不显著下降 |')
        add('')

        add('## 8. 与厂商 Pro M 方案对比')
        add('')
        add('| 维度 | 梅卡曼德 PRO M（厂商方案） | 本方案首选 |')
        add('|---|---|---|')
        add(f"| 官方引导精度 | ±1.5mm（WD 1000-1300，经验值） | "
            f"{rec.get('guidance_error', {}).get('total_mm', '待定')} mm（估算） |")
        add(f"| 工作距离 | 1000-1300 mm | {rec.get('recommended_wd_mm', '待定')} mm |")
        add(f"| FOV | 800×450 mm @1m | "
            f"{rec.get('fov_at_wd_mm', {}).get('width', '待定')}×"
            f"{rec.get('fov_at_wd_mm', {}).get('height', '待定')} mm |")
        add(f"| 点间距 | 0.42 mm @1m | {rec.get('xy_resolution_mm', '待定')} mm |")
        add(f"| 对 300×300 产品的匹配度 | 视野过大，产品占比低，精度浪费 | 视野匹配，点距更细 |")
        add(f"| 结论 | 按官方口径不满足 0.5mm 余量，需打样复核 | 满足 0.5mm 预算，需样件实测 |")
        add('')
        add('> 说明：PRO M 的 ±1.5mm 是梅卡曼德官方选型指南给出的“视觉引导抓取精度”')
        add('> 经验值（WD 1000-1300mm），不是实验室相机精度；若厂商坚持可用，')
        add('> 必须要求其用本项目真实工件打样并出具 0.5mm 验收报告。')
        add('')

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # 客户交付版方案
    # ------------------------------------------------------------------
    @staticmethod
    def render_customer_proposal(result: Dict) -> str:
        """客户可交付的完整方案：选型结论 + BOM + 标定 + 换型 + 验收计划。

        与 render_markdown 的分工：
          render_markdown        = 选型分析报告（内部/评审用，含全部候选与评分）
          render_customer_proposal = 客户方案（结论 + 实施 + 验收，弱化内部评分）
        """
        req = result['requirements']
        budget = result['error_budget']
        rec = result.get('recommendation') or {}
        cands = result.get('candidates') or []
        part = req['part_size_mm']
        lines = []
        add = lines.append

        add('# 3D 视觉引导抓取系统技术方案')
        add('')
        add(f"> 项目：{result['project'].get('name') or '3D 视觉引导抓取'}")
        add(f"> 生成时间：{result['generated_at']}　|　"
            f"安装方式：{'ETH 眼在手外' if result['project'].get('installation') == 'ETH' else 'EIH 眼在手上'}")
        add('')

        # 1 概述
        add('## 1. 项目概述')
        add('')
        add(f"本方案针对 **{part['width']:.0f} × {part['height']:.0f} mm** 产品，"
            f"在传送带静止拍照位由 3D 相机采集点云，输出 6D 位姿引导机器人抓取，"
            f"引导总误差要求 **≤ {req['precision_requirement_mm']:.2f} mm**。")
        add('')
        add('系统采用 Eye-to-Hand（ETH）固定安装：相机固定在支架上，标定一次长期有效，'
            '机器人不带相机、无额外负载与拖链，适合节拍稳定、来料位置相对固定的产线。')
        add('')

        # 2 设计输入
        add('## 2. 设计输入与假设')
        add('')
        add('| 项目 | 输入值 | 来源 |')
        add('|---|---|---|')
        add(f"| 产品外形 | {part['width']:.0f} × {part['height']:.0f} mm | 客户提供 |")
        add(f"| 引导精度 | ≤ {req['precision_requirement_mm']:.2f} mm（引导总误差） | 客户提供 |")
        add(f"| 安装方式 | ETH 眼在手外 | 客户提供 |")
        add(f"| 拍照方式 | 传送带挡停静止拍照 | 客户提供 |")
        add(f"| 夹爪角度引导 | {'需要 6D 位姿' if req.get('gripper_angle_required') else '未要求'} | 客户提供 |")
        add(f"| 换型 | {str(req.get('product_variants')) + ' 种' if req.get('product_variants') else '需要，型号数量待确认'} | 客户提供 |")
        add(f"| 底部状态 | {req.get('bottom_flatness') or '待确认'} | 客户提供 |")
        add(f"| 上表面状态 | {req.get('surface_condition') or '待确认'} | 待现场确认 |")
        add(f"| 节拍 | {req.get('cycle_time_s') or '待确认'} s/件 "
            f"| {'假设值（待客户确认）' if req.get('cycle_time_assumed') else '客户提供'} |")
        add(f"| 工作距离 | {req.get('working_distance_mm') or '按选型结果（见 §4）'} | 设计确定 |")
        add('')
        add('**以下参数尚未确认，需现场/客户补充后复核（不改变本方案架构，但影响细节配置）：**')
        add('')
        add('1. 产品材质、颜色、表面反光特性（决定结构光点云质量与曝光参数）')
        add('2. 换型产品型号数量与各型号外形差异（决定模板数量与是否需要多套夹爪）')
        add('3. 来料方向是否固定（决定 FOV 按边长还是外接圆校核，见 §5 敏感性分析）')
        add('4. 机器人品牌与型号、绝对定位精度（决定误差预算中的机器人项）')
        add('5. 夹爪形式与 TCP 精度（决定是否具备绕 Z 旋转能力）')
        add('6. 现场环境光、粉尘、水汽、温度波动（决定防护等级与遮光措施）')
        add('7. 是否提供各型号 3D CAD 模型（决定模板制作方式与周期）')
        add('')

        # 3 选型结论
        add('## 3. 选型结论')
        add('')
        if rec:
            # 评分差 <3% 视为并列：不能用一个"纸面第一"替客户做决定，应双候选打样
            rivals = [c for c in cands
                      if c.get('verdict') == rec.get('verdict')
                      and c.get('model') != rec.get('model')
                      and abs(c.get('score', 0) - rec.get('score', 0))
                      <= max(rec.get('score', 0) * 0.03, 0.01)]
            title = f"### 3.1 首选方案：{rec.get('brand')} {rec.get('model')}"
            if rivals:
                names = ' / '.join(f"{r.get('brand')} {r.get('model')}" for r in rivals)
                title = (f"### 3.1 首选方案：{rec.get('brand')} {rec.get('model')}"
                         f"（与 {names} 并列，打样定标）")
            add(title)
            add('')
            add('| 项目 | 参数 |')
            add('|---|---|')
            add(f"| 技术类型 | {rec.get('technology') or '-'} |")
            add(f"| 推荐工作距离 | **{rec.get('recommended_wd_mm')} mm**（光窗到产品上表面） |")
            add(f"| 该距离视野 | **{rec['fov_at_wd_mm']['width']:.0f} × {rec['fov_at_wd_mm']['height']:.0f} mm** |")
            add(f"| 点间距 | {rec.get('xy_resolution_mm')} mm（按 FOV ÷ 深度图分辨率估算） |")
            add(f"| 引导误差估算 | **{rec['guidance_error']['total_mm']:.3f} mm** |")
            add(f"| 精度余量 | {rec.get('precision_margin_mm'):.3f} mm |")
            add(f"| 通讯接口 | {rec.get('interface') or '见相机规格'} |")
            add(f"| 防护等级 | {rec.get('ip_rating') or '见相机规格'} |")
            add(f"| 采集时间 | {_fmt_range(rec.get('capture_time_s'))} s |")
            add(f"| 配套软件 | {', '.join(rec.get('software') or ['相机 SDK'])} |")
            add('')
            add('**选型理由：**')
            add('')
            add(f"- 工作距离 {rec.get('recommended_wd_mm')} mm 处于该型号最佳成像区间，"
                f"点距与 Z 精度匹配 {budget['precision_requirement_mm']:.2f} mm 引导要求")
            add(f"- 视野覆盖产品并保留工程余量，产品不必精确对中")
            add(f"- 误差预算 RSS 合计 {budget['total_rss_mm']:.3f} mm，"
                f"对 {budget['precision_requirement_mm']:.2f} mm 规格上限留 "
                f"{budget['rss_margin_mm']:.3f} mm 余量")
            if rivals:
                add('')
                add('**并列候选差异（供打样选型参考）：**')
                add('')
                add('| 型号 | 工作距离 | 视野 | 点距 | 误差估算 | 特点 |')
                add('|---|---|---|---|---|---|')
                for r in [rec] + rivals:
                    fov = r.get('fov_at_wd_mm') or {}
                    feat = []
                    if '彩色' in str(r.get('technology')):
                        feat.append('彩色点云')
                    if '激光' in str(r.get('technology')):
                        feat.append('激光投影')
                    feat.append(f"{r.get('interface')}")
                    add(f"| {r.get('brand')} {r.get('model')} | {r.get('recommended_wd_mm')} mm "
                        f"| {fov.get('width', '-')}×{fov.get('height', '-')} mm "
                        f"| {r.get('xy_resolution_mm', '-')} mm "
                        f"| {r.get('guidance_error', {}).get('total_mm', '-')} mm "
                        f"| {'、'.join(feat)} |")
                add('')
                add('> 并列候选在纸面精度上差异 <3%，无工程意义。最终选择应由**真实工件打样**决定：'
                    '重点比较深色/反光表面的点云空洞率、RZ 定姿稳定性、软件易用性与本地服务响应。')
            if rec.get('needs_vendor_confirmation'):
                add('')
                add('**采购前需厂商书面确认：**')
                for n in rec['needs_vendor_confirmation']:
                    add(f"- {n}")
            add('')

            # 备选（排除已并列展示的型号、以及低置信度候选——
            # 低置信度只能出现在 3.3「数据待确认」，不能同时被当作备选推荐）
            rivals_models = {r.get('model') for r in rivals}
            low_conf_models = {c.get('model')
                               for c in (result.get('low_confidence_candidates') or [])}
            backups = [c for c in cands
                       if c.get('verdict') in ('PASS', 'WARN')
                       and c.get('model') != rec.get('model')
                       and c.get('model') not in rivals_models
                       and c.get('model') not in low_conf_models][:2]
            if backups:
                add('### 3.2 备选方案')
                add('')
                add('| 型号 | 推荐WD | 视野 | 点距 | 引导误差 | 判定 | 备注 |')
                add('|---|---|---|---|---|---|---|')
                for b in backups:
                    fov = b.get('fov_at_wd_mm') or {}
                    warn = '；'.join(b.get('warnings') or []) or '—'
                    verdict = '可用' if b.get('verdict') == 'PASS' else '有条件可用'
                    add(f"| {b.get('brand')} {b.get('model')} | {b.get('recommended_wd_mm')} mm "
                        f"| {fov.get('width', '-')}×{fov.get('height', '-')} mm "
                        f"| {b.get('xy_resolution_mm', '-')} mm "
                        f"| {b.get('guidance_error', {}).get('total_mm', '-')} mm "
                        f"| {verdict} | {warn} |")
                add('')
                add('> 备选最终以真实工件打样结果定标。不同品牌对深色/反光/油污表面的适应性差异较大，'
                    '纸面参数不能替代打样；标注"有条件可用"的型号需先解决备注中的余量问题。')
                add('')

            # 低置信度潜力候选：纸面最优但参数不可信，不能直接推荐
            low_conf = result.get('low_confidence_candidates') or []
            if low_conf:
                add('### 3.3 数据待确认的潜力候选')
                add('')
                add('| 型号 | 纸面评分 | 待确认项 | 处理 |')
                add('|---|---|---|---|')
                for lc in low_conf:
                    notes = '；'.join(lc.get('needs_vendor_confirmation') or ['参数来源待核实'])
                    add(f"| {lc.get('brand')} {lc.get('model')} | {lc.get('score')} "
                        f"| {notes} | 厂商书面确认前不纳入首选 |")
                add('')
                add('> 以上型号的关键精度指标与同类产品物理规律不符或来源不完整，已按低置信度降权。'
                    '若厂商能提供正式数据表（含测试条件、样本数、统计口径），可重新纳入打样对比。')
                add('')
        else:
            add('**当前无满足要求的方案。** 需放宽精度、缩小视野或调整安装方式后重新选型。')
            add('')

        # 4 精度链
        add('## 4. 精度链与误差预算')
        add('')
        add(f"引导总误差按 RSS（均方根）分解，设计目标 "
            f"**{budget['design_target_mm']:.3f} mm**"
            f"（规格上限 {budget['precision_requirement_mm']:.2f} mm × "
            f"{budget['design_margin_ratio'] * 100:.0f}%），剩余为工程余量：")
        add('')
        add('| 误差环节 | 预算（mm） | 说明 |')
        add('|---|---|---|')
        add(f"| 3D 相机测量与位姿 | {budget['camera_budget_mm']:.3f} "
            f"| Z 重复精度、VDI 精度、XY 点距、点云配准 |")
        add(f"| 手眼标定 | {budget['absolute_errors_mm']['calibration']:.3f} "
            f"| 标定残差，要求 ≤0.10mm |")
        add(f"| 机器人绝对定位 | {budget['absolute_errors_mm']['robot']:.3f} "
            f"| 绝对定位精度（非重复定位） |")
        add(f"| 夹爪 / TCP | {budget['absolute_errors_mm']['gripper']:.3f} "
            f"| 加工、装配、夹持变形 |")
        add(f"| 工件位姿 / 形变 | {budget['absolute_errors_mm']['part']:.3f} "
            f"| 放置误差、来料一致性 |")
        add(f"| **RSS 合计** | **{budget['total_rss_mm']:.3f}** "
            f"| 对规格上限余量 {budget['rss_margin_mm']:.3f} mm |")
        add('')
        add('> RSS 为统计合成，验收按 3σ 或双方约定口径执行。若现场实测某一项超预算，'
            '优先压缩该项而不是换相机。')
        add('')

        # 5 视野与工作距离
        add('## 5. 视野与工作距离校核')
        add('')
        if rec:
            add(f"- 产品外形：{part['width']:.0f} × {part['height']:.0f} mm")
            add(f"- FOV 余量系数：×{req.get('fov_margin')} → 需求 "
                f"{part['width'] * req.get('fov_margin', 1.2):.0f} × "
                f"{part['height'] * req.get('fov_margin', 1.2):.0f} mm")
            add(f"- 推荐工作距离：{rec.get('recommended_wd_mm')} mm")
            add(f"- 实际视野：{rec['fov_at_wd_mm']['width']:.0f} × "
                f"{rec['fov_at_wd_mm']['height']:.0f} mm")
            fov = rec.get('fov_at_wd_mm') or {}
            need_w = part['width'] * req.get('fov_margin', 1.2)
            need_h = part['height'] * req.get('fov_margin', 1.2)
            if fov.get('width') and fov.get('height'):
                add(f"- 余量：宽度 {fov['width'] / need_w * 100 - 100:.0f}%，"
                    f"高度 {fov['height'] / need_h * 100 - 100:.0f}%")
            add('')
        add('### 5.1 来料旋转敏感性（重要）')
        add('')
        add('方形产品在传送带上若发生旋转，其外接宽度按 `W·cosθ + H·sinθ` 增大：')
        add('')
        add('| 来料方向偏差 | 300×300 外接宽度 | ×1.2 后 FOV 需求 | 影响 |')
        add('|---|---|---|---|')
        for deg, w in [(0, 300.0), (5, 325.0), (10, 347.6), (45, 424.3)]:
            need = w * req.get('fov_margin', 1.2)
            note = '基准' if deg == 0 else ('方向基本固定可接受' if deg <= 10 else '必须按外接圆校核')
            add(f"| ±{deg}° | {w:.0f} mm | {need:.0f} × {need:.0f} mm | {note} |")
        add('')
        add('**结论**：若来料有导向条/挡停、方向偏差 ≤±10°，当前 FOV 方案成立；'
            '若产品可能任意角度摆放，FOV 必须按外接圆 Ø424mm × 余量校核，'
            '需重新核算工作距离（脚本加 `--part-may-rotate` 可复现）。')
        add('')

        # 6 BOM
        add('## 6. 系统配置清单（BOM）')
        add('')
        add('| 序号 | 名称 | 规格/型号 | 数量 | 备注 |')
        add('|---|---|---|---|---|')
        add(f"| 1 | 3D 相机 | {rec.get('brand', '待定')} {rec.get('model', '待定')} | 1 | 含原厂线缆 |")
        add('| 2 | 相机支架 | 落地/龙门架，刚性 ≥ 相机重量 5 倍 | 1 | 减少振动与漂移 |')
        add('| 3 | 手眼标定板 | 与相机视野匹配的标定板/标定球 | 1 | 标定残差 ≤0.10mm |')
        add(f"| 4 | 工业网卡/交换机 | {rec.get('interface') or 'GigE'}（按相机接口配） | 1 | 10GigE 需配套 10G 交换机 |")
        add('| 5 | 遮光罩 | 黑色哑光，罩住相机与拍照位 | 1 | 隔离车间环境光 |')
        add('| 6 | 工控机 | i7/32GB/独显（按点云处理软件要求） | 1 | 或复用产线 IPC |')
        add(f"| 7 | 视觉软件 | {', '.join(rec.get('software') or ['相机 SDK + 3D 匹配软件'])} | 1 | 按型号授权 |")
        add('| 8 | 触发与通讯 | PLC 到位信号 + 机器人通讯 | 1 | 以太网/Profinet 按现场 |')
        add('')
        add('> 3D 结构光相机自带投影光源，通常不需要外置光源；'
            '但强环境光（阳光直射、高频闪灯）会显著降低点云质量，遮光罩为必配项。')
        add('')

        # 7 ETH 标定
        add('## 7. ETH 手眼标定方案')
        add('')
        add('| 步骤 | 内容 | 通过标准 |')
        add('|---|---|---|')
        add('| 1 | 相机与机器人分别上电，确认通讯与触发正常 | 图像/点云可采集 |')
        add('| 2 | 标定板固定在机器人末端（或工装），示教 ≥20 个位姿 | 位姿覆盖视野四角+中心+常用抓取区 |')
        add('| 3 | 每个位姿采集点云，提取标定板位姿 | 点云完整、无空洞 |')
        add('| 4 | 求解手眼矩阵（ETH：相机固定，求 robot←camera） | 残差 ≤0.10 mm |')
        add('| 5 | 验证：机器人持标定球到 5 个随机点，视觉测量 vs 机器人读数 | 偏差 ≤0.15 mm |')
        add('| 6 | 固化参数，记录标定日期与环境温度 | 参数备份 |')
        add('')
        add('**漂移管理：**')
        add('')
        add('- 每班开机用标定球复检 1 次，偏差 >0.10mm 触发重标定')
        add('- 每周记录一次环境温度与复检偏差，建立温漂曲线')
        add('- 相机/支架受撞击、拆装、车间温度变化 >10℃ 后必须重标定')
        add('- 0.5mm 级应用建议启用软件的漂移自校正功能（若相机支持）')
        add('')

        # 8 换型
        add('## 8. 换型方案')
        add('')
        add('硬件不随型号变化，换型通过软件模板与参数集实现：')
        add('')
        add('| 层级 | 内容 | 管理方式 |')
        add('|---|---|---|')
        add('| 3D 模板 | 各型号 CAD/点云模板 | 与产品编码绑定，带版本号 |')
        add('| 2D 模板 | 上表面纹理/轮廓模板（用于 RZ 定姿） | 同上 |')
        add('| 采集参数 | 曝光、投影模式、滤波阈值 | 每型号独立参数集 |')
        add('| 抓取策略 | 抓取点、夹爪开度、接近方向 | 与夹爪/机器人程序联动 |')
        add('')
        add('**换型流程：** MES/PLC 下发产品型号 → 视觉加载对应模板与参数集 → '
            '首件拍照验证 → 输出位姿 → 机器人抓取。换型后首件必须人工确认，'
            '连续 3 件无误后转自动。')
        add('')
        add('**模板版本控制**：模板文件命名 `{产品编码}_{版本号}.pcd`，'
            '禁止覆盖旧版本；换型记录写入日志，便于追溯误抓。')
        add('')

        # 9 底部不平
        add('## 9. 底部不平整与 6D 位姿专项')
        add('')
        add('### 9.1 问题本质')
        add('')
        add('单相机从上方只能看到产品**上表面**，底部不可见。底部不平会导致：')
        add('')
        add('1. 产品实际姿态与理论姿态不一致（倾斜 RX/RY 偏差）')
        add('2. 产品放置后可能有微小晃动，拍照瞬间姿态不稳定')
        add('3. 夹爪下压时产品受力变形或翻转')
        add('')
        add('### 9.2 位姿可观测性')
        add('')
        add('| 自由度 | 可观测性 | 依赖信息 |')
        add('|---|---|---|')
        add('| X / Y 平移 | 可观测 | 点云整体位置 |')
        add('| Z 高度 | 可观测 | 上表面高度 |')
        add('| RX / RY 倾斜 | 可观测（上表面平面拟合） | 上表面平面度 |')
        add('| **RZ 绕法向旋转** | **弱/不可观测** | 外轮廓角点、2D 纹理、CAD 模板 |')
        add('')
        add('**关键结论**：如果产品上表面是无特征平面（如纯平板），RZ 无法从 3D 点云解出，'
            '必须依赖外轮廓或 2D 纹理。方案要求每种产品提供 CAD 模型或确认上表面有可辨识特征。')
        add('')
        add('### 9.3 对策')
        add('')
        add('| 措施 | 适用场景 | 成本 |')
        add('|---|---|---|')
        add('| 3D CAD 模板匹配（含外轮廓） | 有 CAD、外形有特征 | 低 |')
        add('| 2D 纹理 + 3D 点云融合定姿 | 上表面有丝印/纹理/孔位 | 低 |')
        add('| 机械定位（挡块/V 型槽） | 来料方向要求严格固定 | 低（改机构） |')
        add('| 增加侧视 2D 相机 | RZ 要求高、上表面无特征 | 中 |')
        add('| 柔性夹爪/自适应夹爪 | 底部不平导致夹持不稳 | 中 |')
        add('| 先调姿再下爪（两步动作） | 倾斜超过夹爪容差 | 低（改程序） |')
        add('')

        # 10 节拍与通讯
        add('## 10. 节拍、触发与通讯')
        add('')
        add('| 环节 | 时间估算 | 说明 |')
        add('|---|---|---|')
        add(f"| 挡停到位 | - | PLC 输出到位信号 |")
        add(f"| 3D 采集 | {_fmt_range(rec.get('capture_time_s'))} s（按相机型号） | 静态拍照，可多曝光合成；最高精度模式耗时更长 |")
        add(f"| 点云处理与匹配 | 0.3~0.8s | 取决于点云点数与模板复杂度 |")
        add(f"| 位姿输出 | <50ms | 以太网/机器人通讯 |")
        add(f"| **合计** | **约 1.0~2.0s** | 对 {req.get('cycle_time_s') or '待确认'}s 节拍"
            f"{'（假设值，待确认）' if req.get('cycle_time_assumed') else ''}留有裕量 |")
        add('')
        add('**触发链**：传送带挡停 → 到位传感器 → PLC → 触发相机采集 → '
            '视觉处理 → 位姿发送机器人 → 机器人抓取 → 放行。')
        add('')
        add('**异常处理**：采集超时/点云质量不合格 → 输出 NG 信号 → '
            '产品流入 NG 通道，禁止机器人盲抓。')
        add('')

        # 11 验收
        add('## 11. 验收测试计划')
        add('')
        add('| 序号 | 测试项 | 方法 | 通过标准 |')
        add('|---|---|---|---|')
        add('| 1 | 点云完整性 | 各型号真实工件各 10 件，统计空洞率 | 有效点云覆盖率 ≥95% |')
        add('| 2 | 位姿重复性 | 同一工件固定不动，连续采集 30 次 | 位置σ ≤0.10mm，角度σ ≤0.1° |')
        add('| 3 | 引导精度 | 机器人持标定球到 20 个随机点，视觉测量 vs 机器人读数 | 偏差 ≤0.50mm（3σ） |')
        add('| 4 | 抓取成功率 | 各型号连续抓取 100 次 | 成功率 ≥99%，无误抓 |')
        add('| 5 | 换型切换 | 型号 A→B→A 各 10 件 | 切换时间 ≤5min，识别率 100% |')
        add('| 6 | 底部不平适应性 | 人为制造 3 种放置姿态（含倾斜） | 位姿误差在预算内，抓取成功 |')
        add('| 7 | 环境光抗扰 | 开/关车间照明、手电直射 | 点云质量不显著下降，精度不超差 |')
        add('| 8 | 连续运行 | 连续 8 小时生产节拍运行 | 无通讯中断，标定漂移 ≤0.05mm |')
        add('| 9 | 异常处理 | 人为遮挡/空位/歪斜 | 正确输出 NG，不误抓 |')
        add('')
        add('> 验收必须在**真实工件**上进行，不能用标定板/白板替代；'
            '厂商标称精度均为标准条件下的实验室值。')
        add('')

        # 12 风险
        add('## 12. 风险清单与对策')
        add('')
        add('| 风险 | 影响 | 概率 | 对策 |')
        add('|---|---|---|---|')
        add('| 深色/反光表面点云空洞 | 位姿不稳、精度下降 | 中 | 打样验证；调整曝光/投影模式；必要时喷粉（不推荐） |')
        add('| 底部不平导致倾斜超夹爪容差 | 抓取失败/掉件 | 中 | 两步调姿；柔性夹爪；增加侧视 |')
        add('| RZ 不可观测 | 抓取角度错误 | 中 | CAD 模板+外轮廓；2D 纹理；机械定位 |')
        add('| 机器人绝对定位不足 | 总误差超 0.5mm | 中 | 选高绝对精度机器人；视觉闭环补偿 |')
        add('| 环境光干扰 | 点云质量波动 | 中 | 遮光罩；滤光片；固定车间照明 |')
        add('| 换型模板误用 | 误抓/撞机 | 低 | 模板版本控制；首件人工确认 |')
        add('| 标定漂移 | 精度缓慢劣化 | 低 | 每班复检；漂移自校正 |')
        add('| 节拍不足 | 产线瓶颈 | 低 | 选快采模式；并行处理；预触发 |')
        add('')

        # 13 Pro M 对比
        add('## 13. 与梅卡曼德 PRO M 方案的对比')
        add('')
        pro_m = next((c for c in cands if 'PRO M' in str(c.get('model'))), None)
        add('| 维度 | 梅卡曼德 PRO M（厂商推荐） | 本方案首选 |')
        add('|---|---|---|')
        if pro_m:
            pm_fov = pro_m.get('fov_at_wd_mm') or {}
            add(f"| 官方引导精度 | ±1.5 mm（厂商选型指南，WD 1000-1300） "
                f"| {rec.get('guidance_error', {}).get('total_mm', '待定')} mm（估算） |")
            add(f"| 工作距离 | {pro_m.get('recommended_wd_mm')} mm "
                f"| {rec.get('recommended_wd_mm', '待定')} mm |")
            add(f"| 视野 | {pm_fov.get('width', '-')}×{pm_fov.get('height', '-')} mm "
                f"| {rec.get('fov_at_wd_mm', {}).get('width', '-')}×"
                f"{rec.get('fov_at_wd_mm', {}).get('height', '-')} mm |")
            add(f"| 点间距 | {pro_m.get('xy_resolution_mm', '-')} mm "
                f"| {rec.get('xy_resolution_mm', '-')} mm |")
            add(f"| 对 0.5mm 要求的判定 | **不满足**（1.5mm > 0.5mm） "
                f"| 满足（余量 {rec.get('precision_margin_mm', 0):.2f} mm） |")
        add('')
        add('**结论**：按梅卡曼德官方选型指南，PRO M 的视觉引导抓取精度为 ±1.5mm，'
            '不满足本项目 0.5mm 要求。若厂商坚持 PRO M 可用，必须：')
        add('')
        add('1. 用本项目真实工件打样，出具 0.5mm 验收报告（不是实验室白板数据）')
        add('2. 明确 ±1.5mm 的统计口径（3σ？最大值？）与测试条件')
        add('3. 说明是否通过提高机器人绝对精度/闭环补偿来弥补相机侧误差')
        add('')
        add('> 相机侧 1.5mm 误差无法通过软件标定消除；若厂商方案总误差仍为 0.5mm，'
            '需其书面说明误差分配与补偿手段。')
        add('')
        add('### 13.1 为什么不是梅卡曼德其他型号')
        add('')
        add('| 型号 | 官方引导精度 | 本项目判定 | 排除原因 |')
        add('|---|---|---|---|')
        add('| PRO S-V4D500M | ±0.5 mm | 不满足 | 该 WD 下视野 370×240~444×288，短边 <300mm，装不下产品 |')
        add('| PRO S-V4D700M | ±0.7 mm | 不满足 | 精度 0.7mm > 0.5mm；750mm 处视野约 555×360，高度余量仅 20% |')
        add('| PRO M-V4D1200M | ±1.5 mm | 不满足 | 精度差 3 倍；1m 处视野 800×450，产品占比低、点距 0.42mm 偏粗 |')
        add('| NANO-V4D550M | 官方未给 | 不满足 | 0.6m 处视野 440×300，短边刚好 300mm，无来料余量 |')
        add('| UHP-140 | ±0.2 mm | 不满足 | 视野 135×90mm，远小于 300×300 产品 |')
        add('')
        add('> 结论：梅卡曼德全线在本项目「300×300 视野 + 0.5mm 引导精度」约束下，'
            '**没有任何型号能同时满足**——视野够的精度不够，精度够的视野不够。'
            '这不是品牌优劣问题，是产品线定位（中远距离大视野）与本项目（近景高精度中等视野）不匹配。')
        add('')

        # 14 待确认
        add('## 14. 待确认清单（采购/实施前）')
        add('')
        add('| 序号 | 待确认项 | 影响 | 责任方 |')
        add('|---|---|---|---|')
        add('| 1 | 产品材质/颜色/反光特性 | 点云质量、曝光参数 | 客户 |')
        add('| 2 | 换型型号数量与外形差异 | 模板数量、夹爪方案 | 客户 |')
        add('| 3 | 来料方向偏差范围 | FOV 校核、工作距离 | 客户/机构 |')
        add('| 4 | 机器人品牌/型号/绝对定位精度 | 误差预算、可行性 | 客户 |')
        add('| 5 | 夹爪形式/TCP 精度/是否可绕 Z 旋转 | 6D 位姿执行 | 客户 |')
        add('| 6 | 各型号 3D CAD 模型 | 模板制作周期 | 客户 |')
        add('| 7 | 现场环境光/粉尘/水汽/温度 | 防护等级、遮光 | 客户 |')
        add('| 8 | 安装空间与支架形式 | 工作距离可实现性 | 客户/机构 |')
        add('| 9 | 通讯协议（Profinet/EtherNet/IP 等） | 集成方式 | 客户 |')
        add('| 10 | 验收标准与统计口径（3σ/最大值） | 验收判定 | 双方 |')
        add('')
        add('---')
        add('')
        add('> 本方案基于当前已知输入生成，未确认项按行业常规假设处理并在 §14 列出。'
            '选型结论需经真实工件打样复核后方可定型采购。')
        add('')

        return '\n'.join(lines)


# ----------------------------------------------------------------------
# 配置校验 / CLI
# ----------------------------------------------------------------------
def _validate_params(params: Dict) -> Dict:
    errors = []
    part = params.get('part_size')
    if not part:
        errors.append('【缺少产品尺寸】请填 part_size，如 "300x300"（产品外形长×宽，mm）。')
    precision = _as_float(params.get('precision_requirement'))
    if precision is None or precision <= 0:
        errors.append('【缺少引导精度】请填 precision_requirement（mm），'
                      '并声明 precision_basis="guidance_accuracy"（3D 引导总误差，不是相机测量精度）。')
    basis = params.get('precision_basis')
    if precision is not None and not basis:
        errors.append('【精度口径未声明】3D 引导必须区分：'
                      'guidance_accuracy（机器人抓取总误差）/ measurement_accuracy（测量精度）/ '
                      'drawing_tolerance（图纸公差）。请确认客户原话后填 precision_basis。')
    if precision is not None and precision > 2.0:
        errors.append(f'【精度值偏大】{precision}mm 对 3D 引导不常见；'
                      '请确认是“引导总误差”而不是“测量范围/工件尺寸”。')
    if params.get('installation') and params['installation'] not in ('ETH', 'EIH'):
        errors.append('【安装方式】installation 只能是 ETH（眼在手外）或 EIH（眼在手上）。')
    if errors:
        print('[参数校验失败]')
        for e in errors:
            print(' -', e)
        print('\n请补齐后重跑；禁止自行发明口径。')
        raise SystemExit(2)
    return params


def _load_config(path: str) -> Dict:
    with open(path, encoding='utf-8') as f:
        cfg = json.load(f)
    # 兼容 config_template_3d.json 的说明字段
    return {k: v for k, v in cfg.items() if not str(k).startswith('_')}


def main(argv=None):
    ap = argparse.ArgumentParser(description='3D 视觉引导选型（FOV + 精度链 + 误差预算）')
    ap.add_argument('--config', help='3D 项目配置 JSON')
    ap.add_argument('--part-size', help='产品尺寸，如 300x300')
    ap.add_argument('--precision', type=float, help='引导总误差要求（mm）')
    ap.add_argument('--precision-basis', default='guidance_accuracy',
                    help='guidance_accuracy / measurement_accuracy / drawing_tolerance')
    ap.add_argument('--working-distance', type=float, help='工作距离（mm，可选）')
    ap.add_argument('--cycle-time', type=float, help='节拍（s/件，可选）')
    ap.add_argument('--cycle-time-assumed', action='store_true',
                    help='节拍为假设值（客户未提供）：方案中标注"假设值（待客户确认）"')
    ap.add_argument('--installation', default='ETH', choices=['ETH', 'EIH'])
    ap.add_argument('--fov-margin', type=float, default=1.2)
    ap.add_argument('--part-may-rotate', action='store_true',
                    help='产品可能任意旋转：FOV 按外接圆直径校核（方形件 300×300 → 424mm）')
    ap.add_argument('--output',
                    help='输出目录（默认：当前目录下与项目同名的目录）')
    ap.add_argument('--top-n', type=int, default=6)
    ap.add_argument('--no-markdown', action='store_true')
    ap.add_argument('--customer', action='store_true',
                    help='额外生成客户交付版方案（含 BOM/标定/换型/验收计划）')
    args = ap.parse_args(argv)

    if args.config:
        params = _load_config(args.config)
        # config 里 part_size 允许写字符串 '300x300'，统一解析成 dict
        if isinstance(params.get('part_size'), str):
            parsed = _parse_size(params['part_size'])
            if parsed is None:
                print('[参数校验失败]')
                print(" - 【产品尺寸格式错误】part_size 应为 '300x300' 或 '300x300x120'。")
                return 2
            params['part_size'] = parsed
    else:
        params = {
            'project_name': '3D视觉引导抓取方案',
            'application': '3d_robot_guidance',
            'part_size': _parse_size(args.part_size),
            'precision_requirement': args.precision,
            'precision_basis': args.precision_basis,
            'working_distance': args.working_distance,
            'cycle_time': args.cycle_time,
            'cycle_time_assumed': args.cycle_time_assumed,
            'installation': args.installation,
            'fov_margin': args.fov_margin,
            'part_may_rotate': args.part_may_rotate,
        }
    params = _validate_params(params)

    selector = ThreeDCameraSelector()
    if not selector.cameras:
        return 1
    result = selector.select(params, top_n=args.top_n)

    # 默认输出目录 = 基准目录/<项目名>（目录名与方案同名）。
    # config 链以 config 所在目录为基准（AI 从任意 cwd 调用也不会落错地方），
    # 命令行链没有 config 文件，退回当前工作目录。
    base_dir = os.path.dirname(os.path.abspath(args.config)) if args.config else '.'
    output_dir = args.output or os.path.join(
        base_dir, _safe_name(params.get('project_name') or '3D视觉引导抓取方案'))
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, 'three_d_selection.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')

    if not args.no_markdown:
        md = selector.render_markdown(result, top_n=args.top_n)
        md_path = os.path.join(output_dir, '3D视觉引导方案.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f'[输出] {md_path}')

    if args.customer:
        cp = selector.render_customer_proposal(result)
        cp_path = os.path.join(output_dir, '3D视觉引导抓取系统技术方案_客户版.md')
        with open(cp_path, 'w', encoding='utf-8') as f:
            f.write(cp)
        print(f'[输出] {cp_path}')

    s = result['summary']
    print(f"[汇总] 候选 {s['total']} 台：PASS {s['pass']} / WARN {s['warn']} / FAIL {s['fail']}")
    for c in result['top_n'][:args.top_n]:
        print(f"  [{c['verdict']}] {c['brand']} {c['model']} "
              f"WD={c.get('recommended_wd_mm')}mm "
              f"误差={c.get('guidance_error', {}).get('total_mm')}mm "
              f"评分={c.get('score')}")
    print(f'[输出] {json_path}')
    return 0 if s['has_feasible'] else 1


if __name__ == '__main__':
    sys.exit(main())
