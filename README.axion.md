# Axion PPT Master

本仓库是上游 [PPT Master](https://github.com/hugohe3/ppt-master) 面向 Axion Agent
运行体系的集成分支。

涉及 Axion 的运行配置、部署路径和后端支持范围时，以本文件为准；`README.md` 与
`README_CN.md` 主要保留上游项目的通用介绍和工作流说明。

## 项目宗旨

本项目的宗旨是：**保留 PPT Master 将源材料转换为原生可编辑 PPTX 的核心能力，
同时把 Agent 执行、模型配置、图片生成、安装发布和运行权限统一收敛到 Axion / GlenClaw
体系中。**

它首先是供 Axion Agent 调用的 `ppt-master` Skill，而不是一个独立的 SaaS、模型网关或通用
后端集合。上游负责演示文稿工作流和 SVG → DrawingML 能力；本分支负责让这些能力在 Axion
环境中以可部署、可管控、约定一致的方式运行。

## Axion 集成原则

### 1. 保留上游的演示文稿核心

- 保留 Strategist → Image Generator → Executor 的严格串行工作流及其质量门禁。
- 保留源材料解析、模板复用、SVG 页面生成、实时预览、后处理和原生可编辑 PPTX 导出能力。
- 尽量不分叉通用的排版、转换和 DrawingML 实现，以便持续吸收上游改进。

### 2. 由 Axion Agent 管理运行时上下文

- 文本推理由 Axion Agent 当前会话使用的 LLM 完成，Skill 不另建一套文本 Agent。
- API 地址、密钥和模型名由宿主解析后通过**进程环境变量**注入；运行时不扫描仓库、用户目录
  或当前目录中的 `.env` 文件。
- 仓库中保留 `.env.example` 等上游兼容资料，不代表 Axion 运行时会加载 `.env`。
- 宿主已注入的值优先，内置值只补齐缺省项，不覆盖现有环境变量。
- 文本与图片模型配置分离：`OPENAI_MODEL` 保留给文本 LLM，图片生成只读取
  `OPENAI_IMAGE_MODEL`，避免把文本模型名误用于生图请求。

当前约定的主要变量如下：

| 变量 | Axion 语义 | 当前缺省值 |
|---|---|---|
| `OPENAI_API_KEY` | GlenClaw / OpenAI 兼容接口凭据，由宿主注入 | 空 |
| `OPENAI_API_BASE` | OpenAI 兼容 API 地址 | `https://api.glenclaw.com` |
| `OPENAI_MODEL` | 文本 LLM 模型名；生图脚本忽略此变量 | `chat` |
| `OPENAI_IMAGE_MODEL` | 图片生成模型名 | `image` |
| `IMAGE_BACKEND` | 图片生成后端 | `openai` |

### 3. 默认使用 GlenClaw 图片生成

Axion 的标准生图路径是 GlenClaw 提供的 OpenAI 兼容接口：默认使用
`IMAGE_BACKEND=openai`、`OPENAI_API_BASE=https://api.glenclaw.com` 和
`OPENAI_IMAGE_MODEL=image`。实际密钥由 Axion Agent 在运行时注入，不写入仓库、安装包或生成项目。

图片生成仍遵守 PPT Master 的 manifest、状态回写和审计旁车文件约定；Axion 的改动只替换
provider 接入和配置所有权，不绕过上游的图片资源工作流。

### 4. 收敛后端支持面

Axion 发行策略采用后端白名单：默认支持面以 GlenClaw 的 OpenAI 兼容生图路径为准；其他上游
直连 provider 只有经过 Axion 明确启用和验证后才属于支持范围，否则按禁用或不支持处理。部分
兼容模块可能因上游同步仍保留在源码中，不应仅凭模块或入口存在就判断该后端已经启用。

同步上游时应遵循以下边界：

- 不重新引入由 Skill 自行搜索或加载 `.env` 的行为。
- 不绕过 Axion Agent，直接在 Skill 内管理文本 LLM 会话或长期凭据。
- 不默认启用未经 Axion 验证的第三方直连后端。
- 不用 provider 私有配置替代 GlenClaw / OpenAI 兼容环境变量合同。
- 上游新增后端先作为候选评估，再决定启用、禁用或移除。

### 5. 按 Axion 目录和身份部署

- 本地安装脚本将 Skill 安装到 `~/.axion-agent/skills/ppt-master`。
- 默认生成项目放在 `~/ppt/YYYY-mm/`，使工作产物与仓库源码分离。
- Debian 包将 Skill 安装到 `/opt/axion/skills/ppt-master`。
- 系统包面向 `glenclaw:glenclaw` 运行身份，并校验约定的 UID/GID `10001:10001`。
- Debian 构建只打包 Git 已跟踪的 `skills/ppt-master/` 内容，不携带本地 `.env`、缓存、
  凭据或生成项目。

## 非目标

本分支不以维护所有上游运行方式为目标，也不把 PPT Master 变成新的模型代理层。以下事项不属于
Axion 发行版的核心承诺：

- 为每个第三方模型厂商维护独立、长期稳定的直连适配。
- 在 Skill 内保存密钥或提供另一套 `.env` 配置体系。
- 替代 Axion Agent 的对话、工具编排、权限控制和运行时配置解析。
- 为追求分支差异而重写上游已经成熟的 PPT 生成与导出能力。

## 维护判断准则

面对上游同步或新功能选择时，优先问三个问题：

1. 是否增强了原生可编辑 PPTX 的内容、视觉或导出质量？
2. 是否遵守 Axion Agent 注入运行时配置、GlenClaw 提供标准生图能力的边界？
3. 是否会扩大未经验证的后端、凭据或部署复杂度？

只有同时保住上游 PPT 能力与 Axion 运行边界的改动，才符合本分支的长期方向。
