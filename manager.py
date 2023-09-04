import sys
import os

import json
import uuid
from datetime import date

import torch.multiprocessing as mp

from flask import *
import threading

import nerf
from nerfstudio.utils.flask_utils import flask_conf, generate_id

run_viewers = None


class JsonFlask(Flask):
    def make_response(self, rv):
        """视图函数可以直接返回: list、dict、None"""
        if rv is None or isinstance(rv, (list, dict)):
            rv = JsonResponse.success(rv)
        if isinstance(rv, JsonResponse):
            rv = jsonify(rv.to_dict())
        return super().make_response(rv)


app = JsonFlask(__name__)


class JsonResponse(object):

    def __init__(self, data, code, msg):
        self.data = data
        self.code = code
        self.msg = msg

    @classmethod
    def success(cls, data=None, code=0, msg='success'):
        return cls(data, code, msg)

    @classmethod
    def error(cls, data=None, code=5000, msg='error'):
        return cls(data, code, msg)

    def to_dict(self):
        return {
            "code": self.code,
            "message": self.msg,
            "data": self.data
        }


@app.errorhandler(Exception)
def error_handler(e):
    return JsonResponse.error(msg=str(e))


@app.route('/ping', methods=['GET'])
def ping():
    return JsonResponse.success()


@app.route('/nerf_studio/point_cloud', methods=['POST'])
def nerf_export_point_cloud():
    data = request.get_json()
    load_config = data.get('load_config', '')
    output = data.get('output_dir', 'point_clouds')
    output_path = os.path.join(os.path.join("files/any_files", output), date.today().__str__())
    points = data.get('num_points', flask_conf.point_cloud_num_points)
    num_points = int(points)
    nerf_progress_key = data.get('nerf_progress_key', flask_conf.redis.nerf_point_cloud_key)
    server, client = mp.Pipe()
    try:
        mp.spawn(nerf.export_point_cloud,
                 args=(client, load_config, output_path, nerf_progress_key, num_points), daemon=True)
        pcd_path = server.recv()
        # server.close()
        # pcd_path = ExportPointCloud(load_config=Path(load_config), output_dir=Path(output_path),
        #                             progress_key=nerf_progress_key, num_points=num_points).main()
    except Exception as e:
        print(e)
        return JsonResponse.error(code=5001, msg="点云导出异常", data={"errDetail": str(e)})
    finally:
        server.close()
        client.close()
    return JsonResponse.success(data={"pcd_path": pcd_path})


@app.route('/nerf_studio/viewer', methods=['POST'])
def nerf_viewer_start():
    data = request.get_json()
    load_config = data.get('load_config', '')
    quality = data.get('quality', 30)
    jpeg_quality = int(quality)
    websocket_port = data.get('port', flask_conf.viewer_default_port)
    port = int(websocket_port)
    nerf_progress_key = data.get('nerf_progress_key', flask_conf.redis.nerf_viewer_key)
    key = generate_id(f"{load_config}#{websocket_port}")
    try:
        if run_viewers.get(key) is None:
            server, client = mp.Pipe()
            t = threading.Thread(target=nerf.spawn_viewer_in_thread,
                                 args=(load_config, port, nerf_progress_key, key, client, jpeg_quality,
                                       run_viewers),
                                 daemon=True)
            t.start()
            # mp.spawn(fn=nerf.start_viewer, args=(load_config, port, nerf_progress_key, key, client, jpeg_quality,
            #                                      run_viewers), daemon=True, join=False)
            websocket_url = server.recv()
            if websocket_url.startswith("error"):
                raise Exception(websocket_url)
            run_viewers[key] = {
                "url": websocket_url,
                "server": server,
            }
        else:
            viewer = run_viewers.get(key)
            websocket_url = viewer.get("url")
    except Exception as e:
        print(e)
        return JsonResponse.error(code=5002, msg="模型渲染失败", data={"errDetail": str(e)})
    return JsonResponse.success(data={
        "server_id": key,
        "websocket_url": websocket_url
    })


@app.route('/nerf_studio/viewer', methods=['PUT'])
def nerf_viewer_stop():
    data = request.get_json()
    server_id = data.get('server_id', '')
    if server_id == "":
        return JsonResponse.error(code=5003, msg="uid为空")
    try:
        if run_viewers.get(server_id) is None:
            return JsonResponse.error(code=5004, msg="服务不存在或已关闭")
        viewer_state = run_viewers.get(server_id)
        if viewer_state is None:
            return JsonResponse.error(code=5004, msg="服务不存在或已关闭")
        server = viewer_state.get("server")
        server.send(server_id)
        if server.recv():
            server.close()
    except Exception as e:
        print(e)
        return JsonResponse.error(code=5005, msg="服务关闭失败", data={"errDetail": str(e)})
    return JsonResponse.success()


@app.route("/nerf_studio/render", methods=['POST'])
def nerf_render():
    data = request.get_json()
    load_config = data.get('load_config', '')
    camera_json = data.get('camera', '')
    server, client = mp.Pipe()
    try:
        folder_name = "render_cameras"
        os.makedirs(folder_name, exist_ok=True)
        file_name = f"{uuid.uuid1()}_camera.json"
        output_path = os.path.join("files/any_files/renders", date.today().__str__())
        file_path = os.path.join(folder_name, file_name)  # 获取文件的路径
        with open(file_path, 'w') as file:
            json.dump(camera_json, file)
        mp.spawn(nerf.render_camera,
                 args=(client, load_config, "filename", file_path, output_path, "images"), daemon=True)
        images_path = server.recv()
        server.close()
        # images_path = RenderTrajectory(load_config=Path(load_config), traj="filename",
        #                                camera_path_filename=Path(file_path),
        #                                output_path=Path(output_path), output_format="images").main()
    except Exception as e:
        print(e)
        return JsonResponse.error(code=5006, msg="图片渲染失败", data={"errDetail": str(e)})
    finally:
        server.close()
        client.close()
    return JsonResponse.success(data={
        "images": images_path
    })


if __name__ == '__main__':
    with mp.Manager() as m:
        run_viewers = m.dict()
        app.run(host="0.0.0.0", port=7006, debug=True)