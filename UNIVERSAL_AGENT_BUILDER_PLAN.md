# Universal Agent Builder - 开发规划

## 项目概述

构建一个通用智能体系统，输入需求描述，输出编程项目或深度研究报告。

### 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                    User Input (需求描述)                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      Planner Agent                          │
│  - 管理 PlanNotebook (创建、更新、回滚)                      │
│  - 提供目标导向的 Plan 给 Master Agent                       │
│  - 响应 Reflector 反馈，更新或回滚计划                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      Master Agent                           │
│  Context = Plan + Decision Path + Artifacts                │
│  - Plan: 来自 Planner Agent 的目标导向计划                   │
│  - Decision Path: Reasoning + Acting 历史                   │
│  - Artifacts: 沉淀文件 (md/code/media)                      │
│  - 基于 Context 预测下一个工具/Sub-Agent 调用                │
│  - 使用较小模型，专注于决策                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Tool / Sub-Agent Layer                   │
│  - 独立调用模式: 输入→处理→输出文件                          │
│  - 交互式调用模式: 共享 Context，多轮协作                    │
│  Sub-Agents:                                                │
│  - Code Agent (编程、画图、生成代码)                         │
│  - Browser Agent (网页浏览、信息收集)                        │
│  - Research Agent (深度研究)                                │
│  - Writer Agent (文档撰写)                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      Reflector Agent                        │
│  - 质量检验                                                  │
│  - 准确性验证                                                │
│  - 路由决策:                                                 │
│    → Master Agent: 通过/需要微调(Plan不变)                  │
│    → Planner Agent: 异常，需要更新Plan                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  Docker Sandbox (Per Session)               │
│  - 文件系统                                                  │
│  - 代码运行环境 (Python/Node.js/etc)                        │
│  - 浏览器环境                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心组件详细设计

### 1. Planner Agent

**职责:**
- PlanNotebook 的代理层，封装所有 PlanNotebook 交互
- 自动管理计划生命周期（初始化、更新、版本控制）
- 响应用户打断和 Reflector 反馈

**核心功能:**

```python
class PlannerAgent:
    """计划管理智能体"""

    def __init__(self, plan_notebook: PlanNotebook):
        self.plan_notebook = plan_notebook
        self.plan_history_stack = []  # 本地计划版本栈

    async def initialize_plan(self, user_requirement: str) -> Plan:
        """基于用户需求初始化计划"""
        # 分析需求复杂度
        # 生成初始计划结构
        # 调用 plan_notebook.create_plan()
        pass

    async def update_plan(self, feedback: dict) -> Plan:
        """基于反馈更新计划"""
        # 来源: Reflector Agent 或用户打断
        # 决定是修改 subtask 还是重建计划
        # 调用 plan_notebook.revise_current_plan()
        pass

    async def rollback_plan(self, version: int = -1) -> Plan:
        """回滚到历史版本"""
        # 利用 plan_notebook.view_historical_plans()
        # 调用 plan_notebook.recover_historical_plan()
        pass

    async def get_current_plan_context(self) -> str:
        """获取当前计划的上下文表示（给 Master Agent）"""
        # 格式化当前计划为简洁的文本表示
        # 突出当前 subtask 和进度
        pass

    async def mark_subtask_progress(self, subtask_idx: int,
                                   state: str, outcome: str = None):
        """标记子任务进度"""
        # 调用 plan_notebook.update_subtask_state()
        # 或 plan_notebook.finish_subtask()
        pass
```

**AgentScope 集成点:**
- 继承自 `AgentBase`
- 使用 `PlanNotebook` 作为核心工具
- 不直接暴露 PlanNotebook 工具给 Master Agent

---

### 2. Master Agent

**职责:**
- 核心决策者，基于 Context 预测下一步行动
- 调用工具或 Sub-Agent
- 维护决策路径历史

**Context 组成 (三部分):**

```python
class MasterContext:
    """Master Agent 的上下文"""

    # Part 1: Plan Context
    current_plan: str  # 来自 Planner Agent
    current_subtask: str
    progress: str

    # Part 2: Decision Path
    decision_history: list[Decision]  # [Reasoning → Tool/Agent → Result]

    # Part 3: Artifacts
    artifacts_index: dict  # 文件索引 {path: summary}
    # 实际文件存储在沙盒文件系统中，这里只记录元信息
```

