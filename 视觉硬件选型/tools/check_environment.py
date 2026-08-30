#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境检查与依赖安装脚本
确保skill运行所需的环境和依赖都已就绪
"""

import subprocess
import sys
import os
import importlib
from typing import List, Tuple, Optional

class EnvironmentChecker:
    """环境检查器"""
    
    def __init__(self):
        # 必需的包
        self.required_packages = {
            'pptx': 'python-pptx',      # PPT生成
            'PIL': 'Pillow',            # 图像处理
            'numpy': 'numpy',           # 数值计算
        }
        
        # 可选的包（不影响主流程）
        self.optional_packages = {
            'easyocr': 'easyocr',       # OCR识别
        }
        
        self.checked = False
        self.all_installed = False
        
    def check_all(self, install_missing: bool = True) -> Tuple[bool, List[str]]:
        """
        检查所有依赖
        
        Args:
            install_missing: 是否自动安装缺失的依赖
            
        Returns:
            (是否全部安装, 缺失的包列表)
        """
        if self.checked:
            return self.all_installed, []
        
        print("=" * 60)
        print("环境检查")
        print("=" * 60)
        
        missing_packages = []
        missing_modules = []
        
        # 检查必需的包
        for module_name, package_name in self.required_packages.items():
            if not self._check_module(module_name):
                missing_packages.append(package_name)
                missing_modules.append(module_name)
                print(f"  [缺失] {package_name} (import {module_name})")
            else:
                print(f"  [已安装] {package_name}")
        
        # 检查可选的包
        for module_name, package_name in self.optional_packages.items():
            if not self._check_module(module_name):
                print(f"  [可选-未安装] {package_name} (OCR功能需要)")
            else:
                print(f"  [已安装] {package_name}")
        
        # 如果有缺失的必需包，自动安装
        if missing_packages and install_missing:
            print("\n" + "-" * 60)
            print("自动安装缺失的依赖...")
            print("-" * 60)
            
            success = self._install_packages(missing_packages)
            
            if success:
                print("\n所有必需依赖安装完成！")
                # 重新加载模块
                for module_name in missing_modules:
                    if module_name in sys.modules:
                        del sys.modules[module_name]
            else:
                print("\n部分依赖安装失败，请手动安装：")
                for pkg in missing_packages:
                    print(f"  pip install {pkg}")
        
        self.checked = True
        self.all_installed = len(missing_packages) == 0 or (missing_packages and install_missing)
        
        return self.all_installed, missing_packages
    
    def _check_module(self, module_name: str) -> bool:
        """检查模块是否已安装"""
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False
    
    def _install_packages(self, packages: List[str]) -> bool:
        """安装包"""
        all_success = True
        
        for package in packages:
            print(f"\n安装 {package}...")
            try:
                # 使用pip安装
                cmd = [sys.executable, "-m", "pip", "install", package, "-q"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    print(f"  ✓ {package} 安装成功")
                else:
                    print(f"  ✗ {package} 安装失败")
                    print(f"    错误: {result.stderr}")
                    all_success = False
                    
            except subprocess.TimeoutExpired:
                print(f"  ✗ {package} 安装超时")
                all_success = False
            except Exception as e:
                print(f"  ✗ {package} 安装异常: {e}")
                all_success = False
        
        return all_success
    
    def check_python_version(self) -> bool:
        """检查Python版本"""
        version = sys.version_info
        print(f"Python版本: {version.major}.{version.minor}.{version.micro}")
        
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            print("  [警告] Python版本过低，建议使用3.8+")
            return False
        
        print("  [OK] Python版本符合要求")
        return True
    
    def check_opencv(self) -> bool:
        """检查OpenCV"""
        try:
            import cv2
            print(f"OpenCV版本: {cv2.__version__}")
            return True
        except ImportError:
            print("OpenCV未安装")
            return False
    
    def get_system_info(self) -> dict:
        """获取系统信息"""
        import platform
        
        return {
            'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            'platform': platform.platform(),
            'processor': platform.processor(),
            'machine': platform.machine(),
        }
    
    def print_system_info(self):
        """打印系统信息"""
        info = self.get_system_info()
        print("\n系统信息:")
        print(f"  Python: {info['python_version']}")
        print(f"  平台: {info['platform']}")
        print(f"  处理器: {info['processor']}")


def check_environment(install_missing: bool = True) -> bool:
    """
    检查环境的便捷函数
    
    Args:
        install_missing: 是否自动安装缺失的依赖
        
    Returns:
        环境是否就绪
    """
    checker = EnvironmentChecker()
    
    # 检查Python版本
    checker.check_python_version()
    
    # 检查并安装依赖
    all_installed, missing = checker.check_all(install_missing=install_missing)
    
    if all_installed:
        print("\n" + "=" * 60)
        print("环境检查通过！")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("环境检查未通过，请手动安装缺失的包")
        print("=" * 60)
    
    return all_installed


def ensure_environment():
    """确保环境就绪（自动安装缺失依赖）"""
    return check_environment(install_missing=True)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='环境检查工具')
    parser.add_argument('--no-install', action='store_true', help='不自动安装缺失的依赖')
    parser.add_argument('--info', action='store_true', help='显示系统信息')
    
    args = parser.parse_args()
    
    checker = EnvironmentChecker()
    
    if args.info:
        checker.print_system_info()
    else:
        check_environment(install_missing=not args.no_install)