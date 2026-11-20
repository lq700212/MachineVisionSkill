#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
光源选型工具
============
根据视野、工作距离等参数推荐合适的光源并计算光源工作距离

环形光源工作距离计算公式（基于几何关系）：
  光源工作距离 = (视野对角线 × 系数)
  系数取决于照射角度：
    - 30°角（低角度）：0.5-0.8
    - 45°角（中角度）：0.8-1.0
    - 60°角（高角度）：1.0-1.5
    - 90°角（垂直）：1.5-2.0

数据来源（2026-11-20 重构，根因见 CHANGELOG）：
  旧版本把 6 条光源硬编码在 LIGHT_SOURCE_DATABASE 里，型号是"品牌前缀+尺寸+角度+颜色"
  拼出来的（如 OPT RL-150-120-W），OPT 官网根本没有这个命名，属于幻觉数据；且没有
  verified/官网链接，核验也不查光源，导致假型号一路进 PPT。
  现改为：唯一数据源 = config/hardware_database.json 的 light_sources。
  库为空或条目缺关键字段时，诚实返回空/带 unverified 标记，绝不拼型号。
"""

import argparse
import json
import math
import os
from typing import Dict, List, Optional

# skill 根目录（tools/ 的上一级），用于定位硬件库
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(SKILL_DIR, 'config', 'hardware_database.json')


def load_light_database(db_path: str = None) -> List[Dict]:
    """从 hardware_database.json 读取光源库。

    返回结构合法的条目（至少含 model + type）。库文件缺失/为空/JSON 损坏时
    返回空列表并打印明确提示——调用方必须按"无可用光源"处理，禁止兜底编型号。
    """
    path = db_path or DEFAULT_DB_PATH
    if not os.path.exists(path):
        print(f"  [光源库] 未找到硬件库: {path}")
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            db = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"  [光源库] 读取失败: {e}")
        return []

    lights = db.get('light_sources') or []
    valid = []
    for item in lights:
        if not isinstance(item, dict):
            continue
        if not item.get('model') or not item.get('type'):
            continue
        valid.append(item)

    if not valid:
        print("  [光源库] ⚠ 库内无可用光源条目（light_sources 为空）。"
              "请先按 SKILL.md 扩库流程入库已核验型号，禁止编造。")
    return valid


def calculate_light_working_distance(field_of_view: Dict,
                                     camera_wd: float = 100,
                                     light_angle: int = 45,
                                     safety_factor: float = 1.2) -> Dict:
    """
    计算光源工作距离

    Args:
        field_of_view: 视野 {"width": mm, "height": mm}
        camera_wd: 相机工作距离（镜头到物体距离）
        light_angle: 光源照射角度（度）
        safety_factor: 安全系数

    Returns:
        光源工作距离计算结果
    """
    fov_width = field_of_view.get('width', 50)
    fov_height = field_of_view.get('height', 40)

    # 计算视野对角线
    fov_diagonal = math.sqrt(fov_width**2 + fov_height**2)

    # 根据照射角度确定系数
    # 角度越小，光源越靠近物体，工作距离越短
    angle_factors = {
        30: 0.6,   # 低角度：工作距离短
        45: 0.8,   # 中角度：工作距离适中
        60: 1.0,   # 高角度：工作距离较长
        90: 1.5    # 垂直照射：工作距离最长
    }

    factor = angle_factors.get(light_angle, 0.8)

    # 计算光源工作距离
    # 经验公式：光源WD = 视野对角线 × 角度系数
    light_wd = fov_diagonal * factor * safety_factor

    # 限制最小工作距离（至少30mm）
    light_wd = max(30, light_wd)

    return {
        "field_of_view": field_of_view,
        "fov_diagonal_mm": round(fov_diagonal, 1),
        "light_angle": light_angle,
        "factor": factor,
        "working_distance_mm": round(light_wd, 1),
        "safety_factor": safety_factor,
        "formula": f"光源WD = 视野对角线({fov_diagonal:.1f}mm) × 角度系数({factor}) × 安全系数({safety_factor}) = {light_wd:.1f}mm"
    }


# 角度选型规则（2026-11-20 按应用场景固化，回答"高角度还是低角度"）：
#   定位/测量/孔中心 → 高角度 60~90°：光线接近垂直，孔边倒角受光均匀、
#     阴影短，边缘位置真实；低角度会把孔壁拉出长阴影，圆心产生系统性偏移。
#   表面划痕/纹理/凹凸/字符 → 低角度 10~30°：掠射增强微观起伏对比度。
#   通用外观 → 45°。
LIGHT_ANGLE_RULES = {
    'high': {'angles': (60, 75, 90), 'preferred': 60,
             'reason': '定位/测量场景选高角度环光（60~90°）：孔边受光均匀、阴影短，边缘位置真实'},
    'mid': {'angles': (45,), 'preferred': 45,
            'reason': '通用外观场景选中角度环光（45°）：兼顾照明均匀性与轻微立体感'},
    'low': {'angles': (10, 15, 30), 'preferred': 30,
            'reason': '表面缺陷/纹理场景选低角度环光（10~30°）：掠射增强凹凸、划痕对比度'},
}

_HIGH_ANGLE_KEYWORDS = ('定位', '引导', '贴装', '装配', '孔', '圆心', '尺寸测量',
                        '测量', '对位', '校准', '标定')
_LOW_ANGLE_KEYWORDS = ('划痕', '纹理', '凹凸', '压印', '字符', 'ocr', '表面缺陷',
                       '裂纹', '毛刺', '异物')


def angle_tier(angle) -> str:
    """角度分档：高角度≥60°、中角度40~59°、低角度<40°"""
    try:
        a = float(angle)
    except (TypeError, ValueError):
        return ''
    if a >= 60:
        return 'high'
    if a >= 40:
        return 'mid'
    return 'low'


def recommend_light_angle(detection_type: str = '', detection_items=None) -> Dict:
    """按检测任务推荐环光角度档位。

    缺陷关键词优先于定位关键词：同一任务既要定位又要查划痕时，角度先服从缺陷
    （划痕对比度对角度更敏感，定位可靠 ROI/算法补偿）。
    """
    text = f"{detection_type or ''} {' '.join(detection_items or [])}".lower()
    if any(k.lower() in text for k in _LOW_ANGLE_KEYWORDS):
        key = 'low'
    elif any(k.lower() in text for k in _HIGH_ANGLE_KEYWORDS):
        key = 'high'
    else:
        key = 'mid'
    rule = LIGHT_ANGLE_RULES[key]
    return {'mode': key, 'preferred': rule['preferred'],
            'accept': rule['angles'], 'reason': rule['reason']}


def _split_by_brand(pool: List[Dict], preferred_brands) -> List[List[Dict]]:
    """按品牌优先级切层：每层是同一品牌的子集，层序=优先级。

    品牌名用"包含"匹配（"追光者"命中"追光者(苏州)"）。未登记的尾部品牌
    合并为最后一层，保证库扩容后不会因品牌未列入而全空。
    """
    if not preferred_brands:
        return [pool]
    layers, used = [], set()
    for brand in preferred_brands:
        layer = [l for l in pool
                 if brand in str(l.get('brand') or '') and id(l) not in used]
        if layer:
            layers.append(layer)
            used.update(id(l) for l in layer)
    rest = [l for l in pool if id(l) not in used]
    if rest:
        layers.append(rest)
    return layers


def _filter_candidates(pool: List[Dict], fov_diagonal: float,
                       required_wd: float, angle: int,
                       strict_angle: bool) -> List[Dict]:
    """对单层池做尺寸/内径/角度/WD 过滤并打分（不编造缺失字段的取值）"""
    out = []
    pref_tier = angle_tier(angle) if angle is not None else ''

    for light in pool:
        l_angle = light.get('angle')
        # 角度硬过滤：按档位（高/中/低）匹配；strict_angle=True 时只留完全相同角度
        if angle is not None:
            if strict_angle:
                if l_angle is None or abs(float(l_angle) - float(angle)) > 0.1:
                    continue
            elif pref_tier and l_angle is not None:
                if angle_tier(l_angle) != pref_tier:
                    continue

        # 照射范围：外径必须覆盖视野对角线（缺失外径 = 无法判断，保留并标记）
        outer_d = light.get('outer_diameter')
        outer_ok = None
        if outer_d is not None:
            outer_ok = outer_d >= fov_diagonal * 1.1
            if not outer_ok:
                continue

        # 内孔不得小于视野对角线×1.1（留 10% 装配/光锥余量，否则光源本体
        # 会在视野四角形成遮挡）；缺内径 = 待核验
        inner_d = light.get('inner_diameter')
        inner_unverified = True
        if inner_d is not None:
            inner_unverified = False
            if inner_d < fov_diagonal * 1.1:
                continue

        # 工作距离过滤：区间缺失 = 无法判断，保留并标记（禁止编造区间）
        wd_unverified = False
        wd_min = wd_max = None
        wd_range = light.get('working_distance_range')
        if isinstance(wd_range, (list, tuple)) and len(wd_range) == 2:
            wd_min, wd_max = wd_range
            if required_wd and not (wd_min * 0.8 <= required_wd <= wd_max * 1.2):
                continue
        elif required_wd:
            wd_unverified = True

        # 评分：角度 45% + 尺寸 30% + 工作距离 15% + 可查证 10%
        angle_score = 0.5
        if angle is not None and l_angle is not None:
            angle_score = max(0.0, 1.0 - abs(float(l_angle) - float(angle)) / 90.0)
        size_score = 0.5
        if outer_d is not None and fov_diagonal > 0:
            ideal = fov_diagonal * 1.5
            size_score = max(0.0, 1.0 - abs(outer_d - ideal) / ideal)
        wd_score = 0.5
        if required_wd and wd_min is not None:
            wd_center = (wd_min + wd_max) / 2
            wd_score = 1.0 / (1.0 + abs(required_wd - wd_center) / 50)
        trust_score = 1.0 if light.get('verified') else 0.3

        out.append({
            **light,
            "score": round(angle_score * 0.45 + size_score * 0.30
                           + wd_score * 0.15 + trust_score * 0.10, 4),
            "outer_diameter_verified": outer_ok is not None,
            "inner_diameter_verified": not inner_unverified,
            "wd_range_verified": not wd_unverified,
        })
    return out


def select_light_source(fov_diagonal: float,
                        required_wd: float = None,
                        light_type: str = "环形光",
                        is_fly_shooting: bool = False,
                        max_exposure_us: float = None,
                        lights: List[Dict] = None,
                        db_path: str = None,
                        angle: int = None,
                        preferred_brands: List[str] = None,
                        strict_angle: bool = False) -> List[Dict]:
    """
    根据视野、工作距离、角度档位与品牌优先级选择光源。

    Args:
        fov_diagonal: 视野对角线（mm）
        required_wd: 要求的光源工作距离（mm）
        light_type: 光源类型
        is_fly_shooting: 是否飞拍场景
        max_exposure_us: 最大允许曝光时间（微秒），飞拍时用于筛选支持频闪的光源
        lights: 显式传入光源列表（测试/调用方已加载时用，避免重复读盘）
        db_path: 硬件库路径（默认 skill 的 config/hardware_database.json）
        angle: 首选照射角度；None=不限
        preferred_brands: 品牌优先级（如 ['追光者','孚根','OPT']），逐层降级
        strict_angle: True=只接受完全相同角度；False=同档位（高/中/低）即可

    Returns:
        推荐光源列表；库为空或全不匹配时返回 []（绝不编造型号兜底）
    """
    pool = lights if lights is not None else load_light_database(db_path)

    # 类型/飞拍过滤先做（所有品牌层共用）
    typed = []
    for light in pool:
        # 飞拍场景的频闪光源不受 light_type 过滤：
        # 此前默认 light_type='环形光' 会把唯一频闪光源提前滤掉，飞拍查询恒为空
        if light_type and light["type"] != light_type:
            if not (is_fly_shooting and light.get("strobe", False)):
                continue
        if is_fly_shooting:
            if not light.get("strobe", False):
                continue
            if max_exposure_us is not None:
                min_exp = light.get("min_exposure_us", 0)
                if max_exposure_us < min_exp:
                    continue
        typed.append(light)

    # 品牌分层：追光者层有合适型号就只用它；该层为空才降级到孚根/其他
    candidates = []
    for layer in _split_by_brand(typed, preferred_brands):
        candidates = _filter_candidates(layer, fov_diagonal, required_wd,
                                        angle, strict_angle)
        if candidates:
            break

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def main():
    parser = argparse.ArgumentParser(description="光源选型工具")
    parser.add_argument("--fov_width", type=float, required=True, help="视野宽度（mm）")
    parser.add_argument("--fov_height", type=float, required=True, help="视野高度（mm）")
    parser.add_argument("--camera_wd", type=float, default=100, help="相机工作距离（mm）")
    parser.add_argument("--light_angle", type=int, default=45, choices=[30, 45, 60, 90],
                       help="光源照射角度")
    parser.add_argument("--db", help="硬件库路径（默认 skill 的 config/hardware_database.json）")
    parser.add_argument("--output", help="输出JSON文件路径")
    args = parser.parse_args()

    print("=" * 50)
    print("光源选型")
    print("=" * 50)
    print(f"视野: {args.fov_width} x {args.fov_height} mm")
    print(f"相机工作距离: {args.camera_wd} mm")
    print(f"光源照射角度: {args.light_angle}°")

    # 计算光源工作距离
    result = calculate_light_working_distance(
        field_of_view={"width": args.fov_width, "height": args.fov_height},
        camera_wd=args.camera_wd,
        light_angle=args.light_angle
    )

    print(f"\n计算结果:")
    print(f"  视野对角线: {result['fov_diagonal_mm']} mm")
    print(f"  推荐光源工作距离: {result['working_distance_mm']} mm")
    print(f"  计算公式: {result['formula']}")

    # 推荐光源
    fov_diagonal = result['fov_diagonal_mm']
    recommended_wd = result['working_distance_mm']

    candidates = select_light_source(
        fov_diagonal, recommended_wd, light_type=None, db_path=args.db)

    if candidates:
        print(f"\n推荐光源:")
        for i, light in enumerate(candidates[:3], 1):
            print(f"  {i}. {light['brand']} {light['model']}")
            print(f"     类型: {light['type']}, 角度: {light.get('angle', '-')}°")
            wd_range = light.get('working_distance_range')
            if wd_range:
                print(f"     工作距离范围: {wd_range[0]}-{wd_range[1]} mm")
            else:
                print(f"     工作距离范围: 未核验（禁止猜测，需厂商确认）")
            if not light.get('inner_diameter_verified'):
                print(f"     内径: 未核验（需确认内孔≥视野对角线 {fov_diagonal}mm）")
    else:
        print("\n[无可用光源] 库内无匹配条目，或光源库为空。")
        print("  处置：按 SKILL.md「数据库扩库流程」入库已核验型号后重跑；")
        print("        禁止用品牌+尺寸+角度拼型号。")

    if args.output:
        result["candidates"] = candidates[:3]
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n已保存到: {args.output}")

    return result


if __name__ == "__main__":
    main()
