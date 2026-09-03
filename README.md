# python-file-server

基于 uv 管理的 FastAPI + Uvicorn 文件服务器框架，接口全部使用 `async` 实现。

## 技术栈

- Python 3.13
- FastAPI
- Uvicorn
- Loguru
- uv 管理依赖和版本

## 快速开始

```bash
# 安装依赖
uv sync

# 启动开发服务器
uv run uvicorn main:app --reload --port 8000

# 调用接口
curl http://127.0.0.1:8000/api/hello

# 打开自动生成的接口文档
open http://127.0.0.1:8000/docs
```

## 当前接口

`GET /api/hello`

返回 JSON：

```json
{"message": "hello world"}
```

所有接口使用 `async def` 定义，便于处理 IO 密集型任务。

## 文件接口

| 方法 | 路径 | 场景 |
| --- | --- | --- |
| POST | `/api/files` | multipart 上传文件，返回文件元数据 |
| GET | `/api/files` | 文件元数据列表，支持 `keyword`、`limit`、`offset` |
| GET | `/api/files/{id}` | 单个文件元数据 |
| GET | `/api/files/{id}/chunks` | 分片清单，包含每片的 `seq`、`size`、`sha256` 和下载 URL |
| GET | `/api/files/{id}/chunks/{seq}` | 下载单个分片 |
| GET/HEAD | `/api/files/{id}/download` | 下载完整文件（内部跨分片虚拟流式读取，支持 `Range`） |
| DELETE | `/api/files/{id}` | 删除元数据和磁盘文件 |

上传落盘时按 `FILE_CHUNK_SIZE`（默认 8 MiB）自动切片，文件以分片形式保存在 `data/files/<storage_key>/<seq>.part`，不保留完整副本；元数据和分片索引保存在 SQLite `data/app.db`。`GET /download` 对外仍是完整文件下载，支持 `Range`/`HEAD`，由实现层跨分片流式读取。配置了 `API_TOKEN` 时，所有文件接口必须携带请求头 `X-API-Token: <token>`。

## Demo 接口场景

以下接口用于演示不同 HTTP 方法和错误场景，数据保存在内存中，服务重启后重置：

| 方法 | 路径 | 场景 |
| --- | --- | --- |
| GET | `/api/demo/files` | 文件列表 |
| GET | `/api/demo/files?keyword=main` | Query 参数过滤 |
| GET | `/api/demo/files/1` | 路径参数查询 |
| GET | `/api/demo/files/999` | 文件不存在，返回 30001 |
| POST | `/api/demo/files` | 请求体创建文件，返回 201 |
| POST | `/api/demo/files` | 非法参数，返回 HTTP 422 |
| PUT | `/api/demo/files/1` | 请求体更新文件 |
| DELETE | `/api/demo/files/1` | 删除文件 |
| GET | `/api/demo/auth/not-logged-in` | 未登录，返回 20001 |
| GET | `/api/demo/auth/account-disabled` | 账号异常，返回 20003 |
| GET | `/api/demo/error/unknown` | 未知异常，返回 99999 |
| GET | `/api/demo/error/service` | 组件异常，返回 40001 |

## 统一响应格式

正常业务响应统一返回以下结构：

```json
{
  "code": 0,
  "msg": "success",
  "data": {}
}
```

- `code=0` 表示业务成功
- `data` 为接口原始返回内容

程序中的业务错误通过 `BizError` 表达：

```python
from app.errors import FileNotFoundBizError

raise FileNotFoundBizError(msg="file not found")
```

对应响应：

```json
{
  "code": 30001,
  "msg": "file not found",
  "data": null
}
```

HTTP 状态码由异常决定：业务错误默认 HTTP 200，认证和资源类错误使用真实 HTTP 状态码。HTTP 层错误（如 404、405、500）不包装，交给 FastAPI 默认处理，HTTP 状态码保持正常语义。`/docs`、`/redoc`、`/openapi.json` 等文档接口也不包装。

统一中间件 `ApiMiddleware` 的职责：

- 放行 `/docs`、`/openapi.json` 等文档接口
- 捕获 `BizError` 及子类，返回业务错误码并记录 WARNING 日志
- 捕获 `SvcError`，对外返回 `internal server error`，通过错误码定位问题类型
- 捕获未知异常，返回 `99999 internal server error` 并记录服务器日志
- 包装正常 2xx 响应

错误语义：

- `BizError`：错误码和文案可以告知客户，如参数缺失、格式错误、文件不存在等。
- `SvcError`：明确捕获的已知内部异常，不向客户暴露真实文案，统一返回 `internal server error`，真实错误信息只进日志。
- 其他未捕获异常：说明系统设计未覆盖，返回 `99999 internal server error`，需要结合日志持续优化。

