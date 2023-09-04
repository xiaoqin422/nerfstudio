import os
import time

from typing import Literal, Dict, Any

import psutil
import torch

from scripts.exporter import ExportPointCloud
from scripts.render import RenderTrajectory
from pathlib import Path

from scripts.viewer.run_viewer import RunViewer


def export_point_cloud(pid: int, client, load_config: str, output: str, progress_key: str, num_points: int):
    try:
        with torch.cuda.device(device='cuda'):
            exporter = ExportPointCloud(load_config=Path(load_config), output_dir=Path(output),
                                        progress_key=progress_key, num_points=num_points)
            pcd_path = exporter.main()
            client.send(pcd_path)

    except Exception as e:
        print(e)
        raise e
    print("export_point_cloud子进程执行结束")


def spawn_viewer_in_thread(load_config: str, websocket_port: int, progress_key: str, server_id: str, client,
                           jpeg_quality: int = 30, viewer_servers=None):
    try:
        torch.multiprocessing.spawn(_start_viewer, args=(client, load_config, websocket_port, progress_key, server_id,
                                                         jpeg_quality, viewer_servers), daemon=True)
    except Exception as e:
        client.send(f"error:{e}")
        client.close()
        raise e


def _start_viewer(pid: int, client, load_config: str, websocket_port: int, progress_key: str, server_id: str,
                  jpeg_quality: int = 30, viewer_servers=None):
    try:
        viewer_loader = RunViewer(load_config=Path(load_config), server_id=server_id,
                                  websocket_port=websocket_port, progress_key=progress_key,
                                  client=client, jpeg_quality=jpeg_quality, viewer_servers=viewer_servers)
        viewer_loader.main()
    except Exception as e:
        print(e)
        raise e
    print("_start_viewer子进程执行结束")


def render_camera(pid: int, client, load_config: str, traj: Literal["spiral", "filename", "interpolate"],
                  camera_path_filename: str, output_path: str,
                  output_format: Literal["images", "video"] = "video"):
    try:
        render = RenderTrajectory(load_config=Path(load_config), traj=traj,
                                  camera_path_filename=Path(camera_path_filename),
                                  output_path=Path(output_path), output_format=output_format)
        images = render.main()
        client.send(images)
        client.close()
    except Exception as e:
        print(e)
        raise e
    print("render_camera子进程执行结束")