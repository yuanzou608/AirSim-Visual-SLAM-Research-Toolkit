import math

def quaternion_to_euler(w, x, y, z):
    # Roll (x-axis rotation)
    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2 * (w * y - z * x)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return roll, pitch, yaw


def convert_to_degree(radian):
    return radian * 180 / math.pi

# input orientation from imu
w = 0.011406010948121548
x = 0.0
y = 0.0
z = 0.99993497133255

roll, pitch, yaw = quaternion_to_euler(w, x, y, z)

roll_degree = convert_to_degree(roll)
pitch_degree = convert_to_degree(pitch)
yaw_degree = convert_to_degree(yaw)

print('roll: ', roll_degree)
print('pitch: ', pitch_degree)
print('yaw: ', yaw_degree)