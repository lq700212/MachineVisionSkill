#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
硬件数据库扩库工具 - 把"官网查证后补充数据库"固化为可重复的流程
================================================================

背景：选型遇到数据库无解时（如倍率窗口内无镜头），过去只能报错等人工扩库。
本工具把扩库流程标准化为四步，其中联网查证由AI完成（WebSearch/WebFetch），
参数校验/入库/复核/缺口分析全部脚本化，杜绝编造型号：

  1. gap     缺口报告：选型无解时自动算出"需要什么规格的硬件"（倍率窗口/
             最小像圆/所需像素/帧率），作为查证目标
  2. fetch   三级通道抓取：静态快抓 → 无头Edge渲染（后台零窗口，与有头
             浏览器同内核同效果）→ 前两级失败才输出AI浏览器接管SOP
  3. add     入库：把官网页面提取的参数写入 hardware_database.json。
             强制校验：型号唯一、来源URL必填、关键字段齐全且数值合法；
             新条目 verified=false（参与选型但核验时报"可查证性"警告）
  4. verify  复核：AI/人工核对条目与官网一致后置 verified=true
  5. refresh 保鲜：重取官网参数与库内diff（同样走三级通道），确认后更新
             并留history；参数有变化自动回退verified待复核

用法：
  python database_updater.py gap --fov 63x42 --precision 0.025
  python database_updater.py gap --selection output/selection_result.json
  python database_updater.py fetch --model WWK08-110C-111 --url https://... [--type lens]
  python database_updater.py add --draft draft.json [--db 自定义路径]
  python database_updater.py verify --model WWK08-110C-111
  python database_updater.py check-db
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(SKILL_DIR, 'config', 'hardware_database.json')

# 靶面直径(mm) → 常用规格名
DIAMETER_TO_SIZE = {
    4.0: '1/4"', 4.8: '1/4"', 6.0: '1/3"', 6.2: '1/2.9"', 8.0: '1/2"',
    9.0: '1/1.8"', 11.0: '2/3"', 16.0: '1"', 18.0: '1.1"', 22.0: '4/3"',
}

# 各硬件类型的关键字段（缺失则拒绝入库）
REQUIRED_FIELDS = {
    'cameras': ['brand', 'model', 'resolution', 'pixel_size', 'sensor_size', 'interface'],
    'lenses': ['brand', 'model', 'magnification', 'supported_sensor_diameter', 'working_distance'],
    'light_sources': ['brand', 'model', 'type'],
}

REQUIRED_HINTS = {
    'cameras': "相机必需：brand/model/resolution{width,height}/pixel_size/sensor_size/interface（max_fps强烈建议提供）",
    'lenses': "镜头必需：brand/model/magnification/supported_sensor_diameter/working_distance（建议f_number/distortion/telecentricity/depth_of_field）",
    'light_sources': "光源必需：brand/model/type（建议 diameter/working_distance_range）",
}


def load_db(db_path):
    if not os.path.exists(db_path):
        # 自定义路径首次使用：初始化空库骨架
        return {c: [] for c in REQUIRED_FIELDS}
    with open(db_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_db(db, db_path):
    """写库前自动备份"""
    if os.path.exists(db_path):
        backup = db_path + '.bak'
        shutil.copy2(db_path, backup)
        print(f"  已备份原库: {backup}")
    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"  已写入: {db_path}")