**Decision 结构:**

```python
class Decision:
    reasoning: str  # 为什么选择这个工具/Agent
    action_type: str  # "tool" or "sub_agent"
    action_name: str  # 工具名或 Sub-Agent 名
    action_input: dict  # 输入参数
    action_result: str  # 执行结果摘要（不包含大量数据）
    artifacts_produced: list[str]  # 产生的文件路径
    timestamp: str
```

**核心功能:**

```python
class MasterAgent(AgentBase):
    """主控智能体"""

    def __init__(self,
                 model_config: dict,  # 较小模型，如 GPT-4o-mini
                 planner_agent: PlannerAgent,
                 reflector_agent: ReflectorAgent,
                 sub_agents: dict,
                 tools: dict):
        super().__init__(name="MasterAgent", model_config=model_config)
        self.context = MasterContext()
        self.planner = planner_agent
        self.reflector = reflector_agent
        self.sub_agents = sub_agents
        self.tools = tools

    async def reply(self, user_msg: Msg) -> Msg:
        """主循环"""
        # 1. 更新 Context
        await self._update_context()

        # 2. 构建 Prompt
        prompt = self._build_prompt(user_msg)

        # 3. LLM 预测下一步行动
        action = await self._predict_next_action(prompt)

        # 4. 执行行动（工具或 Sub-Agent）
        result = await self._execute_action(action)

        # 5. 记录到 Decision Path
        self._record_decision(action, result)

        # 6. 可选：触发 Reflector 检验
        if self._should_reflect():
            reflection = await self.reflector.reflect(self.context)
            await self._handle_reflection(reflection)

        return Msg(name=self.name, content=result)

    def _build_prompt(self, user_msg: Msg) -> str:
        """基于三部分 Context 构建 Prompt"""
        return f"""
## Current Plan (from Planner Agent)
{self.context.current_plan}

## Decision Path (Recent Actions)
{self._format_recent_decisions(n=5)}

## Available Artifacts
{self._format_artifacts_index()}

## User Message
{user_msg.content}

## Your Task
Based on the above context, predict the next action (tool or sub-agent call).
You should output a structured decision with reasoning.
"""

    async def _execute_action(self, action: dict):
        """执行工具或 Sub-Agent"""
        if action['type'] == 'tool':
            return await self._call_tool(action)
        elif action['type'] == 'sub_agent_independent':
            return await self._call_sub_agent_independent(action)
        elif action['type'] == 'sub_agent_interactive':
            return await self._call_sub_agent_interactive(action)
```

**Sub-Agent 调用模式:**

```python
# 独立调用模式
async def _call_sub_agent_independent(self, action: dict):
    """
    独立调用：不共享完整 Context
    示例：让 Code Agent 画一个柱状图
    输入：数据 + 指示
    输出：图片文件路径
    """
    sub_agent = self.sub_agents[action['agent_name']]
    input_msg = Msg(
        name=self.name,
        content=action['input']  # 只包含特定任务所需信息
    )
    result = await sub_agent.reply(input_msg)
    return result

# 交互式调用模式
async def _call_sub_agent_interactive(self, action: dict):
    """
    交互式调用：共享 Context
    示例：让 Code Agent 基于前面收集的信息构建网页
    Sub-Agent 可以访问完整的 Artifacts 和 Decision Path
    """
    sub_agent = self.sub_agents[action['agent_name']]

    # 注入 Context
    sub_agent.shared_context = self.context

    # 多轮交互
    input_msg = Msg(
        name=self.name,
        content=action['input'],
        metadata={'context': self.context}
    )
    result = await sub_agent.reply(input_msg)

    # Sub-Agent 可能更新 Artifacts
    self._sync_artifacts(sub_agent)

    return result
```

---

### 3. Reflector Agent

**职责:**
- 质量检验和准确性验证
- 决定反馈路由（Master 或 Planner）

**核心功能:**

