# 内存统计审计（GiB）

当前作者规则允许按类型展示 `GPU_RESERVED` 和带 `*` 的 `CPU_RSS`：GPU 使用 peak_reserved，CPU 使用 peak RSS 并加 `*`；两者均换算为 GiB，但不得混称同一种内存，也不跨类型着色或排名。本次按类型核验覆盖24配置，其中17个为GPU_RESERVED、7个为CPU_RSS；逐项可用记录及现行结果由本次补充部分报告。下方先列现行结果，再保留前次仅接纳 GPU peak_reserved 的审计记录，旧资格、数量和结论均按当时规则保留，不代表本次 CPU_RSS 扩展后的现行结果，也不作为当前阻碍。

## 现行结果：按内存测量类型展示（2026-10-08）

**本轮已完成。** Table 2列名为 **Peak Memory (GiB)**，数据层保留 `value_gib`、`memory_type` 和 `table_display_marker`。24配置均有可靠内存测量：17个 `GPU_RESERVED`、7个 `CPU_RSS`。当前论文候选23配置的内存均可显示；SGS-SLAM虽然有可靠内存数据，仍按既有、独立的Accuracy规则排除论文。没有配置因缺少所有可靠内存数据而在本轮被排除。

原先7个 `not eligible` 的含义是“不满足当时统一GPU peak_reserved定义”，不是“没有memory数据”，更不是实验失败。按作者本轮最终决定，这7个配置现可将真实CPU峰值常驻内存单独标记后纳入；不存在需要补跑实验才能满足Table 2的新要求。

### 显示、脚注与排名

- 未加 `*` 的值为GPU预留显存（`GPU_RESERVED` / `peak_reserved`）；加 `*` 的值为CPU峰值常驻内存（`CPU_RSS` / `peak_rss`），全部为GiB。
- `*` 只说明该单元格的测量类型，不分类算法是否CPU-only，也不代表GPU使用情况。对于ElasticFusion，只能说明“现有保留memory measurement是CPU RSS”；现有保留记录中没有可用于统一GPU peak_reserved定义的指标，不能写成“该算法不使用GPU”。
- 不以 `virtual peak`、`device-used`、`peak_allocated` 或当前RSS替代所选的两种峰值统计。CPU RSS不写入或改名为 `peak_reserved`。
- **本轮直接取消全部内存颜色排名。** metadata及每行Table 2数据均设置 `color_ranking_enabled=false`，metadata设置 `cross_type_ranking_allowed=false`；不计算混合类型的最小值、次小值或内存赢家。
- 真正缺少可靠记录时仍显示 `--` / `unavailable`，不填0，也不因此判定实验失败或阻塞整张Table 2。个别运行缺少测量与配置层面完全没有数据分别处理。

统一脚注：**\* 表示 CPU 峰值常驻内存（peak RSS）；未标 \* 的数值表示 GPU peak_reserved。二者属于不同内存类型，不进行跨类型排名。**

### 当前配置与Table 2显示

代表值继续采用44条有条件标签序列：先对每条序列内有限内存值求均值，再按序列等权；不按ATE或SR筛选。下面仅在显示时保留4位小数，CSV保存完整数值。500帧配置与完整轨迹配置身份不变。