# ======================================================================
# 1. gap 缺口报告
# ======================================================================
def cmd_gap(args):
    from precision_calculator import PrecisionCalculator
    calc = PrecisionCalculator()

    # 参数来源：selection_result.json 或 命令行
    if args.selection:
        with open(args.selection, 'r', encoding='utf-8') as f:
            sel = json.load(f)
        info = sel.get('project_info', {})
        fov = info.get('field_of_view') or {}
        precision = info.get('precision_requirement', 0)
        k = info.get('pixel_per_precision', 3.0)
        cycle_time = info.get('cycle_time', 3)
        if not fov or not precision:
            print("selection_result.json 中缺少 field_of_view/precision_requirement，"
                  "请用 --fov/--precision 补充")
            return 1
    else:
        if not args.fov or not args.precision:
            print("需要 --fov 63x42 --precision 0.025 或 --selection 选型结果.json")
            return 1
        w, h = args.fov.lower().replace('mm', '').split('x')
        fov = {'width': float(w), 'height': float(h)}
        precision = args.precision
        k = args.pixel_per_precision
        cycle_time = args.cycle_time

    pixel_precision_max = calc.required_object_resolution(precision, k)
    need_px_x = int(fov['width'] / pixel_precision_max + 0.999)
    need_px_y = int(fov['height'] / pixel_precision_max + 0.999)

    db = load_db(args.db)
    print("=" * 70)
    print("选型缺口报告（官网查证目标）")
    print("=" * 70)
    print(f"需求: 视野 {fov['width']}x{fov['height']}mm, 精度 {precision}mm "
          f"(像素精度上限{pixel_precision_max*1000:.1f}μm, k={k})")
    print(f"所需相机分辨率 ≥ {need_px_x} x {need_px_y} "
          f"(约{need_px_x*need_px_y/1e6:.0f}MP), 帧率 ≥ {1.5/cycle_time:.2f}fps\n")

    # 相机缺口
    ok_cameras = []
    print("[相机缺口] 现有库中满足分辨率/帧率的型号：")
    for cam in db.get('cameras', []):
        res = cam.get('resolution', {})
        if res.get('width', 0) >= need_px_x and res.get('height', 0) >= need_px_y \
           and cam.get('max_fps', 0) >= 1.5 / cycle_time:
            ok_cameras.append(cam)
            print(f"  ✓ {cam['model']} ({res['width']}x{res['height']}, "
                  f"{cam.get('sensor_size')}, {cam.get('pixel_size')}μm)")
    if not ok_cameras:
        print("  ✗ 无 → 查证目标：分辨率≥上述值、帧率达标的工业相机（带靶面/像元尺寸参数）")

    # 镜头缺口：逐可行相机输出倍率窗口
    print("\n[镜头缺口] 满足精度+视野所需的倍率窗口与最小像圆：")
    found_any = False
    for cam in ok_cameras:
        window = calc.magnification_window(cam, fov, precision, k)
        if not window.get('feasible'):
            continue
        from validate_selection import SelectionValidator
        cam_d = SelectionValidator.sensor_diameter(cam.get('sensor_size', ''))
        matched = []
        for lens in db.get('lenses', []):
            mag = lens.get('magnification')
            if not mag:
                continue
            ld = lens.get('supported_sensor_diameter', 0)
            if window['mag_min'] * 0.98 <= mag <= window['mag_max'] * 1.02 \
               and (cam_d <= 0 or ld <= 0 or ld >= cam_d):
                matched.append(lens['model'])
        if matched:
            print(f"  ✓ {cam['model']}: 窗口[{window['mag_min']:.3f},{window['mag_max']:.3f}]x "
                  f"已有 {', '.join(matched)}")
            found_any = True
        else:
            print(f"  ✗ {cam['model']} ({cam.get('sensor_size')}): "
                  f"需要倍率 {window['mag_min']:.3f}~{window['mag_max']:.3f}x、"
                  f"像圆≥{cam_d}mm 的镜头 ← 查证目标")
    if not ok_cameras or not found_any:
        print("  → 到厂商官网按上述倍率/像圆区间查证型号"
             "（AI用WebSearch/WebFetch），提取参数后走 add 入库")

    print("\n[光源缺口] 检查照射范围覆盖：")
    diag = (fov['width']**2 + fov['height']**2) ** 0.5
    ok_lights = [l for l in db.get('light_sources', [])
                 if max(l.get('outer_diameter', 0), l.get('diameter', 0),
                        l.get('width', 0)) >= diag * 1.1]
    for l in ok_lights:
        print(f"  ✓ {l['model']} (外径{l.get('outer_diameter', l.get('diameter', '?'))}mm)")
    if not ok_lights:
        print(f"  ✗ 需要 照射范围≥{diag*1.1:.0f}mm 的光源 ← 查证目标")
    return 0


def fetch_page(url):
    import urllib.request, urllib.parse, ssl
    # URL含中文/全角字符时需编码（如孚根型号页 ProductsSt_HPDG115-1／2.html）
    url = urllib.parse.quote(url, safe=':/?&=%#[]@!$\'()*+,;~')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    data = urllib.request.urlopen(req, timeout=20, context=ctx).read()
    for enc in ('utf-8', 'gbk', 'gb18030'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', 'ignore')


def find_headless_browser():
    """定位本机可用于无头渲染的浏览器（Edge优先，系统自带零安装）"""
    candidates = [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    for name in ('msedge', 'chrome'):
        path = shutil.which(name)
        if path:
            return path
    return None


def headless_render(url, wait_ms=12000, timeout_s=60):
    """无头浏览器渲染页面并返回渲染后DOM（全程后台、零窗口、零打扰）

    三级获取通道的中间层：静态快抓拿不到JS渲染内容时启用。
    效果与有头浏览器一致（同一内核渲染），但不弹任何窗口。
    失败返回 None（由调用方降级到AI浏览器接管兜底）。
    """
    exe = find_headless_browser()
    if not exe:
        print("  未找到 Edge/Chrome，无法无头渲染")
        return None
    profile = os.path.join(tempfile.gettempdir(), 'vision_headless_profile')
    cmd = [
        exe,
        '--headless=new',
        '--disable-gpu',
        '--no-first-run',
        '--disable-extensions',
        '--disable-background-networking',
        '--mute-audio',
        '--window-size=1920,1080',
        f'--user-data-dir={profile}',
        f'--virtual-time-budget={wait_ms}',
        f'--timeout={timeout_s * 1000}',
        '--dump-dom',
        url,
    ]
    flags = 0
    if os.name == 'nt':
        flags = subprocess.CREATE_NO_WINDOW  # 确保连进程窗口都不闪
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout_s + 15,
                           encoding='utf-8', errors='replace', creationflags=flags)
    except subprocess.TimeoutExpired:
        print(f"  无头渲染超时（{timeout_s}s）")
        return None
    except Exception as e:
        print(f"  无头渲染失败: {e}")
        return None
    html = (r.stdout or '').strip()
    if r.returncode != 0 or len(html) < 500:
        return None
    return html


def _find(pattern, text, cast=float):
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return cast(m.group(1))
    except (ValueError, IndexError):
        return None


def extract_row_params(html, model):
    """
    表格行级提取：在HTML的<table>中定位包含指定型号的<tr>，返回该行各单元格文本。
    解决"型号总表"页面上全文正则会取到第一个型号参数的问题。
    """
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S | re.I):
        if model in tr:
            cells = re.split(r'</t[dh]>', tr, flags=re.I)
            cells = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', c)).strip()
                     for c in cells]
            return [c for c in cells if c]
    return None


