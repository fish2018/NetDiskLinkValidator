import httpx
import json
import re
import asyncio
from urllib.parse import quote


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
        if response_json.get('message') == "ok":
            token = response_json.get('data', {}).get('stoken')
            if not token:
                return False
            detail_url = f"https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail?pwd_id={share_id}&stoken={quote(token)}&_fetch_share=1"
            detail_response = await client.get(detail_url)
            detail_response_json = detail_response.json()
            if detail_response_json.get('status') == 400:
                return True
            if detail_response_json.get('data', {}).get('share', {}).get('status') == 1:
                return True
            return False
        elif response_json.get('message') == "需要提取码":
            return True
        return False


async def check_123pan(share_id):
    api_url = f"https://www.123pan.com/api/share/info?shareKey={share_id}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, headers={"User-Agent": "Mozilla/5.0"})
            response_json = response.json()
            if not response_json:
                return False
            if "分享页面不存在" in response.text or response_json.get('code', -1) != 0:
                return False
            if response_json.get('data', {}).get('HasPwd', False):
                return True
            return True
    except (httpx.RequestError, json.JSONDecodeError) as e:
        return False


async def check_tianyi(share_id):
    api_url = "https://api.cloud.189.cn/open/share/getShareInfoByCodeV2.action"
    async with httpx.AsyncClient() as client:
        response = await client.post(api_url, data={"shareCode": share_id})
        text = response.text
        if any(x in text for x in ["ShareInfoNotFound", "ShareNotFound", "FileNotFound",
                                   "ShareExpiredError", "ShareAuditNotPass"]):
            return False
        if "needAccessCode" in text:
            return True
        return True


async def check_xunlei(share_id):
    token_url = "https://xluser-ssl.xunlei.com/v1/shield/captcha/init"
    headers = {"Content-Type": "application/json"}
    data = json.dumps({
        "client_id": "Xqp0kJBXWhwaTpB6",
        "device_id": "925b7631473a13716b791d7f28289cad",
        "action": "get:/drive/v1/share",
        "meta": {
            "package_name": "pan.xunlei.com",
            "client_version": "1.45.0",
            "captcha_sign": "1.fe2108ad808a74c9ac0243309242726c",
            "timestamp": "1645241033384"
        }
    })
    async with httpx.AsyncClient() as client:
        token_response = await client.post(token_url, headers=headers, data=data)
        token_json = token_response.json()
        token = token_json.get('captcha_token')
        if not token:
            return False
        api_url = f"https://api-pan.xunlei.com/drive/v1/share?share_id={share_id}"
        headers = {
            "x-captcha-token": token,
            "x-client-id": "Xqp0kJBXWhwaTpB6",
            "x-device-id": "925b7631473a13716b791d7f28289cad"
        }
        response = await client.get(api_url, headers=headers)
        text = response.text
        if any(x in text for x in ["NOT_FOUND", "SENSITIVE_RESOURCE", "EXPIRED"]):
            return False
        if "PASS_CODE_EMPTY" in text:
            return True
        return True


async def check_baidu(share_id):
    url = f"https://pan.baidu.com/s/{share_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            text = response.text

            # 无效状态
            if any(x in text for x in ["分享的文件已经被取消", "分享已过期", "你访问的页面不存在", "你所访问的页面"]):
                return False

            # 需要提取码（有效）
            if "请输入提取码" in text or "提取文件" in text:
                return True

            # 公开分享（有效）
            if "过期时间" in text or "文件列表" in text:
                return True

            # 默认未知状态（可能是反爬或异常页面）
            return False
    except httpx.RequestError as e:
        print(f"Baidu check error for {share_id}: {str(e)}")
        return False


def extract_share_id(url):
    """从链接中提取分享ID，支持多域名网盘"""
    net_disk_patterns = {
        'aliyun': {
            'domains': ['aliyundrive.com', 'alipan.com'],
            'pattern': r"https?://(?:www\.)?(?:aliyundrive|alipan)\.com/s/([a-zA-Z0-9]+)"
        },
        'quark': {
            'domains': ['pan.quark.cn'],
            'pattern': r"https?://(?:www\.)?pan\.quark\.cn/s/([a-zA-Z0-9]+)"
        },
        '115': {
            'domains': ['115.com', '115cdn.com', 'anxia.com'],
            'pattern': r"https?://(?:www\.)?(?:115|115cdn|anxia)\.com/s/([a-zA-Z0-9]+)"
        },
        '123pan': {
            'domains': ['123684.com', '123685.com', '123912.com', '123pan.com', '123pan.cn', '123592.com'],
            'pattern': r"https?://(?:www\.)?(?:123684|123685|123912|123pan|123pan\.cn|123592)\.com/s/([a-zA-Z0-9-]+)"
        },
        'tianyi': {
            'domains': ['cloud.189.cn'],
            'pattern': r"https?://cloud\.189\.cn/(?:t/|web/share\?code=)([a-zA-Z0-9]+)"
        },
        'xunlei': {
            'domains': ['pan.xunlei.com'],
            'pattern': r"https?://(?:www\.)?pan\.xunlei\.com/s/([a-zA-Z0-9-]+)"
        },
        'baidu': {
            'domains': ['pan.baidu.com', 'yun.baidu.com'],
            'pattern': r"https?://(?:[a-z]+\.)?(?:pan|yun)\.baidu\.com/(?:s/|share/init\?surl=)([a-zA-Z0-9-]+)"
        }
    }

    for net_disk, config in net_disk_patterns.items():
        if any(domain in url for domain in config['domains']):
            match = re.search(config['pattern'], url)
            if match:
                share_id = match.group(1)
                return share_id, net_disk
    return None, None