| 配置 | `memory_type` | `value_gib`显示 | `table_display_marker` | 有限运行/保留运行 | 有限序列/观测序列 | 当前论文状态 |
|---|---|---:|---|---:|---:|---|
| DPVO::mono | GPU_RESERVED | 2.6030 | 空 | 132/132 | 44/44 | 可展示 |
| DROID-SLAM::mono | GPU_RESERVED | 14.1477 | 空 | 132/132 | 44/44 | 可展示 |
| DROID-SLAM::rgbd | GPU_RESERVED | 14.0737 | 空 | 132/132 | 44/44 | 可展示 |
| DSO::mono | CPU_RSS | 0.1575* | `*` | 116/132 | 39/44 | 可展示 |
| ElasticFusion::rgbd | CPU_RSS | 1.5803* | `*` | 132/132 | 44/44 | 可展示 |
| MASt3R-SLAM::mono_calib | GPU_RESERVED | 19.8200 | 空 | 132/132 | 44/44 | 可展示 |
| MASt3R-SLAM::mono_nocalib | GPU_RESERVED | 19.8200 | 空 | 132/132 | 44/44 | 可展示 |
| MongGS::mono | GPU_RESERVED | 1.7739 | 空 | 130/132 | 44/44 | 可展示 |
| ORB-SLAM2::mono | CPU_RSS | 0.5638* | `*` | 126/132 | 42/44 | 可展示 |
| ORB-SLAM2::rgbd | CPU_RSS | 0.6922* | `*` | 132/132 | 44/44 | 可展示 |
| ORB-SLAM3::mono | CPU_RSS | 0.8728* | `*` | 125/132 | 44/44 | 可展示 |
| ORB-SLAM3::rgbd | CPU_RSS | 0.8343* | `*` | 126/132 | 44/44 | 可展示 |
| Photo-slam::mono | GPU_RESERVED | 4.5234 | 空 | 116/132 | 43/44 | 可展示 |
| Photo-slam::rgbd | GPU_RESERVED | 3.7190 | 空 | 130/132 | 44/44 | 可展示 |
| SGS-SLAM::semantic | GPU_RESERVED | -- | 空 | 113/132 | 41/44 | 内存已核实；独立Accuracy规则排除 |
| SLAM3R::mono | GPU_RESERVED | 28.6256 | 空 | 132/132 | 44/44 | 可展示 |
| SVO::mono | CPU_RSS | 0.1890* | `*` | 132/132 | 44/44 | 可展示 |
| SplaTAM::rgbd | GPU_RESERVED | 4.4229 | 空 | 99/132 | 36/44 | 可展示 |
| TartanVO::mono | GPU_RESERVED | 0.3242 | 空 | 132/132 | 44/44 | 可展示 |
| VGGT-LONG::mono | GPU_RESERVED | 24.2530 | 空 | 132/132 | 44/44 | 可展示 |
| VGGT-SLAM::mono | GPU_RESERVED | 17.0023 | 空 | 90/132 | 35/44 | 可展示 |
| hierslam::rgbd_500 | GPU_RESERVED | 1.4955 | 空 | 132/132 | 44/44 | 可展示 |
| hierslam::rgbd_whole | GPU_RESERVED | 9.4583 | 空 | 123/132 | 43/44 | 可展示 |
| hierslam::semantic_500 | GPU_RESERVED | 7.2581 | 空 | 123/132 | 43/44 | 可展示 |

SGS行的 `value_gib` 仍保存核实后的内存均值，`memory_available=true`；`table_display_value=--` 和 `paper_eligible=false` 来自其独立论文排除规则，不能解读成没有内存数据。

### CPU来源和单位依据

7配置实际保存的相应字段均为MiB：已有生产者读取Linux `VmHWM` 或 `ru_maxrss` 的KiB数值后除以1024。因此本轮再除以1024得到GiB，不根据旧CSV换算猜测单位。按当前清单只读核对了全部对应的小型指标文本，来源和生产者位置见[CPU证据记录](../../../codex_review/benchmark_analysis/audits/memory_gib/20261008_cpu_rss_policy/cpu_evidence.json)。

| 配置 | 精确源字段 | 生产者来源 | 原生单位→GiB | 全量可用记录/保留记录 |
|---|---|---|---|---:|
| DSO::mono | `PeakMemory (MB)` | `VmHWM` | MiB / 1024 | 127/144 |
| ElasticFusion::rgbd | `peak_rss_mb` | `ru_maxrss` | MiB / 1024 | 144/144 |
| ORB-SLAM2::mono | `memory` | `ru_maxrss` | MiB / 1024 | 138/144 |
| ORB-SLAM2::rgbd | `memory` | `ru_maxrss` | MiB / 1024 | 144/144 |
| ORB-SLAM3::mono | `memory_peak_MB` | `VmHWM` | MiB / 1024 | 137/144 |
| ORB-SLAM3::rgbd | `memory_peak_MB` | `VmHWM` | MiB / 1024 | 138/144 |
| SVO::mono | `peak_mem_mb` | `VmHWM` | MiB / 1024 | 144/144 |

