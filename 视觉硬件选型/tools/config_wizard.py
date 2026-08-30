#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置向导脚本
交互式引导用户输入视觉检测项目参数
"""

import json
import os
from typing import Dict, Any, Optional

class ConfigWizard:
    """配置向导"""
    
    def __init__(self):
        self.config = {}
        
    def run(self) -> Dict:
        """运行配置向导"""
        print("\n" + "=" * 60)
        print("视觉检测方案配置向导")
        print("=" * 60)
        print("请按照提示输入项目参数，直接回车使用默认值\n")
        
        # 1. 基本项目信息
        self._input_basic_info()
        
        # 2. 检测需求
        self._input_detection_requirements()
        
        # 3. 硬件偏好
        self._input_hardware_preferences()
        
        # 4. 确认配置
        self._confirm_config()
        
        return self.config
    
    def _input_basic_info(self):
        """输入基本信息"""
        print("\n--- 基本项目信息 ---")
        
        # 项目名称
        project_name = input("项目名称 [视觉检测项目]: ").strip()
        self.config['project_name'] = project_name if project_name else '视觉检测项目'
        
        # 应用场景
        print("\n应用场景类型:")
        print("  1. 尺寸测量")
        print("  2. 缺陷检测")
        print("  3. 装配检测")
        print("  4. 综合检测")
        
        choice = input("请选择 [4]: ").strip()
        scene_map = {'1': '尺寸测量', '2': '缺陷检测', '3': '装配检测', '4': '综合检测'}
        self.config['application_scene'] = scene_map.get(choice, '综合检测')
    
    def _input_detection_requirements(self):
        """输入检测需求"""
        print("\n--- 检测需求 ---")
        
        # 精度/公差输入（二选一）
        print("\n精度要求（输入精度或公差，二选一）:")
        print("  方式1: 直接输入精度，如 0.012mm")
        print("  方式2: 输入公差，系统自动反推精度（精度=公差×1/10）")
        print("  示例: 公差±0.25mm → 精度=0.25×1/10=0.025mm")
        
        precision_input = input("\n请输入精度(mm)或公差(mm) [0.012]: ").strip()
        
        if precision_input:
            try:
                value = float(precision_input)
                # 判断是精度还是公差
                print("  请输入的是：")
                print("  1. 精度（直接使用）")
                print("  2. 公差（系统自动反推精度）")
                choice = input("  请选择 (1/2) [1]: ").strip()
                
                if choice == '2':
                    # 输入的是公差，自动反推精度
                    self.config['tolerance'] = value
                    # 精度会在vision_proposal_generator中自动计算
                    print(f"  已输入公差: ±{value}mm")
                    print(f"  系统将自动反推精度: {value}×1/10={value*0.1}mm")
                else:
                    # 输入的是精度，直接使用
                    self.config['precision_requirement'] = value
                    print(f"  已输入精度: {value}mm")
            except ValueError:
                print("  输入无效，使用默认精度 0.012mm")
                self.config['precision_requirement'] = 0.012
        else:
            print("  使用默认精度 0.012mm")
            self.config['precision_requirement'] = 0.012
        
        # 检测节拍
        print("\n检测节拍:")
        print("  常用值: 1s, 2s, 3s, 5s")
        cycle_time = input("请输入检测节拍(s) [3]: ").strip()
        self.config['cycle_time'] = float(cycle_time) if cycle_time else 3
        
        # 视野范围（工件尺寸）
        print("\n工件尺寸或视野范围:")
        print("  支持的格式:")
        print("    1. 工件尺寸: 50x30x20 (长x宽x高)")
        print("    2. 检测区域: 50x30 (宽x高)")
        print("    3. 直接视野: fov:60x40 (宽x高)")
        print("  注意: 系统会自动加20%余量")
        
        fov_input = input("请输入工件尺寸或视野(mm) [50x40]: ").strip()
        
        if fov_input:
            self.config['part_size'] = fov_input
            print(f"  已输入: {fov_input}")
        else:
            self.config['part_size'] = '50x40'
            print("  使用默认: 50x40")
        
        # 检测项目
        print("\n检测项目（可多选，用空格分隔）:")
        print("  1. 尺寸检测")
        print("  2. 间隙检测")
        print("  3. 位置度检测")
        print("  4. 漏装检测")
        print("  5. 错装检测")
        print("  6. 表面缺陷")
        print("  7. 装配状态")
        
        items_input = input("请选择检测项目 [1 2 3]: ").strip()
        
        item_map = {
            '1': '尺寸检测',
            '2': '间隙检测',
            '3': '位置度检测',
            '4': '漏装检测',
            '5': '错装检测',
            '6': '表面缺陷',
            '7': '装配状态'
        }
        
        if items_input:
            item_codes = items_input.split()
            self.config['detection_items'] = [item_map.get(code, '') for code in item_codes if code in item_map]
        else:
            self.config['detection_items'] = ['尺寸检测', '间隙检测', '位置度检测']
    
    def _input_hardware_preferences(self):
        """输入硬件偏好"""
        print("\n--- 硬件偏好设置 ---")
        
        # 相机品牌
        print("\n相机品牌偏好:")
        print("  1. 海康威视（推荐）")
        print("  2. 大恒图像")
        print("  3. 华睿科技")
        print("  4. 无偏好")
        
        choice = input("请选择 [1]: ").strip()
        brand_map = {'1': '海康威视', '2': '大恒图像', '3': '华睿科技', '4': None}
        self.config['camera_brand'] = brand_map.get(choice, '海康威视')
        
        # 镜头类型
        print("\n镜头类型偏好:")
        print("  1. 远心镜头（推荐，高精度）")
        print("  2. 定焦镜头（经济型）")
        print("  3. 无偏好")
        
        choice = input("请选择 [1]: ").strip()
        lens_type_map = {'1': '物方远心镜头', '2': '定焦镜头', '3': None}
        self.config['lens_type'] = lens_type_map.get(choice, '物方远心镜头')
        
        # 接口类型
        print("\n相机接口偏好:")
        print("  1. GigE（推荐，传输距离远）")
        print("  2. USB3.0（速度快）")
        print("  3. 无偏好")
        
        choice = input("请选择 [1]: ").strip()
        interface_map = {'1': 'GigE', '2': 'USB3.0', '3': None}
        self.config['interface'] = interface_map.get(choice, 'GigE')
    
    def _confirm_config(self):
        """确认配置"""
        print("\n" + "=" * 60)
        print("配置确认")
        print("=" * 60)
        
        print(f"\n项目名称: {self.config.get('project_name', '')}")
        print(f"应用场景: {self.config.get('application_scene', '')}")
        print(f"精度要求: {self.config.get('precision_requirement', '')} mm")
        print(f"检测节拍: {self.config.get('cycle_time', '')} s")
        
        fov = self.config.get('field_of_view', {})
        print(f"视野范围: {fov.get('width', '')} x {fov.get('height', '')} mm")
        print(f"工作距离: {self.config.get('working_distance', '')} mm")
        print(f"检测项目: {', '.join(self.config.get('detection_items', []))}")
        
        print(f"\n相机品牌: {self.config.get('camera_brand', '')}")
        print(f"镜头类型: {self.config.get('lens_type', '')}")
        print(f"接口类型: {self.config.get('interface', '')}")
        
        confirm = input("\n确认配置? (y/n) [y]: ").strip().lower()
        
        if confirm == 'n':
            print("\n配置已取消")
            self.config = {}
        else:
            print("\n配置已确认")
    
    def save_config(self, output_path: str):
        """保存配置到文件"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        print(f"\n配置已保存到: {output_path}")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='配置向导')
    parser.add_argument('--output', '-o', type=str, help='输出配置文件路径')
    
    args = parser.parse_args()
    
    wizard = ConfigWizard()
    config = wizard.run()
    
    if config:
        if args.output:
            wizard.save_config(args.output)
        else:
            # 默认输出路径
            output_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, 'project_config.json')
            wizard.save_config(output_path)


if __name__ == '__main__':
    main()