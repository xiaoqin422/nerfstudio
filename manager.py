import os
import sys

from pathlib import Path
from flask import *

from scripts.exporter import ExportPointCloud


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


@app.route('/nerf_model/export/point_cloud', methods=['POST'])
def nerf_export_point_cloud():
    data = request.get_json()
    load_config = data.get('load_config', '')
    output = data.get('output_dir', '')
    points = data.get('num_points', '1000000')
    num_points = int(points)
    nerf_progress_key = data.get('nerf_progress_key', 'nerf_studio:export_point_cloud')
    try:
        pcd_path = ExportPointCloud(load_config=Path(load_config), output_dir=Path(output),
                                    progress_key=nerf_progress_key, num_points=num_points).main()
    except Exception as e:
        print(e)
        return JsonResponse.error(code=5001, msg="点云导出异常", data={"errDetail": str(e)})
    return JsonResponse.success(data={"pcd_path": pcd_path})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=7006, debug=True)