**ORB-SLAM3的统计项差异必须保留。** 其旧CSV中137个mono及138个RGB-D有限内存值对应虚拟内存峰值，不能直接作为CPU peak RSS。新类型记录从 `TimingResults.txt` 精确读取 `memory_peak_MB`，不读 `memory_vpeak_MB`。例如 `building25fps_1`：mono原值3.41029296875来自虚拟峰值3492.14 MiB，CPU peak RSS为1096.11 MiB，即1.070419921875 GiB；RGB-D原值3.18951171875来自3266.06 MiB，CPU peak RSS为921.16 MiB，即0.8995703125 GiB。原虚拟峰值测量本身没有被判错，也没有被改写；本轮按新表定义选择不同测量项。

### 数据入口、历史保护与实际修改

新入口为 [memory_gib_run_records.csv](memory_gib_run_records.csv)：3456行，每行保留配置、序列、运行编号、真实类型、标记、来源路径/哈希、原生字段/单位、换算及缺失状态。3284条有可靠数值；另外172条为168个缺文件和4个路径中间组件不是目录的情况，保持数值为空。它们不自动改变任何SR或实验状态。GPU部分2312条数值及来源哈希保持前次结果；CPU部分新增972条可用标准化测量。

`memory_gib_metadata.json`升级为schema_version=2，分别记录 `memory_available` 和 `paper_eligible`；记录集的路径与哈希也参与认证。`table2_memory_rows()`返回有类型记录，拒绝过期CSV/记录集哈希、类型/标记不一致、未获论文资格的输入，不从旧 `PeakReservedGB` 列读取CPU值。GPU旧字段 `PeakReservedGiB` 为兼容保留，但CPU行该字段为空。

本轮实际执行的是已审阅的内存读取入口，没有运行18份 `results.py` 的main、SLAM或evo。24份原逐次指标CSV和18份 `results.py` 原字节均保持本轮开始时状态；ATE、FPS、runtime、SR及原始metrics未修改。没有重建第6～11C的历史统计或图像。完整Table 2的排版仍未实施，本轮更新其内存组件、脚注和关闭排名的规则。旧绘图或历史表格不被当作新内存入口。

本轮修改：

- Python：`memory_gib.py`、`normalize_memory_csvs.py`。
- CSV：更新 `memory_gib_table2.csv`；新增 `memory_gib_run_records.csv`；当前论文内容登记仅更新 `main_text_decisions.csv` 的D07解释及证据路径。
- metadata：更新 `memory_gib_metadata.json`，同时提供 `value_gib`、`memory_type`、`table_display_marker` 和显示/排名策略。
- Markdown：本中文报告；工作区 `AGENTS.md` 的长期语言规则；`README.md`、`PROJECT_STATUS.md`；第12步 `manuscript_blueprint.md`、`milestone_summary.md`、`implementation_plan.md` 的必要内存说明。
- 验证材料、CPU原始证据、测试和修改前备份保存于 `/home/yuan/SLAM/codex_review/benchmark_analysis/audits/memory_gib/20261008_cpu_rss_policy/`；前次 `/20261008/` 记录不改写。

本次翻译完整保留下方历史24行配置表、5行样例表、路径、数字和结论；与新策略冲突的旧资格说明明确标为历史，不以翻译伪装结论变化。下方原链接仍指向同名现行文件，前次元数据/表格的精确字节已保存在本轮修改前备份，可与旧证据目录交叉追溯。

### 验证和停止点

已通过12项解析测试和6项元数据准入反例检查，并完成24份原CSV保护检查、3456条运行身份/顺序核对、CPU精确源字段的独立换算和7个配置均值/分母核对、17个GPU配置数值不变检查，以及类型/星号/颜色规则检查；对应[独立验证记录](../../../codex_review/benchmark_analysis/audits/memory_gib/20261008_cpu_rss_policy/independent_typed_table2_verification.json)。
当前策略已覆盖全部有可靠内存数据的配置；7个旧GPU定义不适用项不再构成Table 2内存阻碍。测量类型区别、个别运行缺失及SGS的独立论文排除继续明确保留。实验状态为completed；本轮完成后停止，不新增实验或自动启动其它统计。

