# YYB-GO 本地部署包

## 文件说明

| 文件 | 说明 |
|------|------|
| `yyb-go` | 预编译二进制（linux/amd64，34MB） |
| `resource/` | 资源目录（模板、静态文件、数据库、二维码） |
| `resource/db/yyb.db` | 账号数据库（含已登录微信账号） |
| `yyb_refresh.py` | Token 刷新脚本（Python3，纯标准库） |
| `Dockerfile` | Docker 镜像构建文件 |
| `docker-compose.yml` | Docker Compose 一键部署 |

## 快速启动

### 方式一：Docker Compose（推荐）
```bash
docker compose up -d
```
服务运行在 `http://localhost:8002`

### 方式二：Docker 直接运行
```bash
docker build -t yyb-go:local .
docker run -d --name yyb-go --restart unless-stopped \
  -p 8002:8002 \
  -v $(pwd)/resource:/app/resource \
  yyb-go:local
```

### 方式三：直接运行（需 linux/amd64）
```bash
./yyb-go -host 0.0.0.0 -port 8002 -resource-root ./resource
```

## 接口说明

| 路径 | 用途 |
|------|------|
| `GET /` | 管理控制台（账号管理、状态查看） |
| `GET /scan` | 扫码登录页面（添加微信账号） |
| `GET /accounts` | 账号列表 API |
| `POST /accounts/refresh` | 刷新所有账号存活状态 |
| `POST /wxapp/getCode` | 获取微信小程序 code（青龙脚本调用） |
| `GET /health` | 健康检查 |

## Token 刷新（每日定时）

```bash
# 青龙容器内执行（默认地址 http://172.18.0.1:8002）
python3 yyb_refresh.py

# 本地执行（需指定地址）
YYB_GO_BASE=http://localhost:8002 python3 yyb_refresh.py
```

脚本逻辑：检测账号状态 → 全部健康则跳过 → 有过期则自动刷新 → 409 re-scan 提示人工扫码。

## 青龙集成

青龙环境变量配置：
```
YYB_GO = 宿主机IP:8002@账号openid
```

例如：
```
YYB_GO = 172.17.0.1:8002@owNAX6voamoUZDO-qNXghyALIPCo
```

## 注意事项

1. `resource/db/yyb.db` 包含微信登录态，迁移到新机器后可能需要重新扫码（login_buffer 过期）
2. 容器化部署需安装 `ca-certificates` 以验证微信 HTTPS 证书
3. 二进制仅支持 linux/amd64，其他平台需用源码重新编译（`go build -o yyb-go ./cmd/yyb-go`）
