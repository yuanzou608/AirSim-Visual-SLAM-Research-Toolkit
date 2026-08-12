# Base Image
FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04
SHELL ["bash", "-lc"]
ENV DEBIAN_FRONTEND=noninteractive
ENV TORCH_CUDA_ARCH_LIST="8.6;8.9;9.0;12.0+PTX"

# ============================================================
# Basic system dependencies
# ============================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    ca-certificates \
    gnupg \
    lsb-release \
    locales \
    software-properties-common \
    git \
    bzip2 \
    build-essential \
    ninja-build \
    cmake \
    pkg-config \
    gcc \
    g++ \
    unzip \
    vim \
    ffmpeg \
    python3-pip \
    libboost-all-dev \
    libglib2.0-0 \
    libxext6 \
    libsm6 \
    libxrender1 \
    libgl1 \
 && rm -rf /var/lib/apt/lists/*


# ============================================================
# Locale
# ============================================================
RUN locale-gen en_US en_US.UTF-8 && \
    update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# ============================================================
# Enable Ubuntu universe
# ============================================================
RUN add-apt-repository -y universe

# ============================================================
# ROS 2 Humble repository
# ============================================================
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
      -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
      http://packages.ros.org/ros2/ubuntu \
      $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
      > /etc/apt/sources.list.d/ros2.list

# ============================================================
# Install ROS 2 Humble Desktop
# ============================================================
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
      ros-humble-desktop \
      python3-colcon-common-extensions \
      python3-rosdep \
      python3-argcomplete \
      python3-opencv \
      ros-humble-cv-bridge \
      ros-humble-image-transport \
      ros-humble-sensor-msgs \
      ros-humble-geometry-msgs \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# rosdep initialization
# ============================================================
RUN rosdep init || true

# ============================================================
# Install Anaconda
# ============================================================
RUN wget https://repo.anaconda.com/archive/Anaconda3-2024.02-1-Linux-x86_64.sh \
      -O /tmp/anaconda.sh && \
    bash /tmp/anaconda.sh -b -p /opt/anaconda && \
    rm /tmp/anaconda.sh

# Set PATH so conda is available
# ENV PATH=/opt/anaconda/bin:$PATH

# (Optional) Update conda to latest version
#RUN conda update -n base -c defaults conda -y

# Conda is available but NOT automatically activated.
# ============================================================
RUN echo "source /opt/ros/humble/setup.bash" >> /root/.bashrc && \
    echo "source /opt/anaconda/etc/profile.d/conda.sh" >> /root/.bashrc
#RUN echo "conda activate base" >> ~/.bashrc

# ============================================================
# Conda + PyTorch environment
# ============================================================

RUN source /opt/anaconda/etc/profile.d/conda.sh && \
    conda create -n torch python=3.10 -y && \
    conda activate torch && \
    pip install --upgrade pip wheel setuptools && \
    pip install --no-cache-dir \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu128 && \
    pip install --no-cache-dir \
        numpy \
        scipy \
        pyyaml \
        opencv-python \
        tqdm \
        einops \
        timm \
        matplotlib \
        packaging && \
    conda clean -a -y

WORKDIR /workspace


# Default shell
CMD ["/bin/bash"]