## 前次审计记录（仅GPU peak_reserved策略，历史结果）

2026-10-08。**前次聚合层修正已完成；按当时仅GPU peak_reserved的定义，全配置内存可用性尚未闭合。** 已审计18份 `results.py`、24个保留配置。17个配置具有已核实的 reserved 内存输入；另外7个配置在已检查的保留指标中，提供的是与 GPU peak_reserved 不等价的进程内存统计。这不表示运行失败、没有任何内存数据，亦不据此认定算法仅使用CPU。未执行SLAM、evo或results.py的main。原始实验文件仅作只读检查。

### 当时的输出定义与兼容性

- 当时的目标统计量为 **peak_reserved**，单位 **GiB**。不以 allocated、device-used、RSS或虚拟内存峰值替代。尊重源测量值，只修正所选字段及已核实的单位换算。
- 为兼容现有读取程序，逐运行CSV保留历史列名 `PeakReservedGB`。**只有** [memory_gib_metadata.json](memory_gib_metadata.json) 中匹配的记录，才能确认其在该次审计中的 peak_reserved/GiB 含义；不能只凭列名判断。未获当时GPU定义资格的历史CSV保留原值，不进入该次新建的Table 2内存路径。
- Table 2内存组件：[memory_gib_table2.csv](memory_gib_table2.csv)，字段明确命名为 `PeakReservedGiB`。使用44条有条件标签的序列，先对各序列内有限内存记录求均值，再按序列等权；不以ATE或SR筛选。保留运行和序列两类分母。
- 日志中的GB/MB标记与生产者定义分别记录。下文二进制换算系数来自已检查的生产代码；DROID使用十进制MB。SLAM3R使用十进制MB已在该次任务中标为 **user_confirmed**。没有根据旧 `/1024` 代码或数值大小推断单位。现存源码支持相应日志格式和定义，但不将其表述为已通过密码学哈希认定历史可执行程序。

### 配置清单

results.py列中的路径均相对于本目录。精确原始路径、样例哈希、生产者位置和模式说明见[配置清单](../../../codex_review/benchmark_analysis/audits/memory_gib/20261008/configuration_inventory.csv)。审计证据目录为 `/home/yuan/SLAM/codex_review/benchmark_analysis/audits/memory_gib/20261008/`。

