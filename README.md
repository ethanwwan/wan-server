# WAN Server

轻量级 API 后端服务，提供 IPTV 配置管理和 TVBox 配置更新等功能。

## 功能特性

- **IPTV 配置管理**
  - 提供收藏频道的 M3U 配置文件访问
  - 支持 NAS 存储的 M3U 播放列表
- **TVBox 配置管理**
  - 动态生成 TVBox 配置文件访问接口
  - 支持配置文件 URL 和名称修改
  - 自动映射本地配置文件
- **轻量级架构**
  - 基于 FastAPI 构建，性能优异
  - 模块化设计，易于扩展

## 技术栈

- Python 3.8+
- FastAPI 0.115.2
- Uvicorn 0.32.0
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
│   └── tvbox/           # TVBox 相关 API
│       └── tvbox_api.py  # TVBox API 接口
├── scheduler/           # 调度器模块
│   ├── iptv_scheduler.py    # IPTV 配置调度
│   └── tvbox_scheduler.py   # TVBox 配置调度
├── scripts/             # 脚本模块
│   └── run_all_schedulers.py  # 统一调度脚本
├── utils/               # 工具模块
│   ├── iptv_config.py   # IPTV 配置
│   ├── iptv_checker.py  # IPTV 检测器
│   ├── iptv_utils.py    # IPTV 工具
│   ├── cache_manager.py # 缓存管理
│   └── logger.py        # 日志配置
├── input/               # 输入文件目录
│   └ iptv_urls.txt      # IPTV URL 配置
├── output/              # 输出文件目录
│   ├── iptv/            # IPTV 输出
│   └── tvbox/           # TVBox 输出
├── .github/             # GitHub 配置
│   └ workflows/         # GitHub Actions 工作流
├── .gitignore           # Git 忽略文件
├── main.py              # 主入口文件
├── README.md            # 项目文档
└── requirements.txt     # 依赖文件
```

## 快速开始

### 1. 环境要求

- Python 3.8 或更高版本
- pip 包管理工具
- FFmpeg（用于 IPTV 频道检测）

### 2. 安装依赖

```bash
# 克隆项目
git clone https://github.com/ethanwwan/wan-server.git
cd wan-server

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
# macOS/Linux
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 运行服务

```bash
# 直接运行
python3 main.py

# 或使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8016
```

服务默认运行在 `http://localhost:8016`

### 4. 运行定时任务

定时任务通过 GitHub Actions 自动执行，也可以手动运行：

```bash
# 手动执行所有调度任务
python3 scripts/run_all_schedulers.py
```

## API 文档

### 基础路由

- `GET /` - 服务状态检查（重定向到文档页面）

### IPTV 相关路由

- `GET /iptv/favlist.m3u` - 获取 IPTV 收藏频道 M3U 配置
- `GET /iptv/{file_name}` - 获取 IPTV M3U 文件（支持 ott.m3u、playlist.m3u 等）

### TVBox 相关路由

- `GET /api/tvbox/config.json` - 获取 TVBox 配置文件（特殊处理，修改 URL 和名称）
- `GET /api/tvbox/{file_name}.json` - 获取 TVBox 配置文件（支持 config.json、xiaomi.json、duo.json、fm.json 等）

### API 文档访问

启动服务后，可以通过以下地址访问 API 文档：

- Swagger UI: `http://localhost:8016/docs`
- ReDoc: `http://localhost:8016/redoc`

## GitHub Actions

项目使用 GitHub Actions 进行定时任务调度：

- **schedule-job.yml** - 每天 22:00（北京时间）执行 TVBox 和 IPTV 配置更新
- **sync-to-gist.yml** - 手动触发，同步 output 目录到 Gist

## 开发指南

### 代码风格

- 遵循 PEP 8 编码规范
- 使用 4 个空格进行缩进
- 函数和方法使用文档字符串

### 新增 API 模块

1. 在 `api/` 目录下创建新的模块目录
2. 创建相应的 API 路由和工具文件
3. 在 `api/base/routes.py` 中注册新的路由

## 故障排除

### 常见问题

1. **端口被占用**
   - 修改 `main.py` 中的 `SERVER_PORT` 配置

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

### v1.2.0
- 删除 Singbox 相关功能
- 删除 Docker 部署支持
- 删除配置文件，改为硬编码配置
- 定时任务改为 GitHub Actions 执行
- 优化 IPTV 检测逻辑和缓存策略

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
- 集成后台任务调度