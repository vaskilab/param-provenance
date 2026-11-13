# 发布步骤（照着做，约 10 分钟）

> 这份文件是给你自己看的操作清单，发布前可以删掉，或者留着当维护笔记。

## 前提确认

- [ ] GitHub 账号已注册（用 QQ 邮箱即可）
- [ ] 用**新建的浏览器配置文件**或无痕窗口访问 GitHub（绕开扩展干扰）
- [ ] 本机装了 git 和 Python 3.9+

---

## 第 1 步：GitHub 上做三件设置（网页操作，2 分钟）

### 1.1 隐藏真实邮箱

Settings → Emails → 勾选 **Keep my email addresses private**

勾上后页面会显示一个专用地址，形如 `12345678+vaskilab@users.noreply.github.com`。
**把它抄下来**，下一步要用。

顺便勾上 **Block command line pushes that expose my email**，防止误用真实邮箱提交。

### 1.2 建空仓库

右上角 + → New repository

- Repository name：`param-provenance`
- Description：`Catch fabricated tool arguments in LLM agents. Schema checks the shape; this checks the origin.`
- Public
- **不要**勾 Add a README / .gitignore / license（本地已经有了，勾了会冲突）

建完先别管它。

### 1.3 加 SSH 公钥（先做第 2 步生成，再回来加）

Settings → SSH and GPG keys → New SSH key，把公钥内容粘进去。

---

## 第 2 步：本机配置（3 分钟）

### 2.1 生成 SSH key（如果还没有）

```bash
ssh-keygen -t ed25519 -C "vaskilab@github"
# 一路回车即可，passphrase 可留空
cat ~/.ssh/id_ed25519.pub
```

把输出的整行复制，粘到上面 1.3 的页面里。

### 2.2 配置 SSH 走 443 端口（关键，抗干扰）

编辑 `~/.ssh/config`，追加：

```
Host github.com
  Hostname ssh.github.com
  Port 443
  User git
  IdentityFile ~/.ssh/id_ed25519
```

验证：

```bash
ssh -T git@github.com
# 看到 "Hi vaskilab! You've successfully authenticated" 就通了
```

### 2.3 配置提交身份（用 noreply 地址，贡献图才会算你的）

```bash
git config --global user.name "vaskilab"
git config --global user.email "把 1.1 抄下来的 noreply 地址粘这里"
```

---

## 第 3 步：推送（2 分钟）

解压拿到 `param-provenance` 目录，然后：

```bash
cd param-provenance

# 先本地验证一遍，确认没问题再推
python -m unittest discover -s tests
python examples/demo.py

git init
git add .
git commit -m "Initial commit: provenance checking for agent tool arguments"
git branch -M main
git remote add origin git@github.com:vaskilab/param-provenance.git
git push -u origin main
```

推完刷新仓库页面，应该能看到 README 自动渲染、CI 开始跑。

---

## 第 4 步：让仓库能被找到（3 分钟，别跳过）

### 4.1 加 Topics

仓库主页右侧 About 齿轮 → Topics 填：

```
llm  agent  ai-agents  hallucination  evaluation  observability
tool-calling  provenance  llmops  agent-testing
```

Topics 是 GitHub 内部搜索和推荐的主要入口，不填等于隐身。

### 4.2 填 About

- Description：同上
- Website：留空，或以后填你的文章链接
- 勾上 **Use your GitHub Pages website**（暂时不用）

### 4.3 建第一个 Release（可选，但显得正式）

Releases → Draft a new release → Tag `v0.1.0` → 标题 `v0.1.0 — initial release`
正文写三行：解决什么问题、包含什么、已知边界。

---

## 第 5 步：Gitee 镜像（国内访问保障）

1. Gitee 建同名仓库 `param-provenance`（选"导入已有仓库"，填 GitHub 地址）
2. 仓库 → 管理 → 仓库镜像管理 → 绑定 GitHub 账号 → 配置推送方向
3. 在 GitHub 的 README 顶部加一行 Gitee 链接（方便国内读者）

之后日常在 Gitee 上开发，自动同步到 GitHub，不用天天开 GitHub。

---

## 第 6 步：发文章，把流量导回仓库

文章成稿在 `docs/article-zh.md`（已脱敏，无业务词、无生产数据）。

发布顺序：

1. **掘金首发**：原文直发，末尾加一句
   > 文中提到的溯源校验和结构化引用，我做了一个可跑的最小实现：github.com/vaskilab/param-provenance
2. **知乎**：不要发新文章，去回答已有高流量问题（"Agent 幻觉怎么解决""如何评测大模型应用效果"），开头直接给结论
3. **公众号**：加一段个人开头，末尾引导关注 + 仓库链接
4. **V2EX**：短帖，"做了个小工具检测 Agent 参数编造，求拍砖" + 链接。**不要发全文**

---

## 检查清单

推完之后确认这几条：

- [ ] README 在仓库首页正常渲染，中英切换链接可点
- [ ] CI 绿了（三个 Python 版本都过）
- [ ] 你的 commit 显示了头像，且计入贡献图（说明邮箱配对了）
- [ ] Topics 填了
- [ ] `git clone` 到另一个目录，`python examples/demo.py` 能跑（验证别人拿到能用）

最后一条最重要。**别人 clone 下来跑不起来，前面所有努力都白费。**

---

## 后续可以加的（不要现在做）

- 从 OpenTelemetry span 直接导入 trace（现在要手工构造）
- 更多幻觉类别的规则层检测（工具名不在注册表、error 状态 + 成功语义）
- pytest 插件，让评测直接跑在 CI 里
- 一个 `--warn-only` 的 CLI，方便在现有系统上先观察不拦截

**先把这一个点做到有人用，再扩。** 现在扩只会分散你本来就不够的时间。