| 算法/配置 | results.py | 源字段 | 原生单位 | 原换算 | 前次审计后的换算 | 最终字段/单位 | CSV是否重新生成？ | 说明 |
|---|---|---|---|---|---|---|---|---|
| DPVO::mono | DPVO/results.py | peak_reserved_GiB | GiB | 原值保留 | 原值保留 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA |
| DROID-SLAM::mono | DROID-SLAM/results.py | peak_gpu_reserved_mb | MB（十进制） | value / 1024 | value * 1000000 / 1073741824 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 是；仅修改内存 | 已核实；缺失内存保留NA |
| DROID-SLAM::rgbd | DROID-SLAM/results.py | peak_gpu_reserved_mb | MB（十进制） | value / 1024 | value * 1000000 / 1073741824 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 是；仅修改内存 | 已核实；缺失内存保留NA |
| DSO::mono | DSO/results.py | PeakMemory (MB) | MiB（生产者VmHWM kB / 1024；源标签MB） | value / 1024 | 当时不纳入：无peak_reserved；不可替代 | 历史列 / 未获当时GPU资格确认 | 否；不满足当时GPU定义 | 无reserved等价量；历史CSV未改；按当时GPU定义不进入Table 2 |
| ElasticFusion::rgbd | ElasticFusion/results.py | peak_rss_mb | MiB（生产者ru_maxrss / 1024；源标签mb） | value / 1024 | 当时不纳入：无peak_reserved；不可替代 | 历史列 / 未获当时GPU资格确认 | 否；不满足当时GPU定义 | 无reserved等价量；历史CSV未改；按当时GPU定义不进入Table 2 |
| MASt3R-SLAM::mono_calib | MASt3R-SLAM/results.py | GPU_PeakReserved | GiB（生产者二进制除数1024**3） | 原值保留device-used；GPU_DevicePeakUsed | 明确reserved字段，原值保留 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 是；仅修改内存 | 已核实；缺失内存保留NA |
| MASt3R-SLAM::mono_nocalib | MASt3R-SLAM/results.py | GPU_PeakReserved | GiB（生产者二进制除数1024**3） | 原值保留device-used；GPU_DevicePeakUsed | 明确reserved字段，原值保留 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 是；仅修改内存 | 已核实；缺失内存保留NA |
| MongGS::mono | MongGS/results.py | Peak_reserved_by_process [GiB] | GiB（明确标注） | 原值保留；Peak_reserved_by_process [GiB] | 原值保留 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA |
| ORB-SLAM2::mono | ORB-SLAM2/results.py | memory | MiB（生产者ru_maxrss / 1024；源后缀MB peak RSS） | value / 1024 | 当时不纳入：无peak_reserved；不可替代 | 历史列 / 未获当时GPU资格确认 | 否；不满足当时GPU定义 | 无reserved等价量；历史CSV未改；按当时GPU定义不进入Table 2 |
| ORB-SLAM2::rgbd | ORB-SLAM2/results.py | memory | MiB（生产者ru_maxrss / 1024；源后缀MB peak RSS） | value / 1024 | 当时不纳入：无peak_reserved；不可替代 | 历史列 / 未获当时GPU资格确认 | 否；不满足当时GPU定义 | 无reserved等价量；历史CSV未改；按当时GPU定义不进入Table 2 |
| ORB-SLAM3::mono | ORB-SLAM3/results.py | memory_peak_MB（实际路径）；当时导出器误用Photo-SLAM的Peak reserved (MB) | MiB（实际ORB3使用VmHWM kB / 1024） | 错误来源Photo-SLAM value / 1024 | 当时不纳入：无peak_reserved；不得执行错误来源路径 | 历史列 / 未获当时GPU资格确认 | 否；不满足当时GPU定义 | 无reserved等价量；历史CSV未改；按当时GPU定义不进入Table 2 |
| ORB-SLAM3::rgbd | ORB-SLAM3/results.py | memory_peak_MB（实际路径）；当时导出器误用Photo-SLAM的Peak reserved (MB) | MiB（实际ORB3使用VmHWM kB / 1024） | 错误来源Photo-SLAM value / 1024 | 当时不纳入：无peak_reserved；不得执行错误来源路径 | 历史列 / 未获当时GPU资格确认 | 否；不满足当时GPU定义 | 无reserved等价量；历史CSV未改；按当时GPU定义不进入Table 2 |
| Photo-slam::mono | Photo-slam/results.py | Peak reserved (MB) | MiB（生产者二进制除数1024**2） | /1024；memory_vpeak_MB来自错误的ORB-SLAM2路径 | /1024 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA |
| Photo-slam::rgbd | Photo-slam/results.py | Peak reserved (MB) | MiB（生产者二进制除数1024**2） | /1024；memory_vpeak_MB来自错误的ORB-SLAM2路径 | /1024 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA |
| SGS-SLAM::semantic | SGS-SLAM/results.py | PeakReservedGB | GiB（生产者为二进制，虽标签写GB） | 原值保留 | 原值保留 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA；独立的论文排除仍生效 |
| SLAM3R::mono | SLAM3R/results.py | gpu_peak_reserved_mb | MB（十进制；user_confirmed 2026-10-08） | value/1024 | value * 1000000 / 1073741824 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 是；仅修改内存 | 已核实；缺失内存保留NA；作者已确认原生十进制MB |
| SVO::mono | SVO/results.py | peak_mem_mb | MiB（CPU峰值RSS） | value/1024 | peak_reserved记NA；当时不以RSS替代 | 历史列 / 未获当时GPU资格确认 | 否；不满足当时GPU定义 | 无reserved等价量；历史CSV未改；按当时GPU定义不进入Table 2 |
| SplaTAM::rgbd | SplaTAM/results.py | Peak GPU reserved | MiB（生产者二进制除数1024**2） | /1024; Peak GPU reserved | /1024 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA |
| TartanVO::mono | TartanVO/results.py | peak_gpu_mem_reserved | GiB（明确标注） | 原值保留；peak_gpu_mem_reserved | 原值保留 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA |
| VGGT-LONG::mono | VGGT-LONG/results.py | peak_gpu_gb | GiB（生产者为二进制，虽标签写gb） | 原值保留 | 原值保留 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA |
| VGGT-SLAM::mono | VGGT-SLAM/results.py | Peak reserved  (PyTorch) | GiB（生产者二进制除数1024**3） | 原值保留device-used；Peak device used | 明确reserved字段，原值保留 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 是；仅修改内存 | 已核实；缺失内存保留NA |
| hierslam::rgbd_500 | hierslam/results.py | GPU Peak Memory (MB) | MiB（reserved） | value/1024 | value/1024 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA |
| hierslam::rgbd_whole | hierslam/rgbd_whole_trajectory/results.py | GPU Peak Memory (MB) | MiB（reserved） | value/1024 | value/1024 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 否；已核实，无需改值 | 已核实；缺失内存保留NA |
| hierslam::semantic_500 | hierslam/results.py | peak_reserved_bytes（替换allocated的GPU Peak Memory(MB)字段） | bytes（字节） | 原allocated MiB/1024 | peak_reserved_bytes/1024**3 | PeakReservedGB / GiB; Table2字段PeakReservedGiB | 是；仅修改内存 | 已核实；缺失内存保留NA；135份reserved字节附属文件，9份缺失；不回退allocated |

