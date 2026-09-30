#!/bin/bash

ROOT="/home/yuan/data2tb/dataset/my_data"

echo "Scanning: $ROOT"

for DATASET in "$ROOT"/*; do
    if [ -d "$DATASET" ]; then

        SRC="$DATASET/associations_rgb_depth.txt"
        DST="$DATASET/associations.txt"

        if [ -f "$SRC" ]; then
            echo "Found: $SRC"

            # 如果已有 associations.txt，先删除（避免冲突）
            if [ -f "$DST" ]; then
                echo "  Removing existing $DST"
                rm "$DST"
            fi

            echo "  Renaming to $DST"
            mv "$SRC" "$DST"
        fi
    fi
done

echo "Done."
