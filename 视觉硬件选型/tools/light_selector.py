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
"""

import json
import argparse
import math
from typing import Dict, List


# 光源数据库
LIGHT_SOURCE_DATABASE = [
    {
        "brand": "OPT",
        "model": "RL-100-90-W",
        "type": "环形光",
        "angle": 90,
        "wavelength": "白光",
        "inner_diameter": 50,
        "outer_diameter": 100,
        "led_rows": 3,
        "working_distance_range": [80, 200],
        "recommended_wd": 120
    },
    {
        "brand": "OPT",
        "model": "RL-50-30-W",
        "type": "环形光",
        "angle": 45,
        "wavelength": "白光",
        "inner_diameter": 20,
        "outer_diameter": 50,
        "led_rows": 2,
        "working_distance_range": [30, 100],
        "recommended_wd": 60
    },
    {
        "brand": "OPT",
        "model": "RL-150-120-W",
        "type": "环形光",
        "angle": 60,
        "wavelength": "白光",
        "inner_diameter": 80,
        "outer_diameter": 150,
        "led_rows": 4,
        "working_distance_range": [100, 300],
        "recommended_wd": 180
    },
    {
        "brand": "CCS",
        "model": "ZF-150W",
        "type": "环形光",
        "angle": 45,
        "wavelength": "白光",
        "inner_diameter": 60,
        "outer_diameter": 150,
        "led_rows": 3,
        "working_distance_range": [60, 180],
        "recommended_wd": 120
    },
    {
        "brand": "CCS",
        "model": "ZF-300W",
        "type": "环形光",
        "angle": 30,
        "wavelength": "白光",
        "inner_diameter": 120,
        "outer_diameter": 300,
        "led_rows": 5,
        "working_distance_range": [150, 400],
        "recommended_wd": 250
    }
]


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


def select_light_source(fov_diagonal: float, 
                        required_wd: float = None,
                        light_type: str = "环形光") -> List[Dict]:
    """
    根据视野和工作距离选择光源
    
    Args:
        fov_diagonal: 视野对角线（mm）
        required_wd: 要求的光源工作距离（mm）
        light_type: 光源类型
    
    Returns:
        推荐的光源列表
    """
    candidates = []
    
    for light in LIGHT_SOURCE_DATABASE:
        # 检查光源类型
        if light_type and light["type"] != light_type:
            continue
        
        # 检查工作距离是否满足
        if required_wd:
            wd_min, wd_max = light["working_distance_range"]
            if required_wd < wd_min * 0.8 or required_wd > wd_max * 1.2:
                continue
        
        # 计算适配度分数
        score = 0
        if required_wd:
            wd_min, wd_max = light["working_distance_range"]
            wd_center = (wd_min + wd_max) / 2
            wd_diff = abs(required_wd - wd_center)
            score = 1.0 / (1.0 + wd_diff / 50)
        
        candidates.append({**light, "score": score})
    
    # 按分数排序
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    return candidates


def main():
    parser = argparse.ArgumentParser(description="光源选型工具")
    parser.add_argument("--fov_width", type=float, required=True, help="视野宽度（mm）")
    parser.add_argument("--fov_height", type=float, required=True, help="视野高度（mm）")
    parser.add_argument("--camera_wd", type=float, default=100, help="相机工作距离（mm）")
    parser.add_argument("--light_angle", type=int, default=45, choices=[30, 45, 60, 90], 
                       help="光源照射角度")
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
    
    candidates = select_light_source(fov_diagonal, recommended_wd)
    
    if candidates:
        print(f"\n推荐光源:")
        for i, light in enumerate(candidates[:3], 1):
            print(f"  {i}. {light['brand']} {light['model']}")
            print(f"     类型: {light['type']}, 角度: {light['angle']}°")
            print(f"     工作距离范围: {light['working_distance_range'][0]}-{light['working_distance_range'][1]} mm")
    
    if args.output:
        result["candidates"] = candidates[:3]
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n已保存到: {args.output}")
    
    return result


if __name__ == "__main__":
    main()