### 已核实的变更与未改动的值

已修正单位系数：DROID mono/RGB-D与SLAM3R mono使用十进制MB ×10^6/2^30，不再使用 /1024。已修正字段选择：MASt3R calib/nocalib与VGGT-SLAM由device-used改为明确的reserved字段；Hier semantic 500由allocated的 `GPU Peak Memory` 改为 `gpu_peak_memory.txt: peak_reserved_bytes / 2^30`。

| 配置样例 | 原CSV值 | 正确的reserved GiB值 | 证据 |
|---|---:|---:|---|
| DROID mono与RGB-D，building25fps_1 | 16.3962890625 | 15.636719763278961 | 16789.80十进制MB；两种生产者定义均已核对 |
| MASt3R calib / nocalib, building25fps_1 | 31.21 / 31.25 (device-used) | 19.82 | GPU_PeakReserved；生产者bytes/2^30 |
| SLAM3R, building25fps_1 | 30.13671875 | 28.740614652633667 | 30860.00十进制MB；作者确认 |
| VGGT-SLAM, building25fps_1 | 16.89 (device-used) | 15.7 | Peak reserved (PyTorch)；生产者bytes/2^30 |
| Hier semantic 500, building25fps_4 | 3.547783203125 (allocated) | 15.322265625 | 16452157440 reserved字节 |

共修改999个内存单元格：954个测量值完成单位换算或改用正确的reserved字段；45个VGGT缺文件单元格由元组文本 `('NA', 'NA')` 改为标量 `NA`。这45项仍为缺失，不是新测得的零值或失败记录。没有对缺失项估计或填入有限数值。

10份已核实CSV的数值原本正确，保持逐字节不变：DPVO mono、MongGS mono、Photo mono/RGB-D、SGS semantic、SplaTAM RGB-D、TartanVO mono、VGGT-LONG mono、Hier RGB-D 500和Hier RGB-D whole。7份原脚本的非缺失字段选择/换算逻辑原本正确（DPVO、MongGS、SplaTAM、TartanVO、VGGT-LONG、SGS、Hier whole），共享审计解析器保留了这些逻辑。全部18份脚本都接受了小范围解析器/导入/注释更新，因此不宣称任何脚本逐字节未改。

### 当时定义不接纳的统计量与逐运行缺失记录

在 **DSO mono、ElasticFusion RGB-D、ORB-SLAM2 mono/RGB-D、ORB-SLAM3 mono/RGB-D、SVO mono** 的所选保留指标中，未找到与peak_reserved等价的量。其来源描述的是峰值RSS、当前RSS或虚拟内存峰值。已检查相应生产者和全部所选的小型源文本，未找到可替代的reserved字段。这7份历史CSV保持不变，其内存值当时不能进入仅接纳GPU peak_reserved的Table 2；这不等于它们没有内存测量，也不是运行失败判定。重新执行现有聚合器不会创造缺失的reserved测量。按当时定义，若另有已存在的reserved输出，需要提供其准确路径和定义；这不是补跑实验请求。