def parse_lens_row(cells, model):
    """
    按常见镜头总表列序解析单元格：[型号, 像圆Φ(规格), 倍率, 工作距, F/#, 同轴...]
    列序因品牌而异，解析结果均标注需复核（条目verified=false）。
    """
    entry = {'model': model}
    try:
        for c in cells:
            if c == model:
                continue
            # 像圆：11.0(2/3") 或 18.0(1.1") 或 Φ18.0
            m = re.match(r'^Φ?\s*(\d{1,2}(?:\.\d+)?)\s*[（(]', c)
            if m and 'supported_sensor_diameter' not in entry:
                entry['supported_sensor_diameter'] = float(m.group(1))
                continue
            # 倍率：0.3 / 0.8 / 1.5（0~20之间的小数，且不是后面才出现的WD）
            m = re.match(r'^(\d{1,2}\.\d+)$', c)
            if m and 'magnification' not in entry:
                v = float(m.group(1))
                if 0 < v <= 20:
                    entry['magnification'] = v
                    continue
            # 工作距：110 / 110±2 / 65.5
            m = re.match(r'^(\d{2,4}(?:\.\d+)?)\s*(?:±\s*\d+(?:\.\d+)?)?$', c)
            if m and 'working_distance' not in entry and 'magnification' in entry:
                entry['working_distance'] = float(m.group(1))
                continue
            # F/#：F5.6 / 5.6（倍率和WD之后剩下的数字）
            m = re.match(r'^(?:F/?|#)?\s*(\d{1,2}(?:\.\d+)?)$', c)
            if m and 'magnification' in entry and 'working_distance' in entry \
               and 'f_number' not in entry:
                entry['f_number'] = float(m.group(1))
                continue
            # 同轴光标记
            if re.match(r'^(是|有|同轴|Yes)$', c) and 'has_coaxial_light' not in entry:
                entry['has_coaxial_light'] = True
    except Exception:
        pass
    # 像圆规格名
    if entry.get('supported_sensor_diameter'):
        d = entry['supported_sensor_diameter']
        entry['supported_sensor_size'] = DIAMETER_TO_SIZE.get(d, f'Φ{d}mm')
    return entry


def extract_card_params(html, model):
    """
    卡片布局提取（如 coolens 分类页 div.ptr：ptitle=型号，参数在所属容器内）。
    解决卡片页面全文正则会串到第一个型号参数的问题（与 extract_row_params 同理）。
    返回 entry 或 None；wd 形如 110±2 时同时给出 wd_spec 公差原文。
    """
    for m in re.finditer(
            r'<a[^>]*class="[^"]*ptitle[^"]*"[^>]*>\s*' + re.escape(model) + r'\s*</a>',
            html, re.I):
        start = html.rfind('class="ptr"', 0, m.start())
        if start == -1:
            continue
        nxt = re.search(r'class="ptr"', html[m.end():])
        end = m.end() + nxt.start() if nxt else m.end() + 8000
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html[start:end]))
        entry = {'model': model}

        def g(label):
            mm = re.search(label + r'\s*[：:]\s*([\d./±]+)', text)
            return mm.group(1) if mm else None

        mag = g(r'放大倍率[^0-9]{0,6}')
        wd = g(r'工作距[^0-9]{0,6}')
        fno = g(r'F/#')
        dia = re.search(r'支持CCD尺寸[^0-9]{0,6}Φ?\s*([\d.]+)', text)
        coax = re.search(r'同轴光\s*[：:]\s*(是|有|否|无)', text)
        if mag:
            entry['magnification'] = float(mag)
        if wd:
            mm2 = re.match(r'(\d+(?:\.\d+)?)', wd)
            if mm2:
                entry['working_distance'] = float(mm2.group(1))
                if '±' in wd:
                    entry['wd_spec'] = wd
        if fno:
            entry['f_number'] = float(fno)
        if dia:
            entry['supported_sensor_diameter'] = float(dia.group(1))
            entry['supported_sensor_size'] = DIAMETER_TO_SIZE.get(
                entry['supported_sensor_diameter'],
                f"Φ{entry['supported_sensor_diameter']}mm")
        if coax:
            entry['has_coaxial_light'] = coax.group(1) in ('是', '有')
        return entry if entry.get('magnification') else None
    return None


def extract_lens_params(text, model=None, html=None):
    """镜头参数提取：优先表格行级定位（型号→所属<tr>），其次卡片布局，
    最后退化为全文标签式（多型号页面有串行风险，会打 _serial_risk 标记）"""
    if model and html:
        cells = extract_row_params(html, model)
        if cells:
            entry = parse_lens_row(cells, model)
            if entry.get('magnification'):
                return entry
        card = extract_card_params(html, model)
        if card and card.get('magnification'):
            return card
        # 表格/卡片均未命中且页面含多个型号 → 全文提取可能串行
        if model and html.count(model) > 1:
            return {'_serial_risk': True}
    # 全文标签式（单型号详情页）
    return {
        'magnification': _find(r'放大倍率[^0-9]{0,10}([0-9.]+)', text),
        'supported_sensor_diameter': _find(r'(?:支持CCD尺寸|像面|像方尺寸)[^0-9]{0,10}Φ?\s*([0-9.]+)', text),
        'working_distance': _find(r'工作距[^0-9]{0,10}([0-9.]+)', text),
        'f_number': _find(r'F/#\s*[:：]?\s*([0-9.]+)', text),
        'distortion': _find(r'畸变[^0-9]{0,10}([0-9.]+)', text),
        'telecentricity': _find(r'远心度[^0-9]{0,10}([0-9.]+)', text),
    }


