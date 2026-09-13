# 寻图：GitHub + Railway 在线部署重建版

原 ZIP 无法取得，本项目按对话中确认的功能重新实现，不是原代码的逐行迁移。
你只需要浏览器和解压 ZIP，不需要在电脑安装 Docker、Python 或 Node。

## 包含什么

- 中文网页：图片入库、图片搜索、搜索方式切换、返回 X 原帖链接。
- FastAPI 后端；真实 pHash 和固定版本 CLIP ViT-B/32 的 512 维归一化向量。
- PostgreSQL + pgvector；自动执行 db/init.sql，创建向量索引。
- 原帖链接由入库时填写；不自动辨认作者，不抓取 X，不包含 X API 采集器。
- 图片缩略图和向量保存到数据库。查询图片只在请求中处理，不持久保存。
- 全站密码保护，用户名 admin。适合个人、小规模图库；不是开放注册的公共平台。
- 同图差异越小越接近；视觉相似和综合排序分越大越接近。分数不是匹配概率。
- CLIP 搜索总会返回候选，大幅裁剪、边框、截图可能降低准确率。

## 1. 上传到 GitHub

1. 下载 ZIP，双击解压，打开 x-image-search-railway 文件夹。
2. 打开 https://github.com/new 。如果出现 Sign in，先登录；没有账号点 Create an account。
3. Repository name 填 x-image-search-railway。
4. 选择 Private；其余保持默认；点击 Create repository。
5. 空仓库页面点击 uploading an existing file。已有内容的仓库用 Add file → Upload files。
6. 把解压文件夹**里面的文件和文件夹**拖进去，不要上传 ZIP，也不要把外层文件夹一起套进去。
7. 点击 Commit changes。仓库首页应直接看到 Dockerfile、requirements.txt、railway.toml、app、db。
8. Mac 默认隐藏 .env.example 等点开头文件，未上传不影响运行。环境变量说明也在 ENVIRONMENT.txt 中。不要上传真实密码文件。

## 2. 在 Railway 创建数据库

1. 打开 https://railway.com/dashboard ，登录。如果选择 GitHub，按页面完成授权。
2. 点击 New Project → Empty Project。
3. 在项目画布点击 Create 或 + New → Docker Image，镜像填 `pgvector/pgvector:pg17`。
4. 将这个服务命名为 `pgvector`（后面的变量引用使用这个名字）。
5. 打开该服务的 Variables，逐项添加：

|变量|填写值|
|---|---|
|POSTGRES_USER|postgres|
|POSTGRES_DB|images|
|POSTGRES_PASSWORD|自行生成并保存至少 24 位随机英文字母和数字|
|PGDATA|/var/lib/postgresql/data/pgdata|

6. 给数据库添加 Volume：在画布的 + New 中选择 Volume（部分界面可右键服务 → Attach Volume），关联 pgvector 服务，Mount path 填 `/var/lib/postgresql/data`。
7. 点击 Deploy / Apply changes，等待数据库变为 Active。必须挂载这个磁盘，数据库重部署才会保留数据。
8. 不需要给数据库生成公网域名或 TCP Proxy。数据库与应用放同一项目、同一环境。

不要随意更换 PostgreSQL 大版本。这里固定使用 17；18 的默认数据目录不同。
数据库初始化后，单改 POSTGRES_PASSWORD 不会修改已有数据库密码。

## 3. 添加网页和后端

1. 回到同一个项目画布，+ New → GitHub Repo。
2. 首次连接时点击 Configure GitHub App / Connect GitHub，选择你的账号，只授权刚建的仓库，再返回 Railway。
3. 选择 x-image-search-railway 仓库。Railway 会使用根目录 Dockerfile 构建。
4. 进入应用服务 → Variables，添加下面两项：

|变量|填写值|
|---|---|
|DATABASE_URL|postgresql://postgres:${{pgvector.POSTGRES_PASSWORD}}@${{pgvector.RAILWAY_PRIVATE_DOMAIN}}:5432/images|
|APP_PASSWORD|自行设置至少 16 个字符的网站密码|

