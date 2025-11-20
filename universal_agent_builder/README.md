# Universal Agent Builder

基于 AgentScope 框架的通用智能体构建器系统。

## 概述

输入需求描述，输出编程项目或深度研究报告。

## 核心架构

### 三大主控 Agent

1. **Planner Agent** - 计划管理者
   - 封装 PlanNotebook 交互
   - 管理计划生命周期（创建、更新、回滚）
   - 响应用户打断和 Reflector 反馈

2. **Master Agent** - 核心决策者
   - Context 三部分：Plan + Decision Path + Artifacts
   - 预测下一个工具/Sub-Agent 调用
   - 协调整体工作流

3. **Reflector Agent** - 质量检验者
   - 检验质量和准确性
   - 智能路由反馈（Master 或 Planner）

### 三大 Sub-Agent

1. **Code Agent** - 代码交付
   - 代码执行、生成、测试
   - 数据可视化

2. **Browser Use Agent** - 浏览器自动化
   - 网页浏览、信息提取
   - 与 Web Search 配合使用

3. **Report Agent** - 报告生成
   - 研究报告、技术文档
   - 支持 Markdown、PDF 等格式

## 项目结构

```
universal_agent_builder/
├── src/
│   ├── agents/          # 智能体实现
│   ├── core/            # 核心组件（Context、Decision 等）
│   ├── tools/           # 工具函数
│   ├── sandbox/         # Docker 沙盒管理
│   └── utils/           # 工具函数
├── tests/               # 测试
├── examples/            # 示例
├── docs/                # 文档
├── requirements.txt     # 依赖
├── Dockerfile          # 沙盒镜像
└── README.md
```

## 快速开始

（待完善）

## 开发计划

详见 [UNIVERSAL_AGENT_BUILDER_PLAN.md](../UNIVERSAL_AGENT_BUILDER_PLAN.md)

## License

MIT
