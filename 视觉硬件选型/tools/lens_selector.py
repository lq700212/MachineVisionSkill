#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜头选型工具 - 机器视觉选型工具
根据相机参数和检测需求自动筛选合适的工业镜头
"""

import json
import os
from typing import Dict, List, Optional, Tuple
from precision_calculator import PrecisionCalculator


def lens_wd_status(lens: Dict, wd_required_mm: Optional[float]) -> Tuple[str, Optional[Tuple]]:
    """判定镜头能否在项目要求的工作距离成像。

    根因：此前选型只看倍率/视野/靶面，从未校验工作距离，导致 MOD=500mm 的
    镜头也能在 WD=300mm 的项目里"中选"——型号匹配是假象，装上去根本不合焦。
    WD 是硬约束，必须参与过滤。

    Returns:
        (status, detail)
        status: ok / too_close / too_far / unknown
        detail: (min_wd, max_wd) 或 (mod, None)
    """
    if wd_required_mm is None:
        return 'unknown', None

    wd_range = lens.get('wd_range')
    if wd_range:
        lo = wd_range[0] if len(wd_range) > 0 else None
        hi = wd_range[1] if len(wd_range) > 1 else None
        if lo is None and hi is None:
            return 'unknown', None
        if lo is not None and wd_required_mm < lo * 0.98:
            return 'too_close', (lo, hi)
        if hi is not None and wd_required_mm > hi * 1.02:
            return 'too_far', (lo, hi)
        return 'ok', (lo, hi)

    mod = lens.get('mod')
    if mod:
        if wd_required_mm < mod * 0.98:
            return 'too_close', (mod, None)
        return 'ok', (mod, None)

    return 'unknown', None


def format_wd_requirement(detail: Optional[Tuple]) -> str:
    """把 (min, max) 格式化成可读区间，供日志/报告使用。"""
    if not detail:
        return '未核验'
    lo, hi = detail
    if lo is not None and hi is not None and lo == hi:
        return f'定工作距离 {lo:g}mm'
    if lo is not None and hi is not None:
        return f'{lo:g}~{hi:g}mm'
    if lo is not None:
        return f'≥{lo:g}mm'
    if hi is not None:
        return f'≤{hi:g}mm'
    return '未核验'


def _fit_wd_mag(lens: Dict):
    """用厂家 WD-倍率表拟合 β = 1/(a·WD + b)。

    物理依据：定焦镜头调焦满足 1/β = (WD - h)/f，即 1/β 随 WD 线性变化。
    表内含接圈状态时 h 整体平移，同表内仍自洽，可用于表内插值。
    """
    pts = [(float(w), float(m)) for w, m in (lens.get('wd_mag_table') or [])
           if w and m]
    if len(pts) < 2:
        return None
    n = len(pts)
    sx = sum(p[0] for p in pts)
    sy = sum(1.0 / p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts)
    sxy = sum(p[0] / p[1] for p in pts)
    den = n * sxx - sx * sx
    if abs(den) < 1e-9:
        return None
    a = (n * sxy - sx * sy) / den
    b = (sy - a * sx) / n
    if a <= 0:
        return None
    return a, b


def magnification_at_wd(lens: Dict,
                        wd_required_mm: Optional[float]) -> Tuple[Optional[float], str]:
    """取镜头在指定工作距离的实际倍率，返回 (倍率, 依据)。

    根因（2026-11-20）：库里的 ``magnification`` 只是某个 WD 下的单点值
    （MF7538 的 0.333x 甚至是薄透镜估算）。选型拿它当任意 WD 都成立，
    WD=300 与 WD=500 用同一个倍率算视野，交付的"实际视野"可能是错的。

    依据优先级：厂家 WD-倍率表拟合 > 单点表值 > 薄透镜估算 > 库内单点值。
    """
    if not wd_required_mm:
        return lens.get('magnification'), 'single_point'

    wd = float(wd_required_mm)
    fit = _fit_wd_mag(lens)
    if fit:
        a, b = fit
        denom = a * wd + b
        if denom > 1e-6:
            table_wds = [float(w) for w, _ in lens['wd_mag_table'] if w]
            lo, hi = min(table_wds), max(table_wds)
            source = ('wd_mag_table_interp' if lo <= wd <= hi
                      else 'wd_mag_table_extrapolated')
            return 1.0 / denom, source

    table = lens.get('wd_mag_table') or []
    if len(table) == 1 and table[0][1]:
        return float(table[0][1]), 'wd_mag_table_single_point'

    f = lens.get('focal_length')
    if f and wd > float(f) * 1.05:
        return float(f) / (wd - float(f)), 'thin_lens_estimate'

    return lens.get('magnification'), 'single_point'


class LensSelector:
    """镜头选型器"""
    
    def __init__(self, database_path: str = None):
        """
        初始化镜头选型器
        
        Args:
            database_path: 硬件数据库路径
        """
        if database_path is None:
            # 使用默认路径
            script_dir = os.path.dirname(os.path.abspath(__file__))
            database_path = os.path.join(script_dir, '..', 'config', 'hardware_database.json')
        
        self.database_path = database_path
        self.calculator = PrecisionCalculator()
        self.lenses = self._load_lenses()
    
    def _load_lenses(self) -> List[Dict]:
        """加载镜头数据库"""
        if not os.path.exists(self.database_path):
            print(f"警告: 数据库文件不存在: {self.database_path}")
            return []
        
        with open(self.database_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data.get('lenses', [])
    
    def _calculate_sensor_diameter(self, sensor_size_str: str) -> float:
        """
        根据传感器尺寸字符串计算对角线长度（mm）
        
        常见传感器尺寸：
        - 1/3": 约6mm
        - 1/2": 约8mm
        - 1/1.8": 约9mm
        - 2/3": 约11mm
        - 1": 约16mm
        - 1.1": 约18mm
        """
        sensor_sizes = {
            '1/3"': 6.0,
            '1/2"': 8.0,
            '1/1.8"': 9.0,
            '2/3"': 11.0,
            '1"': 16.0,
            '1.1"': 18.0,
            '4/3"': 22.0,
        }
        
        # 尝试直接匹配
        if sensor_size_str in sensor_sizes:
            return sensor_sizes[sensor_size_str]
        
        # 尝试模糊匹配
        for key, value in sensor_sizes.items():
            if key.replace('"', '') in sensor_size_str.replace('"', ''):
                return value
        
        return 0
    
    def select_lenses_for_camera(self,
                                 camera: Dict,
                                 fov: Dict,
                                 required_precision_mm: float,
                                 pixel_per_precision: float = 3.0,
                                 pixel_precision_max_mm: float = None,
                                 lens_type: str = None,
                                 brand: str = None,
                                 need_coaxial_light: bool = None,
                                 prefer_telecentric: bool = False,
                                 required_working_distance: float = None,
                                 top_n: int = 3) -> List[Dict]:
        """
        为指定相机匹配镜头（视野-精度双约束联动，取代固定倍率假设）

        步骤：
          1. 由相机与需求推导倍率闭区间 [mag_min, mag_max]
             mag_min = pixel/(精度/k)  （精度约束）
             mag_max = sensor/FOV      （视野覆盖约束）
          2. 筛选倍率落在区间内的镜头
          3. 逐项验证：像圆覆盖、接口、精度链、实际视野
          4. 评分：倍率靠近上限（视野刚好覆盖、精度利用充分）得分高
          5. 测量场景（prefer_telecentric=True）远心优先分层：
             先只搜远心镜头，无匹配才回退普通镜头（透视误差风险由核验
             WARNING 提示，交用户确认，而不是硬卡类型导致无解）

        Returns:
            通过验证的镜头列表（附实际视野、安全系数、验证明细；
            测量场景回退命中的条目带 telecentric_fallback=True）
        """
        if prefer_telecentric and not lens_type:
            # 根因注释：尺寸测量对透视误差敏感，远心是行业默认首选；但库内
            # 远心无匹配时硬卡类型只会无解死局 → 分层回退普通镜头并打标记，
            # 风险提示交给 validate_selection 的远心必要性核验（WARNING）
            window = self.calculator.magnification_window(
                camera, fov, required_precision_mm, pixel_per_precision,
                pixel_precision_max_mm=pixel_precision_max_mm)
            if not window.get('feasible'):
                # 窗口无解与镜头类型无关，分层回退无意义，直接按无解处理
                print(f"  [镜头] 该相机无解: {window.get('reason', '')}")
                return []
            # 大视野短路：窗口上限已低于库内远心最低倍率时，远心层注定为空
            # （大视野=低倍率，而远心镜头做不出大视野低倍率——物方远心的前组
            # 口径必须≥视野宽，成本/体积物理不可行）。再搜一遍远心层只是空转，
            # 直接回退普通镜头并把原因讲清楚（2026-09-03 实际项目：视野128mm
            # 窗口上限0.103x < 库内远心最低0.259x，日志先打一遍"无匹配根因"
            # 再回退，用户看不懂远心为何不行）
            tele_mags = sorted(l['magnification'] for l in self.lenses
                               if '远心' in str(l.get('type', ''))
                               and l.get('magnification') and l['magnification'] > 0)
            if tele_mags and window['mag_max'] * 1.02 < tele_mags[0]:
                print(f"  [镜头] 视野过大（窗口上限 {window['mag_max']:.3f}x < "
                      f"库内远心最低倍率 {tele_mags[0]}x）：远心镜头物理上做不了"
                      f"这么大视野，跳过远心层直接选普通镜头"
                      f"（核验将提示确认透视误差风险）")
                fallback = self._match_lenses_for_camera(
                    camera, fov, required_precision_mm, pixel_per_precision,
                    pixel_precision_max_mm=pixel_precision_max_mm,
                    brand=brand, need_coaxial_light=need_coaxial_light,
                    telecentric_only=False, top_n=top_n, window=window,
                    required_working_distance=required_working_distance)
                for lens in fallback:
                    lens['telecentric_fallback'] = True
                return fallback
            telecentric = self._match_lenses_for_camera(
                camera, fov, required_precision_mm, pixel_per_precision,
                brand=brand, need_coaxial_light=need_coaxial_light,
                telecentric_only=True, top_n=top_n, window=window,
                required_working_distance=required_working_distance)
            if telecentric:
                print(f"  [镜头] 测量场景远心优先：命中 {len(telecentric)} 款远心镜头")
                for lens in telecentric:
                    lens['telecentric_preferred'] = True
                return telecentric
            print("  [镜头] 测量场景库内无匹配远心镜头 → 按策略回退普通镜头"
                  "（核验将提示确认透视误差风险）")
            fallback = self._match_lenses_for_camera(
                camera, fov, required_precision_mm, pixel_per_precision,
                brand=brand, need_coaxial_light=need_coaxial_light,
                telecentric_only=False, top_n=top_n, window=window,
                required_working_distance=required_working_distance)
            for lens in fallback:
                lens['telecentric_fallback'] = True
            return fallback

        return self._match_lenses_for_camera(
            camera, fov, required_precision_mm, pixel_per_precision,
            pixel_precision_max_mm=pixel_precision_max_mm,
            lens_type=lens_type, brand=brand, need_coaxial_light=need_coaxial_light,
            telecentric_only=False, top_n=top_n,
            required_working_distance=required_working_distance)

    def _match_lenses_for_camera(self,
                                 camera: Dict,
                                 fov: Dict,
                                 required_precision_mm: float,
                                 pixel_per_precision: float = 3.0,
                                 pixel_precision_max_mm: float = None,
                                 lens_type: str = None,
                                 brand: str = None,
                                 need_coaxial_light: bool = None,
                                 telecentric_only: bool = False,
                                 window: Dict = None,
                                 required_working_distance: float = None,
                                 top_n: int = 3) -> List[Dict]:
        """单层镜头匹配：倍率窗口∩库内镜头 + 逐项验证 + 评分排序。

        telecentric_only=True 时只搜 type 含"远心"的镜头（测量场景第一层）。
        window 可传入已算好的倍率窗口（分层时复用，避免重复计算/重复打印）。
        无匹配的根因分类只在调用方确认这是最终层时才有决策意义，
        因此本方法只打印过滤统计，根因指引由最终层无匹配时输出。
        """
        if window is None:
            window = self.calculator.magnification_window(
                camera, fov, required_precision_mm, pixel_per_precision,
                pixel_precision_max_mm=pixel_precision_max_mm)
        if not window.get('feasible'):
            print(f"  [镜头] 该相机无解: {window.get('reason', '')}")
            return []

        mag_min, mag_max = window['mag_min'], window['mag_max']
        scope = "远心镜头" if telecentric_only else "全部镜头"
        print(f"  [镜头] 倍率窗口: [{mag_min:.3f}x, {mag_max:.3f}x] "
              f"(精度下限 + 视野上限，搜索范围: {scope})")

        camera_sensor = camera.get('sensor_size', '')
        camera_mount = camera.get('lens_mount', '')
        camera_diameter = self._calculate_sensor_diameter(camera_sensor)
        pixel_size = camera.get('pixel_size', 0)
        pixel_precision_max = window['pixel_precision_max_mm'] * 1000  # μm

        suitable = []
        wd_rejected = []    # (model, status, detail) 供无匹配时定位根因
        wd_unverified = []  # 有 WD 需求但镜头缺 mod/wd_range
        for lens in self.lenses:
            magnification = lens.get('magnification')
            if not magnification or magnification <= 0:
                continue  # 倍率未确认的镜头不参与（如DTCM110-56-AL）

            # 类型/品牌/同轴光过滤
            if telecentric_only and '远心' not in str(lens.get('type', '')):
                continue
            if lens_type and lens.get('type', '') != lens_type:
                continue
            if brand and lens.get('brand', '') != brand:
                continue
            if need_coaxial_light is not None and \
               bool(lens.get('has_coaxial_light', False)) != need_coaxial_light:
                continue

            # 工作距离硬约束：WD 不符必须排除。根因：旧逻辑只看倍率/视野，
            # MOD=500mm 的镜头会在 WD=300mm 的项目里"中选"，装上去不合焦。
            wd_status, wd_detail = lens_wd_status(lens, required_working_distance)
            if wd_status in ('too_close', 'too_far'):
                wd_rejected.append((lens.get('model', ''), wd_status, wd_detail))
                continue
            if wd_status == 'unknown':
                wd_unverified.append(lens.get('model', ''))

            # 工作距离决定实际倍率：不能用单点倍率冒充全行程
            magnification, mag_source = magnification_at_wd(
                lens, required_working_distance)
            if not magnification or magnification <= 0:
                continue

            # 倍率必须在窗口内（留2%容差）
            if not (mag_min * 0.98 <= magnification <= mag_max * 1.02):
                continue

            # 像圆覆盖：镜头支持直径 ≥ 相机靶面直径
            supported_d = lens.get('supported_sensor_diameter', 0) or \
                self._calculate_sensor_diameter(lens.get('supported_sensor_size', ''))
            if camera_diameter > 0 and supported_d > 0 and camera_diameter > supported_d:
                continue

            # 接口匹配
            mount_match = (not camera_mount) or (not lens.get('mount', '')) or \
                          (camera_mount == lens.get('mount', ''))

            # 精度链验证：目标值必须用倍率窗口算出的像素当量上限。
            # 根因（2026-11-21）：此处曾写 required_precision_mm / pixel_per_precision，
            # 在 direct_measurement 模式下把"公差带÷10"又按 ÷3 算，判据松 3.3 倍，
            # 与核验链口径不一致。
            object_res = self.calculator.calculate_object_resolution(pixel_size, magnification)
            is_ok, safety = self.calculator.verify_precision(
                object_res, pixel_precision_max / 1000.0)

            # 实际视野验证
            actual = self.calculator.actual_fov(camera, magnification)
            fov_ok = actual['width'] >= fov['width'] * 0.98 and \
                     actual['height'] >= fov['height'] * 0.98

            if not fov_ok:
                continue

            # 评分
            score = 0
            # 倍率位置：越接近上限，视野利用越充分、精度余量越大
            span = max(mag_max - mag_min, 1e-6)
            pos = (magnification - mag_min) / span  # 0~1
            score += int(60 * min(pos, 1.0) + 30)  # 30~90
            # 远心度
            telecentricity = lens.get('telecentricity')
            if telecentricity is None:
                telecentricity = 1.0
            if telecentricity <= 0.05:
                score += 10
            elif telecentricity <= 0.1:
                score += 5
            # 畸变：键存在但值为 None 表示"未核验"，按中性处理，不能当 0 加分
            distortion = lens.get('distortion')
            if distortion is None:
                distortion = 1.0
            if distortion <= 0.05:
                score += 10
            elif distortion <= 0.1:
                score += 5
            if mount_match:
                score += 5
            # 工作距离贴合：原生支持的镜头优先于需接圈/未核验的
            if wd_status == 'ok':
                score += 5

            info = lens.copy()
            info.update({
                # 交付口径：magnification / working_distance 一律用"需求 WD 处"的
                # 实际值，避免下游（PPT 生成、第三方脚本）读到库内单点值。
                # 原库值保留在 *_nominal 字段供追溯（2026-11-20 事故）。
                'magnification': magnification,
                'magnification_nominal': lens.get('magnification'),
                'magnification_at_wd': magnification,
                'magnification_source': mag_source,
                'working_distance': (required_working_distance
                                     if required_working_distance is not None
                                     else lens.get('working_distance')),
                'working_distance_nominal': lens.get('working_distance'),
                'object_resolution': object_res,
                'safety_factor': safety,
                'actual_fov': actual,
                'required_fov': dict(fov),
                'fov_satisfied': fov_ok,
                'mount_match': mount_match,
                'mag_window': {'min': mag_min, 'max': mag_max},
                'wd_status': wd_status,
                'wd_requirement': required_working_distance,
                'wd_capability': wd_detail,
                'recommend_score': score,
                'validated': True,
            })
            suitable.append(info)

        if not suitable:
            wd_is_root_cause = bool(wd_rejected and required_working_distance is not None)
            if wd_is_root_cause:
                # 按与需求的接近程度排序，给出最接近的 3 款，方便判断该接圈还是改 WD
                closest = sorted(
                    wd_rejected,
                    key=lambda x: abs((x[2][0] if x[2] and x[2][0] else 0) - required_working_distance)
                )[:3]
                detail = '、'.join(f"{m}({format_wd_requirement(d)})" for m, _, d in closest)
                print(f"    [镜头无匹配·WD约束] {len(wd_rejected)} 款因工作距离不符被排除："
                      f"需求 {required_working_distance:g}mm；最接近 {detail} "
                      f"→ 需接圈/扩库，或与客户确认 WD 可否调整")
            # 根因分类：窗口与库内镜头倍率的关系决定下一步动作，避免盲目调参
            pool = [l for l in self.lenses
                    if l.get('magnification') and l['magnification'] > 0 and
                    (not telecentric_only or '远心' in str(l.get('type', '')))]
            mags = sorted(l['magnification'] for l in pool)
            if wd_is_root_cause:
                pass  # WD 已给出可执行根因，不再叠加倍率诊断
            elif mags and mag_max < mags[0] * 1.02:
                print(f"    [镜头无匹配·根因] 窗口上限 {mag_max:.3f}x 低于库内{scope}最低倍率 "
                      f"{mags[0]}x → 该相机靶面太小盖不住视野，换更大靶面/更高分辨率相机"
                      f"（不是调镜头）")
            elif mags and mag_min > mags[-1]:
                print(f"    [镜头无匹配·根因] 窗口下限 {mag_min:.3f}x 高于库内{scope}最高倍率 "
                      f"{mags[-1]}x → 精度要求超出库存能力，扩库或与用户确认口径")
            else:
                print(f"    [镜头无匹配·根因] 库内{scope}有倍率落在窗口 "
                      f"[{mag_min:.3f}x, {mag_max:.3f}x]，但被像圆/接口/同轴光/视野验证过滤")

        suitable.sort(key=lambda x: x.get('recommend_score', 0), reverse=True)
        return suitable[:top_n]

    def select_lenses(self,
                     camera_sensor_size: str = None,
                     camera_pixel_size: float = None,
                     required_precision_mm: float = 0.012,
                     pixel_per_precision: float = 3.0,
                     lens_type: str = None,
                     min_working_distance: float = None,
                     max_working_distance: float = None,
                     need_coaxial_light: bool = None,
                     brand: str = None,
                     force_telecentric: bool = None,
                     top_n: int = 3) -> List[Dict]:
        """
        根据需求筛选镜头（只返回通过验证的方案）
        
        Args:
            camera_sensor_size: 相机传感器尺寸
            camera_pixel_size: 相机像元尺寸（μm）
            required_precision_mm: 要求精度（mm）
            pixel_per_precision: 亚像素因子（默认3，与主流程一致）
            lens_type: 镜头类型（远心/定焦/变焦等）
            min_working_distance: 最小工作距离（mm）
            max_working_distance: 最大工作距离（mm）
            need_coaxial_light: 是否需要同轴光
            brand: 品牌
            force_telecentric: 是否优先使用远心镜头（高精度时自动启用；
                库内远心无匹配时回退普通镜头，与主流程分层策略一致）
            top_n: 返回前N个推荐方案
            
        Returns:
            通过验证的镜头列表（最多top_n个）
        """
        # 高精度测量（≤0.01mm）优先使用远心镜头（与主流程 select_lenses_for_camera
        # 的分层策略一致：远心层无匹配回退普通层，透视误差风险由核验提示确认）
        prefer_telecentric_only = force_telecentric
        if required_precision_mm <= 0.01:
            prefer_telecentric_only = True
            print(f"  [约束] 高精度测量（{required_precision_mm}mm），远心镜头优先")

        suitable_lenses = []
        fallback_lenses = []  # 非远心候选：仅当远心层无匹配时启用
        camera_sensor_diameter = self._calculate_sensor_diameter(camera_sensor_size) if camera_sensor_size else 0
        
        for lens in self.lenses:
            # 检查镜头类型
            if lens_type and lens.get('type', '') != lens_type:
                continue

            # 远心优先分层：用户未显式指定类型时，非远心候选进兜底池
            # （远心池有匹配时兜底池整池弃用）
            use_fallback_pool = (prefer_telecentric_only and not lens_type and
                                 '远心' not in str(lens.get('type', '')))

            # 检查品牌
            if brand and lens.get('brand', '') != brand:
                continue
            
            # 检查支持的传感器尺寸
            supported_sensor = lens.get('supported_sensor_size', '')
            supported_diameter = self._calculate_sensor_diameter(supported_sensor)
            
            if camera_sensor_diameter > 0 and supported_diameter > 0:
                if camera_sensor_diameter > supported_diameter:
                    continue
            
            # 检查工作距离
            working_distance = lens.get('working_distance', 0)
            if min_working_distance and working_distance < min_working_distance:
                continue
            if max_working_distance and working_distance > max_working_distance:
                continue
            
            # 检查同轴光
            if need_coaxial_light is not None:
                has_coaxial = lens.get('has_coaxial_light', False)
                if need_coaxial_light != has_coaxial:
                    continue
            
            # 验证精度（如果有相机像元尺寸）
            if camera_pixel_size:
                magnification = lens.get('magnification', 0)
                if magnification > 0:
                    object_resolution = self.calculator.calculate_object_resolution(
                        camera_pixel_size, magnification
                    )
                    # 根因注释：精度链判据是"像素精度 ≤ 精度/k"（与主流程
                    # _match_lenses_for_camera 一致）；此前传整精度，宽松3倍，
                    # 临界镜头在旧接口通过、在主流程/核验被FAIL
                    is_satisfied, safety_factor = self.calculator.verify_precision(
                        object_resolution, required_precision_mm / pixel_per_precision
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
                    
                    # 倍率评分（0.3x~0.8x最通用）
                    if 0.3 <= magnification <= 0.8:
                        score += 20   # 最通用，成本低
                    elif 0.8 < magnification <= 1.0:
                        score += 10
                    elif magnification > 1.0:
                        score += 0    # 高倍率成本高、景深小
                    
                    # 远心度评分
                    telecentricity = lens.get('telecentricity')
                    if telecentricity is None:
                        telecentricity = 1.0
                    if telecentricity <= 0.05:
                        score += 10   # 高精度
                    elif telecentricity <= 0.1:
                        score += 5
                    
                    # 验证标记
                    lens_info = lens.copy()
                    lens_info['object_resolution'] = object_resolution
                    lens_info['safety_factor'] = safety_factor
                    lens_info['recommend_score'] = score
                    lens_info['validated'] = True  # 标记为已验证
                    (fallback_lenses if use_fallback_pool else suitable_lenses).append(lens_info)
            else:
                # 没有相机参数时，只做基本检查
                lens_info = lens.copy()
                lens_info['validated'] = False
                (fallback_lenses if use_fallback_pool else suitable_lenses).append(lens_info)

        # 远心优先分层回退：远心池无匹配时整池启用普通镜头兜底
        if prefer_telecentric_only and not lens_type and not suitable_lenses and fallback_lenses:
            print("  [回退] 库内无匹配远心镜头 → 回退普通镜头（透视误差风险需与用户确认）")
            suitable_lenses = fallback_lenses
            for lens_info in suitable_lenses:
                lens_info['telecentric_fallback'] = True
        
        # 按推荐分数降序排序
        suitable_lenses.sort(key=lambda x: x.get('recommend_score', 0), reverse=True)
        
        # 只返回前top_n个通过验证的方案
        return suitable_lenses[:top_n]
    
    def find_matching_lens_for_camera(self, camera: Dict, required_precision_mm: float = 0.012) -> List[Dict]:
        """
        为指定相机查找匹配的镜头
        
        Args:
            camera: 相机参数字典
            required_precision_mm: 要求精度（mm）
            
        Returns:
            匹配的镜头列表
        """
        return self.select_lenses(
            camera_sensor_size=camera.get('sensor_size', ''),
            camera_pixel_size=camera.get('pixel_size', 0),
            required_precision_mm=required_precision_mm
        )
    
    def get_lens_by_model(self, model: str) -> Optional[Dict]:
        """根据型号获取镜头信息"""
        for lens in self.lenses:
            if lens.get('model', '') == model:
                return lens
        return None
    
    def compare_lenses(self, models: List[str]) -> List[Dict]:
        """比较多个镜头的参数"""
        compared = []
        
        for model in models:
            lens = self.get_lens_by_model(model)
            if lens:
                compared.append(lens)
        
        return compared
    
    def print_lens_info(self, lens: Dict, camera_pixel_size: float = None):
        """打印镜头信息"""
        print(f"\n{'='*60}")
        print(f"镜头型号: {lens.get('brand', '')} {lens.get('model', '')}")
        print(f"{'='*60}")
        print(f"镜头类型: {lens.get('type', '')}")
        print(f"放大倍率: {lens.get('magnification', 0)}x")
        print(f"工作距离: {lens.get('working_distance', 0)} mm")
        print(f"支持传感器: {lens.get('supported_sensor_size', '')}")
        print(f"镜头接口: {lens.get('mount', '')}")
        print(f"像方F/#: {lens.get('f_number', '')}")
        print(f"像方MTF30: {lens.get('mtf30', '')} lp/mm")
        print(f"物方景深: {lens.get('depth_of_field', '')}")
        print(f"像方畸变: {lens.get('distortion', '')}%")
        print(f"物方远心度: {lens.get('telecentricity', '')}°")
        print(f"镜头总长: {lens.get('total_length', '')} mm")
        print(f"同轴光: {'是' if lens.get('has_coaxial_light', False) else '否'}")
        
        # 精度分析
        if camera_pixel_size and lens.get('magnification', 0) > 0:
            calculator = PrecisionCalculator()
            magnification = lens['magnification']
            object_resolution = calculator.calculate_object_resolution(camera_pixel_size, magnification)
            is_satisfied, safety_factor = calculator.verify_precision(
                object_resolution, 0.012  # 假设精度要求0.012mm
            )
            
            print(f"\n精度分析:")
            print(f"  物方分辨率: {object_resolution:.2f} μm")
            print(f"  安全系数: {safety_factor:.2f}")
            print(f"  精度满足: {'✓ 满足' if is_satisfied else '✗ 不满足'}")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='镜头选型工具')
    parser.add_argument('--sensor_size', type=str, help='相机传感器尺寸')
    parser.add_argument('--pixel_size', type=float, help='相机像元尺寸（μm）')
    parser.add_argument('--precision', type=float, default=0.012, help='要求精度（mm）')
    parser.add_argument('--type', type=str, help='镜头类型')
    parser.add_argument('--min_wd', type=float, help='最小工作距离（mm）')
    parser.add_argument('--max_wd', type=float, help='最大工作距离（mm）')
    parser.add_argument('--coaxial', action='store_true', help='需要同轴光')
    parser.add_argument('--brand', type=str, help='品牌')
    parser.add_argument('--model', type=str, help='查询特定型号')
    parser.add_argument('--compare', type=str, nargs='+', help='比较多个型号')
    
    args = parser.parse_args()
    
    selector = LensSelector()
    
    if args.model:
        # 查询特定型号
        lens = selector.get_lens_by_model(args.model)
        if lens:
            selector.print_lens_info(lens, args.pixel_size)
        else:
            print(f"未找到型号: {args.model}")
    elif args.compare:
        # 比较多个型号
        lenses = selector.compare_lenses(args.compare)
        for lens in lenses:
            selector.print_lens_info(lens, args.pixel_size)
    else:
        # 筛选镜头
        suitable_lenses = selector.select_lenses(
            camera_sensor_size=args.sensor_size,
            camera_pixel_size=args.pixel_size,
            required_precision_mm=args.precision,
            lens_type=args.type,
            min_working_distance=args.min_wd,
            max_working_distance=args.max_wd,
            need_coaxial_light=args.coaxial if args.coaxial else None,
            brand=args.brand
        )
        
        print(f"\n满足条件的镜头: {len(suitable_lenses)} 个")
        
        for i, lens in enumerate(suitable_lenses, 1):
            print(f"\n{i}. {lens.get('brand', '')} {lens.get('model', '')}")
            print(f"   类型: {lens.get('type', '')}")
            print(f"   倍率: {lens.get('magnification', 0)}x")
            print(f"   工作距离: {lens.get('working_distance', 0)} mm")
            if 'object_resolution' in lens:
                print(f"   物方分辨率: {lens['object_resolution']:.2f} μm")
                print(f"   安全系数: {lens.get('safety_factor', 0):.2f}")


if __name__ == '__main__':
    main()