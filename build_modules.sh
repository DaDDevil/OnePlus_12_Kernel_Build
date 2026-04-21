#!/bin/bash
# 遇到错误立即停止执行
set -e 

# 检查环境变量
if [ -z "$KERNEL_SRC" ]; then
    echo -e "\033[31m[!] 请先配置 \$KERNEL_SRC 环境变量 (内核源码路径)\033[0m"
    exit 1
fi

# 核心根目录：/home/loopcat/op12/sm8650-modules
BASE_DIR="$(pwd)"
ALL_SYMVERS=""

# 1. 执行内核模块标准清理
find . -type f \( -name "*.o" -o -name "*.ko" -o -name "*.mod.c" -o -name ".*.cm
d" -o -name "Module.symvers" -o -name "modules.order" \) -delete

# ================= 通用编译函数 =================
# 参数1: 模块相对路径 (例如 oplus/display)
# 参数2及之后: 该模块专属的变量
build_mod() {
    local rel_path=$1
    shift 
    
    local full_path="$BASE_DIR/$rel_path"
    
    # 检查目录是否存在
    if [ ! -d "$full_path" ]; then
        echo -e "\n\033[33m[!] 跳过: 目录 $rel_path 不存在\033[0m"
        return
    fi

    echo -e "\n\033[34m>>> 正在编译: $rel_path \033[0m"
    cd "$full_path"
    
    # 执行编译 (自动带入 ALL_SYMVERS 中累积的所有符号)
    make $MAKE_ENV KCFLAGS="-Wno-error" -C "$KERNEL_SRC" M="$(pwd)" \
         KBUILD_EXTRA_SYMBOLS="$ALL_SYMVERS" "$@" modules -j8
    
    # 编译成功后，将生成的 Module.symvers 路径存入变量，供后续模块使用
    if [ -f "Module.symvers" ]; then
        ALL_SYMVERS="$ALL_SYMVERS $(pwd)/Module.symvers"
    fi
}

# ================= 1. 基础内核与框架模块 =================
build_mod qcom/opensource/securemsm-kernel SSG_MODULE_ROOT="$BASE_DIR/qcom/opensource/securemsm-kernel"
build_mod qcom/opensource/dsp-kernel       DSP_ROOT="$BASE_DIR/qcom/opensource/dsp-kernel"
build_mod qcom/opensource/synx-kernel      SYNX_ROOT="$BASE_DIR/qcom/opensource/synx-kernel"
build_mod qcom/opensource/spu-kernel       SPU_ROOT="$BASE_DIR/qcom/opensource/spu-kernel"
build_mod qcom/opensource/mmrm-driver      MMRM_ROOT="$BASE_DIR/qcom/opensource/mmrm-driver"

# ================= 2. 内存管理及 Fence 驱动 =================
# 原命令中 $(pwd)/../ 实际上就是指向 mm-drivers 目录
build_mod qcom/opensource/mm-drivers/hw_fence        MSM_HW_FENCE_ROOT="$BASE_DIR/qcom/opensource/mm-drivers"
build_mod qcom/opensource/mm-drivers/msm_ext_display MSM_EXT_DISPLAY_ROOT="$BASE_DIR/qcom/opensource/mm-drivers"
build_mod qcom/opensource/mm-drivers/sync_fence      SYNC_FENCE_ROOT="$BASE_DIR/qcom/opensource/mm-drivers"
build_mod qcom/opensource/mm-sys-kernel/ubwcp

# ================= 3. 数据与网络模块 (RmNet / IPA) =================
build_mod qcom/opensource/datarmnet-ext/mem
build_mod qcom/opensource/dataipa        KP_MODULE_ROOT="$BASE_DIR/qcom/opensource/dataipa"
build_mod qcom/opensource/datarmnet/core RMNET_CORE_ROOT="$BASE_DIR/qcom/opensource/datarmnet/core"

# 批量合并编译 datarmnet-ext 的扩展模块，它们统一依赖相同的 ccflags
for ext in aps offload wlan perf_tether shs perf sch; do
    build_mod "qcom/opensource/datarmnet-ext/$ext" ccflags-y="-I$BASE_DIR/qcom/opensource/datarmnet/core"
done

# ================= 4. EVA 及多媒体核心驱动 =================
build_mod qcom/opensource/eva-kernel EVA_ROOT="$BASE_DIR/qcom/opensource/eva-kernel"

# 定义开发板通用变量，进一步缩减代码长度
BP="BOARD_PLATFORM=pineapple"

build_mod qcom/opensource/display-drivers $BP DISPLAY_ROOT="$BASE_DIR/qcom/opensource/display-drivers" CONFIG_DRM_MSM=m CAIHONG_DISPLAY_DRIVER=y
build_mod qcom/opensource/graphics-kernel $BP KGSL_MODULE_ROOT="$BASE_DIR/qcom/opensource/graphics-kernel"
build_mod qcom/opensource/video-driver    $BP VIDEO_ROOT="$BASE_DIR/qcom/opensource/video-driver"
build_mod qcom/opensource/wlan/platform   $BP WLAN_PLATFORM_ROOT="$BASE_DIR/qcom/opensource/wlan/platform"
build_mod qcom/opensource/wlan/qcacld-3.0 $BP WLAN_ROOT="$BASE_DIR/qcom/opensource/wlan/qcacld-3.0" WLAN_PROFILE=kiwi_v2 CONFIG_QCA_CLD_WLAN=m MODNAME=qca_cld3_kiwi_v2
build_mod qcom/opensource/bt-kernel       $BP BT_ROOT="$BASE_DIR/qcom/opensource/bt-kernel" CONFIG_BT_HW_SECURE_DISABLE=y CONFIG_MSM_BT_POWER=m CONFIG_BTFM_SLIM=m
build_mod qcom/opensource/camera-kernel   $BP CAMERA_KERNEL_ROOT="$BASE_DIR/qcom/opensource/camera-kernel" KERNEL_ROOT="$KERNEL_SRC"
build_mod qcom/opensource/audio-kernel    $BP AUDIO_ROOT="$BASE_DIR/qcom/opensource/audio-kernel" MODNAME=audio_dlkm

# ================= 5. nxp && oplus 驱动 =================
build_mod nxp/opensource/driver $BP NFC_ROOT="$BASE_DIR/nxp/opensource/driver"
build_mod oplus/secure/biometrics/fingerprints/bsp/uff/driver $BP
build_mod oplus/secure/common/bsp/drivers $BP CONFIG_OPLUS_SECURE_COMMON=m
build_mod oplus/sensor/kernel/oplus_consumer_ir $BP
build_mod oplus/sensor/kernel/qcom/sensor $BP
build_mod oplus/kernel/device_info/pogo_keyboard $BP
build_mod oplus/kernel/device_info/tri_state_key $BP
build_mod oplus/kernel/cpu/thermal $BP
build_mod oplus/kernel/dfr $BP
build_mod oplus/kernel/graphics $BP
build_mod oplus/kernel/touchpanel/oplus_touchscreen_v2/touch_custom $BP
build_mod oplus/kernel/touchpanel/oplus_touchscreen_v2 $BP
build_mod oplus/kernel/touchpanel/synaptics_hbp $BP
build_mod oplus/kernel/tp/hbp/hbp $BP
build_mod oplus/kernel/network/oplus_network_oem_qmi $BP
build_mod oplus/kernel/network/oplus_network_sim_detect $BP
build_mod oplus/kernel/network/oplus_rf_cable_monitor $BP
build_mod oplus/kernel/network/oplus_network_esim $BP
echo -e "\n\033[42;37m 所有模块编译完成！ \033[0m"