## 错误码表

错误码按大类分组，分类号只用于归类标识，实际响应返回具体错误码。

| 分类 | 错误码 | 含义 | HTTP 状态码 | 异常类 |
| --- | --- | --- | --- | --- |
| - | 0 | 成功 | 200 | - |
| 10000 参数类 | 10001 | 参数格式错误 | 422 | 预留 |
| 10000 参数类 | 10002 | 参数缺失 | 422 | 预留 |
| 20000 鉴权认证类 | 20001 | 未登录 | 401 | `NotLoggedInError` |
| 20000 鉴权认证类 | 20002 | 登录已过期 | 401 | 预留 |
| 20000 鉴权认证类 | 20003 | 账号被锁定或异常 | 403 | `AccountDisabledError` |
| 20000 鉴权认证类 | 20004 | 无权限 | 403 | 预留 |
| 30000 业务类 | 30001 | 文件不存在 | 404 | `FileNotFoundBizError` |
| 30000 业务类 | 30002 | 文件已存在 | 409 | 预留 |
| 30000 业务类 | 30003 | 文件过大 | 413 | `FileTooLargeError` |
| 30000 业务类 | 30004 | 文件分片不存在 | 404 | `ChunkNotFoundBizError` |
| 40000 组件类 | 40001 | 数据库调用失败 | 500 | `DatabaseError` |
| 40000 组件类 | 40002 | 系统命令调用失败 | 500 | `SystemCommandError` |
| 40000 组件类 | 40003 | 外部接口调用失败 | 500 | `ExternalAPIError` |
| 40000 组件类 | 40004 | 文件数据缺失 | 500 | `FileDataMissingError` |
| 99999 未知 | 99999 | 未知异常 | 500 | 预留 |

## 日志与追踪

项目使用 Loguru 统一输出日志，启动时由 `app/logging_config.py` 中的 `setup_logging()` 完成配置，所有日志都会自动带上 B3 的 traceId/spanId。

### 日志输出

| 输出位置 | 说明 |
| --- | --- |
| stdout | 控制台日志，适合本地开发和 Docker 容器 |
| `logs/app_info_*.log` | 全量日志，记录 INFO 及以上级别 |
| `logs/app_wf_*.log` | 告警日志，只记录 WARNING/ERROR/CRITICAL |

日志文件按天切分，旧文件压缩为 zip 后保留：info 文件保留 30 天，wf 文件保留 90 天。`logs/` 目录已加入 `.gitignore`。

### 日志级别

| 级别 | 数值 | 典型用途 |
| --- | --- | --- |
| TRACE | 5 | 极细内部跟踪，默认不使用 |
| DEBUG | 10 | 开发调试 |
| INFO | 20 | 正常业务流程 |
| SUCCESS | 25 | 成功事件 |
| WARNING | 30 | 不致命但需要注意 |
| ERROR | 40 | 业务或系统错误 |
| CRITICAL | 50 | 致命错误 |

### 请求追踪

`TraceMiddleware` 负责 B3 链路追踪 id：

- `X-B3-TraceId`：32 位十六进制，上游透传合法值，否则生成
- `X-B3-SpanId`：16 位十六进制，每次请求生成新的 spanId
- 上游携带的 spanId 作为 parentSpanId，只存上下文不展示
- 响应头回写 `X-B3-TraceId` 和 `X-B3-SpanId`
- 该请求内的应用日志、异常日志和访问日志共用同一对 traceId/spanId
- 无请求上下文时，日志中的 traceId/spanId 显示为 `-`

验证方式：

```bash
# 查看响应头中的 X-B3-TraceId 和 X-B3-SpanId
curl -i http://127.0.0.1:8000/api/hello

# 主动透传 traceId 和上游 spanId
curl -i \
  -H "X-B3-TraceId: 463ac35c9f6413ad48485a3953bb6124" \
  -H "X-B3-SpanId: a2fb4a1d1a96d312" \
  http://127.0.0.1:8000/api/hello

# 触发未知异常，观察 ERROR 日志与访问日志使用同一对 traceId/spanId
curl http://127.0.0.1:8000/api/demo/error/unknown

# 查看日志
tail -f logs/app_info_$(date +%F).log
tail -f logs/app_wf_$(date +%F).log
```

注意：使用 `--reload` 启动时，reloader 进程自身输出的前几行仍为 Uvicorn 默认格式，应用进程日志统一走 Loguru。

## RESTful 风格

