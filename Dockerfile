# 纯标准库，运行时零第三方依赖；镜像里只留运行所需文件。
FROM python:3.11-slim

WORKDIR /app

# 先拷依赖声明（本项目无第三方依赖），再拷代码，利用镜像层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true

COPY recipe ./recipe
COPY web ./web
COPY web.py ./

# PaaS 会注入 PORT；HOST 固定 0.0.0.0 以便公网访问
ENV HOST=0.0.0.0
EXPOSE 8765

CMD ["python", "web.py"]
