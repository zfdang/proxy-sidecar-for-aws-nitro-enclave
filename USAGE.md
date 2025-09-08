# AWS Nitro Enclave Sidecar Proxy - 使用指南

## 项目概述

这个项目为运行在AWS Nitro Enclave环境中的应用提供了一个sidecar代理解决方案，使得enclave内的应用可以通过TLS加密与外部服务进行安全通信，确保host无法获取传输的内容。

## 架构组件

### 1. Sidecar服务 (`src/sidecar/main.py`)
- 运行在Nitro Enclave内部
- 处理与外部服务的TLS加密通信
- 使用VSock与host进行通信
- 实现端到端加密，host无法解密内容

### 2. Host Proxy服务 (`src/host_proxy/main.py`)
- 运行在host主机上
- 接收来自应用的HTTP请求
- 通过VSock转发到enclave内的sidecar
- 提供健康检查和监控功能

### 3. 演示应用 (`src/demo_app/main.py`)
- 展示sidecar代理能力的示例应用
- 测试多种HTTP请求类型
- 演示并发请求处理
- 生成测试报告

## 快速开始

### 1. 环境准备
```bash
# 安装依赖
pip install -r requirements.txt

# 或使用开发脚本安装
./scripts/dev.sh deps
```

### 2. 本地开发模式
```bash
# 启动开发环境
./scripts/dev.sh start

# 查看服务状态
./scripts/dev.sh status

# 查看日志
./scripts/dev.sh logs

# 运行测试
./scripts/dev.sh test
```

### 3. 本地运行（不使用Docker）
```bash
# 本地运行模式
./scripts/dev.sh local
```

## 构建和部署

### 1. 构建Docker镜像
```bash
# 构建所有组件
./scripts/build.sh

# 只构建Docker镜像
./scripts/build.sh docker

# 只构建Enclave镜像
./scripts/build.sh enclave
```

### 2. AWS EC2部署
```bash
# 1. 将构建产物复制到EC2实例
scp -r build/ ec2-user@your-instance:/home/ec2-user/

# 2. 在EC2实例上运行部署脚本
sudo ./deploy.sh
```

## 配置说明

### 主配置文件 (`config/config.json`)
```json
{
  "enclave": {
    "cid": 3,                    // Enclave CID
    "port": 5000,                // VSock端口
    "memory_mb": 512,            // 内存分配
    "cpu_count": 1               // CPU核心数
  },
  "host_proxy": {
    "port": 8080,                // HTTP代理端口
    "max_retries": 3,            // 最大重试次数
    "retry_delay": 1.0           // 重试延迟
  },
  "tls": {
    "min_version": "TLSv1.3",    // 最小TLS版本
    "verify_certificates": true   // 证书验证
  }
}
```

### 环境变量 (`config/.env`)
```bash
ENCLAVE_CID=3
ENCLAVE_PORT=5000
HOST_PROXY_PORT=8080
LOG_LEVEL=INFO
DEBUG_MODE=true
```

## API使用

### 健康检查
```bash
curl http://localhost:8080/health
```

### 代理外部服务
```bash
# GET请求
curl http://localhost:8080/https://httpbin.org/get

# POST请求
curl -X POST http://localhost:8080/https://httpbin.org/post \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

## 安全特性

### 1. 端到端TLS加密
- 所有外部通信使用TLS 1.3
- Host无法解密传输内容
- 支持证书验证

### 2. Enclave隔离
- 应用运行在Nitro Enclave内
- 内存加密和隔离
- 可验证的执行环境

### 3. VSock通信
- Enclave和Host之间使用VSock
- 安全的进程间通信
- 不经过网络栈

## 开发工具

### 开发脚本 (`scripts/dev.sh`)
```bash
./scripts/dev.sh start     # 启动开发环境
./scripts/dev.sh stop      # 停止开发环境
./scripts/dev.sh test      # 运行测试
./scripts/dev.sh logs      # 查看日志
./scripts/dev.sh clean     # 清理环境
./scripts/dev.sh local     # 本地运行
./scripts/dev.sh status    # 查看状态
```

### 构建脚本 (`scripts/build.sh`)
```bash
./scripts/build.sh build     # 完整构建
./scripts/build.sh docker    # 构建Docker镜像
./scripts/build.sh enclave   # 构建Enclave镜像
./scripts/build.sh clean     # 清理构建产物
```

## 监控和调试

### 1. 日志查看
```bash
# 查看所有服务日志
./scripts/dev.sh logs

# 查看特定服务日志
./scripts/dev.sh logs host-proxy

# 查看Enclave日志
sudo nitro-cli describe-enclaves
sudo nitro-cli console --enclave-id <enclave-id>
```

### 2. 性能监控
```bash
# 检查Enclave状态
sudo nitro-cli describe-enclaves

# 查看资源使用
docker stats

# 检查网络连接
netstat -tln | grep 8080
```

## 故障排除

### 1. 常见问题

#### Enclave启动失败
```bash
# 检查资源分配
sudo nitro-cli allocate-memory --memory 512

# 检查设备权限
ls -la /dev/nitro_enclaves

# 查看详细错误
sudo nitro-cli run-enclave --debug-mode ...
```

#### VSock连接失败
```bash
# 检查Enclave CID配置
sudo nitro-cli describe-enclaves

# 验证端口监听
sudo netstat -na | grep vsock
```

#### TLS连接错误
```bash
# 检查证书配置
openssl s_client -connect httpbin.org:443

# 验证TLS版本支持
python3 -c "import ssl; print(ssl.OPENSSL_VERSION)"
```

### 2. 调试模式
```bash
# 启用调试模式
export DEBUG_MODE=true

# 增加日志级别
export LOG_LEVEL=DEBUG

# 运行调试版本
./scripts/dev.sh local
```

## 生产环境部署

### 1. 系统要求
- AWS EC2 M5n, M5dn, R5n, R5dn, C5n 或 C6in 实例类型
- Amazon Linux 2 或 Ubuntu 18.04+
- 至少 1GB RAM 和 1 vCPU 用于enclave
- Docker 19.03+
- AWS Nitro CLI

### 2. 安全配置
- 禁用调试模式
- 使用生产证书
- 配置适当的IAM权限
- 启用CloudWatch监控

### 3. 监控和告警
- 集成CloudWatch Logs
- 配置健康检查告警
- 监控Enclave状态
- 设置性能指标

## 贡献指南

1. Fork项目
2. 创建功能分支
3. 编写测试
4. 提交代码
5. 创建Pull Request

## 许可证

MIT License - 详见LICENSE文件
