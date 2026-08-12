xhost +local:root
docker run --rm -it \
	--privileged \
	--gpus all \
	--network=host \
	--ipc=host \
	-e DISPLAY=$DISPLAY \
	-e QT_X11_NO_MITSHM=1 \
	-v /tmp/.X11-unix:/tmp/.X11-unix \
	-v /home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit:/workspace/AirSim-Visual-SLAM-Research-Toolkit \
	-v /home/yuan/data2tb/dataset:/home/yuan/data2tb/dataset \
  	--name airsim-visual-slam-research-toolkit_container \
  	airsim-visual-slam-research-toolkit


