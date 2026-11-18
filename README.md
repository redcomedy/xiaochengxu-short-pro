# xiaochengxu-short-pro

小程序买量投流短篇小说全链路创作与投稿过稿系统（v2.0）。

## 核心特性

- **五阶信息流买量漏斗**：按商业转化权重分配精力（40% 导语点击率 + 30% 第 4 章 40% 付费墙卡点转化 + 30% 前 4,000 字编辑留存）。
- **五路异构导语矩阵**：切面平移 / 双梗杂交 / 猎人设局 / 现实痛点嫁接 / 信息差错位，并内置下沉受众生活常识词库与换名回读防撞稿门禁。
- **付费墙驱动高密度细纲 + `story_bible.json`**：强制 3,500–5,500 字场景细纲、第 `round(N * 0.4)` 章悬崖断章、导语与首章零缝隙咬合，以及结构化反派狠话 `debts` / 道具 `props` 打脸账本。
- **黄金前 4,000 字试写与毒舌主编独立盲审**：先写前 `K` 章过代码质检并拉起隔离上下文只读子智能体盲审打分，达标再扩写后 60%。
- **零外部依赖工具链**：
  - `scripts/manuscript_linter.py`：实测汉字数、章节数对齐、对话占比（55%–75%）、段落节奏、分级禁词、40% 卡点区间与账本核销状态。
  - `scripts/submission_packager.py`：原生 OOXML 生成《书名》_编辑审稿版(标卡点).docx、《书名》_纯净正文版.docx 与 QQ 邮箱投递自荐信 `email_pitch.txt`，并维护 `投稿台账.csv` / `投稿台账.md` 统计各导语策略过稿率。

## 目录结构

```text
xiaochengxu-short-pro/
├── SKILL.md
├── README.md
├── 更新日志.md
├── .gitignore
├── references/
│   ├── 01-deconstruct-and-hybrid.md
│   ├── 02-paywall-outline-and-bible.md
│   ├── 03-prose-and-blind-audit.md
│   └── 04-submission-and-flywheel.md
└── scripts/
    ├── manuscript_linter.py
    └── submission_packager.py
```

## 在其他设备或项目中安装使用

- **安装到个人全局 Skill 目录**（推荐跨项目复用）：
  ```bash
  git clone https://github.com/redcomedy/xiaochengxu-short-pro.git ~/.agents/skills/xiaochengxu-short-pro
  ```
- **安装到单个项目工作区**：
  ```bash
  git clone https://github.com/redcomedy/xiaochengxu-short-pro.git .agents/skills/xiaochengxu-short-pro
  ```

安装后直接在对话中粘贴对标导语并触发五阶流程即可使用，详见 [SKILL.md](./SKILL.md)。
