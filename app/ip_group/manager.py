"""爱快IP分组管理器"""
import json
import re
import time
import hashlib
import threading
from typing import Any, List, Dict, Tuple, Optional

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from app.logger import logger


class IPGroupManager:
    """爱快IP分组管理器"""

    def __init__(self, ikuai_url: str, username: str, password: str):
        self.ikuai_url = ikuai_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = None
        self._lock = threading.Lock()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _login_ikuai(self, session: requests.Session) -> Optional[str]:
        try:
            login_url = f"{self.ikuai_url}/Action/login"
            password_md5 = hashlib.md5(self.password.encode('utf-8')).hexdigest()
            login_data = {"username": self.username, "passwd": password_md5}
            response = session.post(login_url, data=json.dumps(login_data),
                                    headers={'Content-Type': 'application/json'}, timeout=10)
            response.raise_for_status()
            cookies = response.cookies
            sess_key_value = cookies.get("sess_key")
            if sess_key_value:
                return f"sess_key={sess_key_value}"
            set_cookie_header = response.headers.get('Set-Cookie')
            if set_cookie_header:
                match = re.search(r'sess_key=([^;]+)', set_cookie_header)
                if match:
                    return f"sess_key={match.group(1)}"
            logger.error(f"登录成功但未能提取 sess_key")
            return None
        except Exception as e:
            logger.error(f"登录请求失败: {e}")
            return None

    def get_ip_blocks_from_22tool(self, province: str = "", city: str = "", isp: str = "") -> List[Dict[str, Any]]:
        """从22tool获取IP段信息"""
        try:
            url_parts = ["https://www.22tool.com/ip-block", "china"]

            province_map = {
                "北京": "beijing", "天津": "tianjin", "河北": "hebei", "山西": "shanxi",
                "内蒙古": "neimenggu", "辽宁": "liaoning", "吉林": "jilin", "黑龙江": "heilongjiang",
                "上海": "shanghai", "江苏": "jiangsu", "浙江": "zhejiang", "安徽": "anhui",
                "福建": "fujian", "江西": "jiangxi", "山东": "shandong", "河南": "henan",
                "湖北": "hubei", "湖南": "hunan", "广东": "guangdong", "广西": "guangxi",
                "海南": "hainan", "重庆": "chongqing", "四川": "sichuan", "贵州": "guizhou",
                "云南": "yunnan", "西藏": "xizang", "陕西": "shaanxi", "甘肃": "gansu",
                "青海": "qinghai", "宁夏": "ningxia", "新疆": "xinjiang",
                "台湾": "taiwan", "香港": "hongkong", "澳门": "macau",
            }

            isp_map = {"电信": "4", "联通": "10", "移动": "11", "铁通": "18", "教育网": "30", "广电": "133"}

            if province and province != "全部":
                url_parts.append(province_map.get(province, province.lower()))
            else:
                url_parts.append("all")

            if city and city != "全部":
                url_parts.append(city.lower())
            else:
                url_parts.append("all")

            if isp and isp != "全部":
                url_parts.append(isp_map.get(isp, isp))
            else:
                url_parts.append("all")

            base_url = "/".join(url_parts)
            session = self._create_session()

            all_ip_blocks = []
            page = 1
            max_pages = 10

            logger.info(f"开始获取IP段信息，搜索条件: 省份={province or '全部'}, 城市={city or '全部'}, 运营商={isp or '全部'}")

            while page <= max_pages:
                logger.info(f"正在获取第 {page} 页IP段信息...")
                page_url = base_url if page == 1 else f"{base_url}?page={page}"
                response = session.get(page_url, timeout=30)
                response.raise_for_status()
                page_ip_blocks = self._parse_ip_blocks_from_html(response.text)
                if not page_ip_blocks:
                    logger.info(f"第 {page} 页没有找到IP段信息，停止获取")
                    break
                logger.info(f"第 {page} 页获取到 {len(page_ip_blocks)} 个IP段")
                all_ip_blocks.extend(page_ip_blocks)
                if not self._has_next_page(response.text):
                    logger.info("已到达最后一页")
                    break
                page += 1
                time.sleep(1)

            logger.info(f"IP段信息获取完成，共获取到 {len(all_ip_blocks)} 个IP段")
            return all_ip_blocks
        except Exception as e:
            logger.error(f"从22tool获取IP段信息失败: {str(e)}")
            return []

    def _parse_ip_blocks_from_html(self, html_content: str) -> List[Dict[str, Any]]:
        ip_blocks = []
        try:
            table_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_content, re.DOTALL)
            for row in table_rows:
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                if len(cells) >= 6:
                    clean_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                    if len(clean_cells) >= 6:
                        ip_start, ip_end, ip_count, province_name, city_name, isp_name = clean_cells[:6]
                        if (re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_start) and
                            re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_end)):
                            ip_blocks.append({
                                'ip_start': ip_start, 'ip_end': ip_end,
                                'ip_count': int(ip_count.replace(',', '')) if ip_count.replace(',', '').isdigit() else 0,
                                'province': province_name, 'city': city_name, 'isp': isp_name
                            })
        except Exception as e:
            logger.warning(f"表格解析失败: {e}")
        return ip_blocks

    def _has_next_page(self, html_content: str) -> bool:
        return bool(re.search(r'(下一页|next)', html_content, re.IGNORECASE))

    def get_available_provinces(self) -> List[str]:
        try:
            session = self._create_session()
            response = session.get("https://www.22tool.com/ip-block", timeout=30)
            response.raise_for_status()
            provinces = []
            patterns = [
                r'<option value="([^"]+)">([^<]+)</option>',
                r'<option[^>]*value="([^"]+)"[^>]*>([^<]+)</option>',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, response.text)
                for match in matches:
                    value, name = match if isinstance(match, tuple) else (match, match)
                    if value and name and value != "全部" and name != "全部":
                        provinces.append(name.strip())
                if provinces:
                    break
            if not provinces:
                provinces = ["北京","天津","河北","山西","内蒙古","辽宁","吉林","黑龙江","上海","江苏","浙江","安徽",
                             "福建","江西","山东","河南","湖北","湖南","广东","广西","海南","重庆","四川","贵州",
                             "云南","西藏","陕西","甘肃","青海","宁夏","新疆"]
            logger.info(f"获取到 {len(provinces)} 个省份")
            return provinces
        except Exception as e:
            logger.error(f"获取省份列表失败: {str(e)}")
            return ["北京","天津","河北","山西","内蒙古","辽宁","吉林","黑龙江","上海","江苏","浙江","安徽",
                     "福建","江西","山东","河南","湖北","湖南","广东","广西","海南","重庆","四川","贵州",
                     "云南","西藏","陕西","甘肃","青海","宁夏","新疆"]

    def get_available_cities(self, province: str) -> List[str]:
        try:
            session = self._create_session()
            response = session.get("https://www.22tool.com/ip-block", params={'province': province}, timeout=30)
            response.raise_for_status()
            cities = []
            patterns = [
                r'<option value="([^"]+)">([^<]+)</option>',
                r'<option[^>]*value="([^"]+)"[^>]*>([^<]+)</option>',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, response.text)
                for match in matches:
                    value, name = match if isinstance(match, tuple) else (match, match)
                    if value and name and value != "全部" and name != "全部":
                        cities.append(name.strip())
                if cities:
                    break
            if not cities:
                default_cities = {
                    "广东": ["广州","深圳","珠海","佛山","东莞","中山"],
                    "江苏": ["南京","苏州","无锡","常州"],
                    "浙江": ["杭州","宁波","温州"],
                    "山东": ["济南","青岛","烟台"],
                    "北京": ["北京"],"上海": ["上海"],"天津": ["天津"],"重庆": ["重庆"],
                }
                cities = default_cities.get(province, [province])
            logger.info(f"为省份 {province} 获取到 {len(cities)} 个城市")
            return cities
        except Exception as e:
            logger.error(f"获取城市列表失败: {str(e)}")
            return [province] if province else []

    def get_available_isps(self) -> List[str]:
        try:
            session = self._create_session()
            response = session.get("https://www.22tool.com/ip-block", timeout=30)
            response.raise_for_status()
            isps = []
            patterns = [
                r'<option value="([^"]+)">([^<]+)</option>',
                r'<option[^>]*value="([^"]+)"[^>]*>([^<]+)</option>',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, response.text)
                for match in matches:
                    value, name = match if isinstance(match, tuple) else (match, match)
                    if value and name and value != "全部" and name != "全部":
                        isps.append(name.strip())
                if isps:
                    break
            if not isps:
                isps = ["电信","联通","移动","铁通","教育网","广电","长城宽带","鹏博士"]
            return isps
        except Exception as e:
            logger.error(f"获取运营商列表失败: {str(e)}")
            return ["电信","联通","移动","铁通","教育网","广电","长城宽带","鹏博士"]

    def create_ip_group(self, group_name: str, ip_list: List[str], address_pool: bool = False, use_new_api: bool = True) -> Tuple[bool, Optional[str]]:
        try:
            session = self._create_session()
            token = self._login_ikuai(session)
            if not token:
                return False, "登录失败"
            create_url = f"{self.ikuai_url}/Action/call"
            request_headers = {
                'Content-Type': 'application/json', 'Accept': '*/*',
                'Origin': self.ikuai_url.rstrip('/'), 'Referer': self.ikuai_url.rstrip('/') + '/'
            }
            if use_new_api:
                ip_group_data = {
                    "func_name": "route_object_ip", "action": "add",
                    "param": {"name": group_name, "ip_list": ip_list, "type": 0}
                }
            else:
                ip_group_data = {
                    "func_name": "ipgroup", "action": "add",
                    "param": {"group_name": group_name, "addr_pool": ",".join(ip_list) if ip_list else "", "newRow": True, "type": 0}
                }
            try:
                logger.info(f"正在创建IP分组: {group_name}，包含 {len(ip_list)} 个IP范围")
                response = session.post(create_url, data=json.dumps(ip_group_data), headers=request_headers, timeout=30)
                response.raise_for_status()
                res_json = response.json()
                if use_new_api and res_json.get("code") == 0 and res_json.get("message", "").lower() == "success":
                    return True, None
                if not use_new_api and res_json.get("Result") == 30000 and res_json.get("ErrMsg", "").lower() == "success":
                    return True, None
                if "success" in response.text.strip().lower():
                    return True, None
                err_msg = res_json.get("message") or res_json.get("ErrMsg") or "创建失败"
                return False, f"路由器返回错误: {err_msg}"
            except requests.exceptions.Timeout:
                return True, "请求超时，但IP分组可能已开始创建"
            except Exception as e:
                return False, str(e)
        except Exception as e:
            return False, str(e)

    def get_existing_ip_groups(self, use_new_api: bool = True) -> List[Dict[str, Any]]:
        try:
            session = self._create_session()
            token = self._login_ikuai(session)
            if not token:
                return []
            list_url = f"{self.ikuai_url}/Action/call"
            request_headers = {
                'Content-Type': 'application/json', 'Accept': '*/*',
                'Origin': self.ikuai_url.rstrip('/'), 'Referer': self.ikuai_url.rstrip('/') + '/'
            }
            if use_new_api:
                list_data = {"func_name": "route_object_ip", "action": "show", "param": {}}
            else:
                list_data = {"func_name": "ipgroup", "action": "show", "param": {"ORDER": "desc", "ORDER_BY": "time", "LIMIT": "0,50"}}
            response = session.post(list_url, data=json.dumps(list_data), headers=request_headers, timeout=15)
            response.raise_for_status()
            res_json = response.json()
            if use_new_api and res_json.get("code") == 0 and res_json.get("message", "").lower() == "success":
                return res_json.get("results", [])
            if not use_new_api and res_json.get("Result") == 30000 and res_json.get("ErrMsg", "").lower() == "success":
                data = res_json.get("Data", {})
                return data.get("data", [])
            return []
        except Exception as e:
            logger.error(f"获取IP分组列表失败: {e}")
            return []

    def delete_ip_group(self, group_name: str, use_new_api: bool = True) -> Tuple[bool, Optional[str]]:
        try:
            session = self._create_session()
            token = self._login_ikuai(session)
            if not token:
                return False, "登录失败"
            delete_url = f"{self.ikuai_url}/Action/call"
            request_headers = {
                'Content-Type': 'application/json', 'Accept': '*/*',
                'Origin': self.ikuai_url.rstrip('/'), 'Referer': self.ikuai_url.rstrip('/') + '/'
            }
            if use_new_api:
                delete_data = {"func_name": "route_object_ip", "action": "del", "param": {"name": group_name}}
            else:
                delete_data = {"func_name": "ipgroup", "action": "del", "param": {"group_name": group_name}}
            response = session.post(delete_url, data=json.dumps(delete_data), headers=request_headers, timeout=30)
            response.raise_for_status()
            res_json = response.json()
            if res_json and ((use_new_api and res_json.get("code") == 0) or (not use_new_api and res_json.get("result") == 30000)):
                return True, None
            if "success" in response.text.strip().lower():
                return True, None
            return False, "删除失败"
        except Exception as e:
            return False, str(e)

    def sync_ip_groups_from_22tool(self, province: str = "", city: str = "", isp: str = "",
                                  group_prefix: str = "22tool_", address_pool: bool = False) -> Tuple[bool, str]:
        try:
            ip_blocks = self.get_ip_blocks_from_22tool(province, city, isp)
            if not ip_blocks:
                return False, "未获取到IP段信息"

            groups = {}
            for block in ip_blocks:
                key = f"{block['province']}_{block['city']}_{block['isp']}"
                if key not in groups:
                    if not group_prefix or group_prefix.strip() == "":
                        group_name = f"{block['province']}_{block['city']}_{block['isp']}"
                    else:
                        group_name = f"{group_prefix}{block['province']}_{block['city']}_{block['isp']}"
                    groups[key] = {'name': group_name, 'ips': []}
                groups[key]['ips'].append(f"{block['ip_start']}-{block['ip_end']}")

            success_count = 0
            total_count = len(groups)

            for group_info in groups.values():
                success, error = self.create_ip_group(group_info['name'], group_info['ips'], address_pool)
                if success:
                    success_count += 1
                else:
                    logger.warning(f"创建分组 {group_info['name']} 失败: {error}")

            message = f"同步完成: 成功 {success_count}/{total_count} 个分组"
            return True, message
        except Exception as e:
            return False, f"同步IP分组失败: {str(e)}"

    def test_create_simple_ip_group(self) -> Tuple[bool, Optional[str]]:
        try:
            session = self._create_session()
            token = self._login_ikuai(session)
            if not token:
                return False, "登录失败"
            create_url = f"{self.ikuai_url}/Action/call"
            test_data = {
                "func_name": "ipgroup", "action": "add",
                "param": {"group_name": "test_group", "addr_pool": "192.168.1.1", "newRow": True, "type": 0}
            }
            request_headers = {
                'Content-Type': 'application/json', 'Accept': '*/*',
                'Origin': self.ikuai_url.rstrip('/'), 'Referer': self.ikuai_url.rstrip('/') + '/'
            }
            response = session.post(create_url, data=json.dumps(test_data), headers=request_headers, timeout=30)
            response.raise_for_status()
            response_text = response.text.strip().lower()
            if "success" in response_text or response_text == '"success"':
                return True, None
            res_json = response.json()
            if res_json.get("result") == 30000 and res_json.get("errmsg", "").lower() == "success":
                return True, None
            return False, res_json.get("errmsg") or res_json.get("ErrMsg", "测试失败")
        except Exception as e:
            return False, str(e)