```python
class ReflectorAgent(AgentBase):
    """质量检验智能体"""

    async def reflect(self, master_context: MasterContext) -> Reflection:
        """
        检验当前工作状态

        检查点:
        1. 当前 subtask 的完成质量
        2. 产出的 artifacts 是否符合预期
        3. Decision path 是否合理（有无死循环、重复错误）
        4. 是否偏离计划目标
        """
        # 构建检验 prompt
        prompt = f"""
You are a quality inspector. Review the current work status:

Current Plan: {master_context.current_plan}
Recent Decisions: {master_context.decision_history[-3:]}
Produced Artifacts: {master_context.artifacts_index}

Evaluate:
1. Quality: Is the current work meeting the expected outcome?
2. Accuracy: Are the results correct?
3. Alignment: Is the work aligned with the plan?
4. Issues: Any problems or blockers?

Output a structured reflection.
"""

        response = await self.model(prompt)
        reflection = self._parse_reflection(response)
        return reflection

    def _parse_reflection(self, response) -> Reflection:
        """解析反馈结果"""
        return Reflection(
            status='pass' | 'revise' | 'replan',
            routing='master' | 'planner',
            feedback=...,
            suggested_action=...
        )

class Reflection:
    status: str  # 'pass', 'revise', 'replan'
    routing: str  # 'master', 'planner'
    feedback: str  # 具体反馈内容
    suggested_action: str  # 建议的下一步行动
```

**路由逻辑:**

```
Reflection.status → Routing Decision

'pass' → Master Agent (继续当前任务)
'revise' → Master Agent (需要修改，但 Plan 不变)
'replan' → Planner Agent (异常，需要更新 Plan)
```

---

### 4. Sub-Agent Layer

**核心三大 Sub-Agent:**

#### 4.1 Code Agent

```python
class CodeAgent(AgentBase):
    """代码交付智能体 - 负责所有编程任务"""

    tools = [
        'execute_python_code',
        'execute_javascript_code',
        'write_code_file',
        'read_code_file',
        'install_package',
        'run_tests',
        'generate_visualization',  # 数据可视化
    ]

    # 独立调用示例
    async def generate_chart(self, data: dict, chart_type: str) -> str:
        """生成图表，返回图片路径"""
        pass

    # 交互式调用示例
    async def build_web_app(self, requirements: str,
                           shared_context: MasterContext) -> dict:
        """构建网页应用，可访问共享 Context"""
        # 可以读取 shared_context.artifacts_index
        # 查看之前收集的信息、数据文件等
        pass

    async def implement_algorithm(self, spec: str,
                                  shared_context: MasterContext) -> dict:
        """实现算法，可能需要之前的研究资料"""
        pass
```

#### 4.2 Browser Use Agent

```python
class BrowserUseAgent(AgentBase):
    """浏览器自动化智能体 - 详细浏览和信息提取"""

    tools = [
        'navigate_to_url',
        'click_element',
        'extract_text',
        'extract_structured_data',
        'screenshot',
        'fill_form',
        'scroll_page',
        'wait_for_element',
    ]

    async def browse_and_extract(self, url: str, extraction_task: str) -> dict:
        """浏览 URL 并提取信息"""
        # 输入：URL（可能来自 web_search 工具）
        # 输出：结构化数据或文本内容
        pass

    async def multi_page_research(self, urls: list[str],
                                  shared_context: MasterContext) -> dict:
        """多页面研究任务，交互式调用"""
        # 访问多个页面，综合信息
        # 可能需要根据之前的发现调整浏览策略
        pass
```

#### 4.3 Report Agent

```python
class ReportAgent(AgentBase):
    """报告产出智能体 - 生成各类研究报告和文档"""

    tools = [
        'write_markdown',
        'generate_pdf',
        'create_presentation',
        'format_document',
        'add_references',
    ]

    async def generate_research_report(self,
                                       topic: str,
                                       shared_context: MasterContext) -> str:
        """生成深度研究报告"""
        # 读取 shared_context 中的：
        # - Browser Use Agent 收集的信息
        # - Code Agent 生成的数据分析结果
        # - 之前沉淀的资料
        # 输出：格式化的 Markdown/PDF 报告
        pass

    async def create_technical_doc(self,
                                   code_artifacts: list[str],
                                   shared_context: MasterContext) -> str:
        """创建技术文档"""
        # 基于代码文件生成文档
        pass
```

---

**信息检索策略:**

