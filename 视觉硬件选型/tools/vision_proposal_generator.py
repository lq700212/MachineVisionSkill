#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视觉方案生成主流程脚本
根据用户资料自动完成视觉检测方案的设计和PPT生成
"""

import json
import math
import os
import subprocess
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 自动检查并安装依赖
from check_environment import ensure_environment
if not ensure_environment():
    print("环境检查未通过，请手动安装缺失的依赖后重试")
    sys.exit(1)

from parse_user_data import UserDataParser
from precision_calculator import (
    PrecisionCalculator, is_measurement_scene, is_moving_scene, shutter_kind,
    resolve_precision_budget, format_precision_basis,
    required_fps, camera_interface_status,
)
from camera_selector import CameraSelector
from lens_selector import LensSelector
from generate_ppt import generate_ppt

class VisionProposalGenerator:
    """视觉方案生成器"""
    
    def __init__(self):
        self.parser = UserDataParser()
        self.calculator = PrecisionCalculator()
        self.camera_selector = CameraSelector()
        self.lens_selector = LensSelector()
        self.config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
        self.tools_dir = os.path.dirname(__file__)

        # 模板PPT路径（用于继承母版样式）
        self.template_ppt = None
        # 非交互模式（脚本/AI调用时自动选择最优方案）
        self.auto_mode = False
        # 模板中要替换的硬件选型页序号（1起；None=全部硬件页）
        self.hardware_page = None
        
    def set_template(self, template_path: str):
        """设置模板PPT路径"""
        if os.path.exists(template_path):
            self.template_ppt = template_path
            print(f"已设置模板: {template_path}")
        else:
            print(f"警告: 模板文件不存在 - {template_path}")
    
    def load_config(self) -> Dict:
        """加载配置文件"""
        config_path = os.path.join(self.config_dir, 'project_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_config(self, config: Dict):
        """保存配置文件"""
        config_path = os.path.join(self.config_dir, 'project_config.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def generate_from_files(self, file_paths: List[str], output_dir: str = None, template_path: str = None) -> str:
        """
        从用户提供的文件生成方案
        
        Args:
            file_paths: 用户提供的文件路径列表（图片、文档等）
            output_dir: 输出目录
            template_path: 模板PPT路径（可选）
            
        Returns:
            生成的PPT文件路径
        """
        print("=" * 60)
        print("视觉检测方案自动生成系统")
        print("=" * 60)
        
        # 设置模板（命令行参数 > 自动扫描用户资料所在工作目录）
        if template_path:
            self.set_template(template_path)
        elif not self.template_ppt:
            search_dir = os.path.dirname(os.path.abspath(file_paths[0])) if file_paths else None
            template_path = self._discover_template(search_dir)
            if template_path:
                print(f"[模板] 工作目录自动发现模板: {os.path.basename(template_path)}")
                self.set_template(template_path)
        
        # 1. 解析用户资料
        print("\n[步骤1] 解析用户资料...")
        parsed_data = self.parser.parse_files(file_paths)
        
        if not parsed_data:
            print("警告: 未能从文件中提取有效信息，将使用默认配置")
            parsed_data = self._get_default_config()
        
        # 2. 验证并补充参数
        print("\n[步骤2] 验证参数完整性...")
        validated_params = self._validate_params(parsed_data)
        
        # 3. 执行硬件选型
        print("\n[步骤3] 执行硬件选型...")
        selection_candidates = self._perform_selection(validated_params)
        
        if not selection_candidates:
            print("\n错误: 未找到通过验证的方案")
            self._print_gap_report(validated_params)
            return None
        
        # 4. 展示Top 3方案供用户选择
        print("\n[步骤4] 展示候选方案...")
        selected_index = self._present_candidates(selection_candidates)
        
        # 5. 获取用户确认的方案
        selection_result = selection_candidates[selected_index]
        print(f"\n已选择方案 {selected_index + 1}")

        # 5.2 库保鲜：选中超龄条目自动官网刷新（有变化自动用新值重跑选型）
        print("\n[步骤4.2] 数据保鲜检查...")
        refreshed = self._refresh_selection_fresh(validated_params, selection_result)
        if refreshed is None:
            print("\n错误: 官网参数更新后重跑选型无解")
            self._print_gap_report(validated_params)
            return None
        selection_result = refreshed

        # 5.5 选型核验（相当于发版前的回归测试，全项FAIL则中止）
        print("\n[步骤4.5] 选型核验...")
        from validate_selection import SelectionValidator
        validator = SelectionValidator()
        checks = validator.validate(
            selection_result['camera'], selection_result['lens'], validated_params,
            light=selection_result.get('light_source'))
        fail_count = sum(1 for c in checks if c.result.value == '[FAIL]')
        selection_result['validation'] = [
            {'name': c.name, 'result': c.result.value,
             'message': c.message, 'suggestion': c.suggestion}
            for c in checks
        ]
        selection_result['validation_passed'] = fail_count == 0
        if fail_count > 0:
            print(f"\n错误: 核验存在 {fail_count} 项FAIL，方案不可用，已中止")
            return None

        # 选型方案结果（有模板/无模板流程都必须在终端输出）
        self._print_selection_summary(validated_params, selection_result)

        # 6. 设计算法方案
        print("\n[步骤5] 设计算法方案...")
        algorithm_design = self._design_algorithm(validated_params, selection_result)
        
        # 7. 生成PPT
        print("\n[步骤6] 生成方案PPT...")
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
        
        os.makedirs(output_dir, exist_ok=True)
        
        project_name = validated_params.get('project_name', '视觉检测项目')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"{project_name}_{timestamp}.pptx")
        
        # 8. 保存选型结果（无论是否有模板，selection_result.json 都要落盘）
        result_json = self._save_selection_result(validated_params, selection_result, algorithm_design, output_dir)
        # 无模板：不在终端留错误，输出选型结果正常结束（用户放模板后重跑即可生成PPT）
        if not self.template_ppt:
            print("\n[提示] 未找到模板PPT（--template / 工作目录均无），本次只输出选型结果，不生成PPT")
            print(f"  选型结果已保存: {result_json}")
            print("  下一步: 将模板PPT放到工作目录后用同一命令重跑，自动生成方案PPT")
            return 'SELECTION_ONLY'

        self._ensure_camera_image(selection_result)
        ppt_path = generate_ppt(
            template_path=self.template_ppt,
            output_path=output_path,
            camera=selection_result['camera'],
            lens=selection_result['lens'],
            light_source=selection_result.get('light_source'),
            project_name=project_name,
            field_of_view=validated_params.get('field_of_view'),
            hardware_page=getattr(self, 'hardware_page', None)
        )

        if not ppt_path:
            print("\n[失败] PPT 未生成：上方 generate_ppt 已给出原因"
                  "（如 --hardware_page 越界）")
            print("  修正参数后重跑；本次不产出半成品，也不进入验收")
            return None

        # 9. 自动验收（规则自查+渲染导出）；未通过则产物已隔离，不得继续交付
        if not self._run_acceptance(ppt_path, output_dir):
            print("\n[失败] PPT 未通过生成后规则自查（FAIL 项见 acceptance_report.txt），"
                  "已隔离到 output\\_rejected\\，禁止交付")
            return None

        print("\n" + "=" * 60)
        print("方案生成完成！")
        print(f"PPT文件: {ppt_path}")
        print("=" * 60)

        return ppt_path
    
    def generate_from_text(self, text: str, output_dir: str = None,
                           template_path: str = None,
                           dry_run: bool = False) -> str:
        """
        从需求原始文字生成方案（弱模型从0入口：模型只读图/文档抄字，解析判断交给脚本）

        Args:
            text: 用户口述/文档/图纸中的原始文字（原样抄录，不要自己解读成参数）
            output_dir: 输出目录
            template_path: 模板PPT路径（可选，缺省扫描当前工作目录）
            dry_run: True=只选型+核验，不生成PPT

        Returns:
            生成的PPT文件路径；无模板时返回 'SELECTION_ONLY'；dry_run 返回 'DRY_RUN'
        """
        print("=" * 60)
        print("视觉检测方案自动生成系统（需求文本模式）")
        print("=" * 60)

        # 模板：命令行 > 当前工作目录扫描
        if template_path:
            self.set_template(template_path)
        elif not self.template_ppt:
            template_path = self._discover_template(os.getcwd())
            if template_path:
                print(f"[模板] 工作目录自动发现模板: {os.path.basename(template_path)}")
                self.set_template(template_path)

        print("\n[步骤1] 解析需求文本...")
        parsed_data = self.parser._extract_params_from_text(text)
        if not parsed_data:
            raise ValueError(
                "【需求文本未解析出参数】请把需求原文完整抄录给 --text 参数，"
                "包含精度（如≤0.03mm）/ 公差（如±0.25）/ 节拍（如3s）/ 检测区域（如38.5x22）等数字信息。"
                "如原文确实没有某项，改用 --config 手工登记。")
        print(f"  解析出参数: {', '.join(sorted(parsed_data.keys()))}")

        # 走统一校验与生成链（缺必填项时 _validate_params 会给出可执行的填写指引）
        return self.generate_from_config_data(parsed_data, output_dir, template_path,
                                              dry_run=dry_run)

    def generate_from_config(self, config_path: str, output_dir: str = None,
                             template_path: str = None,
                             dry_run: bool = False) -> str:
        """
        从配置文件生成方案

        Args:
            config_path: 配置文件路径
            output_dir: 输出目录
            template_path: 模板PPT路径
            dry_run: True=只跑选型+核验并落盘 selection_result.json，
                     不生成PPT（弱模型先用它确认口径/解是否存在）

        Returns:
            生成的PPT文件路径；dry_run 返回 'DRY_RUN'
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 将配置传递给generate_from_files（携带config目录供模板自动扫描）
        return self.generate_from_config_data(
            config, output_dir, template_path,
            config_dir=os.path.dirname(os.path.abspath(config_path)),
            dry_run=dry_run)
    
    def generate_from_config_data(self, config: Dict, output_dir: str = None,
                                  template_path: str = None, config_dir: str = None,
                                  dry_run: bool = False) -> str:
        """
        从配置数据生成方案

        Args:
            config: 配置数据
            output_dir: 输出目录
            template_path: 模板PPT路径（可选）
            config_dir: 配置文件所在目录（用于自动扫描工作目录模板）

        Returns:
            生成的PPT文件路径；无模板时返回 'SELECTION_ONLY'（已输出选型结果）
        """
        print("=" * 60)
        print("视觉检测方案自动生成系统")
        print("=" * 60)

        # 设置模板（命令行参数 > 配置文件 > 自动扫描工作目录 > 已set_template的）
        template_path = template_path or config.get('template') or self.template_ppt
        # config里的相对路径按config所在目录解析（弱模型cwd不固定，按cwd解析会误判模板不存在）
        if template_path and not os.path.isabs(str(template_path)) \
                and not os.path.exists(template_path) and config_dir:
            candidate = os.path.join(config_dir, template_path)
            if os.path.exists(candidate):
                template_path = candidate
                print(f"[模板] 相对路径按config目录解析: {template_path}")
        if not template_path and config_dir:
            template_path = self._discover_template(config_dir)
            if template_path:
                print(f"[模板] 工作目录自动发现模板: {os.path.basename(template_path)}")
        if template_path:
            self.set_template(template_path)
        
        # 验证参数
        print("\n[步骤1] 验证参数完整性...")
        validated_params = self._validate_params(config)
        
        # 使用配置中的camera和lens（如果有）
        if 'camera' in config and 'lens' in config:
            # 显式硬件分支：用户只指定相机/镜头时，光源按同一需求自动选型。
            # 历史事故：此处曾用 {'brand':'OPT','model':'RL-100-90-W'} 兜底，
            # 该型号官网不存在（拼造），会绕过核验直接进选型结果与 PPT。
            _light = config.get('light_source')
            if not _light:
                _light = self._recommend_light_source(validated_params,
                                                      config['lens'])
            selection_result = {
                'camera': config['camera'],
                'lens': config['lens'],
                'light_source': _light,
            }
            print("\n[步骤2] 使用配置文件中的硬件参数")
            print("  相机: {} {}".format(config['camera']['brand'], config['camera']['model']))
            print("  镜头: {} {}".format(config['lens']['brand'], config['lens']['model']))
            # 根因注释：显式硬件=用户拍板，只核验不换型；此前本分支跳过核验，
            # 落盘的 validation_passed 恒为 False 且无效硬件会带着生成PPT
            print("\n[步骤2.5] 选型核验（显式硬件同样必须过核验）...")
            from validate_selection import SelectionValidator as _SV
            _validator = _SV()
            _checks = _validator.validate(
                selection_result['camera'], selection_result['lens'], validated_params,
                light=selection_result.get('light_source'))
            _fail_count = sum(1 for c in _checks if c.result.value == '[FAIL]')
            selection_result['validation'] = [
                {'name': c.name, 'result': c.result.value,
                 'message': c.message, 'suggestion': c.suggestion}
                for c in _checks
            ]
            selection_result['validation_passed'] = _fail_count == 0
            if _fail_count > 0:
                print(f"\n错误: 核验存在 {_fail_count} 项FAIL，方案不可用，已中止")
                for c in _checks:
                    if c.result.value == '[FAIL]':
                        print(f"  [FAIL] {c.name}: {c.message} → {c.suggestion}")
                return None
            self._print_selection_summary(validated_params, selection_result)
        else:
            # 执行硬件选型
            print("\n[步骤2] 执行硬件选型...")
            selection_candidates = self._perform_selection(validated_params)
            
            if not selection_candidates:
                print("\n错误: 未找到通过验证的方案")
                self._print_gap_report(validated_params)
                return None
            
            # 展示Top 3方案供用户选择
            print("\n[步骤3] 展示候选方案...")
            selected_index = self._present_candidates(selection_candidates)
            selection_result = selection_candidates[selected_index]
            print(f"\n已选择方案 {selected_index + 1}")

            # 库保鲜：选中超龄条目自动官网刷新（有变化自动用新值重跑选型，
            # 与files链共用同一代码路径）
            print("\n[数据保鲜检查]...")
            refreshed = self._refresh_selection_fresh(validated_params, selection_result)
            if refreshed is None:
                print("\n错误: 官网参数更新后重跑选型无解")
                self._print_gap_report(validated_params)
                return None
            selection_result = refreshed

            # 选型核验（与files链一致：全项FAIL则中止）
            print("\n[步骤3.5] 选型核验...")
            from validate_selection import SelectionValidator
            validator = SelectionValidator()
            checks = validator.validate(
                selection_result['camera'], selection_result['lens'], validated_params,
                light=selection_result.get('light_source'))
            fail_count = sum(1 for c in checks if c.result.value == '[FAIL]')
            selection_result['validation'] = [
                {'name': c.name, 'result': c.result.value,
                 'message': c.message, 'suggestion': c.suggestion}
                for c in checks
            ]
            selection_result['validation_passed'] = fail_count == 0
            if fail_count > 0:
                print(f"\n错误: 核验存在 {fail_count} 项FAIL，方案不可用，已中止")
                for c in checks:
                    if c.result.value == '[FAIL]':
                        print(f"  [FAIL] {c.name}: {c.message} → {c.suggestion}")
                return None

            # 选型方案结果（有模板/无模板流程都必须在终端输出）
            self._print_selection_summary(validated_params, selection_result)

        # 设计算法方案
        print("\n[步骤3] 设计算法方案...")
        algorithm_design = self._design_algorithm(validated_params, selection_result)
        
        # 确定输出目录并保存选型结果（dry-run 也要落盘，便于复核）
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
        os.makedirs(output_dir, exist_ok=True)
        project_name = validated_params.get('project_name', '视觉检测项目')
        self._save_selection_result(validated_params, selection_result, algorithm_design, output_dir)

        # dry-run：选型+核验已完成并落盘，弱模型可先确认口径/解，再决定是否生成PPT
        if dry_run:
            print("\n[dry-run] 选型+核验已完成，selection_result.json 已保存；"
                  "本次按 --dry-run 不生成PPT")
            print("  下一步: 去掉 --dry-run 重跑同一命令即生成PPT")
            return 'DRY_RUN'

        # 生成PPT
        print("\n[步骤4] 生成方案PPT...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"{project_name}_{timestamp}.pptx")

        # 无模板：不在终端留错误，输出选型结果正常结束（用户放模板后重跑即可生成PPT）
        if not self.template_ppt:
            print("\n[提示] 未找到模板PPT（--template / config的template字段 / 工作目录均无），"
                  "本次只输出选型结果，不生成PPT")
            print("  下一步: 将模板PPT放到工作目录后用同一命令重跑，自动生成方案PPT")
            return 'SELECTION_ONLY'

        self._ensure_camera_image(selection_result)
        ppt_path = generate_ppt(
            template_path=self.template_ppt,
            output_path=output_path,
            camera=selection_result['camera'],
            lens=selection_result['lens'],
            light_source=selection_result.get('light_source'),
            project_name=project_name,
            field_of_view=validated_params.get('field_of_view'),
            hardware_page=getattr(self, 'hardware_page', None)
        )

        if not ppt_path:
            print("\n[失败] PPT 未生成：上方 generate_ppt 已给出原因"
                  "（如 --hardware_page 越界）")
            print("  修正参数后重跑；本次不产出半成品，也不进入验收")
            return None

        # 自动验收（规则自查+渲染导出）；未通过则产物已隔离，不得继续交付
        if not self._run_acceptance(ppt_path, output_dir):
            print("\n[失败] PPT 未通过生成后规则自查（FAIL 项见 acceptance_report.txt），"
                  "已隔离到 output\\_rejected\\，禁止交付")
            return None

        print("\n" + "=" * 60)
        print("方案生成完成！")
        print(f"PPT文件: {ppt_path}")
        print("=" * 60)

        return ppt_path
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            'project_name': '视觉检测项目',
            'precision_requirement': 0.012,  # mm
            'cycle_time': 3,  # 秒
            'detection_items': [
                '尺寸检测：关键尺寸精度要求≤0.012mm',
                '间隙检测：各组件之间的间隙测量',
                '位置度检测：零件安装位置的准确性检测'
            ]
        }
    
    def _validate_params(self, params: Dict) -> Dict:
        """验证并补充参数（必须有明确来源，不能猜测）"""
        validated = params.copy()
        
        # ============ 检查精度/公差（必须有明确来源） ============
        # 像素级口径（pixel_precision，单位mm/pixel）也是合法精度来源：
        # 用户明说"像素精度X mm/pixel"时直接填它，禁止塞进 precision_requirement
        has_pixel_precision = 'pixel_precision' in validated and validated['pixel_precision'] is not None
        has_precision = 'precision_requirement' in validated and validated['precision_requirement'] is not None
        has_tolerance = 'tolerance' in validated and validated['tolerance'] is not None
        
        # 检查是否在配置文件中提供了camera和lens（如果是，则跳过询问）
        has_camera = 'camera' in validated and validated['camera'] is not None
        has_lens = 'lens' in validated and validated['lens'] is not None
        
        if not has_precision and not has_tolerance and not has_pixel_precision:
            # 如果有camera和lens配置，使用默认精度
            if has_camera and has_lens:
                print("\n  从配置文件中读取相机和镜头参数")
                print("  使用默认精度: 0.03mm")
                validated['precision_requirement'] = 0.03
            elif self.auto_mode or not sys.stdin.isatty():
                # 非交互环境（AI/弱模型调用）：禁止卡死在input()，抛出可执行的填写指引
                raise ValueError(
                    "【缺少精度口径】config 里 precision_requirement / tolerance / pixel_precision 均为空。\n"
                    "  修正方法（三选一，写入 project_config.json 后重跑）：\n"
                    "    1) \"precision_requirement\": 0.03  ← 客户/合同给的视觉测量或检测精度(mm)\n"
                    "    2) \"tolerance\": 0.25             ← 图纸公差（±0.25 填 0.25，并把 tolerance_type 设为 bilateral）\n"
                    "    3) \"pixel_precision\": 0.01          ← 用户明说的像素精度(mm/pixel)，系统×亚像素因子换算\n"
                    "  注意：不要自己发明口径，不确定时向用户确认。")
            else:
                print("\n" + "=" * 60)
                print("【必须】需要提供精度信息")
                print("=" * 60)
                print("请选择输入方式：")
                print("  1. 直接输入精度（测量/检测精度，如 0.012mm）")
                print("  2. 输入图纸公差（±X 形式，系统按整机分配比例换算）")
                print("  示例：公差±0.25mm → 带宽 0.5mm × 视觉分配 30% ÷ 3 像素 ≈ 0.05mm/px")

                while True:
                    choice = input("\n请选择 (1/2): ").strip()
                    if choice in ['1', '2']:
                        break
                    print("请输入 1 或 2")

                if choice == '1':
                    while True:
                        precision_input = input("请输入精度(mm): ").strip()
                        try:
                            validated['precision_requirement'] = float(precision_input)
                            print(f"  已设置精度: {validated['precision_requirement']}mm")
                            break
                        except ValueError:
                            print("输入无效，请输入数字")
                else:
                    while True:
                        tolerance_input = input("请输入公差(mm，如0.25表示±0.25mm): ").strip()
                        try:
                            validated['tolerance'] = float(tolerance_input)
                            print(f"  已设置公差: ±{validated['tolerance']}mm")
                            break
                        except ValueError:
                            print("输入无效，请输入数字")
        
        # ============ 口径合理性复核（2026-11-20 事故） ============
        # 客户口述"偏差/精度不超过 0.5mm"通常是装配公差，不是设备检测精度。
        # 若把公差直接填进 precision_requirement，精度链会松 10 倍
        # （0.5/3=0.167mm/px → 24mm 视野只需 144px），相机被严重低配。
        # 【硬阻断】auto 模式下不允许"提示后继续"——弱模型会忽略提示直接交付
        # 低配方案。必须由用户确认口径（改填 tolerance 或显式确认非公差）才继续。
        _prec = validated.get('precision_requirement')
        _prec_confirmed = bool(validated.get('precision_basis_confirmed'))
        _prec_basis = str(validated.get('precision_basis') or '')
        # 2026-11-22：客户明确说"测量精度/检测精度 0.5mm"时，0.5mm 就是视觉
        # 指标，直接 ÷ 亚像素因子；不能再当成装配公差拦截。只有模糊的
        # "精度 0.5mm"才保留复核（问用户是图纸公差还是检测精度）。
        _explicit_visual = _prec_basis == 'measurement_accuracy'
        if _explicit_visual and _prec is not None:
            print(f"\n  [精度口径] 用户明确给出测量精度 {float(_prec):g}mm，"
                  "按视觉指标直接计算（÷亚像素因子），不再做整机公差分配")
        if (_prec is not None and not has_tolerance and not _prec_confirmed
                and not _explicit_visual):
            try:
                _prec_val = float(_prec)
            except (TypeError, ValueError):
                _prec_val = 0
            _dt = str(validated.get('detection_type') or '')
            _positioning = any(k in _dt for k in
                               ('定位', '贴装', '引导', '装配', '对位'))
            if _prec_val >= 0.2 and (_positioning or not _dt):
                _msg = (
                    "\n  [口径复核·已中止] precision_requirement ="
                    f" {_prec_val:g}mm 偏大，且未说明是测量精度还是图纸公差。\n"
                    "    填错会把精度链放松数倍（相机低配），必须先向用户确认：\n"
                    "    问法：“您说的精度/偏差 X mm，是图纸公差(±X)，"
                    "还是视觉系统要达到的测量/检测精度？”\n"
                    "    用户答“公差/偏差”→ 改用 \"tolerance\": "
                    f"{_prec_val:g}，并把 tolerance_type 设为 bilateral（±X）"
                    "或 total（已给总带宽）；\n"
                    "    用户明确答“就是测量/检测精度，不是公差”→ 在 config 加 "
                    "\"precision_basis\": \"measurement_accuracy\" 后重跑"
                    "（或把原话“测量精度 X mm”交给 --text 入口）。\n"
                    "    禁止自行添加确认字段来绕过本检查（等于发明口径）。"
                )
                if self.auto_mode:
                    raise ValueError(_msg)
                print(_msg)
                _ans = input("  已获用户确认是设备检测精度？(y=继续 / 其他=中止): ").strip().lower()
                if _ans != 'y':
                    raise ValueError("用户未确认精度口径，已中止。请先确认口径再重跑。")
                validated['precision_basis_confirmed'] = True
                print("  已记录用户确认: precision_basis_confirmed=true\n")

        # ============ 检查工件尺寸/检测区域/视野（必须知道其中一个） ============
        has_part_size = 'part_size' in validated and validated['part_size'] is not None
        has_detection_area = 'detection_area' in validated and validated['detection_area'] is not None
        has_field_of_view = 'field_of_view' in validated and validated['field_of_view'] is not None
        
        if not has_part_size and not has_detection_area and not has_field_of_view:
            # 如果有camera和lens配置，使用默认尺寸
            if has_camera and has_lens:
                print("  使用默认工件尺寸: 39x30x20mm")
                validated['part_size'] = '39x30x20'
            elif self.auto_mode or not sys.stdin.isatty():
                # 非交互环境：禁止卡死在input()，抛出可执行的填写指引
                raise ValueError(
                    "【缺少尺寸信息】config 里 part_size / detection_area / field_of_view 均为空。\n"
                    "  修正方法（三选一，写入 project_config.json 后重跑）：\n"
                    "    1) \"part_size\": \"50x30x20\"      ← 工件整体外形(mm)，系统自动×余量\n"
                    "    2) \"detection_area\": \"38.5x22\"   ← 只需检测的区域(mm)，推荐，视野更小\n"
                    "    3) \"field_of_view\": {\"width\": 46, \"height\": 26}  ← 最终视野(mm)，不加余量\n"
                    "  尺寸必须来自用户资料或用户确认，不要拍脑袋。")
            else:
                print("\n" + "=" * 60)
                print("【必须】需要提供尺寸信息（三选一）")
                print("=" * 60)
                print("公式：工件尺寸/检测区域 × 余量系数(1.2或1.5) = 视野")
                print()
                print("请选择输入方式：")
                print("  1. 工件尺寸（如 50x30x20mm，系统自动×1.2余量）")
                print("  2. 检测区域尺寸（如 50x30mm，系统自动×1.2余量）")
                print("  3. 直接输入视野（如 60x40mm，不加余量）")

                while True:
                    choice = input("\n请选择 (1/2/3): ").strip()
                    if choice in ['1', '2', '3']:
                        break
                    print("请输入 1、2 或 3")

                if choice == '1':
                    size_input = input("请输入工件尺寸(mm，如50x30x20): ").strip()
                    validated['part_size'] = size_input
                    print(f"  已设置工件尺寸: {size_input}")
                elif choice == '2':
                    size_input = input("请输入检测区域尺寸(mm，如50x30): ").strip()
                    validated['detection_area'] = size_input
                    print(f"  已设置检测区域: {size_input}")
                else:
                    size_input = input("请输入视野(mm，如60x40): ").strip()
                    validated['field_of_view_input'] = size_input
                    print(f"  已设置视野: {size_input}")
        
        # 设置默认值（注意：pixel_size/magnification等硬件参数不预设，
        # 由选型环节根据视野+精度推导，避免"假设硬件反推需求"的逻辑倒置；
        # cycle_time 不预设——节拍必须来自用户，未提供时跳过帧率约束）
        defaults = {
            'project_name': '视觉检测项目',
            'interface': 'GigE',
            'fov_margin': 1.2,
            'pixel_per_precision': 3.0
        }

        for key, value in defaults.items():
            if key not in validated or validated[key] is None:
                validated[key] = value

        # 清除历史遗留的硬件假设字段
        validated.pop('pixel_size', None)
        validated.pop('magnification', None)

        # 工作距离（2026-11-20 事故）：WD 不参与选型时，MOD 不足的镜头会凭
        # 倍率"中选"，装上去不合焦。未声明不拦死（有些项目无安装距离约束），
        # 但必须在日志与核验报告里留痕，禁止静默通过。
        if validated.get('working_distance') is None:
            print("\n  [WD 未声明] config 没有 working_distance，镜头仅按倍率/视野匹配，"
                  "无法保证现场合焦。交付前须补 working_distance 重跑。")

        # 精度口径决策（config_template 决策表）：
        # 1) pixel_precision（用户明说的像素级口径，mm/pixel）最优先——
        #    等效视觉允许误差 = pixel_precision × pixel_per_precision，下游链不变；
        #    与 precision_requirement 同时给属口径冲突，打印警告采用像素级口径
        #    （用户明说"像素精度"是更强的口径声明），并提示向用户确认。
        # 2) precision_requirement 与 tolerance 同时给时 precision_requirement 优先；
        #    仅当无明确精度时才按 precision_model 从公差换算（见 resolve_precision_budget）。
        if validated.get('pixel_precision') is not None:
            pp = float(validated['pixel_precision'])
            if pp <= 0:
                raise ValueError(
                    f"【口径数值错误】pixel_precision={pp} 必须>0，单位 mm/pixel，"
                    "修正 config 后重跑。")
            k = float(validated.get('pixel_per_precision', 3.0))
            if validated.get('precision_requirement') is not None:
                print(f"  [精度口径] ⚠️ 口径冲突：pixel_precision={pp}mm/pixel 与 "
                      f"precision_requirement={validated['precision_requirement']}mm 同时给出，"
                      f"采用用户明说的像素级口径；如非用户本意请向用户确认")
            validated['precision_requirement'] = pp * k
            validated['precision_source'] = 'pixel_precision'
            print(f"\n  [精度口径] 用户指定像素当量 {pp}mm/pixel（像素级口径）")
            print(f"  等效视觉允许误差 = {pp} × 亚像素因子{k} = {pp*k:.4f}mm（下游按允许误差链计算）")
        elif validated.get('precision_requirement') is not None:
            if validated.get('tolerance') is not None:
                print(f"  [精度口径] precision_requirement 优先（口径决策表），"
                      f"忽略 tolerance={validated['tolerance']}")
        elif validated.get('tolerance') is not None:
            tolerance = validated['tolerance']
            budget = resolve_precision_budget(validated)
            if not budget:
                raise ValueError(
                    f"【精度口径错误】tolerance={tolerance} 无法换算像素当量，"
                    "检查 tolerance_type / allocation_ratio / pixel_factor")
            validated['precision_requirement'] = budget['allowed_error_mm']
            validated['precision_budget'] = budget
            validated['precision_basis_text'] = budget['basis_text']
            print(f"\n  [精度口径] {budget['mode_label']}：{budget['basis_text']}")
            for note in budget.get('assumptions') or []:
                print(f"    · {note}")
            if budget.get('is_assumption'):
                print("  [口径提示] precision_model 未声明，按行业常规视觉分配 30% 兜底"
                      "（等效整机公差 ÷ 9~10）；交付前须与客户确认该数字是整机结果公差"
                      "还是视觉指标")

        # 统一精度口径（2026-11-21）：三个输入分支最终都落到同一预算结构，
        # 供核验器/PPT 复用，避免各处再按 /10 或 /3 二次换算
        if 'precision_budget' not in validated:
            budget = resolve_precision_budget(validated)
            if budget:
                validated['precision_budget'] = budget
                validated['precision_basis_text'] = budget['basis_text']
            else:
                print("\n  [精度口径缺失] 无 tolerance / precision_requirement / pixel_precision")

        # 视野计算 + 需求分析（所需像素等）
        validated = self._calculate_field_of_view(validated)

        return validated
    
    def _calculate_field_of_view(self, params: Dict) -> Dict:
        """计算和验证视野"""
        fov_margin = params.get('fov_margin', 1.2)

        def _has(key):
            """键存在且值非空（config模板里的null字段不应劫持分支）"""
            v = params.get(key)
            return v is not None and v != ''

        # 检查是否已有视野信息
        if _has('field_of_view') and isinstance(params.get('field_of_view'), dict):
            fov = params['field_of_view']
            print(f"\n  [视野] 使用用户提供的视野: {fov['width']:.1f} x {fov['height']:.1f} mm")
        elif _has('field_of_view') and isinstance(params.get('field_of_view'), str):
            # 根因注释：config 手填 "60x40" 字符串时此前会穿透全部分支、
            # 误报【内部错误】；与 field_of_view_input 同规则解析
            try:
                parts = str(params['field_of_view']).lower().replace('mm', '').replace('fov:', '').replace('fov：', '').split('x')
                params['field_of_view'] = {'width': float(parts[0]), 'height': float(parts[1])}
                print(f"\n  [视野] 使用用户提供的视野: {params['field_of_view']['width']:.1f} x {params['field_of_view']['height']:.1f} mm")
            except (ValueError, IndexError):
                raise ValueError(
                    f"【尺寸格式错误】field_of_view=\"{params['field_of_view']}\" 无法解析。\n"
                    "  正确格式如 {\"width\": 60, \"height\": 40} 或 \"60x40\"（宽x高，mm），修改 config 后重跑。")
        elif _has('field_of_view_input'):
            # 用户直接输入了视野值
            fov_str = params['field_of_view_input']
            try:
                parts = str(fov_str).lower().replace('mm', '').split('x')
                params['field_of_view'] = {'width': float(parts[0]), 'height': float(parts[1])}
                print(f"\n  [视野] 使用用户输入的视野: {params['field_of_view']['width']:.1f} x {params['field_of_view']['height']:.1f} mm")
            except (ValueError, IndexError):
                raise ValueError(
                    f"【尺寸格式错误】field_of_view_input=\"{fov_str}\" 无法解析。\n"
                    "  正确格式如 \"60x40\"（宽x高，mm），修改 config 后重跑。")
        elif _has('part_size'):
            # 工件尺寸 × 余量系数 = 视野
            size_str = params['part_size']
            try:
                parts = str(size_str).lower().replace('mm', '').split('x')
                if len(parts) >= 2:
                    length = float(parts[0])
                    width = float(parts[1])
                    fov_width = length * fov_margin
                    fov_height = width * fov_margin
                    params['field_of_view'] = {'width': fov_width, 'height': fov_height}
                    print(f"\n  [视野] 工件尺寸 {length}x{width}mm × {fov_margin} = 视野 {fov_width:.1f}x{fov_height:.1f}mm")
                else:
                    raise ValueError("格式错误")
            except ValueError:
                raise ValueError(
                    f"【尺寸格式错误】part_size=\"{size_str}\" 无法解析。\n"
                    "  正确格式如 \"50x30x20\"（长x宽x高，mm）或 \"50x30\"，修改 config 后重跑。")
        elif _has('detection_area'):
            # 检测区域 × 余量系数 = 视野
            area_str = params['detection_area']
            try:
                parts = str(area_str).lower().replace('mm', '').split('x')
                if len(parts) >= 2:
                    width = float(parts[0])
                    height = float(parts[1])
                    fov_width = width * fov_margin
                    fov_height = height * fov_margin
                    params['field_of_view'] = {'width': fov_width, 'height': fov_height}
                    print(f"\n  [视野] 检测区域 {width}x{height}mm × {fov_margin} = 视野 {fov_width:.1f}x{fov_height:.1f}mm")
                else:
                    raise ValueError("格式错误")
            except ValueError:
                raise ValueError(
                    f"【尺寸格式错误】detection_area=\"{area_str}\" 无法解析。\n"
                    "  正确格式如 \"38.5x22\"（宽x高，mm），修改 config 后重跑。")
        else:
            # 不应该到这里，因为_validate_params已经检查过
            raise ValueError("【内部错误】无尺寸字段却进入视野计算，请检查 _validate_params")
        
        # 计算所需像素（需求侧推导：视野 / 像素精度上限，与硬件无关）
        # 精度口径统一走 resolve_precision_budget：mode 决定是"整机分配"还是
        # "视觉直测"，不再把 /10 与 /3 叠加
        fov = params['field_of_view']
        pixel_per_precision = params.get('pixel_per_precision', 3.0)
        budget = params.get('precision_budget') or resolve_precision_budget(params)
        if budget:
            pixel_precision_max_mm = budget['pixel_precision_max_mm']
        else:
            pixel_precision_max_mm = self.calculator.required_object_resolution(
                params['precision_requirement'], pixel_per_precision)
        params['pixel_per_precision'] = pixel_per_precision
        params['pixel_precision_max_mm'] = pixel_precision_max_mm
        params['required_pixels'] = self.calculator.required_pixels(
            fov, pixel_precision_max_mm)

        print(f"\n  [需求分析]")
        print(f"  所需视野: {fov['width']:.1f} x {fov['height']:.1f} mm")
        if budget:
            print(f"  精度口径: {budget['mode_label']}｜{budget['basis_text']}")
            print(f"  视觉允许误差: {budget['allowed_error_mm']*1000:.1f} μm"
                  f"（像素精度上限 ≤ {pixel_precision_max_mm*1000:.1f} μm/pixel）")
        else:
            print(f"  检测精度: {params['precision_requirement']*1000:.1f} μm "
                  f"(像素精度上限 ≤ {pixel_precision_max_mm*1000:.1f} μm，"
                  f"亚像素因子{pixel_per_precision})")
        print(f"  所需像素: {params['required_pixels']['x']} x "
              f"{params['required_pixels']['y']} = "
              f"{params['required_pixels']['total_mp']:.1f} MP")
        # 只有尺寸测量才拿 5~15μm 的行业典型值做对照；定位/贴合的
        # 像素当量本来就该宽（允许误差大），不能误报"异常宽松"
        if (pixel_precision_max_mm > 0.02 and budget
                and budget.get('application') == 'measurement'):
            print(f"  ⚠️ 像素精度上限 {pixel_precision_max_mm*1000:.1f} μm/pixel "
                  f"偏大（尺寸测量常见 5~15 μm/pixel），核对公差口径")

        return params
    
    def _parse_size_input(self, size_input: str, fov_margin: float = 1.2) -> Dict:
        """解析尺寸输入（支持工件尺寸、检测区域、视野）"""
        # 移除空格和单位
        size_str = str(size_input).lower().replace('mm', '').replace('fov:', '').replace('fov：', '')
        
        try:
            parts = size_str.split('x')
            if len(parts) == 3:
                # 工件尺寸：长x宽x高，取长宽并加余量
                length = float(parts[0])
                width = float(parts[1])
                height = float(parts[2])
                print(f"  识别为工件尺寸: {length} x {width} x {height} mm")
                print(f"  计算视野（余量{fov_margin}倍）: {length*fov_margin:.1f} x {width*fov_margin:.1f} mm")
                return {
                    'width': length * fov_margin,
                    'height': width * fov_margin
                }
            elif len(parts) == 2:
                # 可能是检测区域或直接是视野
                w = float(parts[0])
                h = float(parts[1])
                # 判断是检测区域还是视野
                # 如果用户没有明确说明，假设是检测区域，加余量
                print(f"  识别为检测区域: {w} x {h} mm")
                print(f"  计算视野（余量{fov_margin}倍）: {w*fov_margin:.1f} x {h*fov_margin:.1f} mm")
                return {
                    'width': w * fov_margin,
                    'height': h * fov_margin
                }
        except:
            pass
        
        # 解析失败，使用默认值
        print(f"  无法解析输入，使用默认视野 50x40 mm")
        return {'width': 50, 'height': 40}
    
    def _discover_template(self, search_dir: str) -> Optional[str]:
        """
        在工作目录自动扫描模板PPT（排除output子目录与Office临时文件）
        多个候选时取修改时间最新的一个（弱模型无需决策）
        """
        if not search_dir or not os.path.isdir(search_dir):
            return None
        candidates = []
        for f in os.listdir(search_dir):
            if f.lower().endswith('.pptx') and not f.startswith('~$'):
                p = os.path.join(search_dir, f)
                candidates.append(p)
        if not candidates:
            return None
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidates[0]

    def _print_selection_summary(self, params: Dict, selection: Dict):
        """终端输出选型方案结果（有模板/无模板流程都必须输出）"""
        camera = selection.get('camera', {})
        lens = selection.get('lens', {})
        light = selection.get('light_source', {})
        actual = selection.get('actual_fov', {})
        required = selection.get('required_fov', {})
        fov = params.get('field_of_view', {})
        req_px = params.get('required_pixels', {})
        ppm = params.get('pixel_precision_max_mm', 0)

        print("\n" + "=" * 62)
        print("【选型方案结果】")
        print("=" * 62)
        print(f"  项目: {params.get('project_name', '视觉检测项目')}")
        cycle_txt = f"节拍 {params.get('cycle_time')}s" if params.get('cycle_time') else "节拍未提供"
        print(f"  需求: 视野 {fov.get('width', 0):.1f}x{fov.get('height', 0):.1f}mm | "
              f"检测精度 {params.get('precision_requirement')}mm "
              f"(像素精度上限≤{ppm*1000:.1f}μm/pixel) | {cycle_txt}")
        if req_px:
            print(f"        需要像素 {req_px.get('x')}x{req_px.get('y')} "
                  f"(约{req_px.get('total_mp', 0):.1f}MP)")
        print(f"  相机: {camera.get('brand', '')} {camera.get('model', '')} "
              f"({camera.get('resolution', {}).get('width', 0)}x"
              f"{camera.get('resolution', {}).get('height', 0)}, "
              f"像元{camera.get('pixel_size', 0)}μm, 靶面{camera.get('sensor_size', '')})")
        print(f"  镜头: {lens.get('brand', '')} {lens.get('model', '')} "
              f"(倍率{lens.get('magnification', 0)}x, WD {lens.get('working_distance', 0)}mm, "
              f"物方分辨率{lens.get('object_resolution', 0):.2f}μm)")
        print(f"  光源: {light.get('brand', '')} {light.get('model', '')} ({light.get('type', '')})")
        print(f"  实际视野: {actual.get('width', 0):.1f}x{actual.get('height', 0):.1f}mm "
              f"(需求 {required.get('width', 0):.1f}x{required.get('height', 0):.1f}mm) "
              f"{'满足' if selection.get('fov_satisfied') else '不满足'}")
        if 'safety_factor' in lens:
            print(f"  精度安全系数: {lens['safety_factor']:.2f}")
        if 'validation' in selection:
            fails = sum(1 for v in selection['validation'] if v.get('result') == '[FAIL]')
            print(f"  选型核验: {'通过' if selection.get('validation_passed') else '未通过'} "
                  f"(FAIL={fails})")
        print("=" * 62)

    def _print_gap_report(self, params: Dict):
        """选型无解时输出缺口报告（官网查证目标），指引扩库流程"""
        try:
            from database_updater import cmd_gap, DEFAULT_DB
            import argparse as _ap
            fov = params.get('field_of_view', {})
            ns = _ap.Namespace(cmd='gap', selection=None,
                               fov=f"{fov.get('width')}x{fov.get('height')}",
                               precision=params.get('precision_requirement', 0),
                               pixel_per_precision=params.get('pixel_per_precision', 3.0),
                               cycle_time=params.get('cycle_time', 3),
                               db=DEFAULT_DB)
            cmd_gap(ns)
            print("")
            print("[扩库指引] 数据库无解时，按以下流程扩库（已固化到 database_updater.py）：")
            print("  1. 按上方缺口报告到厂商官网查证型号（AI用WebSearch/WebFetch）")
            print("  2. python tools/database_updater.py add --draft 草稿.json   # 参数入库(强校验)")
            print("  3. python tools/database_updater.py verify --model 型号      # 复核后置verified")
            print("  4. 重跑选型")
        except Exception as e:
            print(f"  (缺口报告生成失败: {e})")

    # ==================================================================
    # 库保鲜：选中超龄条目自动官网刷新（库=官网缓存，数据可信度以官网为准）
    # ==================================================================
    def _refresh_selection_fresh(self, params: Dict, selection_result: Dict) -> Optional[Dict]:
        """数据可信度策略：库是官网的缓存，官网为准。
        - 库内条目近期（默认180天）官网核验过 → 直接用（不重复联网）
        - 选中超龄条目 → 自动走官网 refresh 三级通道查证：
            无变化 → 自动续期核验时间戳；有变化 → 自动apply更新库
            （verified回退false待人工复核）+ 用新参数重跑一次选型
        - 联网失败 → 诚实WARNING降级用库内值继续，提示人工refresh，不阻断

        Returns:
            可能替换后的selection_result（库值变化重跑时取新Top1）；
            重跑后无解返回None（调用方打印缺口报告中止）
        """
        from database_updater import (cmd_refresh, _entry_age_days,
                                      DEFAULT_FRESHNESS_DAYS, DEFAULT_DB,
                                      GOVERNANCE_FIELDS)
        reselect_needed = False
        for kind in ('camera', 'lens'):
            entry = selection_result.get(kind) or {}
            model = entry.get('model', '')
            if not model or not entry.get('verified'):
                continue  # 未verified条目本就要求人工复核（核验环节有WARNING）
            age = _entry_age_days(entry)
            if age is None or age <= DEFAULT_FRESHNESS_DAYS:
                continue  # 新鲜缓存直接用

            print(f"\n[保鲜] {kind} {model} 已 {age} 天未官网核验"
                  f"（阈值{DEFAULT_FRESHNESS_DAYS}天），参数可能有变化")
            print("  → 自动联网官网查证刷新（静态快抓→无头渲染→AI接管）...")
            ns = argparse.Namespace(cmd='refresh', model=model, html=None, url=None,
                                    apply=True, dry_run=False, render_ms=12000,
                                    db=DEFAULT_DB)
            rc = cmd_refresh(ns)
            if rc != 0:
                print(f"  ⚠ 官网刷新未完成（返回码{rc}），本次按库内值继续；"
                      f"建议人工执行: database_updater.py refresh --model {model}")
                continue

            # 库已被续期/更新 → 重读库对比，参数有变化则需用新值重跑选型
            fresh_entry = self._reload_db_entry(model)
            if fresh_entry is None:
                continue
            changed = [k for k, v in fresh_entry.items()
                       if k not in GOVERNANCE_FIELDS and k != 'model'
                       and entry.get(k) != v]
            if changed:
                print(f"  ↑ 官网参数有更新: {changed}"
                      f"（verified已回退false，人工复核后 verify --model {model}）")
                reselect_needed = True
            else:
                print("  ✓ 官网参数与库一致，已续期核验时间戳")

        if not reselect_needed:
            return selection_result

        print("\n[保鲜] 库内参数已按官网更新 → 用新参数重跑选型（仅一次，防循环）...")
        candidates = self._perform_selection(params)
        if not candidates:
            return None
        print("[保鲜] 重跑完成，采用新的Top1方案（选择标准不变：综合分最高）")
        return candidates[0]

    def _reload_db_entry(self, model: str) -> Optional[Dict]:
        """refresh后重读库条目（selection_result里持有的是选型时的旧副本）"""
        from database_updater import DEFAULT_DB
        try:
            with open(DEFAULT_DB, 'r', encoding='utf-8') as f:
                db = json.load(f)
        except Exception:
            return None
        for category in ('cameras', 'lenses', 'light_sources'):
            for entry in db.get(category, []):
                if entry.get('model') == model:
                    return entry
        return None

    def _perform_selection(self, params: Dict) -> List[Dict]:
        """执行硬件选型；无解时做根因定位与口径自动复核（防调参死循环）"""
        candidates = self._select_candidates(params)
        if candidates:
            return candidates

        # ===== 无解诊断：先定位根因，再自动复核口径，禁止反复调参 =====
        mags = sorted(l['magnification'] for l in self.lens_selector.lenses
                      if l.get('magnification') and l['magnification'] > 0)
        ppm = params.get('pixel_precision_max_mm', 0)
        print("\n  " + "=" * 62)
        print("  [无解诊断] 无满足视野+精度约束的相机，或所有候选相机均无匹配镜头")
        if mags:
            print(f"  库内镜头倍率范围: {mags[0]}x ~ {mags[-1]}x")
        print(f"  当前口径: 检测精度 {params.get('precision_requirement')}mm ÷ 亚像素因子 "
              f"{params.get('pixel_per_precision', 3.0)} = 像素精度上限 {ppm*1000:.1f} μm/pixel")

        # 口径自动复核：像素精度上限 >20μm/pixel 对尺寸测量异常宽松，
        # 十有八九是把"设备精度0.03mm"当成了"像素精度0.03mm/pixel"
        if ppm > 0.02:
            print(f"\n  ⚠️ 口径复核: 像素精度上限 {ppm*1000:.1f} μm/pixel 对尺寸测量异常宽松"
                  f"（常见 5~15 μm/pixel），疑似口径混淆")
            if abs(params.get('pixel_per_precision', 3.0) - 3.0) > 1e-9:
                retry = dict(params)
                retry['pixel_per_precision'] = 3.0
                # 根因注释：标准口径 ppm=检测精度/3（不是旧ppm再÷3；
                # 旧公式 ppm/3 实为 精度/(k旧×3)，k旧≠1 时越算越严，永远无解）
                retry['pixel_precision_max_mm'] = params['precision_requirement'] / 3.0
                retry['required_pixels'] = self.calculator.required_pixels(
                    params['field_of_view'], retry['pixel_precision_max_mm'])
                print("  → 按标准口径重试（像素精度上限 = 检测精度 / 3）...")
                fixed = self._select_candidates(retry)
                if fixed:
                    print(f"  ✅ 标准口径有解（像素精度上限 {ppm/3*1000:.1f} μm/pixel）")
                    print("  ⛔ 立即停止调参！向用户确认口径后采用标准口径方案：")
                    print("     “您说的精度 0.03 是设备检测精度(mm)还是像素精度(mm/pixel)？”")
                    return fixed
            else:
                print("  亚像素因子已是3.0，重试无意义 → 检查检测精度数值本身是否填错")

        # 反向口径复核：像素精度上限 <5μm/pixel 异常严格，常见根因是把用户明说的
        # "像素精度X mm/pixel"误填进了 precision_requirement（被再÷3），差3倍导致无解
        if 0 < ppm < 0.005 and params.get('precision_source') != 'pixel_precision':
            print(f"\n  ⚠️ 口径复核: 像素精度上限 {ppm*1000:.1f} μm/pixel 异常严格"
                  f"（常见 5~15 μm/pixel），疑似口径混淆")
            print("  → 若用户原话是“像素精度X mm/pixel”，请把该值改填 config 的 "
                  "\"pixel_precision\" 字段（像素级口径，单位mm/pixel），"
                  "不要塞进 precision_requirement，也不要调 pixel_per_precision 凑解")


        print("\n  ⛔ 防死循环铁律:")
        print("  1. 同一参数组合最多重试2次，第2次仍无解必须停止")
        print("  2. 禁止改 pixel_per_precision/精度数值来'凑出'选型解")
        print("  3. 正确动作：把下方缺口报告原文转给用户，确认精度口径后再继续")
        return []

    def _select_candidates(self, params: Dict) -> List[Dict]:
        """视野-精度双约束联动选型（相机→镜头→光源），返回Top 3候选方案"""
        candidates = []
        fov = params.get('field_of_view', {'width': 50, 'height': 40})
        precision = params['precision_requirement']
        pixel_per_precision = params.get('pixel_per_precision', 3.0)
        cycle_time = params.get('cycle_time')
        min_fps = (1.5 / cycle_time) if cycle_time else None  # 1.5倍节拍余量；未提供节拍则不过滤
        if min_fps is None:
            print("  [提示] 未提供节拍要求，跳过帧率约束（节拍信息建议向用户确认）")

        # 相机选型（需求侧推导）
        print("  选型相机...")
        cameras = self.camera_selector.select_cameras_for_fov(
            fov=fov,
            required_precision_mm=precision,
            pixel_per_precision=pixel_per_precision,
            # 预算模型的像素当量上限必须原样下发；否则 direct_measurement
            # 会把"公差带÷10"再按 ÷3 算，选型与核验两链口径不一致
            pixel_precision_max_mm=params.get('pixel_precision_max_mm'),
            interface=params.get('interface'),
            min_fps=min_fps,
            top_n=3
        )

        if not cameras:
            print("  错误: 未找到满足视野+精度约束的相机")
            return []

        # 运动/飞拍场景：卷帘快门硬排除（逐行曝光→倾斜/果冻/拖影）。
        # 放在选型链而不是只放核验：核验 FAIL 时相机已经进 PPT 了。
        if is_moving_scene(params):
            kept, dropped = [], []
            for cam in cameras:
                if shutter_kind(cam) == 'rolling':
                    dropped.append(cam.get('model', ''))
                else:
                    kept.append(cam)
            if dropped:
                print(f"  [快门] 运动/飞拍场景排除卷帘快门机型: {', '.join(dropped)}")
            cameras = kept
            if not cameras:
                print("  错误: 运动/飞拍场景下库内无全局快门机型满足视野+精度约束"
                      "（卷帘快门会拖影，不能用于飞拍）")
                return []

        # 接口带宽提示：按需求帧率（1.5/节拍）核算，不用 max_fps 冒充工作点
        req_fps = required_fps(params)
        if req_fps:
            over_cams = []
            for cam in cameras:
                bw = camera_interface_status(cam, req_fps)
                if bw['status'] == 'over':
                    over_cams.append(cam)
                    print(f"  [接口] ⚠ {cam.get('model')} 在 {req_fps:.2f}fps 下"
                          f"数据率 {bw['data_rate_mbps']:.0f}MB/s 超接口带宽"
                          f"（核验将 FAIL，可降帧/ROI/换接口）")
                elif bw['status'] == 'warn':
                    print(f"  [接口] ⚠ {cam.get('model')} 带宽利用率"
                          f"{bw['utilization']*100:.0f}%（>80%，余量不足）")
            # 超带宽相机排到最后：优先选能跑满需求帧率的机型；
            # 全超时保留（核验FAIL会拦住交付，不能静默换掉用户的接口约束）
            if over_cams and len(over_cams) < len(cameras):
                cameras = [c for c in cameras if c not in over_cams] + over_cams

        # 为每个相机匹配镜头（倍率窗口联动）
        for i, camera in enumerate(cameras):
            print(f"\n  [相机{i+1}] {camera.get('brand', '')} {camera.get('model', '')} "
                  f"({camera.get('resolution', {}).get('width', 0)}×"
                  f"{camera.get('resolution', {}).get('height', 0)}, "
                  f"余量比{camera.get('precision_margin_ratio', 0)})")

            self._validate_camera_model(camera)

            lenses = self.lens_selector.select_lenses_for_camera(
                camera=camera,
                fov=fov,
                required_precision_mm=precision,
                pixel_per_precision=pixel_per_precision,
                pixel_precision_max_mm=params.get('pixel_precision_max_mm'),
                # 尺寸测量场景远心优先（库内远心无匹配自动回退普通镜头）；
                # 判定条件单点在 is_measurement_scene，与核验共用防两链漂移
                prefer_telecentric=is_measurement_scene(params),
                # 工作距离是硬约束：MOD 不足的镜头再"匹配"也合不了焦
                required_working_distance=params.get('working_distance'),
                top_n=2
            )

            if not lenses:
                print(f"    无匹配镜头，跳过该相机")
                continue

            for lens in lenses:
                self._validate_lens_model(lens)
                actual = lens['actual_fov']

                # 光源选型（基于视野与镜头工作距离）
                light = self._recommend_light_source(params, lens)

                candidate = {
                    'camera': camera,
                    'lens': lens,
                    'light_source': light,
                    'actual_fov': {'width': actual['width'], 'height': actual['height']},
                    'required_fov': {'width': fov['width'], 'height': fov['height']},
                    'fov_satisfied': lens['fov_satisfied'],
                    'object_resolution': lens['object_resolution'],
                    'safety_factor': lens['safety_factor'],
                }
                candidates.append(candidate)

        # 综合排序（相机+镜头分数之和）
        candidates.sort(
            key=lambda x: x['camera'].get('recommend_score', 0) + x['lens'].get('recommend_score', 0),
            reverse=True
        )

        return candidates[:3]

    def _present_candidates(self, candidates: List[Dict]) -> int:
        """
        展示Top 3候选方案供用户选择

        Returns:
            用户选择的方案索引（0-2）
        """
        print("\n" + "=" * 70)
        print("Top 3 候选方案")
        print("=" * 70)

        for i, candidate in enumerate(candidates):
            camera = candidate['camera']
            lens = candidate['lens']
            fov = candidate['actual_fov']
            required_fov = candidate['required_fov']

            print(f"\n【方案 {i+1}】")
            print(f"  相机: {camera.get('brand', '')} {camera.get('model', '')}")
            print(f"    分辨率: {camera.get('resolution', {}).get('width', 0)} x {camera.get('resolution', {}).get('height', 0)}")
            print(f"    像元尺寸: {camera.get('pixel_size', 0)} μm")
            print(f"    推荐分数: {camera.get('recommend_score', 0)}")

            print(f"  镜头: {lens.get('brand', '')} {lens.get('model', '')}")
            print(f"    倍率: {lens.get('magnification', 0)}x")
            print(f"    工作距离: {lens.get('working_distance', 0)} mm")
            print(f"    物方分辨率: {lens.get('object_resolution', 0):.2f} μm")
            print(f"    推荐分数: {lens.get('recommend_score', 0)}")

            print(f"  视野验证:")
            print(f"    实际视野: {fov['width']:.1f} x {fov['height']:.1f} mm")
            print(f"    所需视野: {required_fov['width']:.1f} x {required_fov['height']:.1f} mm")
            print(f"    视野满足: {'是' if candidate['fov_satisfied'] else '否'}")
            print(f"  光源: {candidate.get('light_source', {}).get('brand', '')} "
                  f"{candidate.get('light_source', {}).get('model', '')}")

            total_score = camera.get('recommend_score', 0) + lens.get('recommend_score', 0)
            print(f"  综合评分: {total_score}")

        # 非交互模式（脚本/AI调用）自动选择综合评分最高的方案
        if self.auto_mode or not sys.stdin.isatty():
            print("\n[自动模式] 非交互环境，自动选择综合评分最高的方案 1")
            return 0

        # 获取用户选择
        print("\n" + "-" * 70)
        while True:
            try:
                choice = input(f"请选择方案 (1-{len(candidates)}) [1]: ").strip()
                if choice == '':
                    choice = 1
                else:
                    choice = int(choice)

                if 1 <= choice <= len(candidates):
                    return choice - 1
                else:
                    print(f"请输入 1-{len(candidates)} 之间的数字")
            except ValueError:
                print("请输入有效的数字")
    
    def _validate_camera_model(self, camera: Dict):
        """验证相机型号可查证性"""
        brand = camera.get('brand', '')
        model = camera.get('model', '')
        
        # 已知可查证的型号列表（示例，实际应从官网验证）
        known_models = {
            '海康威视': [
                'MV-CS050-10GM', 'MV-CS050-10GM-PRO', 'MV-CS050-10GC-PRO',
                'MV-CS060-10GM', 'MV-CS200-10GM', 'MV-CS016-10GM',
                'MV-CE050-10GM', 'MV-CE120-10GM', 'MV-CA050-12UM'
            ],
            '大恒图像': [
                'MER2-504-7GM', 'MER2-1220-7GM', 'MARS-1600-7GM'
            ],
            '华睿科技': [
                'AH-5001GM', 'AE-5001GM'
            ]
        }
        
        if brand in known_models:
            if model not in known_models[brand]:
                print(f"  [警告] 型号 {model} 可能不在官网产品列表中，请手动验证")
        else:
            print(f"  [提示] 品牌 {brand} 未在验证列表中，请手动验证型号可查证性")
    
    def _validate_lens_model(self, lens: Dict):
        """验证镜头型号可查证性"""
        brand = lens.get('brand', '')
        model = lens.get('model', '')
        
        # 已知可查证的型号列表（示例，实际应从官网验证）
        known_models = {
            '视清科技': [
                'WWK03-110-230', 'WWK03-110C-230', 'WWK04-110-230', 'WWK05-110-111V3',
                'WWK05-110C-111V3', 'WWK08-110-111V3', 'WWK10-110-111V3',
                'WWK15-110-111', 'WWK20-110-111', 'WWK30-110-111',
                'WWH05-110CT-M', 'WWH10-110CT-M'
            ],
            '海康': [
                'KF0612-2M', 'KF1218-2M', 'MF0614-2M'
            ]
        }
        
        if brand in known_models:
            if model not in known_models[brand]:
                print(f"  [警告] 型号 {model} 可能不在官网产品列表中，请手动验证")
        else:
            print(f"  [提示] 品牌 {brand} 未在验证列表中，请手动验证型号可查证性")
    
    def _get_default_camera(self) -> Dict:
        """获取默认相机配置"""
        return {
            'brand': '海康威视',
            'model': 'MV-CS050-10GM-PRO',
            'sensor': 'Sony IMX264',
            'sensor_size': '2/3"',
            'resolution': {'width': 2448, 'height': 2048},
            'pixel_size': 3.45,
            'interface': 'GigE',
            'max_fps': 24.2,
            'lens_mount': 'C-Mount'
        }
    
    def _get_default_lens(self) -> Dict:
        """获取默认镜头配置"""
        return {
            'brand': '视清科技',
            'model': 'WWK05-110-111V3',
            'type': '物方远心镜头',
            'magnification': 0.5,
            'working_distance': 110,
            'supported_sensor_size': '1.1"',
            'mount': 'C-Mount',
            'telecentricity': 0.08,
            'distortion': 0.1
        }
    
    def _recommend_light_source(self, params: Dict, lens: Dict = None) -> Dict:
        """根据视野/应用场景推荐光源，自动计算工作距离（调用light_selector）"""
        from light_selector import calculate_light_working_distance, load_light_database

        fov = params.get('field_of_view', {'width': 50, 'height': 40})
        fov_width = fov.get('width', 50)
        fov_height = fov.get('height', 40)
        fov_diagonal = math.sqrt(fov_width**2 + fov_height**2)

        # 镜头工作距离作为光源安装参考
        lens_wd = lens.get('working_distance', 110) if lens else 110

        # 角度档位先定（决定 WD 公式的角度系数）：定位/测量→60~90°，
        # 表面缺陷→10~30°，通用→45°
        from light_selector import (calculate_light_working_distance,
                                    load_light_database,
                                    recommend_light_angle,
                                    select_light_source)
        angle_rule = recommend_light_angle(
            params.get('detection_type', ''),
            params.get('detection_items'))
        if params.get('light_angle') is not None:
            angle_rule = {**angle_rule, 'preferred': int(params['light_angle']),
                          'reason': '用户指定角度'}
        light_angle = angle_rule['preferred']

        result = calculate_light_working_distance(
            field_of_view=fov, camera_wd=lens_wd, light_angle=light_angle)
        light_wd_formula = result['working_distance_mm']

        # 物理约束：环形光装在镜头前端。经验公式给的是"光斑覆盖视野所需的最小 WD"，
        # 实际安装位置由镜头 WD 决定（环光发光面通常距工件 150~250mm）。
        # 取 max(公式最小值, 镜头WD-100)，再 cap 到 镜头WD-15（不能顶到镜头）。
        light_wd_install = max(light_wd_formula, round(lens_wd - 100.0, 1))
        light_wd_cap = round(max(20.0, lens_wd - 15.0), 1)
        light_wd = min(light_wd_install, light_wd_cap)
        if light_wd != light_wd_formula:
            print(f"  [光源] WD 由经验公式 {light_wd_formula}mm 调整为安装距离 {light_wd}mm"
                  f"（镜头WD {lens_wd}mm，环光装镜头前端）")

        # 从光源数据库选择：照射范围直径需覆盖视野对角线，工作距离匹配
        # 根因注释：飞拍必须频闪（核验 _check_fly_shooting 对非频闪直接FAIL）；
        # 此前本函数忽略 is_fly_shooting，飞拍项目随机拿到普通环形光→核验必FAIL
        # 唯一数据源 = hardware_database.json 的 light_sources。
        # 历史教训：旧版从代码内硬编码列表取"品牌+尺寸+角度"拼型号（RL-150-120-W），
        # OPT 官网无此命名，假型号一路进 PPT。库空时只能如实返回"未匹配"。
        pool = load_light_database()
        if params.get('is_fly_shooting'):
            known_support = [l for l in pool if l.get('strobe') is True]
            if known_support:
                print("  [光源] 飞拍场景：优先已核验频闪光源")
                pool = known_support
            else:
                # 未核验 ≠ 不支持：保留未核验光源并显式告警，交核验 WARN。
                # 旧逻辑在这里就按 strobe 过滤，库内无 strobe 字段时直接空池。
                print("  [光源] ⚠ 飞拍场景但库内无已核验频闪光源：按未核验光源选型"
                      "（核验将 WARN，须向供应商确认 μs 级频闪能力后补库）")
        is_fly = bool(params.get('is_fly_shooting'))
        # 品牌优先级：默认追光者→孚根→OPT→CCS，逐层降级
        preferred_brands = params.get('light_brand_priority') or \
            ['追光者', '孚根', 'OPT', 'CCS']
        print(f"  [光源] 角度: {angle_rule['preferred']}°（{angle_rule['reason']}）")
        print(f"  [光源] 品牌优先级: {' > '.join(preferred_brands)}")

        candidates = select_light_source(
            fov_diagonal, light_wd,
            light_type='频闪光源' if is_fly else '环形光',
            is_fly_shooting=is_fly, lights=pool,
            angle=angle_rule['preferred'],
            preferred_brands=preferred_brands)
        best = candidates[0] if candidates else None

        if best is None:
            # 诚实降级：库内无匹配就返回空型号，由 PPT 写"待选型（需扩库）"。
            # 历史事故：旧版此处兜底硬编码 OPT RL-100-90-W（编造型号）一路进交付物。
            print("  [光源] ⚠ 库内无满足尺寸/角度/WD 的已核验型号 → 本次不指定型号（需扩库）")
            return {
                'brand': '', 'model': '', 'type': 'LED环形光光源',
                'features': [], 'working_distance': light_wd,
                'light_angle': angle_rule['preferred'],
                'outer_diameter': None, 'inner_diameter': None,
                'inner_diameter_verified': False,
                # None = 频闪能力未知（不得写成 False 冒充"明确不支持"）
                'strobe': None, 'min_exposure_us': None,
                'max_exposure_us': None,
                'needs_expansion': True,
                'angle_reason': angle_rule['reason'],
                'expansion_note': (f'需外径≥{fov_diagonal * 1.1:.0f}mm、'
                                   f'内径≥{fov_diagonal:.0f}mm、'
                                   f'角度≈{angle_rule["preferred"]}°、'
                                   f'WD≈{light_wd}mm 的已核验环光型号'),
                'calculation': result['formula'],
            }

        # 类型标签：DB 的 type 已含"光源"后缀（如频闪光源）时不再追加，避免"LED频闪光源光源"
        _t = best.get('type', '环形光')
        _label = f"LED{_t}" if _t.endswith('光源') else f"LED{_t}光源"
        return {
            'brand': best.get('brand', ''),
            'model': best.get('model', ''),
            'series': best.get('series', ''),
            'type': _label,
            'features': best.get('features', ['可调亮度', '均匀照明']),
            'working_distance': light_wd,
            'light_angle': best.get('angle', angle_rule['preferred']),
            'outer_diameter': best.get('outer_diameter'),
            'inner_diameter': best.get('inner_diameter'),
            'inner_diameter_verified': best.get('inner_diameter_verified', False),
            'wd_range_verified': best.get('wd_range_verified', False),
            'verified': bool(best.get('verified', False)),
            'verification_url': best.get('verification_url', ''),
            'needs_expansion': False,
            'angle_reason': angle_rule['reason'],
            # 频闪三字段必须透传三态：None=未核验（核验 WARN），
            # 不得用 bool() 把"未知"压成 False 冒充"明确不支持"
            'strobe': best.get('strobe'),
            'strobe_unverified': best.get('strobe_unverified',
                                          best.get('strobe') is None),
            'min_exposure_us': best.get('min_exposure_us'),
            'max_exposure_us': best.get('max_exposure_us'),
            'calculation': result['formula'],
        }
    
    def _design_algorithm(self, params: Dict, selection: Dict) -> Dict:
        """设计算法方案"""
        algorithm = {
            'software': '康耐视 VisionPro 9.0',
            'modules': [
                {
                    'name': '图像采集模块',
                    'description': '基于GigE Vision协议的图像采集'
                },
                {
                    'name': '预处理模块',
                    'description': '灰度化、滤波降噪、对比度增强'
                },
                {
                    'name': '尺寸测量模块',
                    'description': '亚像素边缘检测、尺寸计算、公差判断'
                },
                {
                    'name': '缺陷检测模块',
                    'description': '零件有无检测、漏错装检测、表面缺陷检测'
                },
                {
                    'name': '数据管理模块',
                    'description': '检测数据存储、追溯、MES对接'
                }
            ],
            'key_algorithms': [
                '亚像素边缘检测（Cognex Edge工具）',
                '模板匹配（PatMax算法）',
                '尺寸测量（Caliper工具）',
                '缺陷检测（Blob分析）'
            ]
        }
        
        return algorithm

    def _ensure_camera_image(self, selection: Dict):
        """选型相机缺官方产品图时自动从官网补图（失败仅WARN，不阻断PPT生成）"""
        camera = (selection or {}).get('camera') or {}
        model = camera.get('model')
        if not model:
            return
        img = camera.get('image_path') or ''
        img_path = img if os.path.isabs(img) else (
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), img)
            if img else '')
        if img_path and os.path.exists(img_path):
            return  # 产品图已在位
        print(f"\n[自动补图] 相机 {model} 缺产品图，尝试从官网获取...")
        try:
            from fetch_product_image import fetch_camera_image, SKILL_DIR
            r = fetch_camera_image(camera.get('brand', ''), model)
            if r.get('ok'):
                camera['image_path'] = os.path.relpath(r['image_path'], SKILL_DIR).replace(os.sep, '/')
                print(f"  补图成功: {camera['image_path']}")
            else:
                print(f"  [WARN] 补图失败（不阻断，硬件页将无产品图）: {r.get('message')}")
        except Exception as e:  # noqa: BLE001 - 补图是增益步骤，任何异常不阻断主流程
            print(f"  [WARN] 补图异常（不阻断）: {e}")

    def _quarantine_ppt(self, ppt_path: str, output_dir: str, reason: str) -> str:
        """验收未通过时把 PPT 移入 _rejected\\，物理上防止弱模型误交付"""
        out_dir = output_dir or os.path.dirname(ppt_path)
        rejected = os.path.join(out_dir, '_rejected')
        os.makedirs(rejected, exist_ok=True)
        base = os.path.basename(ppt_path)
        target = os.path.join(rejected, base)
        if os.path.abspath(target) == os.path.abspath(ppt_path):
            return ppt_path
        if os.path.exists(target):
            stem, ext = os.path.splitext(base)
            target = os.path.join(
                rejected, f"{stem}_{datetime.now().strftime('%H%M%S')}{ext}")
        try:
            os.replace(ppt_path, target)
        except OSError as e:
            print(f"[验收] [严重] PPT 隔离失败: {e}；请勿交付 {ppt_path}")
            return ppt_path
        print(f"[验收] [拒绝交付] {reason}，PPT 已隔离到: {target}")
        print("[验收] 禁止把 _rejected 里的文件当成交付物；修复后重跑同一命令")
        return target

    def _run_acceptance(self, ppt_path: str, output_dir: str) -> bool:
        """生成后自动验收：规则自查 + 渲染导出（把AI临场验收行为固化为脚本）

        Returns:
            True  = 验收通过（或显式 --no_verify），PPT 在 output 根目录可交付
            False = 验收未通过/无法验收，PPT 已被隔离到 _rejected\\，禁止交付
        """
        if getattr(self, 'no_verify', False):
            print("\n[验收] [警告] 已按要求跳过（--no_verify）：本次产物未经规则自查，"
                  "不得作为交付依据")
            return True
        tools_dir = os.path.dirname(os.path.abspath(__file__))
        # 子进程以 tools_dir 为 cwd，其内部对路径做 abspath——相对路径（如
        # --output output）会错位到 tools\output，必须先归一为绝对路径
        ppt_path = os.path.abspath(ppt_path)
        if output_dir:
            output_dir = os.path.abspath(output_dir)
        report_path = os.path.join(output_dir or os.path.dirname(ppt_path),
                                   'acceptance_report.txt')
        print("\n" + "=" * 60)
        print("[验收] 生成PPT规则自查（check_ppt_quality）...")
        try:
            r = subprocess.run(
                [sys.executable, os.path.join(tools_dir, 'check_ppt_quality.py'),
                 '--pptx', ppt_path, '--out', report_path],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=120, cwd=tools_dir)
            out = (r.stdout or '').strip()
            # 只打印结论段（避免与主流程输出混杂），完整报告在文件里
            tail = "\n".join(out.splitlines()[:6])
            print(tail)
        except Exception as e:
            self._quarantine_ppt(ppt_path, output_dir,
                                 f'规则自查脚本执行失败（{e}），产物未经验收')
            return False

        if r.returncode != 0:
            self._quarantine_ppt(ppt_path, output_dir, '规则自查存在 FAIL 项')
            print("[验收] 处理对照见 acceptance_report.txt；修复后重跑同一命令")
            return False

        # 验收通过 → 自动清理 output 下旧版本PPT（弱模型无需判断清理）
        out_dir = output_dir or os.path.dirname(ppt_path)
        ppt_path_abs = os.path.abspath(ppt_path)
        removed = 0
        for f in os.listdir(out_dir):
            if f.lower().endswith('.pptx') and \
               os.path.abspath(os.path.join(out_dir, f)) != ppt_path_abs:
                try:
                    os.remove(os.path.join(out_dir, f))
                    removed += 1
                except OSError:
                    pass
        if removed:
            print(f"[验收] 已自动清理旧版本PPT {removed} 个（只保留本次交付版）")

        print("[验收] 渲染导出页面图（供人工/评审抽查）...")
        try:
            subprocess.run(
                [sys.executable, os.path.join(tools_dir, 'export_ppt_images.py'), ppt_path],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=180)
            print(f"[验收] 页面图已导出至 ppt_review\\ 目录；完整自查报告: {report_path}")
        except Exception:
            print("[验收] 自动导出不可用（无PowerPoint），可手动打开PPT抽查")
        return True

    def _save_selection_result(self, params: Dict, selection: Dict, algorithm: Dict, output_dir: str):
        """保存选型结果"""
        lens = selection['lens']
        result = {
            'project_info': {
                'name': params.get('project_name', ''),
                'created_at': datetime.now().isoformat(),
                'detection_type': params.get('detection_type'),
                'precision_requirement': params.get('precision_requirement'),
                'precision_basis': params.get('precision_basis'),
                'precision_basis_confirmed': bool(
                    params.get('precision_basis_confirmed')),
                'precision_model': params.get('precision_model'),
                'precision_budget': params.get('precision_budget'),
                'precision_basis_text': params.get('precision_basis_text'),
                'tolerance': params.get('tolerance'),
                'tolerance_band_mm': (params.get('precision_budget') or {}).get(
                    'tolerance_band_mm'),
                'allowed_error_mm': (params.get('precision_budget') or {}).get(
                    'allowed_error_mm'),
                'cycle_time': params.get('cycle_time'),
                'field_of_view': params.get('field_of_view'),
                'working_distance': params.get('working_distance'),
                'fov_margin': params.get('fov_margin'),
                'pixel_per_precision': params.get('pixel_per_precision'),
                'pixel_precision_max_mm': params.get('pixel_precision_max_mm'),
                'required_pixels': params.get('required_pixels')
            },
            'hardware_selection': {
                'camera': selection['camera'],
                'lens': lens,
                'light_source': selection.get('light_source'),
                'actual_fov': selection.get('actual_fov'),
                'required_fov': selection.get('required_fov'),
                'fov_satisfied': selection.get('fov_satisfied')
            },
            'performance': {
                'object_resolution_um': selection.get('object_resolution'),
                'safety_factor': selection.get('safety_factor'),
                'mag_window': lens.get('mag_window'),
                'precision_margin_ratio': selection['camera'].get('precision_margin_ratio')
            },
            'validation': selection.get('validation', []),
            'validation_passed': selection.get('validation_passed', False),
            'algorithm_design': algorithm
        }
        
        result_path = os.path.join(output_dir, 'selection_result.json')
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"  选型结果已保存: {result_path}")
        return result_path


