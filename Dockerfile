FROM python:3.12-slim

WORKDIR /app

# 安装 CJK 字体（Pillow 生成图片用）+ 设置时区
RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-noto-cjk tzdata && \
    ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 暴露端口
EXPOSE 8080

# 启动 RSS 服务
CMD ["python", "rss_server.py"]
