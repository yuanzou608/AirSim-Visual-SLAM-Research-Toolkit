from pathlib import Path

path = Path("/home/yuan/Downloads/traj_est_tum.txt")

total_lines = 0
non_empty_lines = 0
comment_lines = 0
data_rows_8plus = 0  # lines with >= 8 columns (e.g., TUM: timestamp + 7 pose fields)

with open(path, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        total_lines += 1
        s = line.strip()
        if not s:
            continue
        non_empty_lines += 1
        if s.startswith("#"):
            comment_lines += 1
            continue
        parts = s.split()
        if len(parts) >= 8:
            data_rows_8plus += 1


print("\nfile: ", str(path),
      "\ntotal_lines_including_blank_and_comments: ", total_lines, 
      "\nnon_empty_lines: ", non_empty_lines, 
      "\ncomment_lines_starting_with_hash: ", comment_lines, 
      "\ndata_rows_with_8_or_more_columns: ", data_rows_8plus,)
