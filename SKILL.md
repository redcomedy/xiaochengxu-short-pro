---
name: xiaochengxu-short-pro
description: >-
  小程序买量投流短篇小说全链路创作与投稿过稿系统（v2.0）。当用户需要拆解短篇对标、生成导语抽卡（含双梗杂交与热点嫁接）、设计带 40% 付费墙卡点的高密度细纲与打脸伏笔账本、试写黄金前 4000 字并进行毒舌编辑独立盲审、扩写约 13000 字无 AI 味正文、运行多维静态质检、导出标准投稿 .docx 套件或管理投稿追踪台账时激活本技能。
---

# 小程序短篇投流过稿系统（v2.0）

把「短篇小说创作」按**信息流买量漏斗**重构，不再先写满 13,000 字再去赌运气，而是按商业转化权重逐关设防：

- **40% 精力在导语**（买量点击率）：3 秒留住三四线城市 30–40 岁女性；
- **30% 精力在 40% 付费墙卡点**（充值转化率）：在第 4 章（约 4,000 字处）制造“不付费睡不着”的悬崖；
- **30% 精力在前 4,000 字留存**（编辑过稿率）：先写小样并拉起独立毒舌编辑盲审，通过后再扩写后 60%。

---

## 一、项目目录与五阶状态机

每次开工按用户指定目录建档；未指定时在当前工作区下新建 `稿件-<关键词或日期>/`（**严禁往 Skill 安装目录内写任何稿件文件**）。

```text
稿件-<关键词或日期>/
├── 00_state.json              五阶状态机与卡点追踪
├── source_hook.md             对标导语原文（逐字保存）
├── source_full.md             对标全文（阶段 2 起需要）
├── cards.md                   阶段 1 产物：五路异构导语卡
├── outline.md                 阶段 2 产物：原文拆解 + 40% 卡点设计 + 3500-5500 字细纲
├── story_bible.json           阶段 2 产物：角色状态 + 备选书名 + 打脸伏笔账本
├── blind_audit_report.md      阶段 3 产物：毒舌主编独立盲审评分与返修记录
├── manuscript.txt             阶段 3/4 产物：纯正文 UTF-8 TXT（无书名梗概废话）
├── sample_lint_report.json    阶段 3 产物：小样代码质检报告
├── lint_report.json           阶段 4 产物：完稿代码质检报告
├── submission_meta.json       阶段 5 产物：书名、导语与含结局审稿梗概
└── submission/                阶段 5 产物：审稿版/纯净版 .docx + email_pitch.txt
```

### `00_state.json` 阶段门禁表

每次继续对话先读 `00_state.json`（不存在则初始化）：

| `stage` | 含义 | 必须满足的前置条件与下一步动作 |
| :--- | :--- | :--- |
| `hooks` | 5 张导语卡已生成 | 停等用户选定 `picked_card`（1–5）；未选定禁止进入阶段 2 |
| `outline` | 细纲与账本已生成 | 停等用户确认大纲或指定修改；确认后置为 `outline-done` |
| `outline-done` | 大纲已确认 | 进入阶段 3：写第 `1` 至 `paywall_chapter` 章黄金小样 |
| `sample_audit` | 小样质检与盲审通过 | 停等用户确认小样张力；确认后解锁阶段 4 |
| `full_draft` | 全文扩写完成且全量质检通过 | 进入阶段 5：打包投稿 `.docx` 与登记台账 |
| `packaged` | 投稿套件已导出 | 交付路径与邮件模板，等待用户投递后更新台账 |

---

## 二、按需读取资源

| 阶段 | 必读手册 / 工具 |
| :--- | :--- |
| 阶段 1 · 导语抽卡 | [01-deconstruct-and-hybrid.md](./references/01-deconstruct-and-hybrid.md) |
| 阶段 2 · 卡点细纲 | [02-paywall-outline-and-bible.md](./references/02-paywall-outline-and-bible.md) |
| 阶段 3 & 4 · 试写/盲审/扩写 | [03-prose-and-blind-audit.md](./references/03-prose-and-blind-audit.md) |
| 阶段 5 · 打包与台账 | [04-submission-and-flywheel.md](./references/04-submission-and-flywheel.md) |
| 代码质检脚本 | [manuscript_linter.py](./scripts/manuscript_linter.py) |
| 投稿打包与台账脚本 | [submission_packager.py](./scripts/submission_packager.py) |

---

## 三、五阶漏斗执行流程

> 规则：**每完成一个阶段立即停下交付并等待用户确认**；同时支持用户跳过前置步骤单独使用任一阶段（如自带大纲直接进阶段 3 试写，或自带完稿直接跑质检与打包）。

### 阶段 1 · 基因拆解与五路异构导语工坊