def extract_camera_params(text):
    """从渲染后的HTML文本提取相机规格（尽力而为，提取不到的字段为None）"""
    res_w = _find(r'(\d{3,5})\s*[×x*]\s*(\d{3,5})', text)
    res = None
    m = re.search(r'(\d{3,5})\s*[×x*]\s*(\d{3,5})', text)
    if m:
        res = {'width': int(m.group(1)), 'height': int(m.group(2))}
    params = {
        'resolution': res,
        'pixel_size': _find(r'(?:像元|像素)尺寸[^0-9]{0,8}([0-9.]+)', text),
        'max_fps': _find(r'(?:帧率|Frame\s*Rate)[^0-9]{0,8}([0-9.]+)', text),
        'sensor_size': (re.search(r'(1\.1"|1/1\.8"|2/3"|1/2\.9"|1/2"|1/3"|1"|4/3")', text) or [None, None])[1],
    }
    return params


def html_to_plain(html_text):
    """HTML → 纯文本（浏览器导出页或直抓页通用）"""
    body = re.sub(r'<script.*?</script>|<style.*?</style>', '', html_text, flags=re.S)
    plain = re.sub(r'<[^>]+>', ' ', body)
    return re.sub(r'\s+', ' ', plain)


# ======================================================================
# 品牌通道SOP（获取层三级通道：静态快抓 → 无头Edge渲染 → AI浏览器接管）
# mode=auto：fetch/refresh 自动按顺序走三级通道，全程后台无窗口；
# 仅当前两级都失败（站点拒绝/需要登录/验证码）才提示AI接管浏览器。
# ======================================================================
BRAND_SOP = {
    '视清科技': {
        'url': 'https://coolens.cn/product/003000004.html',
        'mode': 'auto',
        'note': '产品数据JS动态加载，无头渲染可取；列表页需从产品分类页进入',
    },
    '海康威视': {
        'url': 'https://www.hikrobotics.com/cn/machinevision',
        'mode': 'auto',
        'note': 'SPA重渲染无公开接口，无头渲染可取；产品列表需点导航加载，'
                '拿到详情页URL后直接fetch该URL',
    },
    '华睿科技': {
        'url': 'https://www.irayple.com/cn/product',
        'mode': 'auto',
        'note': 'SPA壳（首页仅1KB）数据全XHR，无头渲染可取',
    },
    '巴斯勒': {
        'url': 'https://www.baslerweb.cn/zh-cn/cameras/area-scan-cameras/',
        'mode': 'auto',
        'note': '列表页JS渲染（选型工具API需鉴权），无头渲染可取',
    },
    '追光者': {
        'url': 'http://www.f-lighting.cn/',
        'mode': 'auto',
        'note': '企业站，详情页多为JS动态加载，无头渲染可取',
    },
    '孚根': {
        'url': 'https://www.fugenmv.com/',
        'mode': 'auto',
        'note': '详情页正文JS动态加载，无头渲染可取（型号页URL含全角字符已兼容）',
    },
    '诺达佳': {
        'url': 'https://www.nodka.com.cn/',
        'mode': 'auto',
        'note': '脚本直抓403反爬，无头渲染带真实浏览器特征可过；不行则AI接管',
    },
}


def print_browser_guide(brand, model, url, dtype):
    """输出浏览器接管指引（获取层统一走浏览器时AI照此执行）"""
    sop = BRAND_SOP.get(brand, {})
    print("\n" + "-" * 70)
    print(f"[浏览器接管] {brand} 纯脚本获取不可用（动态渲染/反爬/抓取失败），AI按以下SOP执行：")
    print(f"  1. 打开页面: {url or sop.get('url', '(先WebSearch找产品页)')}")
    print(f"  2. 定位型号 {model or '(按缺口报告的规格区间筛选)'} 的详情页")
    print("  3. 将渲染后的页面另存为HTML（或复制参数表文本）")
    print(f"  4. 执行: python tools/database_updater.py add --html 保存的页面.html \\")
    print(f"           --url <详情页网址> --type {dtype} --model {model or '型号'} --brand {brand}")
    print("  5. 复核条目 → verify 置为已验证")
    if sop.get('note'):
        print(f"  (站点特征: {sop['note']})")
    print("-" * 70)


def cmd_brands(args):
    print("品牌核验通道一览（获取层三级通道：静态快抓 → 无头Edge渲染 → AI浏览器接管）：")
    print(f"{'品牌':<8} {'通道':<12} 官网入口 / 说明")
    print("-" * 90)
    for brand, sop in BRAND_SOP.items():
        mode = '自动三级' if sop['mode'] == 'auto' else sop['mode']
        print(f"{brand:<8} {mode:<12} {sop['url']}")
        print(f"{'':22} {sop['note']}")
    print("-" * 90)
    print("原则：全流程后台无窗口（无头渲染与有头浏览器同内核同效果）；")
    print("      仅前两级失败（登录/验证码/强反爬）才需AI接管浏览器；识别/校验/入库全部脚本固化。")


