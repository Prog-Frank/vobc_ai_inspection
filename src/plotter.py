"""
VOBC日志数据绘制模块
- 使用 Matplotlib 绘制曲线图
- 支持单字段和多字段对比
- 生成 PNG 图片返回给前端
"""

import io
import base64
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt
from matplotlib import rcParams
from datetime import datetime

# 设置中文支持
rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
rcParams['axes.unicode_minus'] = False


class DataPlotter:
    """数据绘制器"""
    
    @staticmethod
    def plot_time_series(data_list, fields, title="数据趋势图"):
        """
        绘制时间序列曲线图
        
        Args:
            data_list: 日志数据列表，每个元素是一个字典
            fields: 要绘制的字段列表
            title: 图表标题
        
        Returns:
            base64 编码的 PNG 图片
        """
        if not data_list or not fields:
            return None
        
        # 准备数据
        timestamps = []
        field_data = {field: [] for field in fields}
        
        for idx, record in enumerate(data_list):
            # 使用索引作为时间轴（或使用实际时间）
            timestamps.append(idx)
            
            for field in fields:
                value = record.get(field, "")
                # 尝试转换为数值
                try:
                    num_value = float(value)
                except (ValueError, TypeError):
                    num_value = None
                field_data[field].append(num_value)
        
        # 创建画布
        plt.figure(figsize=(12, 6), dpi=100)
        
        # 为每个字段绘制曲线
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', 
                  '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
                  '#bcbd22', '#17becf']
        
        for i, field in enumerate(fields):
            data = field_data[field]
            # 过滤 None 值
            valid_indices = [j for j, v in enumerate(data) if v is not None]
            valid_x = [timestamps[j] for j in valid_indices]
            valid_y = [data[j] for j in valid_indices]
            
            if valid_x:
                color = colors[i % len(colors)]
                plt.plot(valid_x, valid_y, label=field, color=color, 
                         linewidth=2, alpha=0.8)
        
        # 设置图表属性
        plt.title(title, fontsize=14, fontweight='bold', pad=20)
        plt.xlabel('记录序号', fontsize=12)
        plt.ylabel('数值', fontsize=12)
        plt.legend(loc='upper right', bbox_to_anchor=(1.05, 1), fontsize=10)
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        
        # 保存到缓冲区
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        
        # 转换为 base64
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        
        return img_base64
    
    @staticmethod
    def plot_histogram(data_list, field, title="数据分布直方图"):
        """
        绘制直方图
        
        Args:
            data_list: 日志数据列表
            field: 要分析的字段
            title: 图表标题
        
        Returns:
            base64 编码的 PNG 图片
        """
        if not data_list:
            return None
        
        # 提取数值数据
        values = []
        for record in data_list:
            value = record.get(field, "")
            try:
                num_value = float(value)
                values.append(num_value)
            except (ValueError, TypeError):
                continue
        
        if not values:
            return None
        
        # 创建画布
        plt.figure(figsize=(10, 5), dpi=100)
        
        # 绘制直方图
        plt.hist(values, bins='auto', edgecolor='black', alpha=0.7)
        
        # 设置图表属性
        plt.title(title, fontsize=14, fontweight='bold', pad=20)
        plt.xlabel(field, fontsize=12)
        plt.ylabel('频数', fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        
        # 保存到缓冲区
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        
        # 转换为 base64
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        
        return img_base64
    
    @staticmethod
    def plot_scatter(data_list, x_field, y_field, title="散点图"):
        """
        绘制散点图
        
        Args:
            data_list: 日志数据列表
            x_field: X轴字段
            y_field: Y轴字段
            title: 图表标题
        
        Returns:
            base64 编码的 PNG 图片
        """
        if not data_list:
            return None
        
        # 提取数值数据
        x_values = []
        y_values = []
        
        for record in data_list:
            x_val = record.get(x_field, "")
            y_val = record.get(y_field, "")
            try:
                x_num = float(x_val)
                y_num = float(y_val)
                x_values.append(x_num)
                y_values.append(y_num)
            except (ValueError, TypeError):
                continue
        
        if not x_values or not y_values:
            return None
        
        # 创建画布
        plt.figure(figsize=(10, 6), dpi=100)
        
        # 绘制散点图
        plt.scatter(x_values, y_values, alpha=0.6, color='#1f77b4')
        
        # 设置图表属性
        plt.title(title, fontsize=14, fontweight='bold', pad=20)
        plt.xlabel(x_field, fontsize=12)
        plt.ylabel(y_field, fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        
        # 保存到缓冲区
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        
        # 转换为 base64
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        
        return img_base64
