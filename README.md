# WAN Server

轻量级 API 后端服务，提供 IPTV 配置管理和 Singbox 配置更新等功能。

## 功能特性

- **IPTV 配置管理**
  - 提供收藏频道的 M3U 配置文件访问
  - 支持 NAS 存储的 M3U 播放列表
- **Singbox 配置管理**
  - 定时更新 Singbox 配置
  - 提供配置访问接口
- **TVBox 配置管理**
  - 动态生成 TVBox 配置文件访问接口
  - 支持配置文件 URL 和名称修改
  - 自动映射本地配置文件
- **后台任务调度**
  - 每 8 小时自动更新 Singbox 配置
  - 每 8 小时自动更新 TVBox 配置
- **轻量级架构**
  - 基于 FastAPI 构建，性能优异
  - 模块化设计，易于扩展

## 技术栈

- Python 3.8+
- FastAPI 0.115.2
- Uvicorn 0.32.0
- APScheduler 3.10.4
- Requests 2.32.3

## 项目结构

```
wan-server/
├── api/                 # API 模块
│   ├── base/            # 基础模块
│   │   ├── response.py  # 响应处理
│   │   └── routes.py    # 基础路由
│   ├── common/          # 通用模块
│   ├── iptv/            # IPTV 相关 API
│   │   ├── iptv_api.py          # IPTV API 接口
│   │   ├── iptv_favorite_utils.py  # 收藏频道工具
│   │   └── iptv_nas_utils.py       # NAS 播放列表工具
│   ├── singbox/         # Singbox 相关 API
│   │   └── singbox_api.py  # Singbox API 接口
│   └── tvbox/           # TVBox 相关 API
│       └── tvbox_api.py  # TVBox API 接口
├── scheduler/           # 调度器模块
│   ├── singbox_scheduler.py  # Singbox 配置调度
│   └── tvbox_scheduler.py    # TVBox 配置调度
├── public/              # 静态文件目录
│   └── tvbox/           # TVBox 配置文件目录
├── .github/             # GitHub 配置
├── .gitignore           # Git 忽略文件
├── Dockerfile           # Docker 配置
├── docker-compose.yml   # Docker Compose 配置
├── main.py              # 主入口文件
├── README.md            # 项目文档
└── requirements.txt     # 依赖文件
```

## 快速开始

### 1. 环境要求

- Python 3.8 或更高版本
- pip 包管理工具

### 2. 安装依赖

```bash
# 克隆项目
git clone https://github.com/ethanwwan/wan-server.git
cd wan-server

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
# Windows
transformer_venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置文件

根据需要修改相关配置：

- `api/iptv/iptv_favorite_utils.py` - IPTV 收藏频道配置
- `api/iptv/iptv_nas_utils.py` - NAS 播放列表配置
- `scheduler/singbox_scheduler.py` - Singbox 配置
- `scheduler/tvbox_scheduler.py` - TVBox 配置
- `public/tvbox/` - TVBox 配置文件目录（放置 JSON 格式的配置文件）

### 4. 运行服务

```bash
# 直接运行
python3 main.py

# 或使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

服务默认运行在 `http://localhost:8000`

### 5. Docker 部署

#### 5.1 使用官方镜像

```bash
# 拉取镜像
docker pull docker.io/ethanwwan/wan-server:latest

# 运行容器
docker run -d \
  --name wan-server \
  -p 8000:8000 \
  docker.io/ethanwwan/wan-server:latest
```

#### 5.2 使用 Docker Compose

```bash
# 编辑 docker-compose.yml 文件（如果需要）
# 然后运行
docker-compose up -d
```

#### 5.3 本地构建镜像

```bash
# 克隆项目并进入目录
git clone https://github.com/ethanwwan/wan-server.git
cd wan-server

# 构建镜像
docker build -t wan-server .

# 运行容器
docker run -p 8000:8000 wan-server
```

## API 文档

### 基础路由

- `GET /` - 服务状态检查

### IPTV 相关路由

- `GET /iptv/favorite.m3u` - 获取 IPTV 收藏频道 M3U 配置
- `GET /iptv/playlist.m3u` - 获取 IPTV NAS 播放列表

### Singbox 相关路由

- 详见 `api/singbox/singbox_api.py`

### TVBox 相关路由

- `GET /api/tvbox/config.json` - 获取 TVBox 配置文件（特殊处理，修改 URL 和名称）
- `GET /api/tvbox/{file_name}.json` - 获取 TVBox 配置文件（自动生成的路由，返回原始内容）

### API 文档访问

启动服务后，可以通过以下地址访问 API 文档：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 后台任务

服务启动时会自动初始化后台任务调度器：

- 每 8 小时执行一次 Singbox 配置更新
- 每 8 小时执行一次 TVBox 配置更新

## 开发指南

### 代码风格

- 遵循 PEP 8 编码规范
- 使用 4 个空格进行缩进
- 函数和方法使用文档字符串

### 新增 API 模块

1. 在 `api/` 目录下创建新的模块目录
2. 创建相应的 API 路由和工具文件
3. 在 `main.py` 中注册新的路由

### 测试

```bash
# 运行服务并测试 API 响应
python3 main.py
# 然后使用 curl 或浏览器访问 API 端点
```

## 故障排除

### 常见问题

1. **端口被占用**
   - 修改 `main.py` 中的端口配置

2. **依赖安装失败**
   - 确保 Python 版本正确
   - 尝试使用 `pip install --upgrade pip` 更新 pip

3. **API 访问失败**
   - 检查服务是否正常运行
   - 检查网络连接
   - 查看服务日志

### 日志查看

服务运行时会在控制台输出日志信息，可用于排查问题。

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### v1.1.0
- 新增 TVBox 配置管理功能
  - 动态生成 TVBox 配置文件访问接口
  - 支持配置文件 URL 和名称修改
  - 自动映射本地配置文件
- 新增 tvbox_scheduler.py 调度模块
- 优化路由生成逻辑，解决路由冲突问题

### v1.0.0
- 初始版本
- 实现 IPTV 配置管理功能
- 实现 Singbox 配置管理功能
- 集成后台任务调度
- 支持 Docker 部署