对已核实配置，逐运行文件不可用时仍保留NA，准确路径/状态记录在 `application/memory_cell_audit.csv`。Hier semantic有9份附属内存文件缺失；Hier whole有9份指标文件缺失；MongGS有2项父路径文件/目录冲突。其余缺失源文件数量见元数据。不根据内存缺失推断算法失败。SLAM3R的单位疑问已由作者确认关闭；前次获准的17个配置中，不再有未确定的换算系数。

### 安全执行、模式与前次Table 2路径

已使用的辅助程序为 [normalize_memory_csvs.py](normalize_memory_csvs.py)。它显式枚举24份源CSV及原始内存路径，检查48序列 × 实际3个run ID，Hier500保留4/5/6，其余保留1/2/3；不导入results.py或evo。写入内存值前先完成全部检查，备份受影响CSV，比较源哈希并检查非内存单元格和顺序。默认只预检（dry run）；若审计目录已存在则拒绝执行。未来另行授权刷新时的示例如下，须使用新审计目录：

```bash
/home/yuan/anaconda3/bin/python3 -B /home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/normalize_memory_csvs.py --audit-dir /home/yuan/SLAM/codex_review/benchmark_analysis/audits/memory_gib/NEW_CHECK
```

只有明确执行内存刷新时才添加 `--apply`。前次任务已执行获准修正，上述17个配置不需要手工激活模式。**不要通过运行旧results.py的main复现该内存修正。** 它们还会评估ATE，且多份脚本保留历史输出/模式路径：

- DROID：当时main启用RGB-D；辅助程序分别选择mono和RGB-D。
- MASt3R：当时main启用nocalib；辅助程序分别选择calib和nocalib，两者均为Mono。
- Hier外层：启用no-semantic，semantic的base/output处于注释状态；辅助程序分别绑定RGB-D500和semantic500，semantic使用reserved附属文件。完整轨迹使用独立脚本/路径。
- ORB-SLAM3的main指向Photo-SLAM；Photo的main指向ORB-SLAM2。辅助程序使用各自实际核实的路径，绝不借用Photo的reserved内存值填给ORB3。
- DPVO、SLAM3R、SVO、TartanVO、VGGT-LONG和VGGT-SLAM的main将mono导出命名为rgbd；SGS指向外部ros2humble路径。未执行这些main，也未改变其非内存路径。
- 每配置的准确预期输出和源模式已在清单及辅助程序中枚举。上述7个配置属于**当时GPU peak_reserved定义下的统计量不匹配/证据缺口**，不是等待切换注释即可解决的工作。没有任何CSV只是等待手工执行。

完整新版Table 2仍是论文方案，尚未生成完整排版表。前次内存组件通过 `table2_memory_rows()` 仅使用当次已认证的CSV（配置＋准确路径＋SHA＋统计量＋单位＋资格）。过期输入和dry-run元数据均被拒绝。**按当时仅GPU peak_reserved的规则**，组件中有16个可用论文行、7个不具备合格reserved统计量的行；SGS虽有合格内存值，仍因独立的Accuracy/论文规则被排除。这次内存修正不解除SGS的排除。16/7及SGS说明是前次历史结果，不代表本次CPU_RSS扩展结果。

历史 `Benchmark/statistics/summary_metrics_by_scene_{mono,rgbd}.py` 将旧 `PeakReservedGB_mean/std` 标成 `Peak VRAM(GB)`；高度/速度汇总也读取该历史字段。旧汇总和冻结的第6～11C步内存表**没有**获得该次更新认证，不得用于新版Table 2内存列。它们没有重新生成或重贴标签。前次新增元数据/组件是当时拟定T2的唯一内存选择路径。未改变原PDF/LaTeX表格排版。

