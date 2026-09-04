#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
浏览器接管SOP执行脚本 - 模拟人工操作版
后台静默执行，模拟真实用户浏览器行为
"""

import sys
import os
import tempfile
import time
import re
import random

def simulate_human_behavior(page):
    """模拟人工浏览器行为"""
    # 随机延迟，模拟人工操作
    time.sleep(random.uniform(1, 3))
    
    # 随机滚动页面
    scroll_height = random.randint(300, 800)
    page.evaluate(f"window.scrollBy(0, {scroll_height})")
    time.sleep(random.uniform(0.5, 1.5))
    
    # 随机移动鼠标
    x = random.randint(100, 800)
    y = random.randint(100, 600)
    page.mouse.move(x, y)
    time.sleep(random.uniform(0.3, 0.8))

def search_product_with_browser(model, brand='海康威视', headless=True):
    """
    模拟人工打开浏览器搜索产品
    
    Args:
        model: 产品型号
        brand: 品牌名称
        headless: 是否后台静默执行
    
    Returns:
        HTML文件路径 或 None
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[错误] playwright未安装，请运行: pip install playwright")
        return None
    
    print(f"[浏览器接管] 品牌: {brand}")
    print(f"[浏览器接管] 型号: {model}")
    print(f"[浏览器接管] 模式: {'后台静默' if headless else '前台显示'}")
    
    with sync_playwright() as p:
        # 启动浏览器（后台静默模式）
        browser = p.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',  # 禁用自动化控制特征
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        
        # 创建上下文，模拟真实用户
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        
        # 添加反爬虫脚本
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)
        
        # 输出目录
        output_dir = os.path.join(tempfile.gettempdir(), 'vision_browser_output')
        os.makedirs(output_dir, exist_ok=True)
        
        # SOP步骤1：打开搜索引擎
        print(f"\n[SOP步骤1] 打开搜索引擎...")
        search_keyword = f"{brand} {model} 官网"
        
        try:
            # 模拟人工打开必应
            print(f"  模拟人工打开必应...")
            page.goto('https://www.bing.com', wait_until='networkidle', timeout=60000)
            simulate_human_behavior(page)
            
            # 模拟人工在搜索框输入关键词
            print(f"  模拟人工输入搜索关键词: {search_keyword}")
            search_box = page.locator('input[name="q"]').first
            search_box.click()
            time.sleep(random.uniform(0.5, 1))
            
            # 模拟人工逐字输入
            for char in search_keyword:
                search_box.type(char, delay=random.uniform(50, 150))
            
            time.sleep(random.uniform(0.5, 1))
            
            # 模拟人工按回车键
            print(f"  模拟人工按回车键搜索...")
            search_box.press('Enter')
            time.sleep(random.uniform(3, 5))
            
            # 截图搜索结果
            screenshot_file = os.path.join(output_dir, f'{model}_bing.png')
            page.screenshot(path=screenshot_file, full_page=True)
            print(f"  搜索结果截图: {screenshot_file}")
            
            # 从搜索结果中提取官网链接
            html_content = page.content()
            
            # 品牌域名映射
            brand_domains = {
                '海康威视': 'hikrobotics.com',
                '视清科技': 'coolens.cn',
                '华睿科技': 'irayple.com',
                '大恒图像': 'daheng-imaging.com',
                'OPT': 'optmv.com',
            }
            
            domain = brand_domains.get(brand, 'hikrobotics.com')
            print(f"  目标域名: {domain}")
            
            # 查找包含目标域名的链接
            pattern = rf'href="(https?://[^"]*{domain}[^"]*)"'
            matches = re.findall(pattern, html_content)
            
            if not matches:
                print(f"  [X] 未找到包含 {domain} 的链接")
                browser.close()
                return None
            
            print(f"  [OK] 找到 {len(matches)} 个官网链接")
            
            # 过滤出产品详情页链接
            detail_url = None
            for url in matches:
                # 排除首页、列表页等
                if any(keyword in url for keyword in ['/product', '/detail', '?id=']):
                    detail_url = url
                    print(f"  [OK] 找到产品详情页: {detail_url}")
                    break
            
            # 如果没找到，使用第一个链接
            if not detail_url and matches:
                detail_url = matches[0]
                print(f"  [OK] 使用第一个链接: {detail_url}")
            
        except Exception as e:
            print(f"  [X] 搜索失败: {e}")
            browser.close()
            return None
        
        # SOP步骤2：访问产品详情页
        print(f"\n[SOP步骤2] 访问产品详情页...")
        try:
            # 模拟人工点击链接
            print(f"  模拟人工点击产品链接...")
            page.goto(detail_url, wait_until='networkidle', timeout=60000)
            simulate_human_behavior(page)
            
            # 检查是否是产品列表页，如果是则查找具体产品链接
            html_content = page.content()
            if '产品列表' in html_content or 'PRODUCT LIST' in html_content:
                print(f"  检测到产品列表页，查找具体产品链接...")
                
                # 查找包含型号的链接
                pattern = rf'href="([^"]*)"[^>]*>[^<]*{re.escape(model)}'
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match:
                    product_url = match.group(1)
                    if not product_url.startswith('http'):
                        product_url = f"https://www.hikrobotics.com{product_url}"
                    
                    print(f"  [OK] 找到具体产品链接: {product_url}")
                    print(f"  模拟人工点击具体产品链接...")
                    page.goto(product_url, wait_until='networkidle', timeout=60000)
                    simulate_human_behavior(page)
                else:
                    print(f"  [X] 未在列表页找到具体产品链接")
            
            # SOP步骤3：尝试点击参数标签（如果存在）
            print(f"[SOP步骤3] 尝试展开参数区域...")
            try:
                # 尝试常见的参数标签
                param_selectors = [
                    'text=详细参数',
                    'text=规格参数',
                    'text=技术参数',
                    'text=产品参数',
                    '.param-tab',
                    '.spec-tab',
                ]
                
                for selector in param_selectors:
                    try:
                        param_tab = page.locator(selector).first
                        if param_tab.is_visible():
                            print(f"  模拟人工点击参数标签: {selector}")
                            param_tab.click()
                            time.sleep(random.uniform(2, 4))
                            break
                    except:
                        continue
            except:
                pass
            
            # 滚动页面触发懒加载
            print(f"  模拟人工滚动页面...")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(random.uniform(1, 2))
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(random.uniform(1, 2))
            
            # 截图详情页
            screenshot_file = os.path.join(output_dir, f'{model}_detail.png')
            page.screenshot(path=screenshot_file, full_page=True)
            print(f"  详情页截图: {screenshot_file}")
            
            # 保存HTML
            html_content = page.content()
            detail_file = os.path.join(output_dir, f'{model}.html')
            with open(detail_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"  [OK] 产品详情页已保存: {detail_file}")
            
            browser.close()
            return detail_file
            
        except Exception as e:
            print(f"  [X] 访问详情页失败: {e}")
            browser.close()
            return None