完整复制 DATABASE_URL 的值，包括 `${{...}}`。数据库服务必须叫 pgvector。数据库密码使用随机英文字母数字可避免 URL 特殊字符问题。

5. 点击 Deploy / Apply changes。第一次构建需要下载 Python 依赖和约 605 MB 模型，可能较慢。构建期间不需要你在电脑安装软件。
6. 初次自动部署若先于变量配置失败，保存变量后重新部署即可。
7. 应用默认启动一个进程，自动初始化数据库并加载模型。健康检查 /health 成功后才应视为就绪。
8. 如果出现内存不足，请在应用 Settings 中调整资源上限。建议先按应用 2–4 GB 内存规划，再根据实际 Metrics 调整；这不是实测最低配置。平台额度与费用以你的 Railway 页面为准。
9. 进入应用 Settings → Networking → Public Networking → Generate Domain。若要求填写端口，使用应用 PORT 对应的端口（默认 8080；也可明确将 PORT 设置为 8080 后重部署）。
10. 打开生成的 HTTPS 地址。浏览器登录框中，用户名填 `admin`，密码填 APP_PASSWORD。

Railway 可能要求你选择套餐或付款；看到金额和付款按钮时先由你检查决定。ZIP 本身不会创建付费资源。

## 4. 第一次使用与验收

1. 网页右边选择一张图片，可选填这张图对应的真实 X 原帖链接，点击加入图片库。
2. 确认右上角图片数量增加。重复上传同一文件和同一链接不会重复入库。
3. 左边选择同一图片，点击开始搜索。应出现该图片；同图差异应为 0，视觉相似接近 1。
4. 加入更多不同图片，分别测试综合、同图、视觉相似三个选项。
5. 点击打开 X 原帖，确认跳转到你填写的帖子。帖子被删除或限制访问时，链接仍可能打不开。
6. 在 Railway 重部署应用，再刷新网页，确认图片数量仍保留。数据库磁盘另行检查和设置备份。
7. 用浏览器无痕窗口打开网址，确认必须输入密码。

## 常见问题

- `extension vector is not available`：数据库镜像选错；需要包含 pgvector 的镜像，不是任意 PostgreSQL 镜像。
- 数据库连接失败：检查服务名 pgvector、变量引用、数据库 Active 状态、同项目环境，以及磁盘首次初始化使用的密码。
- 健康检查失败：打开应用 Deployments → 最新部署 → Logs，检查数据库、APP_PASSWORD 长度和模型加载错误。
- 下载模型失败：在 Railway 查看 Build Logs，网络恢复后重新部署。
- 搜不到期待的图：确认已入库；本项目不会搜索整个 X。
- 401：用户名固定 admin；密码是应用 APP_PASSWORD，不是数据库密码。
- 文件被拒绝：仅接受 JPG / PNG / WebP，10 MB 以内且不超过 2000 万像素。

## 验证范围与技术备注

已做 Python/JavaScript 语法检查、配置解析、原帖 URL 校验测试。此交付环境没有 Docker、PostgreSQL、PyTorch 或模型缓存，尚未执行镜像构建、数据库集成或真实向量搜索验证，也尚未上线。请按上述验收步骤完成首次云端验证。

数据库缩略图存储适合 MVP；pHash 检索会扫描图库，图库很大时需要改索引和对象存储。当前无用户管理、自动备份、限流或后台批量采集任务。所有持有网站密码的人都能查看和加入图片。仅将密码分享给受信任使用者。

依赖固定主要版本，传递依赖尚未生成完整锁文件。模型固定为 openai/clip-vit-base-patch32 的 3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268 版本，构建下载、运行离线加载。

## 官方参考（2026-09-13 查阅）

- Railway Dockerfile 与部署：https://docs.railway.com/deployments/reference
- Railway 环境变量：https://docs.railway.com/variables
- Railway 磁盘：https://docs.railway.com/volumes
- Railway 健康检查：https://docs.railway.com/deployments/healthchecks
- GitHub 自动部署：https://docs.railway.com/deployments/github-autodeploys
- pgvector 镜像和扩展：https://github.com/pgvector/pgvector
- CLIP 模型：https://huggingface.co/openai/clip-vit-base-patch32
