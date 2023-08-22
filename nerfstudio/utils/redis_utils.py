from dataclasses import dataclass
import uuid
import time
from redis import StrictRedis, ConnectionPool
import json

pool = ConnectionPool(host='192.168.2.68', port=6379, db=0)
redis_client = StrictRedis(connection_pool=pool)
lock_name = "nerf_studio_lock"
nerf_studio_stop_work = "nerf_studio_stop"


@dataclass
class NerfStudioProcess:
    status: str = "start"
    steps: str = "load"
    total: int = 100
    processed: int = 0
    expect_time: int = 0


def cache_process(conn, key: str, process: NerfStudioProcess):
    progress_script = """
    if redis.call("del", KEYS[1]) == 0
        then return redis.call("set", KEYS[2], ARGV[1])
    else
        return 0
    end
    """
    stop_work = f'{nerf_studio_stop_work}:{key}'
    set_progress = conn.register_script(progress_script)
    result = set_progress(keys=[stop_work, key], args=[json.dumps(process.__dict__)])
    if result == 0:
        raise RuntimeError("任务终止。。。")


def acquire_lock_with_timeout(conn, lock_name, acquire_timeout=5, lock_timeout=3600):
    """
    基于 Redis 实现的分布式锁

    :param conn: Redis 连接
    :param lock_name: 锁的名称
    :param acquire_timeout: 获取锁的超时时间，默认 5 秒
    :param lock_timeout: 锁的超时时间，默认 3600 秒
    :return:
    """
    identifier = str(uuid.uuid4())
    lockname = f'nerf_studio_lock:{lock_name}'

    end = time.time() + acquire_timeout
    while time.time() < end:
        # 如果不存在锁着加锁并设置过期时间，避免死锁
        if conn.set(lockname, identifier, ex=lock_timeout, nx=True):
            return identifier
        time.sleep(0.001)

    return False


def release_lock(conn, lock_name, identifier):
    """
    释放锁

    :param conn: Redis 连接
    :param lock_name: 锁的名称
    :param identifier: 锁的标识
    :return: 解锁是否成功
    """
    unlock_script = """
    if redis.call("get", KEYS[1]) == ARGV[1]
        then return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    lockname = f'nerf_studio_lock:{lock_name}'
    unlock = conn.register_script(unlock_script)
    result = unlock(keys=[lockname], args=[identifier])
    if result == 1:
        return True
    else:
        return False