def _extract_and_save(plain, html_raw, args, dtype, brand, channel):
    """从页面文本提取参数并存草稿；成功返回0，提取不到返回1"""
    model = args.model
    if dtype == 'lens':
        params = extract_lens_params(plain, model=model, html=html_raw)
        if params.get('_serial_risk'):
            print(f"  [{channel}] ⚠️ 串行风险：页面含多个型号但未能定位到 {model} 的参数区，"
                  f"本次不自动提取。请用浏览器打开该型号专用详情页后走 add --html 入库")
            return 1
        found = {k: v for k, v in params.items() if v is not None}
        if not found:
            print(f"  [{channel}] 未能从页面提取到镜头参数")
            return 1
        draft = {
            'category': 'lenses',
            'entry': {
                'brand': args.brand or _guess_brand(plain),
                'model': model,
                'type': args.lens_type or '物方远心镜头',
                'mount': 'C-Mount',
                'verified': False,
                'verification_url': args.url,
                'auto_imported': True,
                'verification_note': f'脚本自动抓取自官网（{channel}），参数需复核后 verify',
                **found,
            }
        }
        if draft['entry'].get('supported_sensor_diameter'):
            d = draft['entry']['supported_sensor_diameter']
            draft['entry']['supported_sensor_size'] = DIAMETER_TO_SIZE.get(d, f'Φ{d}mm')
    else:
        # 相机/光源：从渲染后文本尽力提取
        params = extract_camera_params(plain)
        found = {k: v for k, v in params.items() if v is not None and v}
        if not found:
            print(f"  [{channel}] 未能从页面提取到{dtype}参数")
            return 1
        draft = {
            'category': 'cameras' if dtype == 'camera' else 'light_sources',
            'entry': {
                'brand': args.brand or _guess_brand(plain),
                'model': model,
                'verified': False,
                'verification_url': args.url,
                'auto_imported': True,
                'verification_note': f'脚本自动抓取自官网（{channel}），参数需复核后 verify',
                **found,
            }
        }
    out = args.draft or f"draft_{model}.json"
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    print(f"  提取到参数: {found}")
    print(f"  草稿已保存: {out} （请复核后执行 add 入库）")
    return 0


def cmd_fetch(args):
    """获取层三级通道：静态快抓 → 无头Edge渲染（后台零窗口）→ AI浏览器接管兜底"""
    brand = args.brand or ''
    sop = BRAND_SOP.get(brand, {})
    dtype = args.type or 'lens'
    url = args.url or sop.get('url')
    if not url:
        print("未提供 --url 且品牌SOP无入口URL，无法抓取")
        return 1
    args.url = url  # 草稿的 verification_url 统一用实际抓取地址

    # 通道1：静态快抓（最快，对静态站一次到位）
    print(f"抓取: {url}")
    try:
        html_raw = fetch_page(url)
        plain = html_to_plain(html_raw)
        if args.model and args.model not in plain:
            print(f"  [静态快抓] 页面中未出现型号 {args.model}（可能为JS动态加载）")
        elif _extract_and_save(plain, html_raw, args, dtype, brand, '静态快抓') == 0:
            return 0
    except Exception as e:
        print(f"  [静态快抓] 抓取失败: {e}")

    # 通道2：无头浏览器渲染（后台零窗口，效果=有头浏览器）
    if not args.static_only:
        print("  → 降级无头浏览器渲染（后台执行，无窗口）...")
        html2 = headless_render(url, wait_ms=args.render_ms)
        if html2:
            plain2 = html_to_plain(html2)
            size_kb = len(html2) // 1024
            if args.model and args.model not in plain2:
                print(f"  [无头渲染] 渲染完成（{size_kb}KB）但页面中未出现型号 {args.model}")
            elif _extract_and_save(plain2, html2, args, dtype, brand, '无头渲染') == 0:
                return 0
        else:
            print("  [无头渲染] 失败（未找到浏览器/站点拒绝/超时）")

    # 通道3：AI浏览器接管兜底（前两级均失败时）
    # 尝试自动执行浏览器接管
    browser_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'browser_fetch.py')
    if os.path.exists(browser_script) and args.url:
        print(f"  [浏览器接管] 尝试自动执行浏览器接管...")
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, browser_script, args.url, args.model],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                print(result.stdout)
                # 解析输出的HTML文件路径
                for line in result.stdout.split('\n'):
                    if '页面已保存到:' in line:
                        html_file = line.split('页面已保存到:')[1].strip()
                        if os.path.exists(html_file):
                            print(f"  [浏览器接管] 自动执行成功，继续入库流程...")
                            with open(html_file, 'r', encoding='utf-8') as f:
                                html_content = f.read()
                            plain = _html_to_plain(html_content)
                            if _extract_and_save(plain, html_content, args, dtype, brand, '浏览器接管') == 0:
                                return 0
            else:
                print(f"  [浏览器接管] 自动执行失败: {result.stderr}")
        except Exception as e:
            print(f"  [浏览器接管] 自动执行异常: {e}")
    
    # 如果自动执行失败，输出SOP供AI手动执行
    print_browser_guide(brand, args.model, args.url, dtype)
    return 2  # 退出码2=需浏览器接管


def _guess_brand(plain):
    for brand in ('视清', 'COOLENS', '海康', 'Hikrobot', '大恒', '华睿', 'OPT', 'CCS'):
        if brand in plain:
            return {'视清': '视清科技', 'COOLENS': '视清科技'}.get(brand, brand)
    return ''


