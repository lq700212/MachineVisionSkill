#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
相机选型工具 - 机器视觉选型工具
根据检测需求自动筛选合适的工业相机
"""

import json
import os
from typing import Dict, List, Optional
from precision_calculator import PrecisionCalculator

class CameraSelector:
    """相机选型器"""
    
    def __init__(self, database_path: str = None):
        """
        初始化相机选型器
        
        Args:
            database_path: 硬件数据库路径
        """
        if database_path is None:
            # 使用默认路径
            script_dir = os.path.dirname(os.path.abspath(__file__))
            database_path = os.path.join(script_dir, '..', 'config', 'hardware_database.json')
        
        self.database_path = database_path
        self.calculator = PrecisionCalculator()
        self.cameras = self._load_cameras()
    
    def _load_cameras(self) -> List[Dict]:
        """加载相机数据库"""
        if not os.path.exists(self.database_path):
            print(f"警告: 数据库文件不存在: {self.database_path}")
            return []
        
        with open(self.database_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data.get('cameras', [])
    
    def select_cameras_for_fov(self,
                               fov: Dict,
                               required_precision_mm: float,
                               pixel_per_precision: float = 3.0,
                               interface: str = None,
                               brand: str = None,
                               min_fps: float = None,
                               top_n: int = 3) -> List[Dict]:
        """
        基于"视野+精度"双约束筛选相机（需求侧推导，不依赖假设硬件）

        判据（与硬件无关的必要条件）：
          分辨率 ≥ FOV × 亚像素因子 / 精度
        等价于：该相机存在倍率区间同时满足视野覆盖与精度要求。

        Args:
            fov: {'width': mm, 'height': mm}
            required_precision_mm: 要求检测精度（mm）
            pixel_per_precision: 亚像素因子（默认3：像素精度≤精度/3）
            interface: 接口类型
            brand: 品牌
            min_fps: 最小帧率（默认由cycle_time无法获知时用5fps）
            top_n: 返回前N个

        Returns:
            通过验证的相机列表（附倍率窗口、所需像素信息）
        """
        candidates = []
        pixel_precision_max = self.calculator.required_object_resolution(
            required_precision_mm, pixel_per_precision)

        for camera in self.cameras:
            res = camera.get('resolution', {})
            res_w = res.get('width', 0)
            res_h = res.get('height', 0)
            pixel_size = camera.get('pixel_size', 0)
            if res_w <= 0 or res_h <= 0 or pixel_size <= 0:
                continue

            resolution_mp = (res_w * res_h) / 1000000

            # 必要条件1：分辨率满足 视野/(精度/k)
            need_px_x = fov['width'] / pixel_precision_max
            need_px_y = fov['height'] / pixel_precision_max
            if res_w < need_px_x or res_h < need_px_y:
                continue

            # 必要条件2：倍率窗口非空（等价于条件1，用于给出窗口数据）
            window = self.calculator.magnification_window(
                camera, fov, required_precision_mm, pixel_per_precision)
            if not window.get('feasible'):
                continue

            # 可选过滤：接口/品牌/帧率
            if interface and camera.get('interface', '') != interface:
                continue
            if brand and camera.get('brand', '') != brand:
                continue
            fps = camera.get('max_fps', 0)
            if min_fps and fps < min_fps:
                continue

            # 推荐分数
            score = 0
            # 像素精度余量（实际最佳像素精度 vs 允许上限）
            best_pixel_precision = fov['width'] / res_w  # mm/pixel @ 倍率上限
            ratio = pixel_precision_max / best_pixel_precision  # ≥1
            if 1.0 <= ratio < 1.3:
                score += 60   # 刚好满足，余量小
            elif 1.3 <= ratio < 2.5:
                score += 100  # 余量适中（最佳）
            elif 2.5 <= ratio < 4.0:
                score += 80   # 偏过剩
            else:
                score += 50   # 严重过剩，成本高

            # 靶面评分（2/3"最通用，镜头选择多）
            sensor_size = camera.get('sensor_size', '')
            if '2/3' in sensor_size:
                score += 20
            elif '1/2' in sensor_size or '1/1.8' in sensor_size:
                score += 15
            elif sensor_size.startswith('1"'):
                score += 10
            elif '1.1' in sensor_size:
                score += 5

            # 帧率余量
            if fps >= 30:
                score += 10
            elif fps >= 20:
                score += 5

            info = camera.copy()
            info.update({
                'resolution_mp': resolution_mp,
                'required_pixels': {'x': int(need_px_x + 0.999),
                                    'y': int(need_px_y + 0.999)},
                'pixel_precision_max_mm': pixel_precision_max,
                'best_pixel_precision_mm': best_pixel_precision,
                'precision_margin_ratio': round(ratio, 2),
                'mag_window': window,
                'recommend_score': score,
                'validated': True,
            })
            if 'image_path' not in info:
                info['image_path'] = ''
            candidates.append(info)

        candidates.sort(key=lambda x: x.get('recommend_score', 0), reverse=True)
        return candidates[:top_n]

    def select_cameras(self,
                      required_precision_mm: float = 0.012,
                      min_resolution_mp: float = 5.0,
                      interface: str = None,
                      brand: str = None,
                      max_pixel_size: float = None,
                      top_n: int = 3) -> List[Dict]:
        """
        根据需求筛选相机（只返回通过验证的方案）
        
        Args:
            required_precision_mm: 要求精度（mm）
            min_resolution_mp: 最小分辨率（百万像素）
            interface: 接口类型（GigE/USB3/Camera Link等）
            brand: 品牌
            max_pixel_size: 最大像元尺寸（μm）
            top_n: 返回前N个推荐方案
            
        Returns:
            通过验证的相机列表（最多top_n个）
        """
        suitable_cameras = []
        
        for camera in self.cameras:
            # 检查分辨率
            resolution = camera.get('resolution', {})
            width = resolution.get('width', 0)
            height = resolution.get('height', 0)
            resolution_mp = (width * height) / 1000000
            
            if resolution_mp < min_resolution_mp:
                continue
            
            # 检查接口
            if interface and camera.get('interface', '') != interface:
                continue
            
            # 检查品牌
            if brand and camera.get('brand', '') != brand:
                continue
            
            # 检查像元尺寸
            pixel_size = camera.get('pixel_size', 0)
            if max_pixel_size and pixel_size > max_pixel_size:
                continue
            
            # 验证精度（假设使用1x镜头）
            object_resolution = pixel_size  # 1x时物方分辨率等于像元尺寸
            is_satisfied, safety_factor = self.calculator.verify_precision(
                object_resolution, required_precision_mm
            )
            
            if not is_satisfied:
                continue
            
            # ============ 关键验证：只保留通过验证的方案 ============
            
            # 验证1：安全系数必须在合理区间
            if safety_factor < 1.0:
                continue  # 精度不满足，跳过
            
            # 计算推荐分数
            score = 0
            
            # 安全系数评分（1.5~3最佳）
            if 1.5 <= safety_factor <= 3.0:
                score += 100  # 最佳区间
            elif 1.0 <= safety_factor < 1.5:
                score += 70   # 余量不足但可用
            elif 3.0 < safety_factor <= 5.0:
                score += 80   # 性能略过剩
            else:
                score += 50   # 严重过剩或不足
            
            # 靶面尺寸评分（2/3英寸最通用）
            sensor_size = camera.get('sensor_size', '')
            if '2/3' in sensor_size:
                score += 20   # 最通用，镜头选择多
            elif '1/2' in sensor_size:
                score += 15
            elif '1"' in sensor_size:
                score += 10   # 大靶面，成本高
            elif '1.1"' in sensor_size:
                score += 5
            
            # 帧率余量评分
            fps = camera.get('max_fps', 0)
            if fps >= 30:
                score += 10
            elif fps >= 20:
                score += 5
            
            # 验证标记
            camera_info = camera.copy()
            camera_info['resolution_mp'] = resolution_mp
            camera_info['object_resolution_at_1x'] = object_resolution
            camera_info['safety_factor_at_1x'] = safety_factor
            camera_info['recommend_score'] = score
            camera_info['validated'] = True  # 标记为已验证
            # 确保image_path字段存在
            if 'image_path' not in camera_info:
                camera_info['image_path'] = ''
            suitable_cameras.append(camera_info)
        
        # 按推荐分数降序排序
        suitable_cameras.sort(key=lambda x: x.get('recommend_score', 0), reverse=True)
        
        # 只返回前top_n个通过验证的方案
        return suitable_cameras[:top_n]
    
    def get_camera_by_model(self, model: str) -> Optional[Dict]:
        """根据型号获取相机信息"""
        for camera in self.cameras:
            if camera.get('model', '') == model:
                return camera
        return None
    
    def compare_cameras(self, models: List[str]) -> List[Dict]:
        """比较多个相机的参数"""
        compared = []
        
        for model in models:
            camera = self.get_camera_by_model(model)
            if camera:
                compared.append(camera)
        
        return compared
    
    def print_camera_info(self, camera: Dict):
        """打印相机信息"""
        print(f"\n{'='*60}")
        print(f"相机型号: {camera.get('brand', '')} {camera.get('model', '')}")
        print(f"{'='*60}")
        print(f"传感器: {camera.get('sensor', '')}")
        print(f"传感器尺寸: {camera.get('sensor_size', '')}")
        resolution = camera.get('resolution', {})
        print(f"分辨率: {resolution.get('width', 0)}×{resolution.get('height', 0)} ({camera.get('resolution_mp', 0):.1f}MP)")
        print(f"像元尺寸: {camera.get('pixel_size', 0)} μm")
        print(f"接口: {camera.get('interface', '')}")
        print(f"最大帧率: {camera.get('max_fps', 0)} fps")
        print(f"快门类型: {camera.get('shutter', '')}")
        print(f"动态范围: {camera.get('dynamic_range', '')}")
        print(f"信噪比: {camera.get('snr', '')}")
        print(f"镜头接口: {camera.get('lens_mount', '')}")
        print(f"供电: {camera.get('power', '')}")
        print(f"功耗: {camera.get('power_consumption', '')}")
        print(f"工作温度: {camera.get('operating_temp', '')}")
        print(f"防护等级: {camera.get('ip_rating', '')}")
        
        if 'object_resolution_at_1x' in camera:
            print(f"\n精度分析:")
            print(f"  1x镜头时物方分辨率: {camera['object_resolution_at_1x']:.2f} μm")
            print(f"  安全系数: {camera.get('safety_factor_at_1x', 0):.2f}")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='相机选型工具')
    parser.add_argument('--precision', type=float, default=0.012, help='要求精度（mm）')
    parser.add_argument('--min_resolution', type=float, default=5.0, help='最小分辨率（MP）')
    parser.add_argument('--interface', type=str, help='接口类型（GigE/USB3等）')
    parser.add_argument('--brand', type=str, help='品牌')
    parser.add_argument('--max_pixel_size', type=float, help='最大像元尺寸（μm）')
    parser.add_argument('--model', type=str, help='查询特定型号')
    parser.add_argument('--compare', type=str, nargs='+', help='比较多个型号')
    
    args = parser.parse_args()
    
    selector = CameraSelector()
    
    if args.model:
        # 查询特定型号
        camera = selector.get_camera_by_model(args.model)
        if camera:
            selector.print_camera_info(camera)
        else:
            print(f"未找到型号: {args.model}")
    elif args.compare:
        # 比较多个型号
        cameras = selector.compare_cameras(args.compare)
        for camera in cameras:
            selector.print_camera_info(camera)
    else:
        # 筛选相机
        suitable_cameras = selector.select_cameras(
            required_precision_mm=args.precision,
            min_resolution_mp=args.min_resolution,
            interface=args.interface,
            brand=args.brand,
            max_pixel_size=args.max_pixel_size
        )
        
        print(f"\n满足条件的相机: {len(suitable_cameras)} 个")
        print(f"筛选条件: 精度≤{args.precision}mm, 分辨率≥{args.min_resolution}MP")
        
        for i, camera in enumerate(suitable_cameras, 1):
            print(f"\n{i}. {camera.get('brand', '')} {camera.get('model', '')}")
            resolution = camera.get('resolution', {})
            print(f"   分辨率: {resolution.get('width', 0)}×{resolution.get('height', 0)}")
            print(f"   像元尺寸: {camera.get('pixel_size', 0)} μm")
            print(f"   接口: {camera.get('interface', '')}")


if __name__ == '__main__':
    main()