- 资源：URL 代表资源，例如 `/api/files` 表示文件集合
- 方法：`GET` 查询、`POST` 创建、`PUT`/`PATCH` 更新、`DELETE` 删除
- 状态码：`200 OK`、`201 Created`、`400 Bad Request`、`404 Not Found` 等
- 无状态：每个请求携带完整信息，服务器不保存客户端会话状态
- 数据格式：通常使用 JSON
- 命名：资源用名词，集合常用复数，层级用路径表达

## 接口版本区隔

同一个接口需要升级且保持兼容时，常用以下方式区分版本：

- URL 路径：`/api/v1/hello`、`/api/v2/hello`，最直观，推荐使用
- Header：`Accept-Version: v1`，不影响 URL，但调试不方便
- Query：`/api/hello?version=v1`，简单但容易污染查询参数

本项目当前使用 `/api/hello`，暂不区分版本；后续新增 v1/v2 时按 URL 路径方式扩展。

## 工程结构

```text
main.py
app/
  __init__.py
  errors.py
  config.py
  db.py
  security.py
  storage.py
  responses.py
  middleware.py
  logging_config.py
  trace.py
  api/
    __init__.py
    files.py
    demo.py
    hello.py
```

- `main.py`：创建 FastAPI 应用并挂载路由
- `app/errors.py`：业务错误 `BizError`、错误码和异常子类
- `app/config.py`：环境变量配置
- `app/db.py`：SQLite 初始化和文件元数据读写
- `app/security.py`：API Token 鉴权依赖
- `app/storage.py`：文件流式分片落盘、删除和路径解析
- `app/responses.py`：跨分片虚拟文件下载响应，支持 `Range` 和 `HEAD`
- `app/api/files.py`：真实文件上传、列表、详情、分片、下载、删除接口
- `app/middleware.py`：API 中间件与 TraceMiddleware，处理响应包装、业务异常和请求追踪
- `app/logging_config.py`：Loguru 配置，stdout、info/wf 文件与 Uvicorn 日志接管
- `app/trace.py`：B3 traceId/spanId 上下文与生成逻辑
- `app/api/demo.py`：HTTP 方法和错误场景演示路由
- `app/api/hello.py`：hello 接口路由

## 环境要求

- 已安装 [uv](https://docs.astral.sh/uv/)
- Python 版本由 uv 管理，推荐 3.13

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `API_TOKEN` | 空 | API Token；为空时开发模式放行并告警 |
| `FILE_STORAGE_DIR` | `data/files` | 分片存储根目录 |
| `DB_PATH` | `data/app.db` | SQLite 数据库路径 |
| `MAX_UPLOAD_SIZE` | `104857600` | 单文件上传上限，单位字节 |
| `FILE_CHUNK_SIZE` | `8388608` | 上传自动切片大小，单位字节 |
| `PYTHON_BASE_IMAGE` | `python:3.13-slim` | Docker 运行阶段基础镜像，网络受限时可换成镜像加速源 |

## Docker 部署

```bash
# 构建并启动
API_TOKEN=your-token docker compose up -d --build

# 验证
curl -H "X-API-Token: your-token" http://127.0.0.1:8000/api/files
```

容器使用标准 uv 两阶段构建，运行阶段不再包含 uv。文件、数据库、日志分别挂载 volume，容器重建后数据不丢失。

部署时请务必设置 `API_TOKEN`；未设置时容器仍会启动，但文件接口不做鉴权并打印告警。

## 创建工程步骤

以下命令演示如何从空目录创建一个同样配置的工程：

```bash
# 1. 初始化应用工程，同时初始化 Git 并锁定 Python 3.13
uv init --app --vcs git --python 3.13 --name python-file-server .

# 2. 根据 pyproject.toml 生成 uv.lock，锁定依赖版本
uv lock

# 3. 按锁文件创建虚拟环境并同步依赖
uv sync

# 4. 添加 FastAPI 和 Uvicorn 依赖
uv add fastapi 'uvicorn[standard]'

# 5. 添加 Loguru 依赖
uv add loguru

# 6. 启动开发服务器
uv run uvicorn main:app --reload --port 8000
```

uv init 生成的 `main.py` 需要替换为本项目的 FastAPI 版本，并补充 `app/` 路由结构。

## 日常命令

```bash
# 安装或更新依赖，会自动更新 uv.lock
uv add <package>

# 同步锁文件中的依赖到虚拟环境
uv sync

# 在虚拟环境中运行命令
uv run <command>
```

## 版本锁定说明

- `.python-version` 固定 Python 版本，当前为 3.13
- `uv.lock` 固定所有直接依赖和间接依赖的精确版本
- 依赖变更后请提交 `pyproject.toml`、`uv.lock` 和 `.python-version` 的变更
