# Seeed Studio 产品认证信息查询系统

> 输入 SKU 号，查询产品的认证信息（CE / FCC / RoHS / KC 等）和证书 PDF 下载链接。
> 支持网页查询 + REST API + 飞书机器人集成。

---

## 目录

1. [它是什么](#1-它是什么)
2. [文件说明](#2-文件说明)
3. [安装 Python（只需一次）](#3-安装-python只需一次)
4. [本地快速启动（3 分钟）](#4-本地快速启动3-分钟)
5. [全量抓取所有 SKU 认证数据](#5-全量抓取所有-sku-认证数据)
6. [使用网页查询](#6-使用网页查询)
7. [部署到云服务器（Render 免费版）](#7-部署到云服务器render-免费版)
8. [飞书机器人集成（可选）](#8-飞书机器人集成可选)
9. [API 文档](#9-api-文档)
10. [常见问题](#10-常见问题)

---

## 1. 它是什么

这个程序从 [seeedstudio.com](https://www.seeedstudio.com/) 抓取所有产品的认证信息：

- **SKU 号**：如 `114993117`、`102110207` 等
- **认证类型**：CE（欧盟）、FCC（美国）、RoHS、UKCA（英国）、TELEC（日本）、KC（韩国）等
- **认证 PDF 文件**：每个认证对应的 PDF 证书下载链接
- **产品规格书**：产品规格 PDF 下载链接

**工作原理：**

```
用户输入 SKU 号 ──> 先查本地数据库 ──> 有缓存就直接返回
                        |
                        | 没有
                        v
                  在线探测认证 PDF ──> 返回认证信息
```

**两种使用方式：**

| 方式 | 说明 | 适合场景 |
|------|------|---------|
| 网页查询 | 浏览器打开网页，输入 SKU 查询 | 日常查询 |
| 飞书机器人 | 在飞书里发 SKU 号，机器人自动回复 | 团队协作 |

---

## 2. 文件说明

```
seeed-cert-agent/
├── scraper.py           # 抓取脚本：全量抓取 + 单 SKU 查询
├── app.py               # Web 服务：网页界面 + API + 飞书接口
├── templates/
│   └── index.html       # 网页查询界面
├── requirements.txt     # Python 依赖清单
├── .env.example         # 飞书配置模板
├── render.yaml          # Render 云部署配置
└── README.md            # 本文档
```

运行后会自动生成：

```
├── cert_data.db         # SQLite 数据库（存储抓取的认证数据）
```

---

## 3. 安装 Python（只需一次）

你的电脑需要先安装 Python 3.8 以上版本。

### Windows

1. 打开 https://www.python.org/downloads/windows/
2. 下载 **Python 3.12**（点击 "Windows installer (64-bit)"）
3. 运行安装程序，**务必勾选 "Add Python to PATH"**（页面最底部）
4. 点击 "Install Now" 等待完成

### 验证安装

打开命令行（按 `Win+R`，输入 `cmd`，回车），输入：

```bash
python --version
```

看到 `Python 3.12.x` 就说明安装成功。

### macOS

```bash
# 安装 Homebrew（如已安装可跳过）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# 安装 Python
brew install python
```

---

## 4. 本地快速启动（3 分钟）

### 第 1 步：安装依赖

打开命令行，进入项目文件夹：

```bash
cd seeed-cert-agent
```

安装依赖（只需一次）：

```bash
pip install -r requirements.txt
```

### 第 2 步：启动 Web 服务

```bash
python app.py
```

看到类似输出就成功了：

```
服务启动: http://localhost:5000
 * Running on http://0.0.0.0:5000
```

### 第 3 步：打开网页查询

浏览器打开 http://localhost:5000

在搜索框输入 SKU 号（如 `114993117`），点击"查询"。

> **注意**：首次查询某个 SKU 时，程序会在线探测该 SKU 的认证 PDF，需要等待 5-10 秒。之后同样的 SKU 会从数据库缓存秒回。

---

## 5. 全量抓取所有 SKU 认证数据

如果需要把所有产品的认证数据一次性抓取到本地数据库（方便离线快速查询），运行：

```bash
python scraper.py
```

程序会：
1. 从 sitemap.xml 获取所有产品页面（约 3100 个）
2. 逐个抓取页面，提取 SKU + 认证信息 + PDF 链接
3. 保存到 `cert_data.db` 数据库

**耗时**：约 60-80 分钟（每个页面间隔 1.2 秒，避免给服务器造成压力）

**进度显示**：终端会实时显示进度

```
正在获取 sitemap.xml ...
  共找到 3144 个产品页面
  [1/3144] SKU:102110207 | Raspberry Pi 3 Model A+ | 认证:3个
  [2/3144] SKU:102991022 | Wio LTE EU Version v1.3 | 认证:1个
  ...
  --- 进度: 200/3144 | 成功:195 跳过:0 失败:5 ---
```

**参数说明：**

```bash
python scraper.py              # 增量抓取（跳过24小时内已更新的，速度快）
python scraper.py --force      # 强制全量重新抓取所有
python scraper.py --delay 2    # 每次请求间隔2秒（调慢减轻服务器压力）
python scraper.py --sku 114993117  # 只查询单个SKU
```

> **建议**：定期运行 `python scraper.py`（如每周一次）保持数据更新。

---

## 6. 使用网页查询

启动服务后（`python app.py`），浏览器打开 http://localhost:5000

**查询界面功能：**
- 输入 SKU 号 → 显示认证类型、证书 PDF 链接、产品规格书
- 点击"查看 PDF"直接下载认证证书
- 页面底部显示数据库统计信息

---

## 7. 部署到云服务器（Render 免费版）

本地运行需要电脑一直开着。如果想 24 小时在线（方便团队访问和飞书集成），部署到云服务器。

### 第 1 步：上传代码到 GitHub

1. 注册 GitHub 账号（https://github.com）
2. 创建新仓库（New Repository），命名为 `seeed-cert-agent`
3. 将项目文件夹里的所有文件上传到仓库

### 第 2 步：注册 Render

1. 打开 https://render.com，注册账号
2. 用 GitHub 账号登录（推荐）

### 第 3 步：创建 Web 服务

1. 在 Render 控制台点击 "New +" → "Web Service"
2. 连接你的 GitHub 仓库
3. 配置：
   - **Name**：`seeed-cert-agent`
   - **Runtime**：Python 3
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`python app.py --port $PORT`
4. 点击 "Create Web Service"

### 第 4 步：等待部署完成

Render 会自动安装依赖并启动服务。部署成功后你会得到一个公网地址，如：

```
https://seeed-cert-agent.onrender.com
```

打开这个地址就能看到查询界面了！

### 第 5 步：在云端运行全量抓取

部署后数据库是空的。在 Render 的 "Shell" 功能里运行：

```bash
python scraper.py
```

> **注意**：Render 免费版有存储限制，数据库会在重启后清空。如需持久化存储，
> 可在 Render 中添加 PostgreSQL 数据库（需修改代码中的数据库连接）。
> 对于一般使用，建议本地运行全量抓取，云端用在线查询模式即可。

---

## 8. 飞书机器人集成（可选）

让飞书机器人接收 SKU 号消息，自动回复认证信息。

### 第 1 步：创建飞书应用

1. 打开 https://open.feishu.cn/ ，登录飞书开放平台
2. 点击 "开发者后台" → "创建企业自建应用"
3. 填写应用名称（如"认证查询机器人"）和描述
4. 创建后进入应用详情页，记录以下信息：
   - **App ID**（如 `cli_xxxxxxxx`）
   - **App Secret**（如 `xxxxxxxxxxx`）

### 第 2 步：配置机器人权限

1. 左侧菜单 → "权限管理"
2. 搜索并开通以下权限：
   - `im:message`（获取与发送消息）
   - `im:message.group_at_msg`（读取群聊@机器人消息）
   - `im:message.p2p_msg`（读取私聊消息）
3. 点击 "批量开通" → "确定"

### 第 3 步：配置事件订阅

1. 左侧菜单 → "事件与回调"
2. 编辑 "事件回调地址"，填入你的服务器地址：
   ```
   https://你的域名/feishu/webhook
   ```
   例如：`https://seeed-cert-agent.onrender.com/feishu/webhook`
3. 记录页面上的 **Verification Token** 和 **Encrypt Key**（如有）
4. 添加事件 → 搜索 `im.message.receive_v1`（接收消息）→ 勾选

### 第 4 步：配置环境变量

在 Render（或本地 `.env` 文件）中设置：

```
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxxxxx
FEISHU_ENCRYPT_KEY=（如启用了加密则填，否则留空）
```

本地使用时，复制 `.env.example` 为 `.env` 并填入上述值。

### 第 5 步：发布应用

1. 左侧菜单 → "版本管理与发布" → "创建版本"
2. 填写版本号和更新说明 → 提交审核
3. 审核通过后即可使用

### 第 6 步：使用

在飞书里找到你的机器人，发送 SKU 号（如 `114993117`），机器人会回复：

```
SKU: 114993117
认证: CE, EUDOC, FCC, ROHS, UKDOC

认证文件：
  [CE 认证（欧盟符合性）]
  https://files.seeedstudio.com/Seeed_Certificate/documents_certificate/114993117-CE.pdf
  [FCC 认证（美国联邦通信委员会）]
  https://files.seeedstudio.com/Seeed_Certificate/documents_certificate/114993117-FCC.pdf
  ...

产品规格书: https://files.seeedstudio.com/Bazaar/product_pdf/114993117.pdf
```

---

## 9. API 文档

### 查询 SKU 认证信息

```
GET /api/query?sku=114993117
```

**返回：**

```json
{
  "sku": "114993117",
  "found": true,
  "name": "EdgeBox RPi 200 - Raspberry Pi IoT Edge Device",
  "url": "https://www.seeedstudio.com/EdgeBox-RPi-200-p-5729.html",
  "cert_text": "RoHS, CE, FCC, TELEC, UKCA",
  "certifications": [
    {
      "type": "CE",
      "name": "CE 认证（欧盟符合性）",
      "pdf_url": "https://files.seeedstudio.com/Seeed_Certificate/documents_certificate/114993117-CE.pdf",
      "source": "certificate"
    },
    {
      "type": "FCC",
      "name": "FCC 认证（美国联邦通信委员会）",
      "pdf_url": "https://files.seeedstudio.com/Seeed_Certificate/documents_certificate/114993117-FCC.pdf",
      "source": "certificate"
    }
  ],
  "datasheet_url": "https://files.seeedstudio.com/Bazaar/product_pdf/114993117.pdf"
}
```

### 按产品名搜索

```
GET /api/search?name=EdgeBox
```

### 数据库统计

```
GET /api/stats
```

---

## 10. 常见问题

### Q: 查询某个 SKU 返回"未找到"？

确认 SKU 号是否正确。Seeed Studio 的 SKU 是 9 位数字（如 `114993117`），不是产品页面 URL 里的产品 ID（如 `5729`）。可以在产品页面的 HTML 源码中搜索 `"sku"` 找到正确的 SKU 号。

### Q: 首次查询很慢？

首次查询会在线逐个探测认证 PDF 是否存在（CE/FCC/RoHS/KC 等 8 种类型各请求一次），需要 5-10 秒。之后结果会缓存到数据库，再次查询秒回。运行 `python scraper.py` 全量抓取后所有 SKU 都有缓存。

### Q: 如何更新数据？

重新运行 `python scraper.py`。默认跳过 24 小时内已更新的产品，只抓取新增/变更的，速度快。如需强制全部刷新，用 `python scraper.py --force`。

### Q: 抓取被网站封锁了怎么办？

程序默认每次请求间隔 1.2 秒。如仍被封，可用 `--delay 3` 调慢间隔。

### Q: 数据库在哪？

数据库文件 `cert_data.db` 在项目文件夹根目录。可以用 DB Browser for SQLite（https://sqlitebrowser.org/）查看内容。

### Q: 飞书机器人不回复？

检查：
1. 服务器地址是否能从公网访问（本地运行需要用 ngrok 等内网穿透工具）
2. 环境变量 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 是否正确
3. 飞书应用是否已发布并审核通过
4. 机器人权限是否包含 `im:message`

### Q: 支持 KC 认证吗？

支持。程序会自动探测 KC、CE、FCC、RoHS、UKDOC、TELEC、UL、EUDOC 等认证类型的 PDF。只要 Seeed Studio 上传了对应的证书 PDF，就能查到。

---

## 认证类型对照表

| 代码 | 全称 | 地区 |
|------|------|------|
| CE | CE 认证 | 欧盟 |
| EUDOC | 欧盟符合性声明书 | 欧盟 |
| FCC | 美国联邦通信委员会认证 | 美国 |
| ROHS | 有害物质限制认证 | 全球 |
| UKDOC | 英国符合性声明（UKCA） | 英国 |
| TELEC | 日本无线电法认证 | 日本 |
| KC | 韩国认证 | 韩国 |
| UL | 美国安全认证 | 美国 |
