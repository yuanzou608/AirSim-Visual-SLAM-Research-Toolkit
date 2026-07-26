#!/bin/bash

# 要检查的数据集根目录
DATASET_ROOT="/home/yuan/data2tb/dataset/my_data"

# Python 检查脚本名字（跟你保存的一致）
CHECK_SCRIPT="check_dataset_integrity.py"

# 如果脚本不在当前目录，可以改成绝对路径，例如：
# CHECK_SCRIPT="/home/yuan/tools/check_dataset_integrity.py"

echo "Running dataset integrity check under: $DATASET_ROOT"
echo "Using checker: $CHECK_SCRIPT"
echo

for DATASET in "$DATASET_ROOT"/*; do
    if [ -d "$DATASET" ]; then
        # 直接调用检查脚本
        python "$CHECK_SCRIPT" "$DATASET"
        # Python 脚本内部：有问题才打印；没问题完全静默
    fi
done

echo
echo "Batch check finished."
