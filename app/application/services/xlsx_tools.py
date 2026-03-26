import pandas as pd
from app.core.urltools import get_resource_path


def get_province_in_base_table():
    """
    获取基础表中的省份
    :return: 省份列表
    """
    table = pd.read_excel(get_resource_path('template/provincial_latitude_longitude.xlsx'))
    return table['省份'].tolist()


def filter_out_selected_provinces(province: list, table: pd.DataFrame = None):
    """
    过滤出选中的省份
    :param table: 基础表
    :param province: 省份列表
    :return:
    """
    if table is None:
        table = pd.read_excel(get_resource_path('template/provincial_latitude_longitude.xlsx'))
    table = table[table['省份'].isin(province)]
    return table


def generate_year_for_base_table(year: list, table: pd.DataFrame = None):
    """
    为基础表生成年份列
    :param year: 年份列表
    :return:
    """
    if table is None:
        table = pd.read_excel(get_resource_path('template/provincial_latitude_longitude.xlsx'))
    year_df = pd.DataFrame(year, columns=['年份'])
    table['key'] = 1
    year_df['key'] = 1
    year_df = pd.merge(table, year_df, on='key')
    year_df.drop(columns='key', inplace=True)
    return year_df

def merge_data_to_base_table(data: pd.DataFrame, table: pd.DataFrame, on: list):
    """
    将数据合并到基础表
    :param data: 数据
    :param table: 基础表
    :param on: 合并的列
    :return:
    """
    return pd.merge(table, data, on=on, how='left')



def save_table_to_excel(table: pd.DataFrame, path: str, index=False):
    """
    保存表格到Excel
    :param table: 表格
    :param path: 保存路径
    :param index: 是否保存索引
    :return:
    """
    table.to_excel(path, index=index)
    print(f'数据已保存至{path}')
    return True

