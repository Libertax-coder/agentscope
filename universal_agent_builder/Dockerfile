# Universal Agent Builder Sandbox
FROM ubuntu:22.04

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 安装基础工具
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 3.11
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# 设置 Python 3.11 为默认
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# 安装 Node.js 18
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 安装 Playwright 和浏览器
RUN pip3 install playwright \
    && playwright install --with-deps chromium

# 创建工作目录
WORKDIR /workspace

# 安装常用 Python 包
RUN pip3 install --no-cache-dir \
    pandas \
    matplotlib \
    seaborn \
    numpy \
    scipy \
    requests \
    beautifulsoup4

# 资源限制由 docker run 参数控制:
# docker run --cpus=2 --memory=4g --storage-opt size=10g ...

# 默认命令
CMD ["/bin/bash"]
