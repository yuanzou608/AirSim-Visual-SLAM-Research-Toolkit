from projectairsim import ProjectAirSimClient, Drone
import time

client = ProjectAirSimClient()
client.confirm_connection()

d = Drone(client, name="Drone1")

d.enable_api_control(True)
d.arm(True)

print("Takeoff...")
d.takeoff_async().join()
time.sleep(1)

print("Move forward 5 m")
d.move_by_velocity_async(vx=5, vy=0, vz=0, duration=2).join()
time.sleep(1)

print("Landing...")
d.land_async().join()
d.arm(False)
d.enable_api_control(False)
