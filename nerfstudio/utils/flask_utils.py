import builtins
import hashlib
import http
import json
from dataclasses import dataclass, field

import requests
import yaml


@dataclass
class RedisConfig(yaml.YAMLObject):
    yaml_tag = 'redis'
    host: str = "192.168.2.68"
    """redis server ip"""
    port: int = 6379
    """redis端口"""
    db: int = 0
    """redis db"""
    password: str = ""
    """redis password"""
    lock_name: str = "nerf_studio_lock"
    """nerfstudio锁"""
    nerf_point_cloud_key: str = "nerf_studio:export_point_cloud"
    """nerf点云导出进度key"""
    nerf_viewer_key: str = "nerf_studio:run_viewer"
    """nerf视图解析器key"""
    nerf_studio_stop_work_key: str = "nerf_studio_stop"
    """nerf中断缓存key"""


@dataclass
class AppConfig(yaml.YAMLObject):
    yaml_tag = 'app'
    redis: RedisConfig = field(default_factory=lambda: RedisConfig)
    ip: str = "192.168.2.67"
    """flask"""
    port: int = 7006
    """flask启动端口"""
    viewer_default_port = 7007
    """viewer启动默认端口"""
    point_cloud_num_points: int = 1000000
    """nerf导出点云默认点数"""


flask_conf = AppConfig()


def generate_id(string):
    # 使用 SHA256 哈希算法
    hash_object = hashlib.sha256(string.encode('utf-8'))
    # 获取哈希值的前 8 个字节（64位）
    hash_bytes = hash_object.digest()[:8]
    # 将字节转换为整数
    unique_id = str(int.from_bytes(hash_bytes, byteorder='big'))
    return unique_id


def upload_file(path: any):
    url = 'http://192.168.2.68:1911/api/upload'  # 替换为实际的上传接口URL

    with open(path, "rb") as file:
        files = {'file': file}
        response = requests.post(url, files=files)

    if response.status_code == http.HTTPStatus.OK:
        resp = response.json()
        return resp["data"]["url"]
