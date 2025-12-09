## TraceMind 插件/工作流梳理与概念映射

### 1. 现状梳理（任务一）

- **插件/模块定义**
  - 协议：`tm/plugins/base.py` 定义了 `Plugin` Protocol，要求实现 `build_plan() -> Optional[Plan]` 与 `register_bus(bus, svc)`。
  - 计划结构：`tm/pipeline/engine.py` 的 `Plan` = `{steps, rules}`。`StepSpec`（name, reads, writes, fn）描述同步纯函数；`Rule`（triggers, steps）用选择器触发。`tm/pipeline/selectors.py` 支持 `*` / `[]` 匹配。
  - 插件示例：`tm/plugins/richdemo.py`、`tm/plugins_local/richdemon.py` 均返回一组 `StepSpec`，通过 reads/writes 约定数据路径，未声明类型/能力列表。`StepSpec.fn` 在当前 Pipeline 仅支持同步函数。
  - 发现：无统一插件描述文件/Schema，无能力列表字段；插件发现依赖 `importlib.metadata.entry_points`（`tm/plugins/loader.py:load`），`tm/plugins/loader.py` 已提供 `load_plugins()`（优先 entry_points，回退内置模块），但缺少标准化 manifest 约定。

- **工作流/编排表示**
  - Pipeline（事件驱动）：`tm/app/wiring.py` 合并所有插件的 `Plan`，监听 `ObjectUpserted` 事件，基于 JSON diff 的 changed_paths 触发 `Rule`，上下文 `ctx={kind,id,old,new,effects}`。无显式类型/校验，纯 dict。
  - Flow Runtime（DAG）：`tm/flow/spec.py` `FlowSpec` + `StepDef`（operation=TASK/SWITCH/PARALLEL/FINISH，next_steps，config，before/run/after/on_error 钩子）。`tm/flow/runtime.py` 提供异步执行（StepDef.run/钩子可 async）、队列、幂等、治理、回溯。`tm/app/wiring_flows.py` 用示例 CRUD Flow（`tm/app/example_crud_flows.py`）和 recipe flows 运行。
  - 另一套实验性 DAG：`tm/flow/core.py`（`FlowGraph` + operator registry + meta reads/writes/externals，包含静态检查器），但未与主 runtime 集成。

- **协同/多设备机制**
  - 当前代码未出现 UAV/UGV/摄像头等设备模块，也无多 Agent 协同模式。事件总线 `tm/core/bus.py` 仅在本进程内广播，未标注角色/权限。Pipeline/Flow 组合仅按数据路径触发或 DAG 顺序，无共享地图/协同策略的显式结构。

### 2. 概念映射与空白点（任务二）

1) **compute_model**
   - 现有：Pipeline 的 StepSpec 仅同步；Flow runtime 的 StepDef 支持同步或 async 钩子；Flow runtime 提供队列、并发、响应模式（IMMEDIATE/DEFERRED）；Pipeline 顺序执行规则内步骤，无状态标注。
   - 空白：无统一字段描述 stateful/stream/batch/资源约束/最大延迟；无 compute capabilities 列表或 QoS。

2) **data_model**
   - 现有：上下文均为 `dict`，数据路径用字符串 selector（如 `services[].state`）；FlowGraph operator meta 可登记 reads/writes/externals，但未绑定 schema。
   - 空白：无类型系统/Schema/命名空间（如 Image.Frame、GeoPose）；无输入输出签名或验证；无统一注册/转换表。

3) **io_policies**
   - 现有：未显式声明；实际读写权限仅靠 StepSpec.reads/writes 约定，事件总线无 ACL。
   - 空白：无 external_writable/readable、来源/汇点白名单、机密字段保护或审计。

4) **composability**
   - 现有：插件通过 `Plan` 合并（平铺 steps/rules）；FlowSpec/FlowGraph 描述 DAG（TASK/SWITCH/PARALLEL/FINISH），支持分支与并行。
   - 空白：无角色（sensor/processor/actuator/composite）或组合模式声明（pipeline/fan_in/spatial_merge 等）；缺少冲突检测/拓扑约束以外的组合语义。

5) **data_compatibility & collaboration_model**
   - 现有：无显式转换/兼容性定义；Flow runtime/ Pipeline 直接传递 dict。未见跨设备共享状态、坐标/单位转换、协同模式枚举。
   - 空白：类型转换映射、协同模式 ID、Agent kind/状态模型/同步策略完全缺失。

### 3. 模块样本与 PluginSpec 草稿（任务三）

> 这里只使用仓库内真实存在的模块（rich demo 插件 + CRUD Flow）来校准一义性表示。摄像头/无人机等设备类插件在代码中缺位，后续若接入再补对应样例。