```python
# Master Agent 的信息检索流程
async def research_workflow(self, query: str):
    """信息检索工作流"""

    # Step 1: Web Search 获取相关 URL
    search_results = await self.tools['web_search'](query)
    # 返回：[{url, title, snippet}, ...]

    # Step 2: Browser Use Agent 详细浏览
    for result in search_results[:5]:  # 浏览前5个结果
        detailed_info = await self.sub_agents['browser_use'].browse_and_extract(
            url=result['url'],
            extraction_task=f"Extract detailed information about {query}"
        )
        self._save_artifact(detailed_info)

    # Step 3: Report Agent 整合报告
    report = await self.sub_agents['report'].generate_research_report(
        topic=query,
        shared_context=self.context  # 包含所有浏览结果
    )

    return report
```

---

### 5. Docker Sandbox

**本地部署方案（单 Session 流畅运行）:**

```yaml
Docker Container (Per Session):
  - Base Image: ubuntu:22.04
  - Python 3.11+ 运行环境
  - Node.js 18+ 运行环境
  - Playwright (浏览器自动化 - 用于 Browser Use Agent)
  - 文件系统: 容器内部 /workspace (不使用远程对象存储)
  - 网络: 允许外网访问 (用于 web search 和浏览)
  - 资源限制:
      - CPU: 2 cores
      - Memory: 4GB
      - Disk: 10GB (临时存储，session 结束可选择保留或清理)
      - Timeout: 2 hours
  - 部署方式: 本地 Docker，后续考虑工程化扩展
```

**容器内文件系统结构:**

```
/workspace/  (容器内部，非挂载)
├── session_<id>/
│   ├── artifacts/  (Sub-Agent 产出的文件)
│   │   ├── documents/  # Markdown, PDF 等 (Report Agent 产出)
│   │   ├── code/       # Python, JS, CSS 等 (Code Agent 产出)
│   │   ├── media/      # 图片、音频、视频 (Code Agent 可视化等)
│   │   └── data/       # JSON, CSV 等数据文件 (Browser Use Agent 提取的数据)
│   ├── context/  (Master Agent 状态管理)
│   │   ├── plan.json              # 当前计划
│   │   ├── decision_path.json     # 决策路径历史
│   │   └── artifacts_index.json   # 文件索引
│   ├── browser/  (Browser Use Agent 工作目录)
│   │   ├── screenshots/
│   │   └── downloads/
│   └── logs/
│       └── session.log
```

**工程化扩展预留:**
- 未来可考虑容器池、资源调度
- 可选的持久化存储方案
- 分布式部署支持

---

## 分阶段开发计划

### Phase 0: 准备工作 (1-2天)

**目标:** 设置项目基础结构

**任务:**
- [ ] 创建项目目录结构
- [ ] 设置开发环境
- [ ] 编写基础配置文件
- [ ] 确定技术栈和依赖

**产出:**
```
universal_agent_builder/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── master_agent.py
│   │   ├── planner_agent.py
│   │   ├── reflector_agent.py
│   │   └── sub_agents/
│   ├── core/
│   │   ├── context.py
│   │   ├── decision.py
│   │   └── artifact_manager.py
│   ├── tools/
│   └── utils/
├── tests/
├── examples/
├── docs/
├── requirements.txt
└── README.md
```

---

### Phase 1: Context 管理系统 (3-4天)

**目标:** 实现 Master Agent 的 Context 管理

**任务:**
- [ ] 实现 `MasterContext` 类
- [ ] 实现 `Decision` 数据结构
- [ ] 实现 `ArtifactManager` (文件索引和管理)
- [ ] 实现 Context 序列化/反序列化
- [ ] 编写单元测试

**核心文件:**
- `src/core/context.py`
- `src/core/decision.py`
- `src/core/artifact_manager.py`

**验收标准:**
- Context 可以正确存储和检索三部分信息
- Artifacts 可以正确索引和访问
- Decision Path 可以正确追加和查询

---

### Phase 2: Planner Agent (4-5天)

**目标:** 实现计划管理智能体

**任务:**
- [ ] 封装 PlanNotebook 交互
- [ ] 实现计划初始化逻辑
- [ ] 实现计划更新和修改
- [ ] 实现计划回滚（基于 history）
- [ ] 实现计划上下文提取
- [ ] 编写集成测试

