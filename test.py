import numpy as np
import math
import random
from scipy.spatial.transform import Rotation as R
from pyquaternion import Quaternion


def isRotationMatrix(R):
    Rt = np.transpose(R)
    shouldBeIdentity = np.dot(Rt, R)
    I = np.identity(3, dtype=R.dtype)
    n = np.linalg.norm(I - shouldBeIdentity)
    return n < 1e-6


def eulerAnglesToRotationMatrix(theta):
    R_x = np.array([[1, 0, 0],
                    [0, math.cos(theta[0]), -math.sin(theta[0])],
                    [0, math.sin(theta[0]), math.cos(theta[0])]
                    ])

    R_y = np.array([[math.cos(theta[1]), 0, math.sin(theta[1])],
                    [0, 1, 0],
                    [-math.sin(theta[1]), 0, math.cos(theta[1])]
                    ])

    R_z = np.array([[math.cos(theta[2]), -math.sin(theta[2]), 0],
                    [math.sin(theta[2]), math.cos(theta[2]), 0],
                    [0, 0, 1]
                    ])

    R = np.dot(R_z, np.dot(R_y, R_x))
    return R


def rotationMatrixToEulerAngles(R):
    assert (isRotationMatrix(R))
    sy = math.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
    singular = sy < 1e-6

    if not singular:
        x = math.atan2(R[2, 1], R[2, 2])
        y = math.atan2(-R[2, 0], sy)
        z = math.atan2(R[1, 0], R[0, 0])
    else:
        x = math.atan2(-R[1, 2], R[1, 1])
        y = math.atan2(-R[2, 0], sy)
        z = 0

    return np.array([x, y, z])


def matrix_to_euler(world_matrix):
    rotation_matrix = world_matrix[:3, :3]
    translation = world_matrix[:3, 3]

    # 计算旋转的欧拉角表示
    euler_angles = np.zeros(3)
    euler_angles[0] = np.arctan2(rotation_matrix[2, 1], rotation_matrix[2, 2])  # 绕 x 轴的旋转角度
    euler_angles[1] = np.arctan2(-rotation_matrix[2, 0],
                                 np.sqrt(rotation_matrix[2, 1] ** 2 + rotation_matrix[2, 2] ** 2))  # 绕 y 轴的旋转角度
    euler_angles[2] = np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])  # 绕 z 轴的旋转角度

    return euler_angles, translation


if __name__ == '__main__':
    rot_r = np.array([0.995366, 0.0960471, -0.00467654, 0,
                      -0.0959702, 0.995278, 0.0145625, 0,
                      0.00605315, -0.0140462, 0.999883, 0,
                      0, 0, 0, 1
                      ])

    # print(matrix_to_euler(
    #       [0.995366, 0.0960471, -0.00467654, 0,
    #     -0.0959702, 0.995278, 0.0145625, 0,
    #     0.00605315, -0.0140462, 0.999883, 0,
    #     0, 0, 0, 1
    #       ]))

    rot_r = rot_r.reshape(4, 4)

    rotation_matrix = np.array([[rot_r[0, 0], rot_r[0, 1], rot_r[0, 2]],
                                [rot_r[1, 0], rot_r[1, 1], rot_r[1, 2]],
                                [rot_r[2, 0], rot_r[2, 1], rot_r[2, 2]]
                                ])

    # 输出欧拉角
    euler = rotationMatrixToEulerAngles(rotation_matrix)
    print(euler)

    # 输出旋转矩阵
    rototion_matrix_ret = eulerAnglesToRotationMatrix(euler)
    print(rototion_matrix_ret)

    # 输出xyz坐标
    tra = (rot_r[0, 3], rot_r[1, 3], rot_r[2, 3])
    print(tra)