MonoGS和当时SplaTAM的CSV字节未改变，因此其近期Accuracy的source-SHA资格仍有效。对于修改的输入，`application/csv_updates.json` 记录前后SHA及非内存单元格保持不变的检查；这仅证明内存变更的版本衔接，不授权更新无关Accuracy或统计快照。

### 前次修改与新增文件

**修改的results.py（18份）：**

- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/DPVO/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/DROID-SLAM/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/DSO/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/ElasticFusion/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/MASt3R-SLAM/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/MongGS/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/ORB-SLAM2/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/ORB-SLAM3/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/Photo-slam/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/SGS-SLAM/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/SLAM3R/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/SVO/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/SplaTAM/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/TartanVO/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/VGGT-LONG/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/VGGT-SLAM/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/hierslam/results.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/hierslam/rgbd_whole_trajectory/results.py`

**自动修正的逐运行CSV（7份；仅内存）：**

- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/DROID-SLAM/mono_metrics.csv` — 144个内存单元格
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/DROID-SLAM/rgbd_metrics.csv` — 144个内存单元格
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/MASt3R-SLAM/calib_metrics.csv` — 144个内存单元格
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/MASt3R-SLAM/nocalib_metrics.csv` — 144个内存单元格
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/SLAM3R/mono_metrics.csv` — 144个内存单元格
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/VGGT-SLAM/mono_metrics.csv` — 144个内存单元格
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/hierslam/semantic_metrics_500frames.csv` — 135个内存单元格

**新增聚合/选择文件：**

- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/memory_gib.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/normalize_memory_csvs.py`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/memory_gib_metadata.json`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/memory_gib_table2.csv`
- `/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data/memory_gib_audit.md`

**工作区证据：** `group_a/b/c.json`（各限定范围的初步发现）、`author_confirmation.json`、`configuration_inventory.csv`、解析器测试、`code_changes.json`、`verification.json`、dry-run证据，以及 `application/` 中的前后单元格审计和小范围备份。SLAM3R作者确认替代了group_c的初步未解决条目，但未删除历史发现。以下工作区文件已备份并作最小更新：`README.md`、`PROJECT_STATUS.md`、`paper/12_restructure_plan/manuscript_blueprint.md`、`paper/12_restructure_plan/main_text_decisions.csv`（仅D07）、`paper/12_restructure_plan/milestone_summary.md`、`paper/12_restructure_plan/implementation_plan.md`。

### 前次验证与数量汇总

- 对18份results.py进行AST比较：ATE/FPS/runtime函数与main中的非内存逻辑全部不变；仅修改内存函数/调用目标及导入/注释。
- 7份CSV各自保留全部144条记录；表头、顺序、标识和每个非内存单元格均与备份一致。其余17份CSV保持原SHA。执行前已核对原始小型指标文件的哈希，未写入任何原始文件。
- 12项解析器测试覆盖明确的二进制/十进制单位、reserved与allocated/device-used的区分、缺失/重复/无效字段、单位及冲突、semantic附属文件和路径冲突。未导入研究程序。
- 前次Table 2路径拒绝过期哈希、未经批准/不等价的指标及dry-run认证。独立复核将当时16个可用条件内存均值和有限记录数，与当次已认证CSV逐一核对。
- 保留原CSV的CRLF换行；默认Git空白检查把CR标为行尾空白。使用 `core.whitespace=cr-at-eol` 的只读检查通过；未改变Git设置或CSV格式。
- 未重建既有分析和图表；其旧内存结果保留为历史值，没有静默改成该次定义。

**前次数量：** 审计18份results.py；最小修改18份；7份原本具有正确的数值字段/换算逻辑并予以保留，0份脚本逐字节未改；自动修正7份CSV；10份已核实CSV逐字节未改；7份未满足当时GPU peak_reserved定义的CSV未改；**0份仅等待手工切换模式重新生成**。全部24配置均已登记。

**前次结论：** 17个配置的单位归一化及reserved字段选择已闭合，T2内存路径排除了不兼容值。按当时仅GPU peak_reserved的定义，另外7个配置没有保留的等价证据，因此全配置可用性仍未闭合；没有虚构缺失统计量。该历史结论不否认其CPU RSS数据在本次新规则下可经核实纳入。实验状态始终保持已完成。