**核心文件:**
- `src/agents/planner_agent.py`

**验收标准:**
- 能够基于用户需求自动生成初始计划
- 能够响应反馈更新计划
- 能够回滚到历史版本
- 提供简洁的计划上下文给 Master Agent

**测试场景:**
```python
# 示例测试
planner = PlannerAgent(plan_notebook)

# 1. 初始化计划
plan = await planner.initialize_plan("构建一个天气查询网页应用")

# 2. 获取上下文
context = await planner.get_current_plan_context()

# 3. 更新计划
feedback = {"type": "user_interrupt", "new_requirement": "添加地图显示"}
updated_plan = await planner.update_plan(feedback)

# 4. 回滚
rollback_plan = await planner.rollback_plan(version=-1)
```

---

### Phase 3: Master Agent 核心 (5-6天)

**目标:** 实现主控决策智能体

**任务:**
- [ ] 实现 Master Agent 基础类
- [ ] 实现 Context 集成
- [ ] 实现 Prompt 构建逻辑
- [ ] 实现工具调用机制
- [ ] 实现决策记录
- [ ] 编写单元和集成测试

**核心文件:**
- `src/agents/master_agent.py`

**验收标准:**
- 能够基于 Context 构建合理的 Prompt
- 能够调用工具并记录决策
- Decision Path 正确维护
- Artifacts 正确索引

**重点:**
- Prompt 设计要简洁有效
- 使用较小模型（如 GPT-4o-mini）进行决策
- 清晰的工具调用接口

---

### Phase 4: Reflector Agent (3-4天)

**目标:** 实现质量检验智能体

**任务:**
- [ ] 实现 Reflector Agent 基础类
- [ ] 实现质量检验逻辑
- [ ] 实现反馈路由决策
- [ ] 集成到 Master Agent 工作流
- [ ] 编写测试用例

**核心文件:**
- `src/agents/reflector_agent.py`

**验收标准:**
- 能够检验工作质量
- 能够正确路由反馈（Master 或 Planner）
- 能够识别异常情况

**测试场景:**
```python
reflector = ReflectorAgent(model_config)

# 检验当前状态
reflection = await reflector.reflect(master_context)

# 根据结果路由
if reflection.routing == 'master':
    # 反馈给 Master 继续或修改
    pass
elif reflection.routing == 'planner':
    # 反馈给 Planner 更新计划
    pass
```

---

### Phase 5: Sub-Agent 独立调用 (5-6天)

**目标:** 实现三大 Sub-Agent 的独立调用模式

**任务:**
- [ ] 实现 Code Agent (基础版 - 代码执行、文件操作)
- [ ] 实现 Browser Use Agent (基础版 - 浏览、提取信息)
- [ ] 实现 Report Agent (基础版 - Markdown 生成)
- [ ] 实现独立调用接口
- [ ] 集成到 Master Agent
- [ ] 编写测试

**核心文件:**
- `src/agents/sub_agents/code_agent.py`
- `src/agents/sub_agents/browser_use_agent.py`
- `src/agents/sub_agents/report_agent.py`

**验收标准:**
- Code Agent 可以执行代码、生成图表
- Browser Use Agent 可以浏览网页、提取信息
- Report Agent 可以生成 Markdown 报告
- Master Agent 可以正确调用并获取结果

**示例任务:**
```python
# 示例 1: Code Agent 生成图表
action = {
    'type': 'sub_agent_independent',
    'agent_name': 'code_agent',
    'input': {
        'task': 'generate_bar_chart',
        'data': {'A': 10, 'B': 20, 'C': 15}
    }
}
result = await master._call_sub_agent_independent(action)
# result: {'chart_path': '/workspace/session_xxx/artifacts/media/chart.png'}

# 示例 2: Browser Use Agent 浏览网页
action = {
    'type': 'sub_agent_independent',
    'agent_name': 'browser_use_agent',
    'input': {
        'url': 'https://example.com',
        'extraction_task': 'Extract main content'
    }
}
result = await master._call_sub_agent_independent(action)
# result: {'content': '...', 'data_path': '/workspace/session_xxx/artifacts/data/page_data.json'}
```

---

### Phase 6: Sub-Agent 交互式调用 (5-6天)

