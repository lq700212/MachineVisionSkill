#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户资料解析脚本
从用户提供的图片、文档中提取视觉检测相关参数
"""

import json
import os
import re
from typing import Dict, List, Optional, Any

class UserDataParser:
    """用户资料解析器"""
    
    def __init__(self):
        self.supported_image_formats = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        self.supported_doc_formats = ['.pdf', '.doc', '.docx', '.txt']
        
        # 关键词模式匹配
        self.keywords = {
            'precision': [
                r'精度[要需]?求[：:]?\s*([0-9.]+)\s*(mm|μm|um)',
                r'[精测]度[：:]?\s*[≤<]?\s*([0-9.]+)\s*(mm|μm|um)',
                r'pixel\s*size[：:]?\s*([0-9.]+)\s*(mm|μm|um)',
                r'像素精度[：:]?\s*([0-9.]+)\s*(mm|μm|um)',
            ],
            'cycle_time': [
                r'节拍[要需]?求[：:]?\s*([0-9.]+)\s*(s|秒|sec)',
                r'生产节拍[：:]?\s*([0-9.]+)\s*(件/分钟|件/秒)',
                r'检测时间[：:]?\s*([0-9.]+)\s*(s|秒|sec)',
            ],
            'field_of_view': [
                r'视野[：:]?\s*([0-9.]+)\s*[x×*]\s*([0-9.]+)\s*(mm)',
                r'检测区域[：:]?\s*([0-9.]+)\s*[x×*]\s*([0-9.]+)\s*(mm)',
                r'FOV[：:]?\s*([0-9.]+)\s*[x×*]\s*([0-9.]+)\s*(mm)',
            ],
            'working_distance': [
                r'工作距离[：:]?\s*([0-9.]+)\s*(mm)',
                r'WD[：:]?\s*([0-9.]+)\s*(mm)',
                r'物距[：:]?\s*([0-9.]+)\s*(mm)',
            ],
            'resolution': [
                r'分辨率[要需]?求[：:]?\s*(\d+)\s*[x×*]\s*(\d+)',
                r'相机分辨率[：:]?\s*(\d+)\s*[x×*]\s*(\d+)',
            ],
            'fly_shooting': [
                r'飞拍',
                r'运动中拍照',
                r'不停',
                r'流水线',
                r'移动中',
                r'传送带',
                r'conveyor',
                r'moving',
                r'fly.*shot',
            ],
            'conveyor_speed': [
                r'速度[：:]?\s*([0-9.]+)\s*(mm/s|mm/秒|m/s|m/秒)',
                r'流水线速度[：:]?\s*([0-9.]+)\s*(mm/s|mm/秒|m/s|m/秒)',
                r'传送带速度[：:]?\s*([0-9.]+)\s*(mm/s|mm/秒|m/s|m/秒)',
                r'移动速度[：:]?\s*([0-9.]+)\s*(mm/s|mm/秒|m/s|m/秒)',
            ],
        }
    
    def parse_files(self, file_paths: List[str]) -> Dict:
        """
        解析用户提供的文件
        
        Args:
            file_paths: 文件路径列表
            
        Returns:
            解析出的参数字典
        """
        result = {
            'project_name': '视觉检测项目',
            'raw_text': '',
            'parsed_params': {}
        }
        
        all_text = ""
        
        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"  警告: 文件不存在 - {file_path}")
                continue
            
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext in self.supported_image_formats:
                # 图片文件 - 提取OCR文本（这里简化处理，实际应调用OCR）
                print(f"  处理图片: {os.path.basename(file_path)}")
                text = self._extract_text_from_image(file_path)
                all_text += text + "\n"
                
            elif file_ext in self.supported_doc_formats:
                # 文档文件
                print(f"  处理文档: {os.path.basename(file_path)}")
                text = self._extract_text_from_document(file_path)
                all_text += text + "\n"
                
            elif file_ext == '.json':
                # JSON配置文件
                print(f"  处理配置: {os.path.basename(file_path)}")
                config = self._parse_json_config(file_path)
                result['parsed_params'].update(config)
        
        result['raw_text'] = all_text
        
        # 从文本中提取参数
        if all_text:
            extracted_params = self._extract_params_from_text(all_text)
            result['parsed_params'].update(extracted_params)
        
        # 提取项目名称
        if 'project_name' not in result['parsed_params']:
            result['parsed_params']['project_name'] = self._extract_project_name(all_text)
        
        print(f"  成功提取 {len(result['parsed_params'])} 个参数")
        
        return result['parsed_params']
    
    def _extract_text_from_image(self, image_path: str) -> str:
        """
        从图片中提取文本
        使用EasyOCR进行文字识别
        """
        try:
            import easyocr
            import numpy as np
            from PIL import Image
            
            # 初始化OCR读取器（中文+英文）
            if not hasattr(self, '_ocr_reader'):
                print("    初始化OCR引擎（首次运行需下载模型，请稍候）...")
                self._ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
            
            # 读取图片
            print(f"    正在识别图片文字...")
            results = self._ocr_reader.readtext(image_path)
            
            # 提取识别结果
            text_parts = []
            for (bbox, text, confidence) in results:
                if confidence > 0.3:  # 过滤低置信度结果
                    text_parts.append(text)
            
            text = '\n'.join(text_parts)
            print(f"    OCR识别完成，识别到 {len(text_parts)} 段文字")
            
            return text
            
        except ImportError:
            print("    [警告] EasyOCR未安装，无法进行图片OCR")
            print("    安装命令: pip install easyocr")
            return ""
        except Exception as e:
            print(f"    [错误] OCR识别失败: {e}")
            return ""
    
    def _extract_text_from_document(self, doc_path: str) -> str:
        """从文档中提取文本"""
        file_ext = os.path.splitext(doc_path)[1].lower()
        
        try:
            if file_ext == '.txt':
                with open(doc_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
                    
            elif file_ext == '.pdf':
                return self._extract_from_pdf(doc_path)
                
            elif file_ext in ['.doc', '.docx']:
                return self._extract_from_word(doc_path)
                
        except Exception as e:
            print(f"    提取文档文本失败: {e}")
        
        return ""
    
    def _extract_from_pdf(self, pdf_path: str) -> str:
        """从PDF提取文本"""
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return text
        except ImportError:
            print("    注意: 需要安装PyPDF2库: pip install PyPDF2")
        except Exception as e:
            print(f"    PDF提取失败: {e}")
        return ""
    
    def _extract_from_word(self, doc_path: str) -> str:
        """从Word文档提取文本"""
        try:
            from docx import Document
            doc = Document(doc_path)
            text = "\n".join([para.text for para in doc.paragraphs])
            return text
        except ImportError:
            print("    注意: 需要安装python-docx库: pip install python-docx")
        except Exception as e:
            print(f"    Word提取失败: {e}")
        return ""
    
    def _parse_json_config(self, json_path: str) -> Dict:
        """解析JSON配置文件"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"    JSON解析失败: {e}")
            return {}
    
    def _extract_params_from_text(self, text: str) -> Dict:
        """从文本中提取参数"""
        params = {}

        # 提取检测类型（"尺寸测量"等关键词 → 远心优先分层选型的依据；
        # 判定条件单点在 precision_calculator.is_measurement_scene）
        detection_type = self._extract_detection_type(text)
        if detection_type:
            params['detection_type'] = detection_type

        # 提取像素精度（用户明说"像素精度X mm/pixel"的像素级口径，必须先于设备精度提取，
        # 否则会被 _extract_precision 的"精度"正则误抓成 precision_requirement，差3倍导致无解死循环）
        pixel_precision = self._extract_pixel_precision(text)
        if pixel_precision:
            params['pixel_precision'] = pixel_precision

        # 提取精度要求
        precision = self._extract_precision(text)
        if precision:
            params['precision_requirement'] = precision

        # 提取图纸公差（±X，如 38.50±0.25；无明确精度时按公差/10反推）
        tolerance = self._extract_tolerance(text)
        if tolerance is not None:
            params['tolerance'] = tolerance

        # 提取节拍要求
        cycle_time = self._extract_cycle_time(text)
        if cycle_time:
            params['cycle_time'] = cycle_time
        
        # 提取检测区域（"检测区域"前缀 → detection_area，系统自动加余量）
        area = self._extract_detection_area(text)
        if area:
            params['detection_area'] = f"{area['width']}x{area['height']}"

        # 提取视野范围（"视野/FOV"前缀 → field_of_view，最终视野不加余量）
        fov = self._extract_field_of_view(text)
        if fov:
            params['field_of_view'] = fov
        
        # 提取工作距离
        wd = self._extract_working_distance(text)
        if wd:
            params['working_distance'] = wd
        
        # 提取分辨率要求
        resolution = self._extract_resolution(text)
        if resolution:
            params['resolution_requirement'] = resolution
        
        # 识别飞拍场景
        fly_shooting_keywords = self.keywords.get('fly_shooting', [])
        for keyword in fly_shooting_keywords:
            if keyword in text:
                params['is_fly_shooting'] = True
                break
        
        # 提取流水线速度（如果提供）
        conveyor_speed = self._extract_conveyor_speed(text)
        if conveyor_speed:
            params['conveyor_speed'] = conveyor_speed
        
        # 提取检测项目
        detection_items = self._extract_detection_items(text)
        if detection_items:
            params['detection_items'] = detection_items
        
        return params
    
    def _extract_detection_type(self, text: str) -> Optional[str]:
        """提取检测类型：识别"尺寸测量"场景（决定远心优先分层选型是否启用）。

        关键词必须是明确的测量意图表述，避免被"检测区域"这类几何描述误伤；
        未命中返回 None（非测量场景按普通选型，不做远心优先分层）。
        """
        measurement_keywords = [
            '尺寸测量', '尺寸检测', '检测尺寸', '测量尺寸', '精密测量',
            '测量精度', '高精度测量', '量测', '长度测量', '宽度测量',
            '高度测量', '厚度测量', '直径测量', '孔径测量', '外径测量',
            '位置度测量', '轮廓测量',
        ]
        for keyword in measurement_keywords:
            if keyword in text:
                return '尺寸测量'
        return None

    def _extract_tolerance(self, text: str) -> Optional[float]:
        """提取图纸公差（±X 形式，如 38.50±0.25 / ±0.25mm；系统按公差/10反推精度）"""
        match = re.search(r'±\s*([0-9]+(?:\.[0-9]+)?)', text)
        if match:
            value = float(match.group(1))
            if value > 0:
                return value
        return None

    def _extract_pixel_precision(self, text: str) -> Optional[float]:
        """提取像素级口径（用户明说"像素精度X mm/pixel"才命中）。
        返回 mm/pixel 数值；脚本链按 ×亚像素因子 换算等效设备精度。"""
        patterns = [
            r'像素精度[：:]?\s*[≤<]?\s*([0-9.]+)\s*(mm|μm|um)\s*(?:/\s*(?:pixel|px|像素))?',
            r'([0-9.]+)\s*(mm|μm|um)\s*/\s*(?:pixel|px|像素)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                unit = match.group(2).lower()
                if unit in ['μm', 'um']:
                    value = value / 1000
                if value > 0:
                    return value
        return None

    def _extract_precision(self, text: str) -> Optional[float]:
        """提取精度要求（设备检测精度口径；带"像素"前缀的由 _extract_pixel_precision 处理，
        此处用负向后行断言排除，防止把像素精度误抓成设备精度）"""
        patterns = [
            r'(?<!像素)精度[要需]?求[：:]?\s*[≤<]?\s*([0-9.]+)\s*(mm|μm|um)',
            r'(?<!像素)[精测]度[：:]?\s*[≤<]?\s*([0-9.]+)\s*(mm|μm|um)',
            r'设备精度[：:]?\s*[≤<]?\s*([0-9.]+)\s*(mm|μm|um)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                unit = match.group(2).lower()
                
                # 统一转换为mm
                if unit in ['μm', 'um']:
                    value = value / 1000
                
                return value
        
        return None
    
    def _extract_cycle_time(self, text: str) -> Optional[float]:
        """提取节拍要求"""
        patterns = [
            r'节拍(?:要求)?[：:]?\s*[≤<]?\s*([0-9.]+)\s*(s|秒|sec)',
            r'检测时间[：:]?\s*[≤<]?\s*([0-9.]+)\s*(s|秒|sec)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        
        return None
    
    def _extract_field_of_view(self, text: str) -> Optional[Dict]:
        """提取视野范围"""
        patterns = [
            r'视野[：:]?\s*([0-9.]+)\s*[x×*]\s*([0-9.]+)\s*(mm)',
            r'FOV[：:]?\s*([0-9.]+)\s*[x×*]\s*([0-9.]+)\s*(mm)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return {
                    'width': float(match.group(1)),
                    'height': float(match.group(2)),
                    'unit': 'mm'
                }

        return None

    def _extract_detection_area(self, text: str) -> Optional[Dict]:
        """提取检测区域（区别于最终视野：系统会加余量）"""
        pattern = r'检测区域[：:]?\s*([0-9.]+)\s*[x×*]\s*([0-9.]+)\s*(mm)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return {
                'width': float(match.group(1)),
                'height': float(match.group(2)),
                'unit': 'mm'
            }
        return None
    
    def _extract_working_distance(self, text: str) -> Optional[float]:
        """提取工作距离"""
        patterns = [
            r'工作距离[：:]?\s*([0-9.]+)\s*(mm)',
            r'WD[：:]?\s*([0-9.]+)\s*(mm)',
            r'物距[：:]?\s*([0-9.]+)\s*(mm)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        
        return None
    
    def _extract_resolution(self, text: str) -> Optional[Dict]:
        """提取分辨率要求"""
        patterns = [
            r'分辨率[要需]?求[：:]?\s*(\d+)\s*[x×*]\s*(\d+)',
            r'相机分辨率[：:]?\s*(\d+)\s*[x×*]\s*(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return {
                    'width': int(match.group(1)),
                    'height': int(match.group(2))
                }
        
        return None
    
    def _extract_conveyor_speed(self, text: str) -> Optional[float]:
        """提取流水线速度（mm/s）"""
        patterns = [
            r'速度[：:]?\s*([0-9.]+)\s*(mm/s|mm/秒|m/s|m/秒)',
            r'流水线速度[：:]?\s*([0-9.]+)\s*(mm/s|mm/秒|m/s|m/秒)',
            r'传送带速度[：:]?\s*([0-9.]+)\s*(mm/s|mm/秒|m/s|m/秒)',
            r'移动速度[：:]?\s*([0-9.]+)\s*(mm/s|mm/秒|m/s|m/秒)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                unit = match.group(2).lower()
                # 统一转换为 mm/s
                if unit in ['m/s', 'm/秒']:
                    value = value * 1000
                return value
        return None
    
    def _extract_detection_items(self, text: str) -> List[str]:
        """提取检测项目"""
        items = []
        
        # 常见检测项目关键词
        detection_keywords = [
            '尺寸检测', '间隙检测', '位置度检测', '漏装检测', '错装检测',
            '表面缺陷', '划痕检测', '凹坑检测', '污渍检测', '裂纹检测',
            '有无检测', '装配检测', '外观检测'
        ]
        
        for keyword in detection_keywords:
            if keyword in text:
                items.append(keyword)
        
        return items if items else None
    
    def _extract_project_name(self, text: str) -> str:
        """提取项目名称"""
        # 尝试从文本中提取项目名称
        patterns = [
            r'项目[名称名][：:]?\s*(.+?)(?:\n|$)',
            r'产品[名称名][：:]?\s*(.+?)(?:\n|$)',
            r'检测[对象目标][：:]?\s*(.+?)(?:\n|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:50]  # 限制长度
        
        return '视觉检测项目'


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='用户资料解析器')
    parser.add_argument('files', nargs='+', help='要解析的文件路径')
    parser.add_argument('--output', '-o', type=str, help='输出JSON文件路径')
    
    args = parser.parse_args()
    
    parser_instance = UserDataParser()
    result = parser_instance.parse_files(args.files)
    
    # 输出结果
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f"\n结果已保存到: {args.output}")
    else:
        print("\n" + "=" * 60)
        print("解析结果:")
        print("=" * 60)
        print(output_json)


if __name__ == '__main__':
    main()