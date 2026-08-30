#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建示例相机图片脚本
用于生成各型号相机的示例图片
"""

import os
from PIL import Image, ImageDraw, ImageFont

def create_camera_image(camera_model: str, output_path: str, width: int = 400, height: int = 300):
    """
    创建相机示例图片
    
    Args:
        camera_model: 相机型号
        output_path: 输出路径
        width: 图片宽度
        height: 图片高度
    """
    # 创建图片
    img = Image.new('RGB', (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    
    # 绘制相机轮廓
    # 相机主体
    camera_left = width // 4
    camera_top = height // 4
    camera_right = width * 3 // 4
    camera_bottom = height * 3 // 4
    
    # 绘制相机主体
    draw.rectangle([camera_left, camera_top, camera_right, camera_bottom], 
                   fill=(60, 60, 60), outline=(30, 30, 30), width=2)
    
    # 绘制镜头
    lens_center_x = width // 2
    lens_center_y = height // 2
    lens_radius = min(width, height) // 6
    
    # 镜头外圈
    draw.ellipse([lens_center_x - lens_radius - 10, lens_center_y - lens_radius - 10,
                  lens_center_x + lens_radius + 10, lens_center_y + lens_radius + 10],
                 fill=(40, 40, 40), outline=(20, 20, 20), width=2)
    
    # 镜头内圈
    draw.ellipse([lens_center_x - lens_radius, lens_center_y - lens_radius,
                  lens_center_x + lens_radius, lens_center_y + lens_radius],
                 fill=(100, 100, 100), outline=(50, 50, 50), width=2)
    
    # 镜头中心
    draw.ellipse([lens_center_x - lens_radius // 2, lens_center_y - lens_radius // 2,
                  lens_center_x + lens_radius // 2, lens_center_y + lens_radius // 2],
                 fill=(150, 150, 150), outline=(80, 80, 80), width=1)
    
    # 绘制指示灯
    draw.ellipse([camera_left + 10, camera_bottom - 15, camera_left + 20, camera_bottom - 5],
                 fill=(0, 200, 0), outline=(0, 150, 0))
    
    # 添加型号文字
    try:
        # 尝试使用系统字体
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        # 如果没有系统字体，使用默认字体
        font = ImageFont.load_default()
    
    # 绘制型号文字
    text = camera_model
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    text_x = (width - text_width) // 2
    text_y = camera_bottom + 10
    
    draw.text((text_x, text_y), text, fill=(0, 0, 0), font=font)
    
    # 保存图片
    img.save(output_path, 'PNG')
    print(f"已创建图片: {output_path}")

def main():
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    images_dir = os.path.join(skill_dir, 'images')
    
    # 确保images目录存在
    os.makedirs(images_dir, exist_ok=True)
    
    # 定义要创建的相机图片
    camera_images = [
        ('MV-CS050-10GM', 'MV-CS050-10GM.png'),
        ('MV-CS200-10GM', 'MV-CS200-10GM.png'),
        ('MV-CS120-10GM V5', 'MV-CS120-10GM V5.png'),  # 注意文件名有空格
    ]
    
    # 创建所有相机图片（只创建不存在的，不覆盖已有图片）
    created_count = 0
    for model, filename in camera_images:
        output_path = os.path.join(images_dir, filename)
        if os.path.exists(output_path):
            print(f"  跳过（已存在）: {filename}")
        else:
            create_camera_image(model, output_path)
            created_count += 1
    
    print(f"\n图片处理完成！")
    print(f"图片目录: {images_dir}")
    print(f"新创建 {created_count} 张图片（跳过已存在的）")

if __name__ == '__main__':
    main()