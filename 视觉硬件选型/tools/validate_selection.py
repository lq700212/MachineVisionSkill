#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选型核验工具 - 选型结果的"回归测试"
对相机+镜头+需求参数做全项核验，输出 PASS/WARN/FAIL 报告：
  1. 参数完整性
  2. 精度链（像素精度 ≤ 检测精度/亚像素因子）
  3. 视野覆盖（实际视野 ≥ 所需视野，双向）
  4. 倍率窗口（镜头倍率必须落在[精度下限, 视野上限]区间）
  5. 光学兼容性（像圆覆盖靶面、卡口匹配）
  6. 性能余量（帧率≥1.5×节拍）
  7. 远心必要性（尺寸测量/高精度时应使用远心镜头）
  8. 型号可查证性（相机/镜头/光源 verified标记 + 官网链接）
  9. 光源内径覆盖（内孔 ≥ 视野对角线×1.1，防遮挡视野）
 10. 光学质量（景深/MTF/衍射；厂家未给则按公式估算并标注）
 11. 接口带宽（需求帧率下的数据率 ≤ 接口有效带宽）
 12. 快门类型（运动/飞拍必须全局快门）
 13. 飞拍频闪（光源 strobe 三态：支持/不支持/未核验）
"""

import json
import re
from typing import Dict, List
from dataclasses import dataclass, asdict
from enum import Enum

from precision_calculator import (
    PrecisionCalculator, is_measurement_scene, is_moving_scene,
    resolve_precision_budget, format_precision_basis,
    required_fps, camera_interface_status, parse_depth_of_field_half_mm,
    parse_mtf30_lpmm, estimate_object_dof_half_mm, nyquist_lpmm,
    airy_disk_um, parse_min_f_number, INTERFACE_LABEL, shutter_kind,
)


class CheckResult(Enum):
    PASS = "[PASS]"
    WARNING = "[WARN]"
    FAIL = "[FAIL]"
    # INFO 只用于"厂家未给数据、无法判定"的诚实披露：
    # 不计入 PASS/WARN/FAIL，不阻断交付，但必须在报告里可见，
    # 禁止把未判定项沉默掉（沉默=假绿）。
    INFO = "[INFO]"


@dataclass
class CheckItem:
    name: str
    result: CheckResult
    message: str
    suggestion: str = ""

    def to_dict(self):
        d = asdict(self)
        d['result'] = self.result.value
        return d


def resolve_precision_mm(params: Dict):
    """解析视觉允许误差（mm），返回 (值, 口径说明)。

    优先用统一的 ``resolve_precision_budget``：它会区分
    "整机公差分配" 与 "视觉直接测量" 两种口径，避免 /10 与 /3 叠加。
    旧实现只给 tolerance 时按 tolerance ÷ 10 处理，会把整机公差
    当成视觉指标（2026-11-21 复核基恩士/HSM 口径后修正）。
    """
    budget = resolve_precision_budget(params)
    if budget:
        return budget['allowed_error_mm'], format_precision_basis(budget)
    return 0.0, ''


def effective_magnification(lens: Dict) -> float:
    """取需求工作距离处的实际倍率。

    优先用选型器按 WD 算出的 ``magnification_at_wd``；直接用库内单点
    ``magnification`` 会在 WD 偏离标称点时算错视野（2026-11-20 事故）。
    """
    v = lens.get('magnification_at_wd')
    if v is None:
        v = lens.get('magnification')
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


MAG_SOURCE_LABEL = {
    'wd_mag_table_interp': ('厂家 WD-倍率表插值', CheckResult.PASS),
    'wd_mag_table_extrapolated': ('超出厂家 WD-倍率表范围，按拟合外推',
                                  CheckResult.WARNING),
    'wd_mag_table_single_point': ('厂家仅给单点倍率，未覆盖需求 WD',
                                  CheckResult.WARNING),
    'thin_lens_estimate': ('按薄透镜估算（无厂家 WD-倍率表）', CheckResult.WARNING),
    'single_point': ('库内单点倍率，未按 WD 修正', CheckResult.WARNING),
}


class SelectionValidator:
    """选型核验器"""

    def __init__(self):
        self.checks: List[CheckItem] = []
        self.calculator = PrecisionCalculator()

    # 靶面型号 → 传感器对角线(mm)
    SENSOR_DIAMETERS = {
        '1/4"': 4.0, '1/3"': 6.0, '1/2.9"': 6.2, '1/2"': 8.0,
        '1/1.8"': 9.0, '2/3"': 11.0, '1"': 16.0, '1.1"': 18.0, '4/3"': 22.0,
    }

    @classmethod
    def sensor_diameter(cls, size_str: str) -> float:
        if not size_str:
            return 0
        if size_str in cls.SENSOR_DIAMETERS:
            return cls.SENSOR_DIAMETERS[size_str]
        for key, value in cls.SENSOR_DIAMETERS.items():
            if key.replace('"', '') in size_str.replace('"', ''):
                return value
        return 0

    def validate(self, camera: Dict, lens: Dict, params: Dict,
                 verbose: bool = True, light: Dict = None) -> List[CheckItem]:
        """执行完整核验，返回检查项列表（light 可选：光源WD物理约束核验）"""
        self.checks = []
        if verbose:
            print("\n" + "=" * 70)
            print("选型核验开始")
            print("=" * 70)

        self._check_completeness(camera, lens, params)
        self._check_working_distance(lens, params)
        self._check_magnification_basis(lens, params)
        self._check_precision_basis(params)
        self._check_precision_chain(camera, lens, params)
        self._check_fov_coverage(camera, lens, params)
        self._check_magnification_window(camera, lens, params)
        self._check_optical_compatibility(camera, lens)
        self._check_performance_margin(camera, lens, params)
        self._check_optics_quality(camera, lens, params)
        self._check_interface_bandwidth(camera, params)
        self._check_shutter(camera, params)
        self._check_telecentric_necessity(lens, params)
        self._check_verifiability(camera, lens)
        self._check_light_verifiability(light)
        self._check_light_inner_diameter(light, params)
        self._check_light_working_distance(lens, light, params)
        self._check_fly_shooting(camera, lens, params, light)

        if verbose:
            self._print_validation_result()
        return self.checks

    # ------------------------------------------------------------------
    def _check_light_verifiability(self, light: Dict = None):
        """光源可查证性（2026-11-20 事故：光源型号由代码硬编码拼造，
        核验 19 项全 PASS 仍让不存在的 OPT RL-150-120-W 进了 PPT）"""
        if not light or not light.get('model'):
            self.checks.append(CheckItem(
                "光源可查证性", CheckResult.WARNING,
                "未指定光源型号（光源库无匹配或未提供），无法核验可查证性",
                "按 SKILL.md 扩库流程入库已核验光源后重跑；"
                "禁止用品牌+尺寸+角度拼型号"))
            return

        model = light['model']
        # 与硬件库交叉校验：库内查无此型号时给出明确提示（不直接 FAIL，
        # 兼容用户显式指定并已人工核验的真实型号）
        in_db = None
        try:
            from light_selector import load_light_database
            db_models = {l.get('model') for l in load_light_database()}
            if db_models:
                in_db = model in db_models
        except Exception:
            pass

        if not light.get('verified'):
            extra = "；且该型号不在已核验硬件库中，疑似编造" if in_db is False else ""
            self.checks.append(CheckItem(
                "光源可查证性", CheckResult.WARNING,
                f"光源 {model} 未标记 verified=true（未对照官网核验）{extra}",
                "官网详情页逐项核对型号/角度/内外径后 verify 置真；"
                "未核验型号不得作为交付型号"))
            return

        if not light.get('verification_url'):
            self.checks.append(CheckItem(
                "光源可查证性", CheckResult.WARNING,
                f"光源 {model} 标记已核验但缺少 verification_url（来源不可追溯）",
                "补官网详情页链接后重新 verify"))
            return

        suffix = "" if in_db in (True, None) else "（注意：该型号不在当前硬件库中）"
        self.checks.append(CheckItem(
            "光源可查证性", CheckResult.PASS,
            f"光源 {model} 已验证，官网链接在案{suffix}"))

    def _check_light_inner_diameter(self, light: Dict = None, params: Dict = None):
        """光源内孔必须覆盖视野对角线×1.1，否则光源本体遮挡视野四角"""
        if not light or not light.get('model'):
            return
        fov = (params or {}).get('field_of_view') or {}
        try:
            diag = (fov.get('width', 0) ** 2 + fov.get('height', 0) ** 2) ** 0.5
        except (TypeError, AttributeError):
            diag = 0
        if diag <= 0:
            return

        inner = light.get('inner_diameter')
        need = round(diag * 1.1, 1)
        if inner is None:
            self.checks.append(CheckItem(
                "光源内径覆盖", CheckResult.WARNING,
                f"光源内径未核验（视野对角线 {diag:.1f}mm，需内孔≥{need}mm）",
                "向厂商确认内径后补库；内孔不足会在视野四角形成遮挡"))
        elif inner < need:
            self.checks.append(CheckItem(
                "光源内径覆盖", CheckResult.FAIL,
                f"光源内径 {inner}mm < 视野对角线×1.1={need}mm，会遮挡视野",
                "换更大内径的光源型号，或缩小视野"))
        else:
            self.checks.append(CheckItem(
                "光源内径覆盖", CheckResult.PASS,
                f"光源内径 {inner}mm ≥ 视野对角线×1.1={need}mm"))

    def _check_light_working_distance(self, lens: Dict, light: Dict = None,
                                     params: Dict = None):
        """光源工作距离物理约束：环形/同轴光源装在镜头前端，
        光源到工件距离必须小于镜头物方WD（远心系统WD由镜头决定，不可穿透镜头安装）"""
        if not light:
            return
        # 优先用项目声明 WD：镜头库内 working_distance 是标称单点值，
        # 与现场实际安装距离无关（2026-11-20：WD 改 320 后仍打印 300）
        lens_wd = (params or {}).get('working_distance') \
            or lens.get('working_distance', 0) or 0
        light_wd = light.get('working_distance', 0) or 0
        if not lens_wd or not light_wd:
            return
        if light_wd >= lens_wd:
            self.checks.append(CheckItem(
                "光源工作距离", CheckResult.FAIL,
                f"光源WD {light_wd}mm ≥ 镜头物方WD {lens_wd}mm，物理上无法安装"
                "（光源位于镜头与工件之间）",
                f"光源WD需小于镜头WD；重新选光源或核对视野/角度参数"))
        else:
            self.checks.append(CheckItem(
                "光源工作距离", CheckResult.PASS,
                f"光源WD {light_wd}mm < 镜头物方WD {lens_wd}mm"))

    def _check_fly_shooting(self, camera: Dict, lens: Dict, params: Dict, light: Dict = None):
        """飞拍场景核验：检查曝光时间是否满足要求，光源是否支持频闪"""
        # 检查是否为飞拍场景
        is_fly_shooting = params.get('is_fly_shooting', False)
        if not is_fly_shooting:
            return
        
        # 获取流水线速度
        conveyor_speed = params.get('conveyor_speed', 0)
        if conveyor_speed <= 0:
            self.checks.append(CheckItem(
                "飞拍速度", CheckResult.WARNING,
                "飞拍场景但未提供流水线速度，无法计算曝光时间",
                "请提供流水线速度（mm/s）"))
            return
        
        # 获取像素精度：优先用预算模型已算好的像素当量上限
        # （resolve_precision_mm 返回的是视觉允许误差，除以 k 才是像素当量；
        #  预算模型已含该步，params['pixel_precision_max_mm'] 可直接用）
        pixel_precision = params.get('pixel_precision_max_mm') \
            or params.get('pixel_precision') or 0
        if pixel_precision <= 0:
            precision, _ = resolve_precision_mm(params)
            k = params.get('pixel_per_precision') or 3.0
            if precision > 0:
                pixel_precision = precision / k
            else:
                self.checks.append(CheckItem(
                    "飞拍精度", CheckResult.WARNING,
                    "飞拍场景但未提供像素精度或精度要求，无法计算曝光时间",
                    "请提供精度要求或像素精度"))
                return
        
        # 计算最大允许曝光时间
        calculator = PrecisionCalculator()
        try:
            exposure_result = calculator.calculate_max_exposure_time(pixel_precision, conveyor_speed)
            max_exposure_us = exposure_result['max_exposure_us']
        except ValueError as e:
            self.checks.append(CheckItem(
                "飞拍计算", CheckResult.FAIL,
                f"曝光时间计算失败: {e}",
                "检查流水线速度是否大于0"))
            return
        
        # 检查光源是否支持频闪（三态：True=支持 / False=明确不支持 /
        # None=厂商资料未给、未核验）。未核验给 WARN 而不是 FAIL：
        # 不能把"不知道"判成"不支持"（反之亦然），但必须显式暴露待确认。
        if light:
            strobe = light.get('strobe', None)
            if strobe is False:
                self.checks.append(CheckItem(
                    "飞拍光源", CheckResult.FAIL,
                    "飞拍场景需要频闪光源，当前光源明确不支持频闪",
                    "更换为频闪光源（如CCS LFV系列）"))
            elif strobe is None:
                self.checks.append(CheckItem(
                    "飞拍光源", CheckResult.WARNING,
                    f"光源 {light.get('model') or '未指定型号'} 的频闪能力未核验"
                    f"（库内缺 strobe/min_exposure_us 字段）",
                    "向供应商确认是否支持 μs 级频闪及最短脉宽；"
                    "确认后在硬件库补 strobe=true/min_exposure_us 并核验"))
            else:
                # 检查曝光时间是否在光源支持范围内：
                # 系统要求曝光 ≤ max_exposure_us，光源只需能打到一样短
                # （系统上限比光源max宽松是正常余量，不得告警；仅当系统上限
                # 比光源最短还短时光源装不住）
                min_exp = light.get('min_exposure_us', 0)
                max_exp = light.get('max_exposure_us', float('inf'))
                if max_exposure_us < min_exp:
                    self.checks.append(CheckItem(
                        "飞拍曝光时间", CheckResult.WARNING,
                        f"计算的最大曝光时间 {max_exposure_us:.1f}μs 短于光源最短 {min_exp}μs",
                        "更换响应更快的频闪光源或降低流水线速度"))
                else:
                    self.checks.append(CheckItem(
                        "飞拍曝光时间", CheckResult.PASS,
                        f"最大曝光时间 {max_exposure_us:.1f}μs 在光源支持范围内"))
        else:
            self.checks.append(CheckItem(
                "飞拍光源", CheckResult.WARNING,
                "飞拍场景未提供光源信息，无法核验频闪支持",
                "请提供光源型号或选择频闪光源"))
    
    def _check_completeness(self, camera: Dict, lens: Dict, params: Dict):
        for param in ['brand', 'model', 'sensor_size', 'resolution', 'pixel_size', 'lens_mount']:
            if camera.get(param):
                self.checks.append(CheckItem(f"相机.{param}", CheckResult.PASS, "已提供"))
            else:
                self.checks.append(CheckItem(f"相机.{param}", CheckResult.FAIL,
                                             "缺失必要参数", f"请补充相机{param}"))
        for param in ['brand', 'model', 'magnification', 'working_distance', 'mount']:
            if lens.get(param):
                self.checks.append(CheckItem(f"镜头.{param}", CheckResult.PASS, "已提供"))
            else:
                self.checks.append(CheckItem(f"镜头.{param}", CheckResult.FAIL,
                                             "缺失必要参数", f"请补充镜头{param}"))

    def _check_working_distance(self, lens: Dict, params: Dict):
        """工作距离 / MOD 核验。

        根因（2026-11-20）：WD 从未进入选型判定，MOD=500mm 的镜头在
        WD=300mm 的项目里仅凭倍率/视野"中选"，实际装上去不合焦。
        """
        wd_req = params.get('working_distance')
        source = '配置'
        if not wd_req:
            wd_req = lens.get('working_distance')
            source = '镜头标称值兜底（配置未声明项目 WD）'

        if not wd_req:
            self.checks.append(CheckItem(
                "工作距离/MOD", CheckResult.WARNING,
                "项目 WD 与镜头 WD 均缺失，无法校验能否合焦",
                "在 project_config.json 补 working_distance（镜头前端面到工件）"))
            return

        from lens_selector import lens_wd_status, format_wd_requirement
        status, detail = lens_wd_status(lens, float(wd_req))
        capability = format_wd_requirement(detail)

        if status == 'too_close':
            self.checks.append(CheckItem(
                "工作距离/MOD", CheckResult.FAIL,
                f"需求 WD={float(wd_req):g}mm 小于镜头最近工作距离 {capability}，无法合焦",
                "换 WD 覆盖该距离的镜头；或确认可否加接圈（超规格需实测畸变/MTF）"))
        elif status == 'too_far':
            self.checks.append(CheckItem(
                "工作距离/MOD", CheckResult.FAIL,
                f"需求 WD={float(wd_req):g}mm 超出镜头可用范围 {capability}",
                "换工作距离更远的镜头，或与客户确认安装空间"))
        elif status == 'ok':
            result = CheckResult.PASS if source == '配置' else CheckResult.WARNING
            self.checks.append(CheckItem(
                "工作距离/MOD", result,
                f"需求 WD={float(wd_req):g}mm 在镜头可用范围 {capability} 内（依据：{source}）",
                "" if result == CheckResult.PASS else
                "配置未声明项目 WD，本次按镜头标称值兜底；交付前须在配置中写明现场 WD"))
        else:
            self.checks.append(CheckItem(
                "工作距离/MOD", CheckResult.WARNING,
                f"镜头缺 mod/wd_range，无法判定 WD={float(wd_req):g}mm 能否合焦",
                "官网核查最近摄距后补入数据库；未核验前不得作为交付依据"))

    def _check_magnification_basis(self, lens: Dict, params: Dict):
        """倍率取值依据核验（2026-11-20 事故）。

        库内 ``magnification`` 是单点值；项目 WD 偏离该点时倍率/视野都会变。
        没有厂家 WD-倍率表的镜头只能估算，交付前必须实测标定。
        """
        source = lens.get('magnification_source')
        if not source:
            return
        label, result = MAG_SOURCE_LABEL.get(
            source, ('依据未知', CheckResult.WARNING))
        mag = effective_magnification(lens)
        wd = params.get('working_distance') or lens.get('working_distance')
        detail = (f"{label}：WD={float(wd):g}mm 处倍率 {mag:.3f}x"
                  if wd else f"{label}：倍率 {mag:.3f}x")
        sug = ''
        if result != CheckResult.PASS:
            sug = ('向厂家索取 WD-倍率表并记入 wd_mag_table 后重算；'
                   '交付前用标定板实测复核视野与畸变')
        self.checks.append(CheckItem("倍率依据", result, detail, sug))

    def _check_precision_basis(self, params: Dict):
        """精度口径核验（2026-11-21）。

        业界两套口径不能叠加："公差带÷10"是视觉直测口径，
        "允许误差÷3"是已分配后的亚像素判据。报告必须写明用的哪套、
        分配比例多少，否则客户无法判断 0.05mm 是视觉指标还是整机精度。
        """
        budget = resolve_precision_budget(params)
        if not budget:
            return
        label = budget['mode_label']
        if budget['mode'] == 'system_budget':
            detail = f"{label}：{budget['basis_text']}"
            if budget.get('is_assumption'):
                self.checks.append(CheckItem(
                    "精度口径", CheckResult.WARNING, detail,
                    "分配比例用的是默认 30%（未声明 precision_model）；"
                    "请与客户确认该数字是整机结果公差还是视觉指标后写进 config"))
            else:
                self.checks.append(CheckItem("精度口径", CheckResult.PASS, detail))
        elif budget['mode'] == 'direct_measurement':
            self.checks.append(CheckItem(
                "精度口径", CheckResult.PASS,
                f"{label}：{budget['basis_text']}",
                "该口径假定视觉独占整个公差带，不再另做误差分配"))
        else:
            self.checks.append(CheckItem(
                "精度口径", CheckResult.PASS,
                f"{label}：{budget['basis_text']}"))

    def _check_precision_chain(self, camera: Dict, lens: Dict, params: Dict):
        pixel_um = camera.get('pixel_size') or 0
        mag = effective_magnification(lens)
        budget = resolve_precision_budget(params)
        precision_mm, basis = resolve_precision_mm(params)
        k = params.get('pixel_per_precision') or 3.0

        if pixel_um <= 0 or mag <= 0 or precision_mm <= 0:
            self.checks.append(CheckItem("精度链", CheckResult.FAIL,
                                         "参数无效，无法计算",
                                         "检查像元尺寸/倍率/精度要求（precision_requirement 或 tolerance）"))
            return

        obj_res_um = pixel_um / mag
        # 有统一口径模型时直接取它的像素当量上限（已含 mode/pixel_factor），
        # 不再用 precision_mm / k 二次换算，避免 /10 与 /3 叠加
        if budget:
            pixel_precision_max_um = budget['pixel_precision_max_um']
        else:
            pixel_precision_max_um = precision_mm * 1000 / k
        margin = pixel_precision_max_um / obj_res_um

        if budget:
            if budget['mode'] == 'system_budget':
                short = (f"公差{budget['tolerance_band_mm']:g}mm"
                         f"×分配{budget['allocation_ratio']:.0%}"
                         f"={budget['allowed_error_mm'] * 1000:.0f}μm"
                         f"÷{budget['pixel_factor']:g}像素")
            elif budget['mode'] == 'direct_measurement':
                short = f"公差带÷{budget.get('direct_factor', 10):g}"
            else:
                short = f"允许误差÷{budget['pixel_factor']:g}像素"
        else:
            short = f"精度{k}等分{basis}"
        if obj_res_um <= pixel_precision_max_um:
            result = CheckResult.PASS if margin >= 1.3 else CheckResult.WARNING
            msg = (f"像素精度{obj_res_um:.2f}μm ≤ 上限{pixel_precision_max_um:.2f}μm"
                   f"（{short}），余量{margin:.2f}x")
            sug = "" if margin >= 1.3 else "余量偏小，建议提高倍率或换更高分辨率相机"
            self.checks.append(CheckItem("精度链", result, msg, sug))
        else:
            self.checks.append(CheckItem(
                "精度链", CheckResult.FAIL,
                f"像素精度{obj_res_um:.2f}μm > 上限{pixel_precision_max_um:.2f}μm"
                f"（{basis}）",
                "需要提高镜头倍率或更换更高分辨率相机"))

    def _check_fov_coverage(self, camera: Dict, lens: Dict, params: Dict):
        fov = params.get('field_of_view') or {}
        if not fov.get('width') or not fov.get('height'):
            self.checks.append(CheckItem("视野覆盖", CheckResult.WARNING,
                                         "未提供所需视野，跳过"))
            return
        actual = self.calculator.actual_fov(camera, effective_magnification(lens))
        ratio = min(actual['width'] / fov['width'], actual['height'] / fov['height'])
        ok_w = actual['width'] >= fov['width'] * 0.98
        ok_h = actual['height'] >= fov['height'] * 0.98
        if ok_w and ok_h:
            if ratio >= 1.0:
                self.checks.append(CheckItem(
                    "视野覆盖", CheckResult.PASS,
                    f"实际视野{actual['width']:.1f}x{actual['height']:.1f}mm "
                    f"≥ 所需{fov['width']:.1f}x{fov['height']:.1f}mm"
                    f"（余量{(ratio - 1) * 100:.1f}%）"))
            else:
                # 落在 2% 容差内但没达到标称需求：工程上是零余量，必须提示
                self.checks.append(CheckItem(
                    "视野覆盖", CheckResult.WARNING,
                    f"实际视野{actual['width']:.1f}x{actual['height']:.1f}mm "
                    f"未达标称需求{fov['width']:.1f}x{fov['height']:.1f}mm"
                    f"（差{(1 - ratio) * 100:.1f}%，仅靠 2% 容差通过）",
                    "视野余量为 0，WD/倍率稍有偏差就盖不住；"
                    "建议工作距离上调 20~30mm（倍率下降、视野变大）后重算"))
        else:
            self.checks.append(CheckItem(
                "视野覆盖", CheckResult.FAIL,
                f"实际视野{actual['width']:.1f}x{actual['height']:.1f}mm "
                f"< 所需{fov['width']:.1f}x{fov['height']:.1f}mm",
                "镜头倍率过大，需减小倍率或换更大靶面相机"))

    def _check_magnification_window(self, camera: Dict, lens: Dict, params: Dict):
        fov = params.get('field_of_view') or {}
        precision_mm, _ = resolve_precision_mm(params)
        if not fov or precision_mm <= 0:
            return
        k = params.get('pixel_per_precision') or 3.0
        window = self.calculator.magnification_window(camera, fov, precision_mm, k)
        mag = effective_magnification(lens)
        if not window.get('feasible'):
            self.checks.append(CheckItem("倍率窗口", CheckResult.FAIL,
                                         window.get('reason', '无解'),
                                         "该相机无法同时满足视野与精度"))
            return
        if window['mag_min'] * 0.98 <= mag <= window['mag_max'] * 1.02:
            self.checks.append(CheckItem(
                "倍率窗口", CheckResult.PASS,
                f"镜头倍率{mag:.3f}x在可行窗口[{window['mag_min']:.3f}, "
                f"{window['mag_max']:.3f}]内"))
        else:
            self.checks.append(CheckItem(
                "倍率窗口", CheckResult.FAIL,
                f"镜头倍率{mag:.3f}x不在可行窗口[{window['mag_min']:.3f}, "
                f"{window['mag_max']:.3f}]内",
                "窗口下限由精度决定，上限由视野决定"))

    def _check_optical_compatibility(self, camera: Dict, lens: Dict):
        # 像圆覆盖
        cam_d = self.sensor_diameter(camera.get('sensor_size', ''))
        lens_d = lens.get('supported_sensor_diameter', 0) or \
            self.sensor_diameter(lens.get('supported_sensor_size', ''))
        if cam_d > 0 and lens_d > 0:
            if cam_d <= lens_d:
                self.checks.append(CheckItem(
                    "像圆覆盖", CheckResult.PASS,
                    f"相机靶面{camera.get('sensor_size', '')}({cam_d}mm) "
                    f"≤ 镜头像圆{lens_d}mm"))
            else:
                self.checks.append(CheckItem(
                    "像圆覆盖", CheckResult.FAIL,
                    f"相机靶面({cam_d}mm) > 镜头像圆({lens_d}mm)",
                    "镜头无法覆盖靶面，画面四角黑掉"))

        # 卡口
        cam_mount = camera.get('lens_mount', '')
        lens_mount = lens.get('mount', '')
        if cam_mount and lens_mount:
            if cam_mount == lens_mount:
                self.checks.append(CheckItem("卡口匹配", CheckResult.PASS,
                                             f"{cam_mount} = {lens_mount}"))
            else:
                self.checks.append(CheckItem(
                    "卡口匹配", CheckResult.WARNING,
                    f"{cam_mount} ≠ {lens_mount}",
                    "需要转接环并确认法兰距兼容"))

    def _check_performance_margin(self, camera: Dict, lens: Dict, params: Dict):
        # 帧率余量（cycle_time 允许缺省：config 模板该字段可为 null，
        # 此前 params.get('cycle_time', 3) 在显式 null 时返回 None 直接崩溃）
        fps = camera.get('max_fps', 0)
        cycle_time = params.get('cycle_time', 3)
        if cycle_time is None:
            cycle_time = 3
        if fps > 0 and cycle_time > 0:
            # 需求帧率 = 1/节拍；余量判据 1.5x（触发/曝光占空/通信抖动）
            req_fps = 1.0 / cycle_time
            margin = fps / req_fps
            if margin >= 1.5:
                self.checks.append(CheckItem(
                    "帧率余量", CheckResult.PASS,
                    f"{fps}fps ≥ 节拍要求{req_fps:.2f}fps，余量{margin:.1f}x"))
            elif margin >= 1.0:
                self.checks.append(CheckItem(
                    "帧率余量", CheckResult.WARNING,
                    f"{fps}fps 仅{margin:.1f}x于节拍要求{req_fps:.2f}fps",
                    "余量不足，考虑触发/频闪或换高帧率机型"))
            else:
                self.checks.append(CheckItem(
                    "帧率余量", CheckResult.FAIL,
                    f"{fps}fps < 节拍要求{req_fps:.2f}fps",
                    "必须更换更高帧率相机"))

    def _check_optics_quality(self, camera: Dict, lens: Dict, params: Dict):
        """光学质量核验：景深 / 镜头解析力(MTF30) / 光圈衍射。

        工控选型只算"分辨率够不够"会漏掉三类硬约束：
          · 景深不够 → 工件高度波动就失焦（尤其微距/大倍率）；
          · 镜头 MTF 低于相机奈奎斯特 → 高像素相机拿不到细节；
          · 光圈收太小 → 艾里斑超过像元，衍射成瓶颈。
        厂家给值优先；未给则按公式估算（标"估算"），完全无法估算才 INFO。
        """
        pixel_size = camera.get('pixel_size', 0) or 0
        mag = lens.get('magnification_at_wd') or lens.get('magnification') or 0

        # ---------- 景深 ----------
        dof_vendor = parse_depth_of_field_half_mm(lens.get('depth_of_field'))
        height_variation = params.get('part_height_variation_mm')
        if dof_vendor is not None:
            dof_half, dof_src = dof_vendor, '厂家标注'
        else:
            dof_half = estimate_object_dof_half_mm(
                lens.get('f_number'), pixel_size, mag)
            dof_src = '公式估算'

        if dof_half is None:
            self.checks.append(CheckItem(
                "景深", CheckResult.INFO,
                "镜头未给景深且缺 F 数/像元/倍率，无法估算景深",
                "向厂商索取景深曲线或补全 f_number 后重算"))
        elif height_variation is None:
            f_no_txt = parse_min_f_number(lens.get('f_number'))
            f_no_txt = f"F{f_no_txt:g}" if f_no_txt else "F?"
            self.checks.append(CheckItem(
                "景深", CheckResult.INFO,
                f"景深 ±{dof_half:.3f}mm（{dof_src}，{f_no_txt}/"
                f"β{float(mag):.3f}）；未提供工件高度波动，未做余量判定",
                "交付前按实际工件高度波动确认；有波动时提供 "
                "part_height_variation_mm 重算"))
        else:
            try:
                hv = abs(float(height_variation))
            except (TypeError, ValueError):
                hv = 0
            if dof_half >= hv:
                self.checks.append(CheckItem(
                    "景深", CheckResult.PASS,
                    f"景深 ±{dof_half:.3f}mm（{dof_src}）≥ 高度波动 ±{hv:g}mm"))
            else:
                self.checks.append(CheckItem(
                    "景深", CheckResult.FAIL,
                    f"景深 ±{dof_half:.3f}mm（{dof_src}）< 高度波动 ±{hv:g}mm",
                    "减小倍率/收小光圈增加景深，或加调焦/测高机构"))

        # ---------- 镜头解析力 vs 相机奈奎斯特 ----------
        nyq = nyquist_lpmm(pixel_size)
        mtf = parse_mtf30_lpmm(lens.get('mtf30'))
        if nyq is None:
            pass
        elif mtf is None:
            self.checks.append(CheckItem(
                "镜头解析力", CheckResult.INFO,
                f"镜头未提供 MTF30，无法核验是否匹配相机奈奎斯特 {nyq:.0f}lp/mm",
                "向厂商索取 MTF 曲线；换更高解析力镜头前先实测对比度"))
        elif mtf >= nyq:
            self.checks.append(CheckItem(
                "镜头解析力", CheckResult.PASS,
                f"MTF30 {mtf:g}lp/mm ≥ 相机奈奎斯特 {nyq:.0f}lp/mm"))
        else:
            self.checks.append(CheckItem(
                "镜头解析力", CheckResult.WARNING,
                f"MTF30 {mtf:g}lp/mm < 相机奈奎斯特 {nyq:.0f}lp/mm："
                f"镜头成为分辨率瓶颈，高像素相机拿不到额外细节",
                "换高解析力镜头，或降低相机像素/加大倍率匹配"))

        # ---------- 光圈衍射 ----------
        f_no = parse_min_f_number(lens.get('f_number'))
        airy = airy_disk_um(f_no)
        if airy is None or pixel_size <= 0:
            pass
        else:
            ratio = airy / float(pixel_size)
            if ratio <= 3.0:
                self.checks.append(CheckItem(
                    "光圈衍射", CheckResult.PASS,
                    f"最大光圈 F{f_no:g} 艾里斑 {airy:.1f}μm = {ratio:.1f}×像元"
                    f"（≤3×，衍射不构成瓶颈）"))
            else:
                self.checks.append(CheckItem(
                    "光圈衍射", CheckResult.WARNING,
                    f"最大光圈 F{f_no:g} 艾里斑 {airy:.1f}μm = {ratio:.1f}×像元"
                    f"（>3×，衍射已成为分辨率瓶颈）",
                    "开大光圈（减小 F 数）或换大靶元相机；收小光圈只会更差"))

    def _check_interface_bandwidth(self, camera: Dict, params: Dict):
        """接口带宽核验：需求帧率下的数据率必须 ≤ 接口有效带宽。

        GigE 标称 1Gbps，实际有效约 110MB/s；5MP@24fps 就超了。
        超带宽的后果是丢帧/降帧，相机标称帧率跑不到，节拍不达标。
        """
        req = required_fps(params)
        if req is None:
            self.checks.append(CheckItem(
                "接口带宽", CheckResult.INFO,
                "未提供节拍（cycle_time），无法核验需求帧率下的接口带宽",
                "提供 cycle_time 后重算；满帧标称值不能直接当工作点"))
            return

        status = camera_interface_status(camera, req)
        rate = status['data_rate_mbps']
        bw = status['bandwidth_mbps']
        if status['status'] == 'unknown':
            self.checks.append(CheckItem(
                "接口带宽", CheckResult.INFO,
                f"接口 '{status['interface']}' 未知或参数不全，"
                f"无法核验 {req:.2f}fps 下的数据率",
                "确认相机接口类型（GigE/USB3/10GigE）后重算"))
        elif status['status'] == 'over':
            self.checks.append(CheckItem(
                "接口带宽", CheckResult.FAIL,
                f"{req:.2f}fps 数据率 {rate:.1f}MB/s > "
                f"{INTERFACE_LABEL.get(status['interface'], status['interface'])}"
                f" 有效带宽 {bw:.0f}MB/s（利用率 {status['utilization']*100:.0f}%）",
                "降帧/开 ROI/换 10GigE 或 USB3 机型；标称帧率不等于可用帧率"))
        elif status['status'] == 'warn':
            self.checks.append(CheckItem(
                "接口带宽", CheckResult.WARNING,
                f"{req:.2f}fps 数据率 {rate:.1f}MB/s 占接口带宽 "
                f"{bw:.0f}MB/s 的 {status['utilization']*100:.0f}%（>80%）",
                "余量不足，建议开 ROI/降位深或换更高带宽接口"))
        else:
            self.checks.append(CheckItem(
                "接口带宽", CheckResult.PASS,
                f"{req:.2f}fps 数据率 {rate:.1f}MB/s / 带宽 {bw:.0f}MB/s"
                f"（利用率 {status['utilization']*100:.0f}%）"))

    def _check_shutter(self, camera: Dict, params: Dict):
        """快门类型核验：运动/飞拍必须全局快门。

        卷帘快门逐行曝光，工件运动会产生倾斜/果冻/拖影；静态工位可用。
        """
        shutter = str(camera.get('shutter') or '')
        moving = is_moving_scene(params)
        kind = shutter_kind(camera)
        if kind == 'unknown':
            self.checks.append(CheckItem(
                "快门类型", CheckResult.WARNING,
                f"相机未提供/无法识别快门类型（'{shutter}'），无法核验"
                f"{'（本项目为运动/飞拍场景）' if moving else ''}",
                "补全局快门(Global)/卷帘快门(Rolling)字段"))
            return
        is_global = kind == 'global'
        is_rolling = kind == 'rolling'
        if moving and is_rolling:
            self.checks.append(CheckItem(
                "快门类型", CheckResult.FAIL,
                f"运动/飞拍场景使用卷帘快门（{shutter}）：运动工件会拖影/变形",
                "必须换全局快门机型（Global Shutter）"))
        elif moving and is_global:
            self.checks.append(CheckItem(
                "快门类型", CheckResult.PASS,
                f"运动/飞拍场景使用全局快门（{shutter}）"))
        elif is_global:
            self.checks.append(CheckItem(
                "快门类型", CheckResult.PASS,
                f"全局快门（{shutter}），静态/运动场景均适用"))
        elif is_rolling:
            self.checks.append(CheckItem(
                "快门类型", CheckResult.PASS,
                f"卷帘快门（{shutter}），静态工位可用；若后续提速需复评"))
        else:
            self.checks.append(CheckItem(
                "快门类型", CheckResult.WARNING,
                f"快门类型 '{shutter}' 无法识别（既非全局也非卷帘）",
                "按厂商规格书写明 Global/Rolling"))

    def _check_telecentric_necessity(self, lens: Dict, params: Dict):
        """远心必要性核验：测量场景必须远心（FAIL）；库内远心无匹配由选型层
        分层回退到普通镜头（lens带telecentric_fallback标记）——回退是"库内
        无货的权宜方案"，必须醒目提示与用户确认透视误差风险（WARNING）。"""
        precision_mm, _ = resolve_precision_mm(params)
        # 场景判定复用单点函数（与lens_selector选型分层同一条件，防两链漂移）
        is_measurement = is_measurement_scene(params)
        lens_type = lens.get('type', '')
        is_tele = '远心' in lens_type
        if is_measurement and is_tele:
            self.checks.append(CheckItem(
                "远心必要性", CheckResult.PASS,
                f"测量/高精度场景(精度{precision_mm}mm)使用远心镜头，正确"))
        elif is_measurement and not is_tele:
            if lens.get('telecentric_fallback'):
                self.checks.append(CheckItem(
                    "远心必要性", CheckResult.WARNING,
                    f"测量场景(精度{precision_mm}mm)库内无匹配远心镜头，已回退普通镜头"
                    f"（{lens_type} {lens.get('model', '')}）",
                    "远心无货的权宜方案：普通镜头存在透视误差，安装需严格控制物距"
                    "一致性，建议扩库远心型号后重跑选型，并向用户说明该风险"))
            else:
                self.checks.append(CheckItem(
                    "远心必要性", CheckResult.WARNING,
                    f"精度{precision_mm}mm的测量场景建议使用远心镜头（当前{lens_type}）",
                    "普通镜头透视误差会吃掉精度余量"))
        # 非测量场景不强制

    def _check_verifiability(self, camera: Dict, lens: Dict):
        for kind, item in (("相机", camera), ("镜头", lens)):
            if item.get('verified') and item.get('verification_url'):
                msg = f"{item.get('model', '')}已验证，含官网链接"
                # 数据新鲜度：官网参数可能变化，超龄提示重核验
                verified_at = item.get('verified_at') or item.get('created_at')
                if verified_at:
                    try:
                        from datetime import datetime
                        age = (datetime.now() - datetime.fromisoformat(verified_at)).days
                        if age > 180:
                            self.checks.append(CheckItem(
                                f"{kind}可查证", CheckResult.WARNING,
                                f"{msg}，但参数距上次核验已{age}天",
                                "官网参数可能已变化，建议 database_updater.py refresh 重核验"))
                            continue
                        msg += f"（{age}天内核验）"
                    except ValueError:
                        pass
                self.checks.append(CheckItem(
                    f"{kind}可查证", CheckResult.PASS, msg))
            else:
                self.checks.append(CheckItem(
                    f"{kind}可查证", CheckResult.WARNING,
                    f"{item.get('model', '')}未验证或缺少官网链接",
                    "请到官网确认型号真实性后再出方案"))

    # ------------------------------------------------------------------
    def _print_validation_result(self):
        print("\n" + "=" * 70)
        print("核验结果汇总")
        print("=" * 70)
        p = sum(1 for c in self.checks if c.result == CheckResult.PASS)
        w = sum(1 for c in self.checks if c.result == CheckResult.WARNING)
        f = sum(1 for c in self.checks if c.result == CheckResult.FAIL)
        i = sum(1 for c in self.checks if c.result == CheckResult.INFO)
        print(f"\n通过: {p}  警告: {w}  失败: {f}  待确认: {i}\n" + "-" * 70)
        for check in self.checks:
            print(f"{check.result.value} {check.name}: {check.message}")
            if check.suggestion:
                print(f"       建议: {check.suggestion}")
        print("-" * 70)
        if f == 0:
            msg = "选型结果核验通过" if w == 0 else \
                f"选型结果核验通过（{w}个警告，可优化）"
            print(f"\n[PASS] {msg}")
        else:
            print(f"\n[FAIL] 核验失败：{f}项必须解决")


