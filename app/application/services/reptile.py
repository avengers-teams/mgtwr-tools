import json
import os
import time

import httpx
import numpy as np
import pandas as pd


province_mapping = {
    '北京市': '北京', '天津市': '天津', '上海市': '上海', '重庆市': '重庆', '河北省': '河北',
    '山西省': '山西', '辽宁省': '辽宁', '吉林省': '吉林', '黑龙江省': '黑龙江', '江苏省': '江苏',
    '浙江省': '浙江', '安徽省': '安徽', '福建省': '福建', '江西省': '江西', '山东省': '山东',
    '河南省': '河南', '湖北省': '湖北', '湖南省': '湖南', '广东省': '广东', '海南省': '海南',
    '四川省': '四川', '贵州省': '贵州', '云南省': '云南', '陕西省': '陕西', '甘肃省': '甘肃',
    '青海省': '青海', '内蒙古自治区': '内蒙古', '广西壮族自治区': '广西', '西藏自治区': '西藏',
    '宁夏回族自治区': '宁夏', '新疆维吾尔自治区': '新疆'
}

DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_DELAY = 1.5


def get_timestamp():
    return int(time.time() * 1000)


def normalize_proxy_url(proxy_url):
    proxy_value = (proxy_url or "").strip()
    if not proxy_value:
        proxy_value = (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("https_proxy")
            or os.environ.get("http_proxy")
            or ""
        ).strip()
    if not proxy_value:
        return None
    if "://" not in proxy_value:
        proxy_value = f"http://{proxy_value}"
    return proxy_value


def build_proxies(proxy_url):
    normalized_proxy = normalize_proxy_url(proxy_url)
    if not normalized_proxy:
        return None
    return {
        "http://": normalized_proxy,
        "https://": normalized_proxy,
    }


def stop_aware_sleep(seconds, stop_callback=None):
    deadline = time.time() + max(seconds, 0)
    while time.time() < deadline:
        if stop_callback and stop_callback():
            raise InterruptedError("任务已终止")
        time.sleep(min(0.2, deadline - time.time()))


def make_request(params, proxy_url=None, retries=DEFAULT_RETRY_COUNT, retry_delay=DEFAULT_RETRY_DELAY,
                 progress_callback=None, stop_callback=None):
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
        'Referer': 'https://data.stats.gov.cn/easyquery.htm',
        'X-Requested-With': 'XMLHttpRequest',
    }
    proxies = build_proxies(proxy_url)
    total_attempts = max(1, retries)
    last_error = None

    for attempt in range(1, total_attempts + 1):
        if stop_callback and stop_callback():
            raise InterruptedError("任务已终止")
        try:
            response = httpx.get(
                'https://data.stats.gov.cn/easyquery.htm',
                params=params,
                headers=headers,
                verify=False,
                follow_redirects=True,
                timeout=60,
                proxies=proxies,
                trust_env=proxies is None,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= total_attempts:
                break

            retry_message = f"请求失败，第 {attempt}/{total_attempts} 次尝试未成功，准备重试: {exc}"
            if progress_callback:
                progress_callback(retry_message)
            else:
                print(retry_message)
            stop_aware_sleep(retry_delay * attempt, stop_callback=stop_callback)

    failure_message = f"Request failed after {total_attempts} attempts: {last_error}"
    if progress_callback:
        progress_callback(failure_message)
    else:
        print(failure_message)
    return None


def get_province_valuecode(proxy_url=None, progress_callback=None, stop_callback=None):
    params = {
        'm': 'getOtherWds',
        'dbcode': 'fsnd',
        'rowcode': 'zb',
        'colcode': 'sj',
        'wds': '[]',
        'k1': get_timestamp(),
    }
    data = make_request(
        params=params,
        proxy_url=proxy_url,
        progress_callback=progress_callback,
        stop_callback=stop_callback,
    )
    if not data:
        return []
    province_code = [item['code'] for item in data['returndata'][0]['nodes']]
    return [{"wdcode": "reg", "valuecode": item} for item in province_code]


def fetch_data(wds, dfwds, proxy_url=None, progress_callback=None, stop_callback=None):
    params = {
        'm': 'QueryData',
        'dbcode': 'fsnd',
        'rowcode': 'zb',
        'colcode': 'sj',
        'wds': wds,
        'dfwds': dfwds,
        'k1': get_timestamp(),
        'h': '1',
    }
    return make_request(
        params=params,
        proxy_url=proxy_url,
        progress_callback=progress_callback,
        stop_callback=stop_callback,
    )


def process_data(data, province):
    index = [item['cname'] for item in data['returndata']['wdnodes'][0]['nodes']]
    columns = [item['cname'] for item in data['returndata']['wdnodes'][2]['nodes']]
    dataset = [item['data']['data'] if item.get('data') else None for item in data['returndata']['datanodes']]
    array = np.array(dataset).reshape(len(index), len(columns))

    df = pd.DataFrame(array, columns=columns, index=index)
    df['Province'] = province
    return df


def get_data_pre(data_id, excel_path, progress_callback=None, stop_callback=None, proxy_url=None):
    def emit(message):
        if progress_callback:
            progress_callback(message)
        else:
            print(message)

    def should_stop():
        return bool(stop_callback and stop_callback())

    normalized_proxy = normalize_proxy_url(proxy_url)
    if normalized_proxy:
        emit(f"已启用代理: {normalized_proxy}")
    else:
        emit("未设置代理，使用直连或系统环境代理")

    province_dimensions = get_province_valuecode(
        proxy_url=normalized_proxy,
        progress_callback=progress_callback,
        stop_callback=stop_callback,
    )
    if not province_dimensions:
        raise RuntimeError("未获取到地区编码，无法继续爬取数据")

    frames = []
    total = len(province_dimensions)
    for index, wd in enumerate(province_dimensions, start=1):
        if should_stop():
            raise InterruptedError("任务已终止")

        province_code = wd['valuecode']
        emit(f"正在获取 {province_code} 的数据 ({index}/{total})...")
        data = fetch_data(
            json.dumps([wd]),
            json.dumps([{"wdcode": "zb", "valuecode": data_id}, {"wdcode": "sj", "valuecode": "LAST20"}]),
            proxy_url=normalized_proxy,
            progress_callback=progress_callback,
            stop_callback=stop_callback,
        )
        if not data:
            emit(f"{province_code} 数据获取失败，已跳过")
            continue

        province_name = next(
            item['cname'] for item in data['returndata']['wdnodes'][1]['nodes'] if item['code'] == province_code
        )
        frames.append(process_data(data, province_name))

    if not frames:
        raise RuntimeError("未获取到任何有效数据")

    combined_df = pd.concat(frames, axis=0).reset_index().rename(columns={'index': '指标'})
    long_format_data = combined_df.melt(id_vars=['指标', 'Province'], var_name='年份', value_name='数值')
    pivoted_data = long_format_data.pivot_table(
        index=['Province', '年份'],
        columns='指标',
        values='数值',
        aggfunc='first',
    ).reset_index()

    base_data = pd.read_excel(excel_path)
    pivoted_data['Province'] = pivoted_data['Province'].replace(province_mapping)
    pivoted_data['年份'] = pivoted_data['年份'].astype(str).str.replace('年', '', regex=False).astype(int)
    merged_data = pd.merge(base_data, pivoted_data, left_on=['省份', '年份'], right_on=['Province', '年份'], how='left')
    merged_data = merged_data.drop(columns=['Province'])
    merged_data.to_excel(excel_path, index=False)
    emit(f'数据已保存至 {excel_path}')
    return True

