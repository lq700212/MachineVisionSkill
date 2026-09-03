#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
精度计算器 - 机器视觉选型工具
用于计算物方分辨率、验证精度要求
"""

import json
import os
from typing import Dict, List, Tuple, Optional


def is_measurement_scene(params) -> bool:
    """尺寸测量场景判定（单点维护：选型分层与核验共用同一条件，防两链漂移）。

    判定依据（满足其一即为测量场景）：
      1. detection_type 含测量关键词（"尺寸测量"等，来自 --text 解析或 config 手填）
      2. application == 'measurement'
      3. 精度 ≤ 0.01mm（超高精度，透视误差不可接受，行业默认必须远心）
    测量场景的选型策略：远心优先，库内远心无匹配时回退普通镜头（lens_selector）。
    """
    if not isinstance(params, dict):
        return False
    detection_type = str(params.get('detection_type') or '')
    if any(kw in detection_type for kw in ('尺寸', '测量', '量测')):
        return True
    if params.get('application') == 'measurement':
        return True
    try:
        precision = float(params.get('precision_requirement') or 0)
    except (TypeError, ValueError):
        return False
    return 0 < precision <= 0.01


class PrecisionCalculator:
    """精度计算器"""
    
    def __init__(self):
        self.units = {
            'pixel_size': 'μm',      # 像元尺寸
            'magnification': 'x',     # 放大倍率
            'resolution': 'μm',       # 物方分辨率
            'precision': 'mm',        # 精度要求
        }
    
    def tolerance_to_precision(self, tolerance_mm: float, method: str = 'unilateral') -> Dict:
        """
        根据公差反推检测精度
        
        Args:
            tolerance_mm: 公差值（mm）
            method: 计算方法
                - 'unilateral': 单边公差（默认），精度 = 公差 × 1/10
                - 'bilateral': 双边公差（总公差带），精度 = 公差/2 × 1/10
                - 'total': 总公差带，精度 = 公差 × 1/10
        
        Returns:
            包含精度计算结果的字典
        """
        # 行业标准：精度 = 公差的 1/10
        precision_ratio = 1/10
        
        if method == 'unilateral':
            # 单边公差：直接用公差值计算
            # 例：±0.25mm → 精度 = 0.25 × 1/10 = 0.025mm
            required_precision = tolerance_mm * precision_ratio
            explanation = f"单边公差 {tolerance_mm}mm × 1/10 = {required_precision}mm"
        elif method == 'bilateral':
            # 双边公差（总公差带）：公差/2后计算
            # 例：±0.25mm (总范围0.5mm) → 精度 = 0.5/2 × 1/10 = 0.025mm
            half_tolerance = tolerance_mm / 2
            required_precision = half_tolerance * precision_ratio
            explanation = f"双边公差 {tolerance_mm}mm，半宽 {half_tolerance}mm × 1/10 = {required_precision}mm"
        elif method == 'total':
            # 总公差带：直接用总公差计算
            # 例：总公差带0.5mm → 精度 = 0.5 × 1/10 = 0.05mm
            required_precision = tolerance_mm * precision_ratio
            explanation = f"总公差带 {tolerance_mm}mm × 1/10 = {required_precision}mm"
        else:
            raise ValueError(f"不支持的计算方法: {method}")
        
        # 转换为μm
        required_precision_um = required_precision * 1000
        
        return {
            'tolerance_mm': tolerance_mm,
            'method': method,
            'precision_ratio': precision_ratio,
            'required_precision_mm': required_precision,
            'required_precision_um': required_precision_um,
            'explanation': explanation
        }
    
    def recommend_precision_from_tolerance(self, tolerance_mm: float) -> Dict:
        """
        根据公差推荐检测精度（使用单边公差计算，更严谨）
        
        Args:
            tolerance_mm: 公差值（mm），支持以下格式：
                - 单边公差：0.25（表示±0.25mm）
                - 总公差带：0.5（表示总变化范围0.5mm）
        
        Returns:
            推荐精度结果
        """
        # 默认使用单边公差计算（更严谨）
        result = self.tolerance_to_precision(tolerance_mm, method='unilateral')
        
        # 添加推荐说明
        result['recommendation'] = (
            f"根据公差 ±{tolerance_mm}mm，按照行业标准（精度=公差×1/10），"
            f"推荐检测精度为 {result['required_precision_mm']:.3f}mm ({result['required_precision_um']:.0f}μm)"
        )
        
        # 计算安全区间
        result['precision_range'] = {
            'conservative': result['required_precision_mm'] * 1.5,  # 保守：精度更高
            'standard': result['required_precision_mm'],            # 标准
            'relaxed': result['required_precision_mm'] * 0.7,       # 放松：精度略低
        }
        
        return result
    
    def calculate_object_resolution(self, pixel_size_um: float, magnification: float) -> float:
        """
        计算物方分辨率（像素精度）

        Args:
            pixel_size_um: 像元尺寸（μm）
            magnification: 镜头放大倍率

        Returns:
            物方分辨率（μm）
        """
        if magnification <= 0:
            raise ValueError("放大倍率必须大于0")

        object_resolution = pixel_size_um / magnification
        return object_resolution

    def required_object_resolution(self, required_precision_mm: float,
                                   pixel_per_precision: float = 3.0) -> float:
        """
        根据检测精度推导允许的最大像素精度（物方分辨率）

        行业方法（CSDN远心选型/长步道选型实例）：
            单个特征/边缘需占3~5个像素（亚像素算法取1/3像素），
            即 像素精度 ≤ 检测精度 / pixel_per_precision

        Args:
            required_precision_mm: 要求检测精度（mm）
            pixel_per_precision: 每精度单位占用像素数，默认3（保守取1）

        Returns:
            允许的最大像素精度（mm）
        """
        if pixel_per_precision <= 0:
            raise ValueError("pixel_per_precision 必须大于0")
        return required_precision_mm / pixel_per_precision

    def required_pixels(self, fov: Dict, pixel_resolution_mm: float) -> Dict:
        """
        根据视野和像素精度计算所需相机分辨率（与硬件无关，需求侧推导）

        Args:
            fov: {'width': mm, 'height': mm}
            pixel_resolution_mm: 像素精度（mm/pixel）

        Returns:
            {'x': int, 'y': int, 'total_mp': float}
        """
        if pixel_resolution_mm <= 0:
            raise ValueError("像素精度必须大于0")
        px_x = fov['width'] / pixel_resolution_mm
        px_y = fov['height'] / pixel_resolution_mm
        return {
            'x': int(px_x + 0.999),  # 向上取整
            'y': int(px_y + 0.999),
            'total_mp': (px_x * px_y) / 1000000
        }

    def magnification_window(self, camera: Dict, fov: Dict,
                             required_precision_mm: float,
                             pixel_per_precision: float = 3.0) -> Dict:
        """
        推导某相机同时满足"视野覆盖+精度"的镜头倍率闭区间

        视野约束：  FOV = 传感器宽 / 倍率  →  倍率 ≤ sensor_w / fov_w
        精度约束：  pixel/倍率 ≤ 精度/k    →  倍率 ≥ pixel / (精度/k)

        Args:
            camera: 相机字典（需 resolution.width/height、pixel_size）
            fov: {'width': mm, 'height': mm}
            required_precision_mm: 要求检测精度（mm）
            pixel_per_precision: 亚像素因子

        Returns:
            {'mag_min', 'mag_max', 'feasible', 'reason',
             'pixel_precision_max_mm': 精度允许的最大像素精度}
        """
        res = camera.get('resolution', {})
        res_w = res.get('width', 0)
        res_h = res.get('height', 0)
        pixel_um = camera.get('pixel_size', 0)
        if res_w <= 0 or res_h <= 0 or pixel_um <= 0:
            return {'feasible': False, 'reason': '相机参数不完整', 'mag_min': 0, 'mag_max': 0}

        sensor_w_mm = res_w * pixel_um / 1000.0
        sensor_h_mm = res_h * pixel_um / 1000.0

        pixel_precision_max = self.required_object_resolution(
            required_precision_mm, pixel_per_precision)  # mm/pixel

        # 精度下限：倍率必须够大
        mag_min = (pixel_um / 1000.0) / pixel_precision_max
        # 视野上限：倍率不能太大（否则视野不够）
        mag_max_w = sensor_w_mm / fov['width'] if fov['width'] > 0 else float('inf')
        mag_max_h = sensor_h_mm / fov['height'] if fov['height'] > 0 else float('inf')
        mag_max = min(mag_max_w, mag_max_h)

        feasible = mag_min <= mag_max and mag_min > 0
        reason = ''
        if not feasible:
            if mag_max <= 0:
                reason = '视野参数无效'
            else:
                reason = (f"无解：精度要求需要倍率≥{mag_min:.3f}x，"
                          f"但视野覆盖限制倍率≤{mag_max:.3f}x（该相机分辨率不足）")
        return {
            'feasible': feasible,
            'reason': reason,
            'mag_min': round(mag_min, 4),
            'mag_max': round(mag_max, 4),
            'pixel_precision_max_mm': pixel_precision_max,
            'sensor_w_mm': round(sensor_w_mm, 2),
            'sensor_h_mm': round(sensor_h_mm, 2),
        }

    def actual_fov(self, camera: Dict, magnification: float) -> Dict:
        """某相机配某倍率镜头时的实际视野（mm）"""
        res = camera.get('resolution', {})
        pixel_um = camera.get('pixel_size', 0)
        if magnification <= 0:
            return {'width': 0, 'height': 0}
        return {
            'width': res.get('width', 0) * pixel_um / 1000.0 / magnification,
            'height': res.get('height', 0) * pixel_um / 1000.0 / magnification,
        }
    
    def verify_precision(self, object_resolution_um: float, required_precision_mm: float) -> Tuple[bool, float]:
        """
        验证精度是否满足要求
        
        Args:
            object_resolution_um: 物方分辨率（μm）
            required_precision_mm: 要求精度（mm）
            
        Returns:
            (是否满足要求, 安全系数)
        """
        required_precision_um = required_precision_mm * 1000  # mm转μm
        
        # 安全系数 = 要求精度 / 实际分辨率
        safety_factor = required_precision_um / object_resolution_um
        
        # 通常要求安全系数 >= 1.5（预留50%余量）
        is_satisfied = safety_factor >= 1.0
        recommended_factor = 1.5
        
        return is_satisfied, safety_factor
    
    def find_suitable_cameras(self, required_precision_mm: float, cameras: List[Dict]) -> List[Dict]:
        """
        根据精度要求筛选合适的相机
        
        Args:
            required_precision_mm: 要求精度（mm）
            cameras: 相机列表
            
        Returns:
            满足精度要求的相机列表
        """
        suitable_cameras = []
        
        for camera in cameras:
            pixel_size = camera.get('pixel_size', 0)
            if pixel_size <= 0:
                continue
            
            # 计算最大允许放大倍率（假设使用1x镜头）
            max_magnification_needed = pixel_size / (required_precision_mm * 1000)
            
            camera_info = camera.copy()
            camera_info['max_allowed_magnification'] = max_magnification_needed
            camera_info['object_resolution_at_1x'] = pixel_size  # 1x时的物方分辨率
            
            suitable_cameras.append(camera_info)
        
        # 按像元尺寸排序（越小精度越高）
        suitable_cameras.sort(key=lambda x: x['pixel_size'])
        
        return suitable_cameras
    
    def find_suitable_lenses(self, camera_pixel_size_um: float, required_precision_mm: float, 
                            lenses: List[Dict]) -> List[Dict]:
        """
        根据相机和精度要求筛选合适的镜头
        
        Args:
            camera_pixel_size_um: 相机像元尺寸（μm）
            required_precision_mm: 要求精度（mm）
            lenses: 镜头列表
            
        Returns:
            满足要求的镜头列表
        """
        suitable_lenses = []
        required_precision_um = required_precision_mm * 1000
        
        for lens in lenses:
            magnification = lens.get('magnification', 0)
            if magnification <= 0:
                continue
            
            # 计算物方分辨率
            object_resolution = camera_pixel_size_um / magnification
            
            # 验证精度
            is_satisfied, safety_factor = self.verify_precision(object_resolution, required_precision_mm)
            
            if is_satisfied:
                lens_info = lens.copy()
                lens_info['object_resolution'] = object_resolution
                lens_info['safety_factor'] = safety_factor
                suitable_lenses.append(lens_info)
        
        # 按安全系数降序排序（余量越大越好）
        suitable_lenses.sort(key=lambda x: x['safety_factor'], reverse=True)
        
        return suitable_lenses
    
    def calculate_optical_params(self, pixel_size_um: float, magnification: float, 
                                sensor_width_px: int, sensor_height_px: int) -> Dict:
        """
        计算光学参数
        
        Args:
            pixel_size_um: 像元尺寸（μm）
            magnification: 放大倍率
            sensor_width_px: 传感器宽度（像素）
            sensor_height_px: 传感器高度（像素）
            
        Returns:
            光学参数字典
        """
        # 物方分辨率
        object_resolution = self.calculate_object_resolution(pixel_size_um, magnification)
        
        # 物方视野（FOV）
        fov_width = (sensor_width_px * pixel_size_um) / magnification / 1000  # mm
        fov_height = (sensor_height_px * pixel_size_um) / magnification / 1000  # mm
        
        # 物方对角线
        fov_diagonal = (fov_width**2 + fov_height**2)**0.5
        
        return {
            'object_resolution_um': object_resolution,
            'fov_width_mm': fov_width,
            'fov_height_mm': fov_height,
            'fov_diagonal_mm': fov_diagonal,
            'magnification': magnification,
            'pixel_size_um': pixel_size_um
        }
    
    def calculate_max_exposure_time(self, pixel_precision_mm: float, conveyor_speed_mm_s: float, safety_factor: float = 0.5) -> Dict:
        """计算飞拍最大允许曝光时间
        
        Args:
            pixel_precision_mm: 像素精度（mm/pixel）
            conveyor_speed_mm_s: 流水线速度（mm/s）
            safety_factor: 安全系数（允许的运动模糊占像素精度的比例，默认0.5即半像素）
        
        Returns:
            包含曝光时间计算结果的字典
        """
        if conveyor_speed_mm_s <= 0:
            raise ValueError("流水线速度必须大于0")
        
        # 允许的运动模糊量（mm）
        allowed_blur_mm = pixel_precision_mm * safety_factor
        
        # 最大曝光时间（秒）
        max_exposure_s = allowed_blur_mm / conveyor_speed_mm_s
        
        # 转换为微秒
        max_exposure_us = max_exposure_s * 1e6
        
        return {
            'pixel_precision_mm': pixel_precision_mm,
            'conveyor_speed_mm_s': conveyor_speed_mm_s,
            'safety_factor': safety_factor,
            'allowed_blur_mm': allowed_blur_mm,
            'max_exposure_s': max_exposure_s,
            'max_exposure_us': max_exposure_us,
            'explanation': f"允许运动模糊 {allowed_blur_mm:.4f}mm = 像素精度 {pixel_precision_mm}mm × 安全系数 {safety_factor}，"
                          f"最大曝光时间 = {allowed_blur_mm:.4f}mm / {conveyor_speed_mm_s}mm/s = {max_exposure_s:.6f}s ({max_exposure_us:.1f}μs)"
        }


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='精度计算器')
    parser.add_argument('--pixel_size', type=float, required=True, help='像元尺寸（μm）')
    parser.add_argument('--magnification', type=float, required=True, help='放大倍率')
    parser.add_argument('--precision', type=float, required=True, help='要求精度（mm）')
    parser.add_argument('--sensor_width', type=int, default=2448, help='传感器宽度（像素）')
    parser.add_argument('--sensor_height', type=int, default=2048, help='传感器高度（像素）')
    
    args = parser.parse_args()
    
    calculator = PrecisionCalculator()
    
    # 计算物方分辨率
    object_resolution = calculator.calculate_object_resolution(args.pixel_size, args.magnification)
    
    # 验证精度
    is_satisfied, safety_factor = calculator.verify_precision(object_resolution, args.precision)
    
    # 计算光学参数
    optical_params = calculator.calculate_optical_params(
        args.pixel_size, args.magnification, args.sensor_width, args.sensor_height
    )
    
    print("=" * 50)
    print("精度计算结果")
    print("=" * 50)
    print(f"像元尺寸: {args.pixel_size} μm")
    print(f"放大倍率: {args.magnification}x")
    print(f"物方分辨率: {object_resolution:.2f} μm")
    print(f"要求精度: {args.precision} mm ({args.precision*1000} μm)")
    print(f"安全系数: {safety_factor:.2f}")
    print(f"精度满足: {'满足' if is_satisfied else '不满足'}")
    print()
    print("光学参数:")
    print(f"  物方视野宽度: {optical_params['fov_width_mm']:.2f} mm")
    print(f"  物方视野高度: {optical_params['fov_height_mm']:.2f} mm")
    print(f"  物方视野对角线: {optical_params['fov_diagonal_mm']:.2f} mm")


if __name__ == '__main__':
    main()