1. 把用户提供的对标导语逐字存进 `source_hook.md` 并实测汉字数与段落数（若已存在且内容不同，先询问用户是否覆盖或另建目录）。
2. 阅读 [01-deconstruct-and-hybrid.md](./references/01-deconstruct-and-hybrid.md)，按五维雷达完成对标拆解（含核心梗、矛盾逻辑、权力关系、钩子类型、节奏指纹）。
3. 按**五路正交策略**（切面平移 / 双梗杂交 / 猎人设局 / 现实痛点嫁接 / 信息差错位）生成 5 张全新导语卡写入 `cards.md`，严格通过**下沉生活化词库检查**与**换名回读自检**。
4. 将 `00_state.json` 置为 `stage: "hooks"`，**停下请用户选定一张卡**。

### 阶段 2 · 40% 付费卡点细纲 + 打脸伏笔账本

1. 核验 `picked_card` 已选定；读取 `source_full.md`（若无全文且需对齐原文章节数则先向用户索取；若用户指示按标准篇幅自建，默认 **10–12 章**）。
2. 阅读 [02-paywall-outline-and-bible.md](./references/02-paywall-outline-and-bible.md)，先拆解原文总章数与 **40% 付费卡点机制**，锁定新大纲卡点章 `K = round(total_chapters * 0.4)`。
3. 设计导语末句到第一章首段的**零缝隙咬合方案**，编写 **3,500–5,500 汉字**的高密度场景细纲写入 `outline.md`（每章 8–12 个三元组剧情点，相邻情绪标签不重样，第 `K` 章结尾必须急停在底牌掀开前 0.5 秒）。
4. 同步生成 `story_bible.json`（备选书名、角色当前状态与约束、反派狠话 `debts` 与核心道具 `props` 台账）。
5. 置 `00_state.json` 为 `stage: "outline"`，**停下请用户确认大纲与第 `K` 章卡点**；确认后更新为 `outline-done`。

### 阶段 3 · 黄金前 4,000 字小样试写 + 毒舌编辑独立盲审

1. 阅读 [03-prose-and-blind-audit.md](./references/03-prose-and-blind-audit.md)，只扩写第 `1` 至 `K` 章写入 `manuscript.txt`（短句快切、对话占 55%–75%、零环境废话、第一人称微自嘲）。
2. 运行小样静态质检（退出码须为 `0`）：
   ```bash
   python3 .agents/skills/xiaochengxu-short-pro/scripts/manuscript_linter.py "<项目目录>/manuscript.txt" \
     --mode sample --expected-chapters <K> --paywall-chapter <K> \
     --output "<项目目录>/sample_lint_report.json"
   ```
3. 启动独立只读子智能体（`research` 角色，不传 `outline.md`），仅基于「选定导语 + 前 `K` 章正文」扮演**日审 300 封稿件的买量主编**打分（满分 100，`< 80` 分或单项 `< 15` 分则按批注自动返修并重跑质检），将评分与修改记录写入 `blind_audit_report.md`。
4. 更新 `00_state.json` 为 `stage: "sample_audit"`，**停下向用户汇报小样与盲审评分，确认方向后再写后半程**。

### 阶段 4 · 账本制完稿扩写 + 全维度静态质检

1. 按章扩写第 `K+1` 至 `N` 章并追加至 `manuscript.txt`；每章动笔前读取 `story_bible.json`，写完一章即更新人物状态并把已兑现的 `debts`（原话打脸）与 `props` 标记为 `"resolved"`。
2. 如单次生成遇截断、用户回复“继续”，先读 `manuscript.txt` 末尾 300 字与账本，**零废话精确接续正文**。
3. 完稿后必须运行全量质检并直至退出码为 `0`（不许口头跳过）：
   ```bash
   python3 .agents/skills/xiaochengxu-short-pro/scripts/manuscript_linter.py "<项目目录>/manuscript.txt" \
     --mode full --expected-chapters <N> --paywall-chapter <K> \
     --bible "<项目目录>/story_bible.json" \
     --output "<项目目录>/lint_report.json"
   ```
4. 质检通过后更新 `00_state.json` 为 `stage: "full_draft"`。

### 阶段 5 · 投稿套件打包与渠道反馈台账

1. 阅读 [04-submission-and-flywheel.md](./references/04-submission-and-flywheel.md)，区分「投流导语（不剧透）」与「编辑审稿梗概（含卡点与结局）」，编写 `submission_meta.json`。
2. 导出标准 Word `.docx`（审稿标卡点版 + 纯净版）与 QQ 邮箱投递自荐信：
   ```bash
   python3 .agents/skills/xiaochengxu-short-pro/scripts/submission_packager.py package \
     --project-dir "<项目目录>" --mark-paywall
   ```
3. 登记/更新工作区投稿台账并统计各导语策略过稿率：
   ```bash
   python3 .agents/skills/xiaochengxu-short-pro/scripts/submission_packager.py track add \
     --title "<书名>" --genre "<题材>" --hook-strategy "<策略>" --han-count <字数> --channel "<渠道>"
   ```
4. 更新 `00_state.json` 为 `stage: "packaged"`，向用户交付文件链接与实操提醒。

---

## 四、严格边界

- 不虚构平台审核结果、读者测试数据或过稿承诺；
- 不代为发送外部邮件或自动登录平台投稿；
- 一切字数、对话率、禁词、段落节奏与账本核销结论必须以 `manuscript_linter.py` 实测 JSON 报告为准。
