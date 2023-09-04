import open3d as o3d
import numpy as np
from open3d import io as o3d_io
import json
import copy
import os
def transofrm_cloud(cloud_in_path:str, transforam_scale_json_path:str):
    pcd = o3d_io.read_point_cloud(cloud_in_path)
    with open(transforam_scale_json_path, "r") as fr:
        transforam_scale_json = json.load(fr)
    # transformation = torch.as_tensor(transforam_scale_json["transform"])[None]
    cloud_out_path = os.path.join(os.path.dirname(cloud_in_path), "transformed_point_cloud.ply")

    transformation = np.asarray(transforam_scale_json["transform"])
    # transformation[:, :3] = np.linalg.inv(transformation[:, :3])
    transformation = np.concatenate([transformation, np.array([[0, 0, 0, 1/transforam_scale_json["scale"]]])], 0)
    transformation = np.linalg.inv(transformation)
    # use numpy to scale
    # points = np.asarray(pcd.pcd_transformed)
    # centroid
    # centroid = points.mean(axis=0)
    # # scale
    # scaled_points = (points - centroid) * scale_factor + centroidc
    # update point
    # pcd_transformed.points = o3d.utility.Vector3dVector(scaled_points)
    pcd_transformed = copy.deepcopy(pcd)
    # use open3d to scale and transform
    pcd_transformed.transform(transformation)
    # pcd_transformed.scale(scale_factor, center=pcd_transformed.get_center())
    o3d_io.write_point_cloud(cloud_out_path, pcd_transformed)

if __name__ == '__main__':
    transofrm_cloud("/Users/cybertron/workspace/deepglint/python/nerf_models/poster/pointclouds/5eac86ea-4b1b-11ee-9c28-93e65b946cce.ply", "/Users/cybertron/workspace/deepglint/python/nerf_models/poster/pointclouds/dataparser_transforms.json")