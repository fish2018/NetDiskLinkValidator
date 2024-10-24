import httpx
import json
import re
import asyncio

async def check_aliyun(share_id):
    api_url = "https://api.aliyundrive.com/adrive/v3/share_link/get_share_by_anonymous"
    headers = {"Content-Type": "application/json"}
    data = json.dumps({"share_id": share_id})
    async with httpx.AsyncClient() as client:
        response = await client.post(api_url, headers=headers, data=data)
        response_json = response.json()
        if response_json.get('has_pwd'):
            return True
        if response_json.get('code') == 'NotFound.ShareLink':
            return False
        if not response_json.get('file_infos'):
            return False
        return True

async def check_115(share_id):
    api_url = "https://webapi.115.com/share/snap"
    params = {"share_code": share_id, "receive_code": ""}
    async with httpx.AsyncClient() as client:
        response = await client.get(api_url, params=params)
        response_json = response.json()
        if response_json.get('state'):
            return True
        elif '请输入访问码' in response_json.get('error', ''):
            return True
        return False

async def check_quark(share_id):
    api_url = "https://drive.quark.cn/1/clouddrive/share/sharepage/token"
    headers = {"Content-Type": "application/json"}
    data = json.dumps({"pwd_id": share_id, "passcode": ""})
    async with httpx.AsyncClient() as client:
        response = await client.post(api_url, headers=headers, data=data)
        response_json = response.json()
        # print(response_json)
        if response_json.get('message') == "ok":
            token = response_json.get('data', {}).get('stoken')
            if not token:
                return False
            detail_url = f"https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail?pwd_id={share_id}&stoken={token}&_fetch_share=1"
            detail_response = await client.get(detail_url)
            detail_response_json = detail_response.json()
            if detail_response_json.get('status') == 400:
                '''忽略非法token情况，判断为有效'''
                return True
            if detail_response_json.get('data', {}).get('share', {}).get('status') == 1:
                return True
            else:
                return False
        elif response_json.get('message') == "需要提取码":
            return True
        return False

def extract_share_id(url):
    if "aliyundrive.com" in url or "alipan.com" in url:
        pattern = r"https?://[^\s]+/s/([a-zA-Z0-9]+)"
    elif "pan.quark.cn" in url:
        pattern = r"https?://[^\s]+/s/([a-zA-Z0-9]+)"
    elif "115.com" in url:
        pattern = r"https?://[^\s]+/s/([a-zA-Z0-9]+)"
    else:
        return None

    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None

async def check_url(url):
    share_id = extract_share_id(url)
    if not share_id:
        print(f"无法识别的链接或网盘服务: {url}")
        return url, False
    if "aliyundrive.com" in url or "alipan.com" in url:
        result = await check_aliyun(share_id)
        # print(f"阿里云链接有效性: {url} - {'有效' if result else '无效'}")
        return url, result
    elif "pan.quark.cn" in url:
        result = await check_quark(share_id)
        # print(f"夸克链接有效性: {url} - {'有效' if result else '无效'}")
        return url, result
    elif "115.com" in url:
        result = await check_115(share_id)
        # print(f"115链接有效性: {url} - {'有效' if result else '无效'}")
        return url, result

async def main(urls):
    tasks = [check_url(url) for url in urls]
    results = await asyncio.gather(*tasks)
    for url, result in results:
        print(f"{url} - {'有效' if result else '无效'}")
    return results

if __name__ == "__main__":
    urls = [
        'https://www.aliyundrive.com/s/hz1HHxhahsE', # aliyundrive 公开分享
        'https://www.alipan.com/s/QbaHJ71QjV1', # alipan 公开分享
        'https://www.alipan.com/s/GMrv1QCZhNB',  # 带提取码
        'https://www.aliyundrive.com/s/p51zbVtgmy', # 链接错误 NotFound.ShareLink
        'https://www.aliyundrive.com/s/hZnj4qLMMd9',  # 空文件
        'https://115.com/s/swhsaua36a1?password=oc92',  # 带访问码
        'https://115.com/s/sw313r03zx1',  # 分享的文件涉嫌违规，链接已失效
        'https://pan.quark.cn/s/9803af406f13',  # 公开分享
        'https://pan.quark.cn/s/f161a5364657',  # 提取码
        'https://pan.quark.cn/s/9803af406f15',  # 分享不存在
        'https://pan.quark.cn/s/b999385c0936',  # 违规
        'https://pan.quark.cn/s/c66f71b6f7d5',  # 取消分享
    ]
    results = asyncio.run(main(urls))
