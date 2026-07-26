import rclpy
from rclpy.node import Node
from airsim_interfaces.msg import VelCmd
import sys
import termios
import tty
import select

# Define key bindings for movement
KEY_BINDINGS = {
    'w': (1.0, 0.0, 0.0, 0.0),  # Move forward
    's': (-1.0, 0.0, 0.0, 0.0), # Move backward
    'a': (0.0, 1.0, 0.0, 0.0),  # Move left
    'd': (0.0, -1.0, 0.0, 0.0), # Move right
    'r': (0.0, 0.0, -1.0, 0.0), # Move up
    'f': (0.0, 0.0, 1.0, 0.0),  # Move down
    'q': (0.0, 0.0, 0.0, 1.0),  # Rotate left
    'e': (0.0, 0.0, 0.0, -1.0), # Rotate right
    ' ': (0.0, 0.0, 0.0, 0.0),  # Stop movement
}

class DroneKeyboardControl(Node):
    def __init__(self):
        super().__init__('drone_keyboard_control')
        self.publisher = self.create_publisher(VelCmd, '/airsim_node/SimpleFlight/vel_cmd_body_frame', 10)
        self.get_logger().info("\n🚀 Keyboard control for AirSim started!\n"
                               "🔹 Use W/A/S/D to move.\n"
                               "🔹 R/F for up/down.\n"
                               "🔹 Q/E to rotate.\n"
                               "🔹 SPACEBAR to stop.\n"
                               "🔹 CTRL+C to exit.\n")

    def get_key(self):
        """Captures a single keypress without requiring Enter."""
        tty.setraw(sys.stdin.fileno())  # Switch to raw input mode
        select.select([sys.stdin], [], [], 0)  # Wait for input
        key = sys.stdin.read(1)  # Read single character
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, termios.tcgetattr(sys.stdin))  # Restore terminal settings
        return key

    def run(self):
        """Captures key presses and publishes velocity commands in a loop."""
        while rclpy.ok():
            key = self.get_key()

            if key == '\x03':  # Detects CTRL+C (exit)
                break

            # Ensure 4 values are always returned (default: stop motion)
            linear_x, linear_y, linear_z, angular_z = KEY_BINDINGS.get(key, (0.0, 0.0, 0.0, 0.0))

            # Publish velocity command
            msg = VelCmd()
            msg.twist.linear.x = linear_x * 2.0  # Adjust speed
            msg.twist.linear.y = linear_y * 2.0
            msg.twist.linear.z = linear_z * 2.0
            msg.twist.angular.z = angular_z * 1.0  # Adjust rotation speed
            self.publisher.publish(msg)

            self.get_logger().info(f"Key Pressed: {key} | Vel: ({linear_x}, {linear_y}, {linear_z}) | Rot: {angular_z}")

def main(args=None):
    rclpy.init(args=args)
    node = DroneKeyboardControl()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
