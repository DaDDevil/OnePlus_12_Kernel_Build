#!/usr/bin/env python3
import os
import sys
import shlex
import subprocess
from pathlib import Path
import multiprocessing
import time
from datetime import datetime
from contextlib import contextmanager

# ================= 1. 环境与初始化 =================
KERNEL_SRC = os.environ.get("KERNEL_SRC")
if not KERNEL_SRC:
    print("\033[31m[!] 请先配置 $KERNEL_SRC 环境变量\033[0m")
    sys.exit(1)

BASE_DIR = Path.cwd().resolve()
ALL_SYMVERS = []

# 自动获取最大 CPU 核心数，火力全开
NPROC = multiprocessing.cpu_count()

# ================= 2. 时间监控上下文引擎 =================
@contextmanager
def timing_tracker(description: str, is_total: bool = False):
    """优雅的时间跟踪上下文管理器"""
    start_time = time.time()
    start_dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if is_total:
        print(f"\033[42;37m🚀 {description} - 起始时间: {start_dt}\033[0m")
    else:
        print(f"\n\033[34m>>> 正在编译: {description} (开始: {start_dt})\033[0m")
        
    try:
        yield # 执行真正的业务代码
    finally:
        end_time = time.time()
        end_dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        duration = end_time - start_time
        mins, secs = divmod(duration, 60)
        
        if is_total:
            print(f"\n\033[42;37m✅ 所有模块编译完成！ 结束时间: {end_dt}\033[0m")
            print(f"\033[42;37m⏱️  总耗时: {int(mins)}分 {secs:.2f}秒\033[0m\n")
        else:
            print(f"\033[36m<<< {description} 编译结束 | 耗时: {int(mins)}分 {secs:.2f}秒\033[0m")

# ================= 3. 核心编译引擎 =================
def build_mod(rel_path: str, extra_args: dict = None):
    mod_dir = BASE_DIR / rel_path

    if not mod_dir.is_dir():
        print(f"\n\033[33m[!] 跳过: 目录 {rel_path} 不存在\033[0m")
        return

    # 使用上下文管理器自动接管计时期
    with timing_tracker(rel_path):
        # === 预置任务钩子 (Pre-build Hook) ===
        if extra_args and "__pre_cmd__" in extra_args:
            pre_cmd = extra_args.pop("__pre_cmd__") 
            resolved_pre_cmd = pre_cmd.format(mod_dir=mod_dir, base_dir=BASE_DIR)
            print(f"\033[35m[*] 执行预置任务: {resolved_pre_cmd}\033[0m")
            subprocess.run(resolved_pre_cmd, cwd=mod_dir, shell=True, check=True)
            
        # 1. 组装基础 make 命令
        make_env_str = os.environ.get("MAKE_ENV", "")
        cmd = ["make"] + shlex.split(make_env_str) + [
            "KCFLAGS=-Wno-error",
            f"-C", str(KERNEL_SRC),
            f"M={mod_dir}",
        ]

        # 2. 组装动态依赖符号表
        if ALL_SYMVERS:
            cmd.append(f"KBUILD_EXTRA_SYMBOLS={' '.join(ALL_SYMVERS)}")

        # 3. 动态解析该模块专属参数
        if extra_args:
            for key, val in extra_args.items():
                resolved_val = str(val).format(mod_dir=mod_dir, base_dir=BASE_DIR)
                cmd.append(f"{key}={resolved_val}")

        cmd.extend(["modules", f"-j{NPROC}"])

        # 5. 执行正式编译
        try:
            subprocess.run(cmd, cwd=mod_dir, check=True)
        except subprocess.CalledProcessError:
            print(f"\033[31m[x] 编译惨遭失败: {rel_path}\033[0m")
            sys.exit(1)

        # 6. 自动收集产物
        sym_file = mod_dir / "Module.symvers"
        if sym_file.exists():
            ALL_SYMVERS.append(str(sym_file))
            print(f"\033[32m[+] 成功提取并载入 {sym_file.name}\033[0m")


# ================= 4. 模块配置清单 =================
BP = {"BOARD_PLATFORM": "pineapple"}

MODULES_CONFIG = [
    # --- 1. 基础内核与框架模块 ---
    ("qcom/opensource/securemsm-kernel", {"SSG_MODULE_ROOT": "{mod_dir}"}),
    ("qcom/opensource/dsp-kernel",       {"DSP_ROOT": "{mod_dir}"}),
    ("qcom/opensource/synx-kernel",      {"SYNX_ROOT": "{mod_dir}"}),
    ("qcom/opensource/spu-kernel",       {"SPU_ROOT": "{mod_dir}"}),
    ("qcom/opensource/mmrm-driver",      {"MMRM_ROOT": "{mod_dir}"}),

    # --- 2. 内存管理及 Fence 驱动 ---
    ("qcom/opensource/mm-drivers/hw_fence",        {"MSM_HW_FENCE_ROOT": "{base_dir}/qcom/opensource/mm-drivers", "ccflags-y": "-I{base_dir}/qcom/opensource/mm-drivers/hw_fence/include/"}),
    ("qcom/opensource/mm-drivers/msm_ext_display", {"MSM_EXT_DISPLAY_ROOT": "{base_dir}/qcom/opensource/mm-drivers"}),
    ("qcom/opensource/mm-drivers/sync_fence",      {"SYNC_FENCE_ROOT": "{base_dir}/qcom/opensource/mm-drivers", "ccflags-y": "-I{base_dir}/qcom/opensource/mm-drivers/sync_fence/include/"}),
    ("qcom/opensource/mm-sys-kernel/ubwcp",        {}),

    # --- 3. 数据与网络模块 ---
    ("qcom/opensource/datarmnet-ext/mem", {}),
    ("qcom/opensource/dataipa",           {"KP_MODULE_ROOT": "{mod_dir}", "ccflags-y": "-I{base_dir}/qcom/opensource/datarmnet-ext/mem"}),
    ("qcom/opensource/datarmnet/core",    {"RMNET_CORE_ROOT": "{mod_dir}", "ccflags-y": "-I{base_dir}/qcom/opensource/datarmnet-ext/mem -I{base_dir}/qcom/opensource/dataipa/drivers/platform/msm/include -I{base_dir}/qcom/opensource/dataipa/drivers/platform/msm/include/uapi"}),
]