def check_config_only(config_path: str) -> int:
    """只校验配置参数（不选型、不生成PPT），几秒内给出可执行结论。

    弱模型最容易死在"参数填错→跑30秒生成→才发现口径不对"。
    先用 --check-config 拿即时反馈，确认后再跑完整流程。
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[配置校验] 读取失败: {e}")
        return 2

    print("=" * 60)
    print("配置校验（只校验参数，不选型/不生成PPT）")
    print("=" * 60)
    generator = VisionProposalGenerator()
    generator.auto_mode = True
    try:
        params = generator._validate_params(config)
    except ValueError as e:
        print(f"\n{e}")
        print("\n[配置校验] ✗ 未通过：按上面指引修正后重跑")
        return 2

    budget = params.get('precision_budget') or {}
    fov = params.get('field_of_view') or {}
    print("\n" + "-" * 60)
    print("[配置校验] ✓ 参数合法")
    print(f"  精度口径: {params.get('precision_basis_text') or '未声明'}")
    print(f"  像素当量上限: "
          f"{float(params.get('pixel_precision_max_mm') or 0) * 1000:.2f} μm/px")
    print(f"  视野: {fov.get('width')} × {fov.get('height')} mm")
    print(f"  工作距离: {params.get('working_distance')} mm")
    print(f"  亚像素因子: {params.get('pixel_per_precision')}")
    if budget.get('is_assumption'):
        print("  [警告] precision_model 未声明，按兜底口径计算；"
              "交付前必须向用户确认公差语义")
    print("-" * 60)
    print("下一步: 用 --config 跑完整选型；想先看能不能选出来就加 --dry-run")
    return 0


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='视觉检测方案自动生成系统（选型 → 核验 → PPT）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
三种入口（按手上资料选一个）:
  A. 有需求文字/图纸数字 → --config（推荐，参数可复核）
     先校验: python vision_proposal_generator.py --check-config project_config.json
     再选型: python vision_proposal_generator.py --config project_config.json --auto --output output
  B. 只有一段口述需求 → --text "检测20x16区域圆孔，公差±0.5mm，节拍1s"
  C. 有图纸/文档/图片 → --files 图纸.pdf 工件.jpg --auto

退出码（脚本/弱模型按这个判断，不要靠猜输出）:
  0 = 成功（PPT已过规则自查；或 --dry-run/--check-config 通过）
  1 = 选型无解 / 核验FAIL / PPT生成失败（看上方[FAIL]与缺口报告）
  2 = 参数/口径错误（按提示修正后重跑，禁止改口径凑解）

硬规则:
  · 型号参数只能来自官网/官方规格书，查不到写 null 或扩库，禁止编造
  · 交付PPT必须 check_ppt_quality FAIL=0 且 WARN=0；禁止 --no_verify
  · 公差口径不确定就问用户，禁止自行加 precision_basis_confirmed 绕过
        """
    )

    parser.add_argument('--files', nargs='+', help='用户提供的文件路径（图片、文档等）')
    parser.add_argument('--config', type=str, help='配置文件路径（JSON格式）')
    parser.add_argument('--text', type=str, help='需求原始文字（从0入口：把图纸/文档/口述中的数字信息原样抄录给脚本解析）')
    parser.add_argument('--check-config', metavar='JSON',
                        help='只校验配置参数（不选型/不生成PPT），几秒内给出结论')
    parser.add_argument('--dry-run', action='store_true',
                        help='只跑选型+核验并保存 selection_result.json，不生成PPT')
    parser.add_argument('--wizard', action='store_true', help='使用向导模式（交互式输入）')
    parser.add_argument('--template', type=str, help='模板PPT路径（用于继承母版样式）')
    parser.add_argument('--output', type=str, help='输出目录')
    parser.add_argument('--auto', action='store_true',
                        help='自动模式：非交互选择最优方案（脚本调用必加）')
    parser.add_argument('--hardware_page', type=int, default=None,
                        help='模板中要替换的硬件选型页序号（1=第1个硬件页，2=第2个；缺省全部替换）')
    parser.add_argument('--no_verify', action='store_true',
                        help='跳过生成后自动验收（缺省自动跑规则自查+导出页面图）')
    parser.add_argument('--version', action='version',
                        version='视觉硬件选型 skill v1.15.3')

    args = parser.parse_args()

    if args.check_config:
        sys.exit(check_config_only(args.check_config))

    generator = VisionProposalGenerator()
    generator.auto_mode = args.auto or not sys.stdin.isatty()
    generator.hardware_page = args.hardware_page
    generator.no_verify = args.no_verify

    try:
        result = None
        if args.files:
            # 从用户文件生成
            if args.dry_run:
                print("[提示] --files 链不支持 --dry-run（文件解析后直接进入生成），"
                      "本次忽略该开关；想先验参请用 --config + --dry-run")
            result = generator.generate_from_files(args.files, args.output, args.template)
        elif args.text:
            # 从需求文本生成（弱模型从0入口）
            result = generator.generate_from_text(
                args.text, args.output, args.template, dry_run=args.dry_run)
        elif args.config:
            # 从配置文件生成
            result = generator.generate_from_config(
                args.config, args.output, args.template, dry_run=args.dry_run)
        elif args.wizard:
            # 向导模式
            from config_wizard import ConfigWizard
            wizard = ConfigWizard()
            config = wizard.run()

            # 保存配置
            config_path = os.path.join(generator.config_dir, 'project_config.json')
            generator.save_config(config)

            # 生成方案
            result = generator.generate_from_config(config_path, args.output,
                                                    dry_run=args.dry_run)
        else:
            # 默认：检查是否有用户资料
            print("请提供用户资料文件或使用向导模式")
            print("使用 --help 查看帮助信息")
            parser.print_help()
    except ValueError as e:
        print(f"\n{e}")
        print("\n[停止] 按上面指引修正后重跑同一命令。禁止修改口径参数来凑解；"
              "不确定的口径向用户确认。")
        sys.exit(2)

    if result == 'SELECTION_ONLY':
        print("\n本次运行结束：已输出选型方案结果（未找到模板PPT，未生成PPT文件）")

    if result == 'DRY_RUN':
        print("\n本次运行结束：dry-run 只输出选型结果，未生成PPT")

    if result is None:
        # 根因注释：选型无解/核验FAIL 时各链返回 None，此前 main 仍 exit 0，
        # CI 与调用方无法感知失败；显式非零退出
        print("\n[失败] 未生成可用方案（见上方错误/缺口报告），已中止")
        sys.exit(1)


if __name__ == '__main__':
    main()