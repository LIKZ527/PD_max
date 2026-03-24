# 1. 基础镜像
FROM python:3.10-slim

# 2. 设置工作目录
WORKDIR /app

# 3. 复制依赖文件
COPY requirements.txt .

# 4. 安装依赖
RUN pip install --no-cache-dir -r requirements.txt
# 5. 复制项目代码
COPY . .

# 6. 暴露端口（按你项目改）
EXPOSE 8000

# 7. 启动命令（按你项目改）
CMD ["python", "app.py"]