# ======================================================================
# 3. add 入库（带强校验）
# ======================================================================
def validate_entry(category, entry):
    """入库前强校验，返回错误列表"""
    errors = []
    if not entry.get('model'):
        errors.append("缺少 model（型号）")
    if not entry.get('verification_url'):
        errors.append("缺少 verification_url（官网来源链接）——没有来源的参数不允许入库")
    for field in REQUIRED_FIELDS[category]:
        v = entry.get(field)
        # 倍率待确认的镜头（有magnification_note）允许magnification为空
        if field == 'magnification' and v is None and entry.get('magnification_note'):
            continue
        if v is None or v == '' or (isinstance(v, dict) and not v):
            errors.append(f"缺少必需字段 {field}")
    # 数值合法性
    if category == 'lenses':
        mag = entry.get('magnification')
        if mag is None:
            # 倍率待确认的条目（如DTCM110-56-AL）允许存在，但新入库的草稿必须带倍率
            if not entry.get('magnification_note'):
                errors.append("镜头 magnification 必须提供"
                              "（倍率未确认且无 magnification_note 的镜头无法参与自动选型）")
        elif not (isinstance(mag, (int, float)) and 0 < float(mag) <= 20):
            errors.append(f"magnification={mag} 不合法（应为0~20的数值）")
        d = entry.get('supported_sensor_diameter')
        if d is not None and not (isinstance(d, (int, float)) and 3 <= float(d) <= 60):
            errors.append(f"supported_sensor_diameter={d} 不合法（像圆直径应为3~60mm）")
        wd = entry.get('working_distance')
        if wd is not None and not (isinstance(wd, (int, float)) and float(wd) > 0):
            errors.append(f"working_distance={wd} 不合法")
        # 型号数字与倍率一致性提示（仅提示不阻断：DTCM110-64H实为0.259x，型号数字≠倍率）
        if isinstance(mag, (int, float)) and entry.get('model'):
            m = re.search(r'(\d{2})H?', entry['model'].split('-')[1] if '-' in entry['model'] else '')
            # 不做硬校验，仅记录提醒
    if category == 'cameras':
        res = entry.get('resolution') or {}
        if not (isinstance(res, dict) and res.get('width', 0) > 0 and res.get('height', 0) > 0):
            errors.append("resolution 需为 {width, height} 且大于0")
        ps = entry.get('pixel_size')
        if ps is not None and not (0.5 <= float(ps) <= 30):
            errors.append(f"pixel_size={ps} 不合法（0.5~30μm）")
    return errors