#### 3.1 已有模块样本（Pipeline 插件：`tm/plugins/richdemo.py`）
- **现状摘要**（精简关键字段）
  ```python
  steps = {
    "validate_services": StepSpec(
      name="validate_services",
      reads=["services[].name"],
      writes=[],
      fn=_step_validate_services,  # sync
    ),
    "derive_status": StepSpec(
      name="derive_status",
      reads=["status", "services[].state"],
      writes=["status"],
      fn=_step_derive_status,
    ),
  }
  rules = [
    Rule(name="on_services_name_change", triggers=["services[].name"], steps=["validate_services"]),
    Rule(name="on_status_related_change", triggers=["status", "services[].state"], steps=["derive_status"]),
  ]
  ```
- **五个角度简析**
  - compute_model：同步、无状态标注；依赖事件触发（ObjectUpserted diff → Rule）。
  - data_model：自由 dict，读取 `services[].name/state`，写 `status`，无 schema/type。
  - io_policies：仅隐式读写，无外部可读/可写声明。
  - composability：通过 `_merge_plans` 平铺合并；无角色/模式标注。
  - data_compatibility & collaboration_model：无转换/协同定义。
- **PluginSpec 草稿（对照实际行为）**
  ```yaml
  kind: PluginSpec
  version: "0.1-draft"
  plugin:
    id: "demo.service-status"
    name: "Service Status Deriver"
    provider: "internal"
    compute_model:
      mode: "stateless"
      invocation: "sync"
    data_model:
      inputs:
        - name: services[].name
          type: "Service.Name"
        - name: services[].state
          type: "Service.State"
      outputs:
        - name: status
          type: "Service.Status"
    io_policies: {}  # 未声明
    composability:
      role: "processor"
      composition_patterns: ["pipeline"]
    data_compatibility: {}
    collaboration_model:
      supports_collaboration: false
  ```

#### 3.2 已有模块样本（Flow：`tm/app/example_crud_flows.py`）
- **现状摘要**
  ```python
  spec = FlowSpec(name="sample.create")
  spec.add_step(StepDef(name="dispatch", operation=Operation.SWITCH,
                        next_steps=("create","read"), config={"key": self._operation}))
  spec.add_step(StepDef(name="create", operation=Operation.TASK,
                        next_steps=("finish",), config={"mode": ResponseMode.DEFERRED.value}))
  spec.add_step(StepDef(name="read", operation=Operation.TASK,
                        next_steps=("finish",), config={"mode": ResponseMode.IMMEDIATE.value}))
  spec.add_step(StepDef(name="finish", operation=Operation.FINISH))
  ```
- **五个角度简析**
  - compute_model：支持 async 钩子（未使用），配置了 IMMEDIATE/DEFERRED；无资源/状态标注。
  - data_model：未声明输入输出 schema，`config["key"]` 仅路由；任务输出未结构化。
  - io_policies：无。
  - composability：DAG（TASK/SWITCH/FINISH），无角色/模式。
  - data_compatibility & collaboration_model：无。
- **PluginSpec 草稿（作为 Flow → 插件化示例）**
  ```yaml
  kind: PluginSpec
  version: "0.1-draft"
  plugin:
    id: "flow.sample-crud"
    name: "Sample CRUD Flow"
    provider: "internal"
    compute_model:
      mode: "stateful"
      invocation: "async"
      supports_deferred: true
    data_model:
      inputs:
        - name: request
          type: "Crud.Request"
      outputs:
        - name: response
          type: "Crud.Response"
    io_policies: {}
    composability:
      role: "composite"
      composition_patterns: ["pipeline", "switch"]
    data_compatibility: {}
    collaboration_model:
      supports_collaboration: false
  ```

#### 3.3 设备类插件缺口提示
- 当前仓库无摄像头/无人机/无人车模块；若未来接入，建议复用上面的五个角度，用真实接口/数据结构填充 PluginSpec 草稿。

### 4. 最小类型/IO 声明确认（针对现有样本）
- `demo.service-status`: 输入 `Service.Name` / `Service.State`，输出 `Service.Status`。可作为类型注册表的占位符命名。
- `flow.sample-crud`: 输入 `Crud.Request`，输出 `Crud.Response`。可在 WorkflowSpec 中对应 Flow 输入输出签名。

### 4. 主要缺口与落地提示
- 缺少统一的 PluginSpec/WorkflowSpec Schema、插件发现/验证工具（`load_plugins()` 未实现，`tm cli plugin verify` 仅做基本接口调用）。
- 数据类型与 IO 策略未结构化，所有 reads/writes/ctx 均为自由 dict；需要引入类型注册、字段可见性与 ACL。
- 组合/协同语义目前只体现在 DAG 与 triggers，未标注角色/模式/资源约束；多 Agent（UAV/UGV/Camera）完全缺席。
- Flow runtime 已有队列、幂等、治理钩子，可作为 compute_model 中 async/deferred/治理的实现约束输入。
