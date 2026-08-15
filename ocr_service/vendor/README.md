# NAS PaddlePaddle wheel

本目录中的 wheel 用于社会理论书库 OCR 容器。目标 NAS 的 Intel Celeron N5105 不支持 AVX，PaddlePaddle 官方 x86-64 wheel 会在导入阶段以退出码 132 终止。该文件由 PaddlePaddle 3.3.1 源码编译，并在目标 NAS 上完成断网运行测试。

## 固定版本

- 源码提交：`7688495538f4d6c1893f084dd238a402e8f68ab6`
- Python ABI：CPython 3.11
- wheel：`paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl`
- wheel 大小：120,997,886 字节
- SHA-256：`80d0ed4ce96859395cf634d4c3e06df4527ea2abdffc826f24b8f6bc68656f39`
- 原始 wheel SHA-256：`0b362c4777eb4f8df6d78c8fc1ff0a5dfb57fd7644ca3f646b06ecd6e873e2b3`
- auditwheel：6.7.0
- 最低审计平台标签：`manylinux_2_35_x86_64`

## 编译约束

编译使用 `-march=x86-64 -mtune=generic -mno-avx -mno-avx2 -mno-avx512f`。`WITH_AVX`、MKL、oneDNN、XBYAK、GPU 和分布式组件均关闭，BLAS 使用系统 OpenBLAS。源码树只增加了 `PADDLE_SKIP_SUBMODULE_UPDATE` 构建选项，以便使用事先固定并核验的第三方源码。该补丁 SHA-256 为 `d51ac28619a1ceba268e7744e1918b27e567591a6a027b7f72552962cb2d0408`。

打包前单独执行官方 `op_map_codegen` 目标。随后用 auditwheel 将 OpenBLAS 等非系统库封装进 wheel。封装后的 wheel 包含 `paddlepaddle.libs/libopenblasp-r0-234bd196.3.21.so`。

## 目标机验证

2026-08-08 在目标 NAS 的 Intel Celeron N5105 上，以 Docker `--network none` 安装并运行。检查结果为 `cpu_avx=false`、PaddlePaddle 3.3.1 导入成功、矩阵计算结果正确，`paddle.utils.run_check()` 通过。

Dockerfile 与升级脚本会在安装前复核 SHA-256。不要用同名文件替换该 wheel。更新 PaddlePaddle 时应生成新文件名、新校验值和新的目标机验证记录。