async def check_url(url):
    share_id, service = extract_share_id(url)
    if not share_id or not service:
        print(f"无法识别的链接或网盘服务: {url}")
        return url, False

    check_functions = {
        "aliyun": check_aliyun,
        "quark": check_quark,
        "115": check_115,
        "123pan": check_123pan,
        "tianyi": check_tianyi,
        "xunlei": check_xunlei,
        "baidu": check_baidu
    }

    if service in check_functions:
        result = await check_functions[service](share_id)
        return url, result
    print(f"No checker function for service: {service}")
    return url, False


async def main(urls):
    tasks = [check_url(url) for url in urls]
    results = await asyncio.gather(*tasks)
    for url, result in results:
        print(f"{url} - {'有效' if result else '无效'}")
    return results



if __name__ == "__main__":
    urls = [
        # 阿里云
        'https://www.aliyundrive.com/s/hz1HHxhahsE',  # aliyundrive 公开分享
        'https://www.alipan.com/s/QbaHJ71QjV1',  # alipan 公开分享
        'https://www.alipan.com/s/GMrv1QCZhNB',  # 带提取码
        'https://www.aliyundrive.com/s/p51zbVtgmy',  # 链接错误 NotFound.ShareLink
        'https://www.aliyundrive.com/s/hZnj4qLMMd9',  # 空文件
        # 115
        'https://115cdn.com/s/swh88n13z72?password=r9b2#',
        'https://anxia.com/s/swhm75q3z5o?password=ayss',
        'https://115.com/s/swhsaua36a1?password=oc92',  # 带访问码
        'https://115.com/s/sw313r03zx1',  # 分享的文件涉嫌违规，链接已失效
        # 夸克
        'https://pan.quark.cn/s/9803af406f13',  # 公开分享
        'https://pan.quark.cn/s/f161a5364657',  # 提取码
        'https://pan.quark.cn/s/9803af406f15',  # 分享不存在
        'https://pan.quark.cn/s/b999385c0936',  # 违规
        'https://pan.quark.cn/s/c66f71b6f7d5',  # 取消分享
        # 123
        'https://www.123pan.com/s/i4uaTd-WHn0',  # 公开分享
        'https://www.123912.com/s/U8f2Td-ZeOX',
        'https://www.123684.com/s/u9izjv-k3uWv',
        'https://www.123pan.com/s/A6cA-AKH11',  # 外链不存在
        # 天翼
        'https://cloud.189.cn/t/viy2quQzMBne',  # 公开分享
        'https://cloud.189.cn/web/share?code=UfUjiiFRbymq',  # 带密码分享长链接
        'https://cloud.189.cn/t/vENFvuVNbyqa',  # 外链不存在
        'https://cloud.189.cn/t/notexist',  # 分享不存在
        # 百度
        'https://pan.baidu.com/s/1rIcc6X7D3rVzNSqivsRejw?pwd=0w0j',  # 带提取码分享
        "https://pan.baidu.com/s/1TMhfQ5yNnlPPSGbw4RQ-LA?pwd=6j77",  # 带提取码分享
        'https://pan.baidu.com/s/1J_CUxLKqC0h3Ypg4sQV0_g',  # 无法识别
        'https://pan.baidu.com/s/1HlvGfj8qVUBym24X2I9ukA',  # 分享被和谐
        'https://pan.baidu.com/s/1cgsY10lkrPGZ-zt8oVdR_w',  # 分享已过期
        'https://pan.baidu.com/s/1R_itrvmA0ZyMMaHybg7G2Q',  # 分享已删除
        'https://pan.baidu.com/s/1hqge8hI',  # 分享链接错误
        'https://pan.baidu.com/s/1notexist',  # 分享不存在

    ]
    results = asyncio.run(main(urls))