def main():
    if len(sys.argv) < 2:
        print("用法: python browser_fetch.py <型号> [品牌] [--headless]")
        print("示例:")
        print("  python browser_fetch.py MV-CA500-10GM 海康威视")
        print("  python browser_fetch.py DTCM110-64H-AL 视清科技")
        print("  python browser_fetch.py MV-CS050-10GM 海康威视 --headless")
        sys.exit(1)
    
    model = sys.argv[1]
    brand = sys.argv[2] if len(sys.argv) > 2 else '海康威视'
    headless = '--headless' in sys.argv
    
    html_file = search_product_with_browser(model, brand, headless)
    
    if html_file:
        print(f"\n{'='*60}")
        print(f"[成功] 产品详情页已获取")
        # 两种标记行都输出：database_updater 通道3按这两行解析HTML路径
        print(f"文件路径: {html_file}")
        print(f"页面已保存到: {html_file}")
        print(f"下一步执行:")
        print(f"python tools/database_updater.py add --html {html_file} \\")
        print(f"           --url <详情页网址> --type camera --model {model} --brand {brand}")
    else:
        print(f"\n{'='*60}")
        print(f"[失败] 未能获取产品详情页")
        print(f"请手动访问官网获取产品参数")
        sys.exit(2)

if __name__ == '__main__':
    main()
