#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
精度计算器 - 机器视觉选型工具
用于计算物方分辨率、验证精度要求
"""

import json
import math
import os
import re
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
    # precision_model.application 是 2026-11-21 引入的口径字段，顶层
    # application 可能为空。只看顶层会让 direct_measurement 的测量项目
    # 被判成非测量场景，远心优先策略静默失效（2026-11-21 复核发现）。
    _model = params.get('precision_model')
    if isinstance(_model, dict) and _model.get('application') == 'measurement':
        return True
    try:
        precision = float(params.get('precision_requirement') or 0)
    except (TypeError, ValueError):
        return False
    return 0 < precision <= 0.01


# ============================================================
# 精度口径模型（2026-11-21 事故）
#
# 行业里有两套"公差 → 像素当量"的口径，前提不同，禁止叠加：
#   A. 视觉直接测这个尺寸（基恩士/HSM）：像素当量 = 公差带 / 10
#      基恩士原文：尺寸测量 测量精度 = 10 × 像素精度；
#      外观检测 检测精度 = 4 × 像素精度
#   B. 视觉是整机链路一环：像素当量 = 视觉允许误差 / 3
#      其中 视觉允许误差 = 整机公差带 × 视觉分配比例（1/10~1/3）
#
# 旧实现把 A 的 /10 和 B 的 /3 连用，等价于 公差/30，比行业常规严 3 倍，
# 还把中间值叫"设备精度"，容易被读成整机精度。现用 mode 显式区分。
# ============================================================

# ============================================================
# 光学/接口工程常数（2026-11-21 行业规范复核补齐）
#
# 选型只算"分辨率够不够"是不够的：镜头景深、镜头解析力（MTF）、
# 光圈衍射、相机接口带宽、快门类型都是工控视觉的硬约束。
# 这些函数只做工程估算，返回值必须标注"估算"，不得冒充厂家实测值。
# ============================================================

# 接口有效载荷带宽（MB/s，已扣协议开销；8bit 单通道）
# 参考：GigE 1Gbps 理论 125MB/s，实际有效约 110~118MB/s；
#       USB3.0 5Gbps 理论 500MB/s，实际有效约 350MB/s。
INTERFACE_EFFECTIVE_BW_MBPS = {
    'gige': 110.0,
    '10gige': 1100.0,
    'usb3': 350.0,
    'cameralink': 255.0,
    'coaxpress': 600.0,
}

INTERFACE_LABEL = {
    'gige': 'GigE（有效约110MB/s）',
    '10gige': '10GigE（有效约1100MB/s）',
    'usb3': 'USB3（有效约350MB/s）',
    'cameralink': 'Camera Link Base（有效约255MB/s）',
    'coaxpress': 'CoaXPress（有效约600MB/s）',
}


def normalize_interface(name) -> str:
    """接口名归一化：'GigE Vision'/'gige'/'10GigE' → 内部键。"""
    s = str(name or '').lower().replace(' ', '').replace('-', '').replace('_', '')
    if '10gige' in s or '10gbase' in s:
        return '10gige'
    if 'gige' in s:
        return 'gige'
    if 'usb3' in s or 'usb 3' in s:
        return 'usb3'
    if 'cameralink' in s:
        return 'cameralink'
    if 'coaxpress' in s or s.startswith('cxp'):
        return 'coaxpress'
    return ''


def interface_effective_bandwidth_mbps(name) -> Optional[float]:
    """接口有效带宽（MB/s）；未知接口返回 None（调用方应 WARN，不得默认通过）。"""
    return INTERFACE_EFFECTIVE_BW_MBPS.get(normalize_interface(name))


def parse_min_f_number(value) -> Optional[float]:
    """从 'F3.8 ~ F12' / 'F2.8' / 2.8 中取最小 F 数（最大光圈）。

    景深和衍射都按最大光圈（最小 F 数）估算：这是镜头能力上限，
    实际收小光圈只会让景深变大、衍射变差，交付文案必须写清工作光圈。
    """
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    nums = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', str(value))]
    nums = [x for x in nums if x > 0]
    return min(nums) if nums else None


def estimate_object_dof_half_mm(f_number, pixel_size_um: float,
                                magnification: float,
                                coc_pixels: float = 1.0) -> Optional[float]:
    """物方景深半宽（±mm）估算，Harry Norton 近似。

        DOF_total ≈ 2 · N · c · (1 + β) / β²

    其中 c 为像方容许弥散圆，取 ``coc_pixels × 像元``。默认 1 像素
    （偏保守；行业也有取 2 像素的宽松口径）。返回值是总景深的一半，
    与数据库 ``depth_of_field="±0.35mm"`` 的语义一致。

    这是估算值，不是厂家实测；厂家给了 depth_of_field 时优先用厂家值。
    """
    f = parse_min_f_number(f_number)
    try:
        px = float(pixel_size_um)
        m = float(magnification)
    except (TypeError, ValueError):
        return None
    if not f or px <= 0 or m <= 0:
        return None
    c_mm = px / 1000.0 * float(coc_pixels)
    return f * c_mm * (1.0 + m) / (m * m)


def nyquist_lpmm(pixel_size_um: float) -> Optional[float]:
    """相机奈奎斯特频率（lp/mm）= 1000 / (2 × 像元μm)。

    镜头 MTF30 应不低于该值（工程上建议 ≥1.2 倍），否则镜头成为
    分辨率瓶颈，换更高像素相机也拿不到更多细节。
    """
    try:
        px = float(pixel_size_um)
    except (TypeError, ValueError):
        return None
    return 1000.0 / (2.0 * px) if px > 0 else None


def airy_disk_um(f_number, wavelength_um: float = 0.55) -> Optional[float]:
    """艾里斑直径（μm）= 2.44 · λ · F#（λ 默认 0.55μm 绿光）。

    要求艾里斑 ≤ 2 个像元；超过 3 个像元说明光圈收得太小、衍射
    已成为分辨率瓶颈（此时提高像素/倍率都没用，要开大光圈）。
    """
    f = parse_min_f_number(f_number)
    if not f or f <= 0:
        return None
    return 2.44 * float(wavelength_um) * f


DEFAULT_PRECISION_MODEL = {
    'mode': 'system_budget',
    'application': 'positioning',
    'tolerance_type': 'unilateral',
    # 行业口径对齐（2026-11-22）：整机公差分配给视觉的常见比例是 1/3，
    # 叠加上亚像素判据 pixel_factor=3 后等效"整机公差 ÷ 9"，与基恩士/HSM
    # 的"像素当量 = 公差带 ÷ 10"基本一致。旧默认 0.1 再 ÷3 等于 ÷30，
    # 比行业常规严 3 倍（会把相机/镜头选贵一个档）。
    'allocation_ratio': 0.3,
    'pixel_factor': 3.0,
}

PRECISION_MODE_LABEL = {
    'system_budget': '整机误差分配',
    'direct_measurement': '视觉直接测量',
    'explicit_pixel': '用户指定像素当量',
    'explicit_precision': '已确认视觉允许误差',
}

TOLERANCE_TYPE_LABEL = {
    'unilateral': '单向公差（给定值即带宽）',
    'bilateral': '双向公差（±值，带宽×2）',
    'total': '已给总带宽',
}

APPLICATION_LABEL = {
    'positioning': '定位/贴合',
    'measurement': '尺寸测量',
    'defect': '外观检测',
}

# 视觉直接测量时的行业口径系数（基恩士/HSM）
DIRECT_FACTOR_BY_APPLICATION = {
    'measurement': 10.0,   # 尺寸测量：测量精度 = 10 × 像素精度
    'defect': 4.0,         # 外观检测：检测精度 = 4 × 像素精度
    'positioning': 6.0,    # 定位：介于两者之间（无单一官方值，取中值）
}


def _as_float(value, default=None):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_precision_budget(params: Dict) -> Optional[Dict]:
    """把客户给的一个精度数字，统一换算成"像素当量上限"。

    输入优先级（从强到弱）：
      1. ``pixel_precision``：用户直接给像素当量（mm/pixel），最明确；
      2. ``precision_requirement``：客户/合同明确给出的测量或检测精度，
         直接作为视觉指标（÷亚像素因子），不再按整机公差分配；
      3. ``precision_model`` + ``tolerance``：声明了整机公差分配模型；
      4. ``tolerance`` + 默认模型：未声明模型时按行业常规 30% 分配（兜底）。

    返回 ``None`` 表示精度口径完全缺失（调用方应判 FAIL/提示补参数）。
    """
    if not isinstance(params, dict):
        return None

    model = dict(DEFAULT_PRECISION_MODEL)
    model.update(params.get('precision_model') or {})
    # 兼容 config 里把模型写成平铺字段的写法
    for key in ('mode', 'application', 'tolerance_type',
                'allocation_ratio', 'pixel_factor', 'direct_factor'):
        if key not in model and params.get(key) is not None:
            model[key] = params[key]

    model_declared = bool(params.get('precision_model'))
    mode = str(model.get('mode') or 'system_budget')
    application = str(model.get('application') or 'positioning')
    tolerance_type = str(model.get('tolerance_type') or 'unilateral')
    pixel_factor = _as_float(model.get('pixel_factor'), 3.0) or 3.0
    if pixel_factor <= 0:
        pixel_factor = 3.0

    # --- 1. 用户直接给像素当量 ---
    explicit_pixel = _as_float(params.get('pixel_precision'))
    if explicit_pixel and explicit_pixel > 0:
        return {
            'mode': 'explicit_pixel',
            'mode_label': PRECISION_MODE_LABEL['explicit_pixel'],
            'application': application,
            'application_label': APPLICATION_LABEL.get(application, application),
            'tolerance_type': tolerance_type,
            'tolerance_input_mm': None,
            'tolerance_band_mm': None,
            'allocation_ratio': None,
            'allowed_error_mm': explicit_pixel * pixel_factor,
            'pixel_factor': pixel_factor,
            'pixel_precision_max_mm': explicit_pixel,
            'pixel_precision_max_um': explicit_pixel * 1000,
            'assumptions': [],
            'is_assumption': False,
            'basis_text': (f"用户指定像素当量 {explicit_pixel * 1000:.1f}μm/px"
                           f"（等效视觉允许误差 {explicit_pixel * pixel_factor:.3f}mm）"),
        }

    tolerance = _as_float(params.get('tolerance'))

    # --- 2/4. 从整机公差分配 ---
    # 2026-11-22 口径修正：precision_requirement 是"视觉/测量精度"这种最明确的
    # 指标，必须绝对优先于 tolerance。旧逻辑在 precision_model 已声明时让
    # tolerance 反过来压过 precision_requirement，导致 config 同时写两者时
    # 日志说"精度优先"、预算却按公差算，选型链与核验链口径分裂。
    if tolerance and tolerance > 0 and not _as_float(params.get('precision_requirement')):
        if tolerance_type == 'bilateral':
            band = tolerance * 2.0
            band_text = f"±{tolerance:g}mm（带宽 {band:g}mm）"
        elif tolerance_type == 'total':
            band = tolerance
            band_text = f"{tolerance:g}mm（已给总带宽）"
        else:
            band = tolerance
            band_text = f"{tolerance:g}mm（单向，带宽 {band:g}mm）"

        if mode == 'direct_measurement':
            # 只有显式配了 direct_factor 才覆盖行业口径，否则按应用取
            # （尺寸测量10 / 外观4 / 定位6）
            explicit_factor = _as_float(model.get('direct_factor'))
            factor = explicit_factor or DIRECT_FACTOR_BY_APPLICATION.get(
                application, 10.0)
            if factor <= 0:
                factor = 10.0
            pixel_max = band / factor
            basis = (f"公差带 {band:g}mm ÷ {factor:g}"
                     f"（{APPLICATION_LABEL.get(application, application)}直测口径）"
                     f" = {pixel_max * 1000:.1f}μm/px")
            return {
                'mode': 'direct_measurement',
                'mode_label': PRECISION_MODE_LABEL['direct_measurement'],
                'application': application,
                'application_label': APPLICATION_LABEL.get(application, application),
                'tolerance_type': tolerance_type,
                'tolerance_input_mm': tolerance,
                'tolerance_band_mm': band,
                'allocation_ratio': 1.0,
                'direct_factor': factor,
                'allowed_error_mm': band,
                'pixel_factor': factor,
                'pixel_precision_max_mm': pixel_max,
                'pixel_precision_max_um': pixel_max * 1000,
                'assumptions': [
                    f'{APPLICATION_LABEL.get(application, application)}按行业口径'
                    f'（公差带 ÷ {factor:g}）直接换算，视觉独占该公差带'],
                'is_assumption': not model_declared,
                'basis_text': basis,
            }

        ratio = _as_float(model.get('allocation_ratio'), 0.1)
        if ratio is None or not (0 < ratio <= 1):
            ratio = 0.1
        allowed = band * ratio
        pixel_max = allowed / pixel_factor
        assumptions = [
            f'视觉只承担整机公差的 {ratio:.0%}，其余留给机器人/标定/取料',
            f'亚像素判据：允许误差内留 {pixel_factor:g} 像素余量',
        ]
        basis = (f"整机公差 {band_text} × 视觉分配 {ratio:.0%}"
                 f" = 视觉允许误差 {allowed * 1000:.0f}μm"
                 f" ÷ {pixel_factor:g} = {pixel_max * 1000:.1f}μm/px")
        return {
            'mode': 'system_budget',
            'mode_label': PRECISION_MODE_LABEL['system_budget'],
            'application': application,
            'application_label': APPLICATION_LABEL.get(application, application),
            'tolerance_type': tolerance_type,
            'tolerance_input_mm': tolerance,
            'tolerance_band_mm': band,
            'allocation_ratio': ratio,
            'allowed_error_mm': allowed,
            'pixel_factor': pixel_factor,
            'pixel_precision_max_mm': pixel_max,
            'pixel_precision_max_um': pixel_max * 1000,
            'assumptions': assumptions,
            'is_assumption': not model_declared,
            'basis_text': basis,
        }

    # --- 3. 已确认的视觉允许误差 / 客户测量精度 ---
    precision = _as_float(params.get('precision_requirement'))
    if precision and precision > 0:
        pixel_max = precision / pixel_factor
        # 2026-11-22：客户说"测量精度/检测精度 X"时，X 就是视觉系统要保证的
        # 指标，直接 ÷ 亚像素因子，不再乘分配比例（旧实现把它当整机公差
        # 再分 1/10，导致 0.5mm 被算成 16.7μm/px，严了 10 倍）。
        source_is_measurement = str(
            params.get('precision_basis') or '') == 'measurement_accuracy'
        source_label = '客户测量精度' if source_is_measurement else '视觉允许误差'
        return {
            'mode': 'explicit_precision',
            'mode_label': PRECISION_MODE_LABEL['explicit_precision'],
            'application': application,
            'application_label': APPLICATION_LABEL.get(application, application),
            'tolerance_type': tolerance_type,
            'tolerance_input_mm': tolerance,
            'tolerance_band_mm': tolerance,
            'allocation_ratio': None,
            'allowed_error_mm': precision,
            'pixel_factor': pixel_factor,
            'pixel_precision_max_mm': pixel_max,
            'pixel_precision_max_um': pixel_max * 1000,
            'assumptions': [
                (f'{source_label} {precision:g}mm 直接作为视觉指标，未再分摊'
                 if source_is_measurement
                 else f'视觉允许误差 {precision:g}mm 已确认，未再分摊'),
            ],
            'is_assumption': False,
            'basis_text': (f"{source_label} {precision * 1000:.0f}μm"
                           f" ÷ {pixel_factor:g} = {pixel_max * 1000:.1f}μm/px"),
        }

    return None


def format_precision_basis(budget: Optional[Dict]) -> str:
    """精度口径的一行人话说明，供日志/核验报告/PPT 复用。"""
    if not budget:
        return '未声明精度口径'
    return budget.get('basis_text') or '未声明精度口径'


# ============================================================
# 场景/工程约束判定（2026-11-21 行业规范复核补齐）
# ============================================================

_MOVING_KEYWORDS = ('飞拍', '运动', '动态', '流水线', '在线', 'on-the-fly',
                    'onthefly', 'conveyor')


def is_moving_scene(params: Dict) -> bool:
    """是否为运动/飞拍场景（决定快门类型、频闪光源、曝光时间约束）。

    判据（任一成立）：显式 is_fly_shooting；流水线速度 > 0；检测类型/项目
    文本含运动关键词。静态场景返回 False。
    """
    if params.get('is_fly_shooting'):
        return True
    try:
        if float(params.get('conveyor_speed') or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    text = f"{params.get('detection_type') or ''} " \
           f"{' '.join(params.get('detection_items') or [])}".lower()
    return any(k in text for k in _MOVING_KEYWORDS)


def required_fps(params: Dict, margin: float = 1.5) -> Optional[float]:
    """由节拍推导需求帧率（Hz）：margin / cycle_time；无节拍返回 None。

    工程上帧率要留 1.5 倍余量（触发抖动、曝光占空、通信抖动）。
    不得用相机 max_fps 冒充需求帧率——max_fps 是上限，不是工作点。
    """
    try:
        cycle = float(params.get('cycle_time') or 0)
    except (TypeError, ValueError):
        return None
    if cycle <= 0:
        return None
    return margin / cycle


def estimate_camera_data_rate_mbps(camera: Dict, fps: float,
                                   bit_depth: int = None) -> Optional[float]:
    """估算某帧率下的接口数据率（MB/s，未计协议开销）。

    MB/s = W × H × 位深/8 × fps ÷ 1e6
    bit_depth 缺省取 8（黑白工业相机常见输出）；相机字段优先。
    """
    res = camera.get('resolution') or {}
    try:
        w = int(res.get('width') or 0)
        h = int(res.get('height') or 0)
        f = float(fps or 0)
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0 or f <= 0:
        return None
    depth = bit_depth or camera.get('bit_depth') or 8
    try:
        depth = float(depth)
    except (TypeError, ValueError):
        depth = 8.0
    return w * h * (depth / 8.0) * f / 1e6


def camera_interface_status(camera: Dict, fps: float) -> Dict:
    """接口带宽校核：返回 {status, data_rate_mbps, bandwidth_mbps,
    utilization, interface}；status ∈ ok/over/warn/unknown。

    超带宽不等于相机不能买：可降帧、开 ROI、换 10GigE/USB3。
    但"需求帧率下超带宽"必须显式告警，不能默认通过。
    """
    iface = camera.get('interface', '')
    bw = interface_effective_bandwidth_mbps(iface)
    rate = estimate_camera_data_rate_mbps(camera, fps)
    out = {'status': 'unknown', 'data_rate_mbps': rate,
           'bandwidth_mbps': bw, 'utilization': None,
           'interface': iface}
    if rate is None or bw is None or bw <= 0:
        return out
    util = rate / bw
    out['utilization'] = util
    if util > 1.0:
        out['status'] = 'over'
    elif util > 0.8:
        out['status'] = 'warn'
    else:
        out['status'] = 'ok'
    return out


def parse_depth_of_field_half_mm(value) -> Optional[float]:
    """解析镜头景深字段为半宽（±mm）。

    只接受厂家明确标注 ``±X mm`` 的写法（如 '±0.35mm'、'±2.5mm@F5.6'）。
    纯数字/无 ± 的写法语义不明（可能是总景深），返回 None 交核验标
    "未核验"，禁止猜成半宽或总宽——景深差 2 倍会直接放行超差方案。
    """
    if value is None or value == '' or isinstance(value, (int, float)):
        return None
    s = str(value)
    if '±' not in s:
        return None
    m = re.search(r'±\s*([\d.]+)\s*mm', s)
    if not m:
        return None
    try:
        v = abs(float(m.group(1)))
    except ValueError:
        return None
    return v if v > 0 else None


def parse_mtf30_lpmm(value) -> Optional[float]:
    """解析镜头 MTF30 字段为 lp/mm（取第一个数值）。

    兼容 170、'170 lp/mm'、'≥124lp/mm@...'；无法解析返回 None。
    """
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    m = re.search(r'([\d.]+)', str(value))
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    return v if v > 0 else None


def shutter_kind(camera: Dict) -> str:
    """相机快门类型归一化：'global' / 'rolling' / 'unknown'。

    中英混写都识别（'全局快门'、'Global Shutter'、'卷帘快门'、'Rolling'）。
    无法识别返回 unknown——调用方必须 WARN，不得默认全局快门。
    """
    s = str(camera.get('shutter') or '')
    if not s:
        return 'unknown'
    low = s.lower()
    if '全局' in s or 'global' in low:
        return 'global'
    if '卷帘' in s or 'rolling' in low:
        return 'rolling'
    return 'unknown'


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

        ⚠️ 已废弃（2026-11-21）：本方法只保留给旧调用方兼容，主流程一律
        走 ``resolve_precision_budget()``。它只有单一系数（÷10），无法表达
        direct_measurement / system_budget 两套口径；bilateral 分支的语义
        也与预算模型不同（此处 ÷2 再 ÷10，预算模型是 ±值 ×2 成带宽）。
        新代码禁止调用。
        
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
        
        # 计算安全区间（数值越小精度越严：
        # 保守=更严取下限，宽松=放宽取上限；此前两者写反）
        result['precision_range'] = {
            'conservative': result['required_precision_mm'] * 0.7,  # 保守：精度更高
            'standard': result['required_precision_mm'],            # 标准
            'relaxed': result['required_precision_mm'] * 1.5,       # 放松：精度略低
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
            'x': math.ceil(px_x),  # 向上取整（此前 int(x+0.999) 在小数部分<0.001 时少进一位）
            'y': math.ceil(px_y),
            'total_mp': (px_x * px_y) / 1000000
        }

    def magnification_window(self, camera: Dict, fov: Dict,
                             required_precision_mm: float,
                             pixel_per_precision: float = 3.0,
                             pixel_precision_max_mm: float = None) -> Dict:
        """
        推导某相机同时满足"视野覆盖+精度"的镜头倍率闭区间

        视野约束：  FOV = 传感器宽 / 倍率  →  倍率 ≤ sensor_w / fov_w
        精度约束：  pixel/倍率 ≤ 像素当量上限  →  倍率 ≥ pixel / 上限

        2026-11-21 修正：优先接收 ``pixel_precision_max_mm``（预算模型的
        最终产物）。此前调用方传 ``允许误差 / 亚像素因子``，在
        direct_measurement 模式下会把"公差带÷10"又按 ÷3 算，窗口下限
        松 3.3 倍，选型与核验两链口径不一致。

        Args:
            camera: 相机字典（需 resolution.width/height、pixel_size）
            fov: {'width': mm, 'height': mm}
            required_precision_mm: 视觉允许误差（mm），仅在未给
                pixel_precision_max_mm 时参与换算（兼容旧调用）
            pixel_per_precision: 亚像素因子（旧口径兜底）
            pixel_precision_max_mm: 像素当量上限（mm/pixel），优先使用

        Returns:
            {'mag_min', 'mag_max', 'feasible', 'reason',
             'pixel_precision_max_mm': 精度允许的最大像素当量}
        """
        res = camera.get('resolution', {})
        res_w = res.get('width', 0)
        res_h = res.get('height', 0)
        pixel_um = camera.get('pixel_size', 0)
        if res_w <= 0 or res_h <= 0 or pixel_um <= 0:
            return {'feasible': False, 'reason': '相机参数不完整', 'mag_min': 0, 'mag_max': 0}

        sensor_w_mm = res_w * pixel_um / 1000.0
        sensor_h_mm = res_h * pixel_um / 1000.0

        if pixel_precision_max_mm and pixel_precision_max_mm > 0:
            pixel_precision_max = float(pixel_precision_max_mm)
        elif required_precision_mm and required_precision_mm > 0:
            pixel_precision_max = self.required_object_resolution(
                required_precision_mm, pixel_per_precision)  # mm/pixel
        else:
            return {'feasible': False, 'reason': '精度参数无效',
                    'mag_min': 0, 'mag_max': 0}

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
        if pixel_precision_mm <= 0:
            raise ValueError("像素精度必须大于0")
        
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