for ext in ["aps", "offload", "wlan", "perf_tether", "shs", "perf", "sch"]:
    MODULES_CONFIG.append(
        (f"qcom/opensource/datarmnet-ext/{ext}", {"ccflags-y": "-I{base_dir}/qcom/opensource/datarmnet/core"})
    )

# --- 4. EVA 及多媒体核心驱动 ---
MODULES_CONFIG.extend([
    ("qcom/opensource/eva-kernel", {"EVA_ROOT": "{mod_dir}"}),
    ("qcom/opensource/display-drivers", {**BP, "DISPLAY_ROOT": "{mod_dir}", "CONFIG_DRM_MSM": "m", "CAIHONG_DISPLAY_DRIVER": "y"}),
    ("qcom/opensource/graphics-kernel", {**BP, "KGSL_MODULE_ROOT": "{mod_dir}"}),
    ("qcom/opensource/video-driver/video", {**BP, "VIDEO_ROOT": "{mod_dir}"}),
    ("qcom/opensource/video-driver/msm_video", {**BP, "VIDEO_ROOT": "{mod_dir}"}),
    ("qcom/opensource/wlan/platform",   {**BP, "WLAN_PLATFORM_ROOT": "{mod_dir}"}),
    ("qcom/opensource/wlan/qcacld-3.0", {**BP, "WLAN_ROOT": "{mod_dir}", "WLAN_PROFILE": "kiwi_v2", "CONFIG_QCA_CLD_WLAN": "m", "MODNAME": "qca_cld3_kiwi_v2", "KCFLAGS": "-I{base_dir}/qcom/opensource/dataipa/drivers/platform/msm/include/uapi/ -I{base_dir}/qcom/opensource/dataipa/drivers/platform/msm/include/"}),
    ("qcom/opensource/bt-kernel",       {**BP, "BT_ROOT": "{mod_dir}", "CONFIG_BT_HW_SECURE_DISABLE": "y", "CONFIG_MSM_BT_POWER": "m", "CONFIG_BTFM_SLIM": "m"}),
    ("qcom/opensource/camera-kernel",   {**BP, "CAMERA_KERNEL_ROOT": "{mod_dir}", "KERNEL_ROOT": str(KERNEL_SRC), "__pre_cmd__": "make cam_generated_h"}),
    ("qcom/opensource/audio-kernel",    {**BP, "AUDIO_ROOT": "{mod_dir}", "MODNAME": "audio_dlkm"}),
    
    # --- 5. NXP && OPLUS 驱动 ---
    ("nxp/opensource/driver", {**BP, "NFC_ROOT": "{mod_dir}"}),
    ("oplus/secure/biometrics/fingerprints/bsp/uff/driver", {**BP, "KCFLAGS": "-Wno-error -I{base_dir}/oplus/kernel/touchpanel/oplus_touchscreen_v2/touchpanel_notify"}),
    ("oplus/secure/common/bsp/drivers", {**BP, "CONFIG_OPLUS_SECURE_COMMON": "m"}),
    ("oplus/sensor/kernel/oplus_consumer_ir", {**BP}),
    ("oplus/sensor/kernel/qcom/sensor", {**BP}),
    ("oplus/kernel/device_info/pogo_keyboard", {**BP}),
    ("oplus/kernel/device_info/tri_state_key", {**BP}),
    ("oplus/kernel/cpu/thermal", {**BP}),
    ("oplus/kernel/dfr", {**BP}),
    ("oplus/kernel/graphics", {**BP}),
    ("oplus/kernel/touchpanel/oplus_touchscreen_v2/touch_custom", {**BP, "KCFLAGS": "-I{mod_dir}/../"}),
    ("oplus/kernel/touchpanel/oplus_touchscreen_v2", {**BP, "KCFLAGS": "-I{base_dir}/oplus/kernel/touchpanel/oplus_touchscreen_v2/"}),
    ("oplus/kernel/touchpanel/synaptics_hbp", {**BP, "KCFLAGS": "-I{base_dir}/oplus/kernel/touchpanel/oplus_touchscreen_v2/ -I{base_dir}/oplus/kernel/touchpanel/synaptics_hbp/", "ccflags-y": "-DTOUCHPANEL_STATS_TRACE_INCLUDE_PATH={base_dir}/oplus/kernel/touchpanel/synaptics_hbp/touchpanel_healthinfo -DCONFIG_TOUCHPANEL_OPLUS_MODULE"}),
    ("oplus/kernel/tp/hbp/hbp", {**BP, "KCFLAGS": "-Wno-error -I{mod_dir}"}),
    ("oplus/kernel/network/oplus_network_oem_qmi", {**BP}),
    ("oplus/kernel/network/oplus_network_sim_detect", {**BP}),
    ("oplus/kernel/network/oplus_rf_cable_monitor", {**BP}),
    ("oplus/kernel/network/oplus_network_esim", {**BP}),
])

# ================= 5. 启动流水线 =================
if __name__ == "__main__":
    with timing_tracker("启动 Python 编译流水线", is_total=True):
        for mod_path, mod_args in MODULES_CONFIG:
            build_mod(mod_path, mod_args)