def cmd_add(args):
    # --html 模式：从浏览器导出的渲染后页面提取参数（识别层固化）
    if args.html:
        if not args.url:
            print("--html 模式必须同时给 --url（详情页网址，作为verification_url来源）")
            return 1
        with open(args.html, 'r', encoding='utf-8', errors='ignore') as f:
            html_raw = f.read()
        plain = html_to_plain(html_raw)
        dtype = args.type or 'lens'
        if dtype == 'lens':
            params = extract_lens_params(plain, model=args.model, html=html_raw)
            category = 'lenses'
        else:
            params = extract_camera_params(plain)
            category = 'cameras' if dtype == 'camera' else 'light_sources'
        found = {k: v for k, v in params.items() if v is not None and v}
        entry = {
            'brand': args.brand or '',
            'model': args.model or '',
            'verified': False,
            'verification_url': args.url,
            'auto_imported': True,
            'source': 'browser_page',
            'verification_note': '浏览器页面提取，参数需复核后 verify',
        }
        if dtype == 'lens':
            entry['type'] = args.lens_type or '物方远心镜头'
            entry['mount'] = 'C-Mount'
            if found.get('supported_sensor_diameter'):
                d = found['supported_sensor_diameter']
                entry['supported_sensor_size'] = DIAMETER_TO_SIZE.get(d, f'Φ{d}mm')
        entry.update(found)
        missing = [k for k in REQUIRED_FIELDS[category] if not entry.get(k)]
        payload = {'category': category, 'entry': entry}
        out = args.draft or f"draft_{args.model or 'import'}.json"
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"  从页面提取到: {found}")
        if missing:
            print(f"  ⚠ 缺少字段 {missing}，草稿已保存 {out}，请人工补齐缺失字段后 add")
        else:
            print(f"  草稿已保存: {out}，可直接 add 入库")
        # 字段齐全时直接入库
        if not missing and not args.draft_only:
            args.draft = out
            args.force = False
            args.overwrite = args.overwrite
            return _add_items(args, payload)
        return 0

    with open(args.draft, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    return _add_items(args, payload)


def _add_items(args, payload):
    """草稿→数据库（去重+强校验+备份）"""
    items = payload.get('entries') or [payload]
    db = load_db(args.db)
    added, skipped = 0, 0

    for item in items:
        category = item.get('category')
        entry = item.get('entry') or {k: v for k, v in item.items()
                                      if k not in ('category',)}
        if category not in REQUIRED_FIELDS:
            print(f"  ✗ 未知类别 {category}（应为 cameras/lenses/light_sources）")
            skipped += 1
            continue

        errors = validate_entry(category, entry)
        if errors and not args.force:
            print(f"  ✗ {entry.get('model')}: 校验未通过，未入库：")
            for e in errors:
                print(f"      - {e}")
            print(f"      {REQUIRED_HINTS[category]}")
            skipped += 1
            continue
        if errors and args.force:
            print(f"  ⚠ {entry.get('model')}: 带 --force 入库，但存在校验问题：{errors}")

        existing = [e for e in db[category] if e.get('model') == entry['model']]
        if existing:
            if args.overwrite:
                db[category].remove(existing[0])
                print(f"  ↻ 覆盖已有条目 {entry['model']}")
            else:
                print(f"  - {entry['model']} 已存在（--overwrite 可覆盖），跳过")
                skipped += 1
                continue

        entry.setdefault('verified', False)
        entry.setdefault('auto_imported', True)
        entry.setdefault('verification_note', '脚本入库，复核后请执行 verify')
        entry.setdefault('created_at', datetime.now().isoformat())
        db[category].append(entry)
        added += 1
        print(f"  ✓ 已入库 {category}/{entry['model']} (verified=false, "
              f"来源: {entry.get('verification_url', '')[:60]})")

    if added:
        save_db(db, args.db)
    print(f"完成: 新增{added}, 跳过{skipped}")
    return 0


# ======================================================================
# 4. verify 复核置真
# ======================================================================
def cmd_verify(args):
    db = load_db(args.db)
    found = 0
    for category in REQUIRED_FIELDS:
        for entry in db[category]:
            if entry.get('model') == args.model:
                entry['verified'] = True
                entry['verified_at'] = datetime.now().isoformat()
                entry.pop('verification_note', None)
                found += 1
                print(f"  ✓ {category}/{args.model} → verified=true")
    if found:
        save_db(db, args.db)
    else:
        print(f"  未找到型号 {args.model}")
        return 1
    return 0


# ======================================================================
# 5. check-db 库一致性校验 + 数据新鲜度审计
# ======================================================================
DEFAULT_FRESHNESS_DAYS = 180


def _entry_age_days(entry):
    """条目距上次核验的天数（verified_at优先，其次created_at）"""
    from datetime import datetime as _dt
    stamp = entry.get('verified_at') or entry.get('created_at')
    if not stamp:
        return None
    try:
        dt = _dt.fromisoformat(stamp)
        return (_dt.now() - dt).days
    except ValueError:
        return None


def cmd_check_db(args):
    db = load_db(args.db)
    problems = []
    stale = []
    seen = {}
    for category in REQUIRED_FIELDS:
        for entry in db.get(category, []):
            model = entry.get('model', '?')
            key = (category, model)
            if key in seen:
                problems.append(f"重复条目: {category}/{model}")
            seen[key] = True
            for e in validate_entry(category, entry):
                # 已有库条目放宽：只警告缺来源
                problems.append(f"{category}/{model}: {e}")
            if entry.get('image_path') and not os.path.exists(
                    os.path.join(SKILL_DIR, entry['image_path'])):
                problems.append(f"{category}/{model}: image_path 不存在 {entry['image_path']}")
            # 数据新鲜度审计：官网参数可能变化，超龄条目提示重核验
            age = _entry_age_days(entry)
            if entry.get('verified') and age is not None and age > args.freshness_days:
                stale.append(f"{category}/{model}: 已核验{age}天（阈值{args.freshness_days}天），"
                             f"建议 refresh 重核验: {entry.get('verification_url', '')}")

    if problems:
        print(f"数据库校验发现 {len(problems)} 个问题:")
        for p in problems:
            print(f"  ⚠ {p}")
    else:
        print("数据库校验通过：型号唯一、来源齐全、参数合法")
    if stale:
        print(f"\n数据新鲜度审计: {len(stale)} 个条目超过{args.freshness_days}天未复核"
              f"（官网参数可能已变化）:")
        for s in stale:
            print(f"  ⏰ {s}")
        print("  → refresh --model 型号 [--html 新页面.html] 重新核对并更新")
    elif not problems:
        print(f"数据新鲜度: 全部已核验条目均在{args.freshness_days}天内")
    return 0


# ======================================================================
# 6. refresh 库条目刷新（增量更新 + history留痕）
# ======================================================================
# 治理字段不参与diff（它们由流程管理，不来自官网页面）
GOVERNANCE_FIELDS = {'verified', 'verified_at', 'verification_url', 'created_at',
                     'updated_at', 'history', 'auto_imported', 'source',
                     'verification_note', 'image_path', 'brand'}
# 品牌不diff（页面上往往有歧义），型号是主键


def _find_entry(db, model):
    for category in REQUIRED_FIELDS:
        for i, entry in enumerate(db[category]):
            if entry.get('model') == model:
                return category, i, entry
    return None, None, None


def cmd_refresh(args):
    """刷新库内型号：重新从官网页面提取参数，与库内值diff，确认后更新"""
    db = load_db(args.db)
    category, idx, entry = _find_entry(db, args.model)
    if entry is None:
        print(f"库中未找到型号 {args.model}（新增请用 add）")
        return 1

    # 1) 获取新参数
    if args.html:
        with open(args.html, 'r', encoding='utf-8', errors='ignore') as f:
            html_raw = f.read()
        plain = html_to_plain(html_raw)
        source_url = args.url or entry.get('verification_url', '')
    else:
        source_url = args.url or entry.get('verification_url', '')
        if not source_url:
            print("条目无 verification_url，请用 --url 或 --html 提供来源")
            return 1
        print(f"尝试直抓: {source_url}")
        html_raw = None
        try:
            html_raw = fetch_page(source_url)
        except Exception as e:
            print(f"  [静态快抓] 失败: {e}")
        # 无头渲染降级：静态失败或静态页面里没有该型号时（后台零窗口）
        if html_raw is None or (args.model and
                                args.model not in html_to_plain(html_raw)):
            print("  → 降级无头浏览器渲染（后台执行，无窗口）...")
            rendered = headless_render(source_url, wait_ms=args.render_ms)
            if rendered:
                html_raw = rendered
            elif html_raw is None:
                brand = entry.get('brand', '')
                print_browser_guide(brand, args.model, source_url,
                                    'lens' if category == 'lenses' else 'camera')
                return 2
        plain = html_to_plain(html_raw)

    dtype = 'lens' if category == 'lenses' else ('camera' if category == 'cameras' else 'light')
    if dtype == 'lens':
        params = extract_lens_params(plain, model=args.model, html=html_raw)
    else:
        params = extract_camera_params(plain)
    params.pop('model', None)
    fresh = {k: v for k, v in params.items() if v is not None and v != ''}
    if not fresh:
        print("未能从页面提取到参数（页面可能未含该型号数据）")
        return 1

    # 2) 与库内值diff
    print(f"\n[{args.model}] 官网参数 vs 库内参数：")
    changes = {}
    for k, v in fresh.items():
        old = entry.get(k)
        if old == v:
            print(f"  = {k}: {v}（一致）")
        else:
            changes[k] = {'old': old, 'new': v}
            print(f"  ↑ {k}: {old} → {v}")
    unchanged_expected = [k for k in entry
                          if k not in GOVERNANCE_FIELDS and k not in fresh
                          and k != 'model']
    if unchanged_expected:
        print(f"  ! 页面未提供以下库内字段（保持不变）: {unchanged_expected}")

    if not changes:
        print("\n参数无变化，库已是最新。")
        # 仍刷新核验时间戳（本轮复核过）
        if not args.dry_run:
            entry['verified_at'] = datetime.now().isoformat()
            save_db(db, args.db)
        return 0

    if args.dry_run or not args.apply:
        print("\n[预览] 确认无误后执行 refresh --model %s --apply%s 完成更新"
              % (args.model, " --html 页面.html" if args.html else ""))
        return 0

    # 3) 应用更新 + history留痕
    history = entry.setdefault('history', [])
    record = {'date': datetime.now().isoformat(), 'action': 'refresh',
              'source_url': source_url, 'changes': changes}
    history.append(record)
    for k, ch in changes.items():
        entry[k] = ch['new']
    if args.url:
        entry['verification_url'] = args.url
    entry['updated_at'] = datetime.now().isoformat()
    # 官网参数已变化 → 需重新人工复核，回退verified状态
    entry['verified'] = False
    entry['verification_note'] = 'refresh后参数有变化，请复核后重新 verify'
    save_db(db, args.db)
    print(f"\n✓ 已更新 {category}/{args.model}（{len(changes)}个字段），"
          f"verified已回退为false待复核，变更已记录history")
    print("  复核后执行: verify --model %s" % args.model)
    return 0


def main():
    parser = argparse.ArgumentParser(description='硬件数据库扩库工具')
    parser.add_argument('--db', default=DEFAULT_DB, help='数据库路径（缺省skill内置库）')
    sub = parser.add_subparsers(dest='cmd')

    g = sub.add_parser('gap', help='选型缺口报告（查证目标）')
    g.add_argument('--selection', help='选型结果JSON')
    g.add_argument('--fov', help='视野，如 63x42')
    g.add_argument('--precision', type=float, help='检测精度(mm)')
    g.add_argument('--pixel_per_precision', type=float, default=3.0)
    g.add_argument('--cycle_time', type=float, default=3)

    f = sub.add_parser('fetch',
                       help='三级通道抓取：静态快抓→无头Edge渲染(后台零窗口)→浏览器接管SOP')
    f.add_argument('--model', required=True)
    f.add_argument('--url', required=False, help='详情页URL（动态站可省略，用品牌SOP入口）')
    f.add_argument('--type', choices=['lens', 'camera', 'light'], default='lens')
    f.add_argument('--brand', help='品牌名（决定获取通道）')
    f.add_argument('--lens_type', help='镜头类型，如 物方远心镜头')
    f.add_argument('--draft', help='草稿输出路径')
    f.add_argument('--static_only', action='store_true',
                   help='禁用无头渲染，只走静态快抓')
    f.add_argument('--render_ms', type=int, default=12000,
                   help='无头渲染等待JS执行的虚拟时间预算ms（默认12000）')

    a = sub.add_parser('add', help='参数草稿入库（强校验）；支持--html从浏览器导出页提取')
    a.add_argument('--draft', help='草稿JSON路径（与--html二选一）')
    a.add_argument('--html', help='浏览器导出的渲染后页面HTML（识别参数来源）')
    a.add_argument('--url', help='详情页网址（--html模式必填，作为verification_url）')
    a.add_argument('--type', choices=['lens', 'camera', 'light'], default='lens')
    a.add_argument('--model', help='型号（--html模式必填）')
    a.add_argument('--brand', help='品牌（--html模式建议提供）')
    a.add_argument('--lens_type', help='镜头类型')
    a.add_argument('--draft_only', action='store_true', help='只生成草稿不入库')
    a.add_argument('--overwrite', action='store_true')
    a.add_argument('--force', action='store_true', help='跳过校验强制入库（不推荐）')

    v = sub.add_parser('verify', help='复核确认后置verified=true')
    v.add_argument('--model', required=True)

    c = sub.add_parser('check-db', help='数据库一致性校验+数据新鲜度审计')
    c.add_argument('--freshness_days', type=int, default=DEFAULT_FRESHNESS_DAYS,
                   help='新鲜度阈值天数（默认180）')
    sub.add_parser('brands', help='品牌核验通道一览（静态快抓/浏览器接管SOP）')

    r = sub.add_parser('refresh', help='刷新库内型号（重取官网参数diff更新，留history）')
    r.add_argument('--model', required=True)
    r.add_argument('--html', help='浏览器导出的最新页面HTML（动态站用）')
    r.add_argument('--url', help='新的详情页网址（型号页地址变化时用）')
    r.add_argument('--apply', action='store_true', help='确认diff后应用更新（缺省仅预览）')
    r.add_argument('--dry_run', action='store_true', help='只预览不写任何状态')
    r.add_argument('--render_ms', type=int, default=12000,
                   help='无头渲染等待JS执行的虚拟时间预算ms（默认12000）')

    args = parser.parse_args()
    if args.cmd == 'gap':
        sys.exit(cmd_gap(args))
    elif args.cmd == 'fetch':
        sys.exit(cmd_fetch(args))
    elif args.cmd == 'add':
        sys.exit(cmd_add(args))
    elif args.cmd == 'verify':
        sys.exit(cmd_verify(args))
    elif args.cmd == 'check-db':
        sys.exit(cmd_check_db(args))
    elif args.cmd == 'brands':
        sys.exit(cmd_brands(args))
    elif args.cmd == 'refresh':
        sys.exit(cmd_refresh(args))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