**目标:** 实现三大 Sub-Agent 的交互式调用模式（共享 Context）

**任务:**
- [ ] 设计 Context 共享机制
- [ ] 实现 Sub-Agent Context 访问接口
- [ ] 实现 Artifacts 同步机制
- [ ] 扩展三个 Sub-Agent 支持交互式调用
- [ ] 实现典型工作流（Web Search + Browser Use + Report）
- [ ] 编写复杂场景测试

**验收标准:**
- Sub-Agent 可以访问 Master Context
- Sub-Agent 可以读取之前的 Artifacts
- Master 和 Sub-Agent 的 Artifacts 正确同步
- 完整的信息检索工作流可以运行

**示例任务:**
```python
# 示例 1: Code Agent 交互式调用
action = {
    'type': 'sub_agent_interactive',
    'agent_name': 'code_agent',
    'input': {
        'task': 'build_web_app',
        'requirements': '基于之前收集的天气数据构建展示网页'
    }
}
# Code Agent 可以访问:
# - shared_context.artifacts_index['weather_data.json']
# - shared_context.decision_history (了解数据来源)
result = await master._call_sub_agent_interactive(action)

# 示例 2: 完整的研究工作流
# Step 1: Web Search
search_results = await master.tools['web_search']('AI Agent 最新进展')

# Step 2: Browser Use Agent 详细浏览（交互式）
for url in search_results[:5]:
    action = {
        'type': 'sub_agent_interactive',
        'agent_name': 'browser_use_agent',
        'input': {'url': url, 'task': 'extract_research_insights'}
    }
    await master._call_sub_agent_interactive(action)

# Step 3: Report Agent 整合报告（交互式）
action = {
    'type': 'sub_agent_interactive',
    'agent_name': 'report_agent',
    'input': {'topic': 'AI Agent 最新进展综述'}
}
# Report Agent 访问所有之前收集的数据
report = await master._call_sub_agent_interactive(action)
```

---

### Phase 7: Docker Sandbox 集成 (4-5天)

**目标:** 为每个 Session 提供隔离的运行环境

**任务:**
- [ ] 设计 Docker 镜像
- [ ] 实现 Session 管理器
- [ ] 实现文件系统挂载
- [ ] 实现代码执行沙盒
- [ ] 实现浏览器环境
- [ ] 编写资源限制和清理逻辑

**核心文件:**
- `src/sandbox/docker_manager.py`
- `src/sandbox/session_manager.py`
- `Dockerfile`

**验收标准:**
- 每个 Session 有独立的 Docker 容器
- 文件系统正确隔离
- 代码可以在沙盒中安全执行
- 浏览器可以正常工作
- 资源限制生效

**Dockerfile 示例:**
```dockerfile
FROM ubuntu:22.04

# 安装 Python
RUN apt-get update && apt-get install -y python3.11 python3-pip

# 安装 Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
RUN apt-get install -y nodejs

# 安装 Playwright
RUN pip3 install playwright
RUN playwright install --with-deps chromium

# 工作目录
WORKDIR /workspace

# 资源限制在 docker run 时设置
```

---

### Phase 8: 端到端集成 (5-6天)

**目标:** 整合所有组件，实现完整工作流

**任务:**
- [ ] 实现主控流程编排
- [ ] 实现用户交互界面（CLI）
- [ ] 实现会话持久化
- [ ] 实现错误处理和重试
- [ ] 编写端到端测试

**核心文件:**
- `src/orchestrator.py`
- `src/cli.py`

**验收标准:**
- 完整的用户请求处理流程
- 计划、执行、检验的闭环
- 用户可以打断和修改需求
- 会话可以保存和恢复

**工作流示例:**
```
1. 用户输入需求
2. Planner 初始化计划
3. Master 开始执行
   - 调用工具/Sub-Agent
   - 记录决策
   - 沉淀文件
4. Reflector 检验
   - 通过 → 继续
   - 需要修改 → Master 调整
   - 需要重新计划 → Planner 更新
5. 循环直到完成
6. 输出最终结果
```

---

### Phase 9: 高级功能和优化 (6-8天)

**目标:** 实现高级特性和性能优化

