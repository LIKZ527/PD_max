# Docker 部署文档

---

## 一、环境准备

确保已安装 Docker，查看版本：
```bash
docker --version
```

---

## 二、单独启动（手动逐个）

### 1. 启动 MySQL

```bash
docker run -d \
  --name mysql-lite \
  --network mynet \
  -e MYSQL_ROOT_PASSWORD=123456 \
  -e MYSQL_DATABASE=demo \
  -p 3306:3306 \
  -v mysql_data:/var/lib/mysql \
  mysql:8.0
```

> 第一次运行需要先创建网络：
> ```bash
> docker network create new_rq_default
> ```

---

### 2. 构建后端镜像

```bash
docker build -t my-backend .
```

---

### 3. 启动后端

```bash
docker run -d \
  --name my-backend \
  --network mynet \
  -p 8000:8000 \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=your-password
  -e MYSQL_HOST=mysql-lite \
  -e MYSQL_PORT=3306 \
  -e MYSQL_USER=root \
  -e MYSQL_PASSWORD=123456 \
  -e MYSQL_DATABASE=demo \
  -e JWT_SECRET_KEY=your-secret-key \
  -e LLM_API_KEY=sk-sp-85d22a3083934e79850cba43520cc569 \
  -e LLM_BASE_URL=https://coding.dashscope.aliyuncs.com/v1\
  -e LLM_MODEL=qwen3.5-plus \
  my-backend
```

---

## 三、更新代码后重新部署

```bash
# 停止并删除旧容器
docker rm -f my-backend

# 重新构建镜像
docker build -t my-backend .

# 重新启动（同上 docker run 命令）
```

---

## 四、常用指令

### 查看容器状态
```bash
docker ps                  # 查看运行中的容器
docker ps -a               # 查看所有容器（含已停止）
```

### 查看日志
```bash
docker logs my-backend             # 查看全部日志
docker logs my-backend -f          # 实时跟踪日志
docker logs my-backend --tail 50   # 只看最后50行
```

### 启动 / 停止 / 重启
```bash
docker start my-backend
docker stop my-backend
docker restart my-backend
```

### 进入容器内部
```bash
docker exec -it my-backend bash
```

### 进入 MySQL
```bash
docker exec -it mysql-lite mysql -uroot -p123456 demo
```

### 删除容器
```bash
docker rm -f my-backend     # 强制删除（含运行中）
docker rm -f mysql-lite
```

### 查看镜像
```bash
docker images
```

### 删除镜像
```bash
docker rmi my-backend
```

### 查看网络
```bash
docker network ls
docker network inspect new_rq_default
```

### 查看数据卷
```bash
docker volume ls
docker volume inspect mysql_data
```

---

## 五、环境变量说明

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MYSQL_HOST` | MySQL 容器名或地址 | - |
| `MYSQL_PORT` | MySQL 端口 | 3306 |
| `MYSQL_USER` | MySQL 用户名 | - |
| `MYSQL_PASSWORD` | MySQL 密码 | - |
| `MYSQL_DATABASE` | 数据库名 | - |
| `JWT_SECRET_KEY` | JWT 签名密钥（同时用于 A5 改密校验） | change_this_to_a_strong_random_secret |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token 有效期（分钟） | 1440（24小时） |
| `ADMIN_USERNAME` | 默认管理员账号（首次启动自动创建） | admin |
| `ADMIN_PASSWORD` | 默认管理员密码（首次启动自动创建） | admin123 |
| `LLM_API_KEY` | LLM 接口 API Key | - |
| `LLM_BASE_URL` | LLM 接口 Base URL | https://api.anthropic.com |
| `LLM_MODEL` | LLM 模型名称 | claude-sonnet-4-6 |

---

## 六、接口访问

- 后端 API：http://localhost:8000
- Swagger 文档：http://localhost:8000/docs
- ReDoc 文档：http://localhost:8000/redoc
