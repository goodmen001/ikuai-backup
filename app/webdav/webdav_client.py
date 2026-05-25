"""
WebDAV客户端模块
提供标准WebDAV上传、下载、列表等功能
"""
import os
import time
import re
from datetime import datetime
from typing import Tuple, Optional, List, Dict
from urllib.parse import urlparse, quote
from requests import Session
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class WebDAVClient:
    """标准WebDAV客户端"""

    def __init__(self, url: str, username: str, password: str, path: str = "",
                 skip_dir_check: bool = True, logger=None, plugin_name: str = ""):
        self.url = url.rstrip('/')
        self.username = username
        self.password = password
        self.path = path.lstrip('/')
        self.skip_dir_check = skip_dir_check
        self.logger = logger
        self.plugin_name = plugin_name or "WebDAV"

        self.parsed_url = urlparse(self.url)
        self.is_alist = self.parsed_url.port == 5244 or '5244' in self.url

        if self.is_alist and '/dav' not in self.url:
            self.base_url = f"{self.url}/dav"
        else:
            self.base_url = self.url

        self.session = None
        self.auth = None

    def _get_session(self) -> Optional[Session]:
        if self.session:
            return self.session

        auth = HTTPBasicAuth(self.username, self.password)

        session = Session()
        session.auth = auth

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=retry_strategy
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        try:
            response = session.request(
                'PROPFIND',
                self.base_url,
                headers={'Depth': '0'},
                timeout=None,
                verify=False
            )

            if response.status_code in [200, 207]:
                self.session = session
                self.auth = auth
                return session
            elif response.status_code == 401:
                auth = HTTPDigestAuth(self.username, self.password)
                session.auth = auth
                response = session.request(
                    'PROPFIND',
                    self.base_url,
                    headers={'Depth': '0'},
                    timeout=None,
                    verify=False
                )
                if response.status_code in [200, 207]:
                    self.session = session
                    self.auth = auth
                    return session

            if self.logger:
                self.logger.error(f"{self.plugin_name} WebDAV认证失败，状态码: {response.status_code}")
            return None

        except Exception as e:
            if self.logger:
                self.logger.error(f"{self.plugin_name} WebDAV连接失败: {str(e)}")
            return None

    def _build_upload_url(self, filename: str) -> str:
        if self.path:
            return f"{self.base_url}/{self.path}/{quote(filename)}"
        else:
            return f"{self.base_url}/{quote(filename)}"

    def get_upload_url(self, filename: str) -> str:
        return self._build_upload_url(filename)

    def _create_directories(self) -> Tuple[bool, Optional[str]]:
        if not self.path or self.skip_dir_check:
            return True, None
        try:
            session = self._get_session()
            if not session:
                return False, "无法建立WebDAV连接"

            path_parts = [p for p in self.path.split('/') if p]
            current_path = self.base_url

            for part in path_parts:
                current_path = f"{current_path}/{part}"

                response = session.request('PROPFIND', current_path, headers={'Depth': '0'}, timeout=None, verify=False)

                if response.status_code == 404:
                    mkdir_response = session.request('MKCOL', current_path, timeout=None, verify=False)
                    if mkdir_response.status_code not in [200, 201, 204, 405]:
                        return False, f"创建目录失败: {current_path}"
                elif response.status_code not in [200, 207]:
                    return False, f"检查目录失败: {current_path}"

            return True, None
        except Exception as e:
            return False, f"创建目录时发生错误: {str(e)}"

    def upload(self, local_file_path: str, filename: str, progress_callback=None) -> Tuple[bool, Optional[str]]:
        if not os.path.exists(local_file_path):
            return False, f"本地文件不存在: {local_file_path}"

        session = self._get_session()
        if not session:
            return False, "无法建立WebDAV连接"

        self._create_directories()

        file_size = os.path.getsize(local_file_path)
        upload_url = self._build_upload_url(filename)

        SMALL_FILE_THRESHOLD = 10 * 1024 * 1024

        if file_size < SMALL_FILE_THRESHOLD:
            try:
                start_time = time.time()
                with open(local_file_path, 'rb') as f:
                    file_data = f.read()
                response = session.put(
                    upload_url, data=file_data,
                    headers={'Content-Type': 'application/octet-stream', 'User-Agent': 'MoviePilot/1.0'},
                    timeout=30, verify=False
                )
                if response.status_code in [200, 201, 204]:
                    total_time = time.time() - start_time
                    if self.logger:
                        self.logger.info(f"{self.plugin_name} 文件上传成功: {filename}, 耗时: {total_time:.2f}秒")
                    return True, None
                elif response.status_code == 409:
                    response = session.put(
                        upload_url, data=file_data,
                        headers={'Content-Type': 'application/octet-stream', 'User-Agent': 'MoviePilot/1.0', 'Overwrite': 'T'},
                        timeout=30, verify=False
                    )
                    if response.status_code in [200, 201, 204]:
                        return True, None
                    return False, f"上传失败: HTTP {response.status_code}"
                return False, f"上传失败: HTTP {response.status_code}"
            except Exception as e:
                return False, f"上传过程中发生错误: {str(e)}"

        # Large file streaming
        if file_size < 100 * 1024 * 1024:
            chunk_size = 16 * 1024 * 1024
        elif file_size < 500 * 1024 * 1024:
            chunk_size = 32 * 1024 * 1024
        elif file_size < 5 * 1024 * 1024 * 1024:
            chunk_size = 64 * 1024 * 1024
        elif file_size < 50 * 1024 * 1024 * 1024:
            chunk_size = 128 * 1024 * 1024
        else:
            chunk_size = 256 * 1024 * 1024

        timeout = None

        try:
            start_time = time.time()

            def file_generator():
                with open(local_file_path, 'rb') as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk

            response = session.put(
                upload_url, data=file_generator(),
                headers={'Content-Type': 'application/octet-stream', 'User-Agent': 'MoviePilot/1.0'},
                timeout=timeout, verify=False
            )

            if response.status_code in [200, 201, 204]:
                total_time = time.time() - start_time
                if self.logger:
                    self.logger.info(f"{self.plugin_name} 文件上传成功: {filename}, 耗时: {total_time:.1f}秒")
                return True, None
            elif response.status_code == 409:
                def file_generator_overwrite():
                    with open(local_file_path, 'rb') as f:
                        while True:
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            yield chunk
                response = session.put(
                    upload_url, data=file_generator_overwrite(),
                    headers={'Content-Type': 'application/octet-stream', 'User-Agent': 'MoviePilot/1.0', 'Overwrite': 'T'},
                    timeout=timeout, verify=False
                )
                if response.status_code in [200, 201, 204]:
                    return True, None
                return False, f"上传失败，状态码: {response.status_code}"
            else:
                return False, f"上传失败，状态码: {response.status_code}"
        except Exception as e:
            return False, f"上传过程中发生错误: {str(e)}"

    def list_files(self, pattern: str = None) -> Tuple[List[Dict], Optional[str]]:
        session = self._get_session()
        if not session:
            return [], "无法建立WebDAV连接"

        try:
            list_url = self._build_upload_url("")
            response = session.request('PROPFIND', list_url, headers={'Depth': '1'}, timeout=None, verify=False)

            if response.status_code not in [200, 207]:
                return [], f"列表请求失败，状态码: {response.status_code}"

            from xml.etree import ElementTree
            root = ElementTree.fromstring(response.content)

            files = []
            ns = {'D': 'DAV:'}

            for response_elem in root.findall('.//D:response', ns):
                href_elem = response_elem.find('D:href', ns)
                if href_elem is None:
                    continue
                href = href_elem.text
                if not href or href.endswith('/') or href == list_url:
                    continue

                filename = href.split('/')[-1]

                if pattern and pattern not in filename:
                    continue

                propstat = response_elem.find('D:propstat', ns)
                if propstat is not None:
                    prop = propstat.find('D:prop', ns)
                    if prop is not None:
                        size_elem = prop.find('D:getcontentlength', ns)
                        date_elem = prop.find('D:getlastmodified', ns)

                        size = int(size_elem.text) if size_elem is not None and size_elem.text else 0

                        file_time = None
                        if date_elem is not None and date_elem.text:
                            try:
                                from email.utils import parsedate_to_datetime
                                file_time = parsedate_to_datetime(date_elem.text).timestamp()
                            except Exception:
                                match = re.search(r'(\d{4}[_-]\d{2}[_-]\d{2}[_-]\d{2}[_-]\d{2}[_-]\d{2})', filename)
                                if match:
                                    try:
                                        time_str = match.group(1).replace('_', '')
                                        file_time = datetime.strptime(time_str, '%Y%m%d%H%M%S').timestamp()
                                    except Exception:
                                        pass
                                if file_time is None:
                                    file_time = time.time()

                        files.append({
                            'filename': filename,
                            'size': size,
                            'size_mb': size / (1024 * 1024),
                            'href': href,
                            'time': file_time or time.time()
                        })

            return files, None
        except Exception as e:
            return [], f"列表文件时发生错误: {str(e)}"

    def download(self, filename: str, local_path: str, progress_callback=None) -> Tuple[bool, Optional[str]]:
        session = self._get_session()
        if not session:
            return False, "无法建立WebDAV连接"

        try:
            download_url = self._build_upload_url(filename)
            response = session.get(download_url, stream=True, timeout=None, verify=False)

            if response.status_code not in [200, 206]:
                return False, f"下载失败，状态码: {response.status_code}"

            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            if self.logger:
                self.logger.info(f"{self.plugin_name} 文件下载成功: {filename}")

            return True, None
        except Exception as e:
            return False, f"下载文件时发生错误: {str(e)}"

    def delete_file(self, filename: str) -> Tuple[bool, Optional[str]]:
        session = self._get_session()
        if not session:
            return False, "无法建立WebDAV连接"

        try:
            delete_url = self._build_upload_url(filename)
            response = session.delete(delete_url, timeout=None, verify=False)

            if response.status_code in [200, 201, 204]:
                return True, None
            elif response.status_code == 404:
                return False, "文件不存在"
            else:
                return False, f"删除失败，状态码: {response.status_code}"
        except Exception as e:
            return False, f"删除文件时发生错误: {str(e)}"

    def cleanup_old_files(self, keep_count: int, pattern: str = None) -> Tuple[int, Optional[str]]:
        if keep_count <= 0:
            return 0, None

        files, error = self.list_files(pattern)
        if error:
            return 0, error

        if len(files) <= keep_count:
            return 0, None

        files.sort(key=lambda x: (x.get('time', 0), x['filename']), reverse=True)

        deleted_count = 0
        for file_info in files[keep_count:]:
            success, error = self.delete_file(file_info['filename'])
            if success:
                deleted_count += 1
                if self.logger:
                    self.logger.info(f"{self.plugin_name} 已删除旧文件: {file_info['filename']}")

        return deleted_count, None

    def close(self):
        if self.session:
            self.session.close()
            self.session = None