**任务:**
- [ ] 增强三大 Sub-Agent 功能
  - Code Agent: 测试自动生成、代码审查
  - Browser Use Agent: 复杂交互、表单填写
  - Report Agent: PDF 生成、多格式导出
- [ ] 实现并行工具调用（Master Agent 同时调用多个工具）
- [ ] 实现长期记忆（跨 Session 的知识积累）
- [ ] 可选：RAG 知识库集成（为 Report Agent 提供参考资料）
- [ ] 性能优化和稳定性改进

**可选功能（工程化扩展）:**
- 多模态输入支持（图片、语音）
- 实时流式输出
- Web UI 界面
- 分布式部署支持
- Session 状态持久化到数据库

---

### Phase 10: 测试和文档 (3-4天)

**目标:** 完善测试和文档

**任务:**
- [ ] 编写完整的单元测试
- [ ] 编写集成测试
- [ ] 编写端到端测试
- [ ] 编写用户文档
- [ ] 编写开发者文档
- [ ] 创建示例项目

**产出:**
- 测试覆盖率 > 80%
- 完整的 API 文档
- 用户使用指南
- 开发者贡献指南

---

## 技术栈

**核心框架:**
- AgentScope (多智能体框架)
- Python 3.11+
- asyncio (异步编程)

**LLM 支持:**
- OpenAI GPT-4o-mini (Master Agent)
- OpenAI GPT-4 (Planner, Reflector, Sub-Agents)
- 或其他兼容模型（Anthropic Claude, Qwen 等）

**工具和依赖:**
- Docker (沙盒环境)
- Playwright (浏览器自动化)
- Pydantic (数据验证)
- SQLite (会话持久化)

**开发工具:**
- pytest (测试)
- black/ruff (代码格式化)
- mypy (类型检查)

---

## 里程碑

| Phase | 目标 | 预计时间 | 关键产出 |
|-------|------|----------|---------|
| 0 | 项目设置 | 1-2天 | 项目结构 |
| 1 | Context 管理 | 3-4天 | Context/Decision 类 |
| 2 | Planner Agent | 4-5天 | 计划管理智能体 |
| 3 | Master Agent | 5-6天 | 主控决策智能体 |
| 4 | Reflector Agent | 3-4天 | 质量检验智能体 |
| 5 | Sub-Agent 独立调用 | 5-6天 | Code/Browser Agent |
| 6 | Sub-Agent 交互式调用 | 5-6天 | Context 共享机制 |
| 7 | Docker Sandbox | 4-5天 | 沙盒环境 |
| 8 | 端到端集成 | 5-6天 | 完整工作流 |
| 9 | 高级功能 | 6-8天 | Research/Writer Agent |
| 10 | 测试和文档 | 3-4天 | 文档和测试 |

**总预计时间:** 6-8周

---

## 风险和挑战

### 技术风险
1. **Context 大小管理**: 随着任务复杂度增加，Context 可能过大
   - 缓解: 实现 Context 压缩和总结机制

2. **Sub-Agent Context 共享复杂性**: 交互式调用的状态同步
   - 缓解: 清晰定义共享接口，使用版本控制

3. **Docker 资源开销**: 每个 Session 一个容器可能资源密集
   - 缓解: 实现容器池和复用机制

### 开发风险
1. **集成复杂度**: 多个 Agent 协作的复杂性
   - 缓解: 逐步集成，充分测试

2. **Prompt 工程**: 不同 Agent 的 Prompt 设计
   - 缓解: 迭代优化，建立 Prompt 库

---

## 下一步

**立即行动:**
1. 确认整体设计
2. 开始 Phase 0: 项目设置
3. 搭建开发环境
4. 创建 Git 分支和项目结构

**需要讨论的问题:**
1. 使用哪个 LLM 提供商？(OpenAI, Anthropic, 国产模型?)
2. Docker 部署方式？(本地 or 云端?)
3. 文件存储方案？(本地文件系统 or 对象存储?)
4. 是否需要 Web UI？

---

## 参考资料

- AgentScope 文档: https://github.com/modelscope/agentscope
- PlanNotebook 源码: `/src/agentscope/plan/_plan_notebook.py`
- ReAct Agent 实现: `/src/agentscope/agent/_react_agent.py`
- MsgHub 工作流: `/src/agentscope/pipeline/_msghub.py`