def validate_selection(camera: Dict, lens: Dict, params: Dict,
                       light: Dict = None) -> bool:
    """便捷函数：返回是否通过核验（无FAIL）"""
    validator = SelectionValidator()
    checks = validator.validate(camera, lens, params, light=light)
    return all(c.result != CheckResult.FAIL for c in checks)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='选型核验工具')
    parser.add_argument('--selection', required=True, help='选型结果JSON文件')
    parser.add_argument('--params', help='项目参数JSON文件(可选)')
    parser.add_argument('--json_out', help='核验报告输出路径')
    args = parser.parse_args()

    with open(args.selection, 'r', encoding='utf-8') as f:
        selection = json.load(f)

    params = {}
    if args.params:
        with open(args.params, 'r', encoding='utf-8') as f:
            params = json.load(f)
        # 用选型结果里的 project_info 补齐缺失项（视野/精度口径等），
        # 否则 CLI 只传 config 时视野检查会被静默跳过
        for k, v in (selection.get('project_info') or {}).items():
            if params.get(k) is None and v is not None:
                params[k] = v
    else:
        params = selection.get('project_info', {})

    hw = selection.get('hardware_selection', {})
    validator = SelectionValidator()
    # 光源必须一起核验：此前 CLI 只传 camera/lens，光源假型号能绕过全部检查
    checks = validator.validate(hw.get('camera', {}), hw.get('lens', {}), params,
                                light=hw.get('light_source'))

    if args.json_out:
        report = {
            'passed': all(c.result != CheckResult.FAIL for c in checks),
            'summary': {
                'pass': sum(1 for c in checks if c.result == CheckResult.PASS),
                'warning': sum(1 for c in checks if c.result == CheckResult.WARNING),
                'fail': sum(1 for c in checks if c.result == CheckResult.FAIL),
            },
            'checks': [c.to_dict() for c in checks]
        }
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"核验报告已保存: {args.json_out}")


if __name__ == '__main__':
    main()
