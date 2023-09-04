import numpy as np

if __name__ == '__main__':
    original_matrix = np.array([[0.995366, 0.0960471, -0.00467654, 2],
                                [-0.0959702, 0.995278, 0.0145625, 1],
                                [0.00605315, -0.0140462, 0.999883, 0],
                                [0, 0, 0, 1]
                                ])

    # 进行尺度矫正
    scale_factor = 1.8
    tra = (
    original_matrix[0, 3] * scale_factor, original_matrix[1, 3] * scale_factor, original_matrix[2, 3] * scale_factor)

    # nerf坐标系转机器人坐标系 flip the y and z axis
    # 创建一个3x3的目标矩阵
    rot = np.zeros((3, 3))
    rot = original_matrix[:3, :3]
    rot[0:3, 2] *= -1
    rot[0:3, 1] *= -1
    print(rot)

    # 创建4x4的变换矩阵
    new_matrix = np.eye(4)
    new_matrix[:3, :3] = rot
    new_matrix[:3, 3] = tra
    print(new_matrix)

    from scipy.spatial.transform import Rotation as R

    quat = R.from_matrix(rot[0:3, 0:3]).as_quat()
    print(quat)
