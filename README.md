# API Server

轻量级API后端服务，提供IPTV配置管理和Singbox配置更新等功能。

## 功能特性

- **IPTV配置管理**
  - 提供收藏频道的M3U配置文件访问
  - 支持NAS存储的M3U播放列表
- **Singbox配置管理**
  - 定时更新Singbox配置
  - 提供配置访问接口
- **TVBox配置管理**
  - 动态生成TVBox配置文件访问接口
  - 支持配置文件URL和名称修改
  - 自动映射本地配置文件
- **后台任务调度**
  - 每8小时自动更新Singbox配置
  - 每8小时自动更新TVBox配置
- **轻量级架构**
  - 基于FastAPI构建，性能优异
  - 模块化设计，易于扩展

## 技术栈

- Python 3.8+
- FastAPI 0.115.2
- Uvicorn 0.32.0
- APScheduler 3.10.4
- Requests 2.32.3

## 项目结构

```
api-server/
├── api/                 # API模块
│   ├── base/            # 基础模块
│   │   ├── response.py  # 响应处理
│   │   └── routes.py    # 基础路由
│   ├── common/          # 通用模块
│   ├── iptv/            # IPTV相关API
│   │   ├── iptv_api.py          # IPTV API接口
│   │   ├── iptv_favorite_utils.py  # 收藏频道工具
│   │   └── iptv_nas_utils.py       # NAS播放列表工具
│   ├── singbox/         # Singbox相关API
│   │   └── singbox_api.py  # Singbox API接口
│   └── tvbox/           # TVBox相关API
│       └── tvbox_api.py  # TVBox API接口
├── scheduler/           # 调度器模块
│   ├── singbox_scheduler.py  # Singbox配置调度
│   └── tvbox_scheduler.py    # TVBox配置调度
├── public/              # 静态文件目录
│   └── tvbox/           # TVBox配置文件目录
├── .github/             # GitHub配置
├── .gitignore           # Git忽略文件
├── Dockerfile           # Docker配置
├── docker-compose.yml   # Docker Compose配置
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
git clone <repository-url>
cd api-server

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

- `api/iptv/iptv_favorite_utils.py` - IPTV收藏频道配置
- `api/iptv/iptv_nas_utils.py` - NAS播放列表配置
- `scheduler/singbox_scheduler.py` - Singbox配置
- `scheduler/tvbox_scheduler.py` - TVBox配置
- `public/tvbox/` - TVBox配置文件目录（放置JSON格式的配置文件）

### 4. 运行服务

```bash
# 直接运行
python3 main.py

# 或使用uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

服务默认运行在 `http://localhost:8000`

### 5. Docker 部署

#### 5.1 使用官方镜像

```bash
# 拉取镜像
docker pull docker.io/ethanwwan/api-server:latest

# 运行容器
docker run -d \
  --name api-server \
  -p 8000:8000 \
  docker.io/ethanwwan/api-server:latest
```

#### 5.2 使用Docker Compose

```bash
# 编辑docker-compose.yml文件（如果需要）
# 然后运行
docker-compose up -d
```

#### 5.3 本地构建镜像

```bash
# 克隆项目并进入目录
git clone <repository-url>
cd api-server

# 构建镜像
docker build -t api-server .

# 运行容器
docker run -p 8000:8000 api-server
```

## API 文档

### 基础路由

- `GET /` - 服务状态检查

### IPTV 相关路由

- `GET /iptv/favorite.m3u` - 获取IPTV收藏频道M3U配置
- `GET /iptv/playlist.m3u` - 获取IPTV NAS播放列表

### Singbox 相关路由

- 详见 `api/singbox/singbox_api.py`

### TVBox 相关路由

- `GET /api/tvbox/config.json` - 获取TVBox配置文件（特殊处理，修改URL和名称）
- `GET /api/tvbox/{file_name}.json` - 获取TVBox配置文件（自动生成的路由，返回原始内容）

### API 文档访问

启动服务后，可以通过以下地址访问API文档：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 后台任务

服务启动时会自动初始化后台任务调度器：

- 每8小时执行一次Singbox配置更新
- 每8小时执行一次TVBox配置更新

## 开发指南

### 代码风格

- 遵循PEP 8编码规范
- 使用4个空格进行缩进
- 函数和方法使用文档字符串

### 新增API模块

1. 在 `api/` 目录下创建新的模块目录
2. 创建相应的API路由和工具文件
3. 在 `main.py` 中注册新的路由

### 测试

```bash
# 运行服务并测试API响应
python3 main.py
# 然后使用curl或浏览器访问API端点
```

## 故障排除

### 常见问题

1. **端口被占用**
   - 修改 `main.py` 中的端口配置

2. **依赖安装失败**
   - 确保Python版本正确
   - 尝试使用 `pip install --upgrade pip` 更新pip

3. **API访问失败**
   - 检查服务是否正常运行
   - 检查网络连接
   - 查看服务日志

### 日志查看

服务运行时会在控制台输出日志信息，可用于排查问题。

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎提交Issue和Pull Request！

## 更新日志

### v1.1.0
- 新增TVBox配置管理功能
  - 动态生成TVBox配置文件访问接口
  - 支持配置文件URL和名称修改
  - 自动映射本地配置文件
- 新增tvbox_scheduler.py调度模块
- 优化路由生成逻辑，解决路由冲突问题

### v1.0.0
- 初始版本
- 实现IPTV配置管理功能
- 实现Singbox配置管理功能
- 集成后台任务调度
- 支持Docker部署
