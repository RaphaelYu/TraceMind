# TraceMind 操作手册

本文档整理 TraceMind 常用场景下的命令与步骤。涉及具体业务逻辑（Flow、插件、策略等）的位置均以 **你来写** 标注。

---

## 0. 环境与安装

```bash
python3 -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install trace-mind==1.1.0      # 或从源码: pip install -e .
# 推荐：pip install pyyaml （触发器 YAML 支持）
```

---

## 1. 创建应用骨架

```bash
tm init demo-app
cd demo-app
```

目录说明：`flows/`、`policies/`、`plugins/`、`housekeeping/` 等。

---

## 2. Flow 开发

```bash
tm new flow hello-world
```

- 编辑 `flows/hello-world.yaml`（**你来写**：steps、输入输出、插件调用等）。
- CLI 验证：

```bash
tm run flows/hello-world.yaml -i '{"name":"world"}'
tm flow lint flows/hello-world.yaml
tm flow plan flows/hello-world.yaml
tm validate flows/hello-world.yaml
tm simulate flows/hello-world.yaml
```

---

## 3. 插件集成

1. 在 `plugins/` 下创建模块（例如 `plugins/my_plugin.py`）。
2. 插件逻辑 **你来写**：

```python
def greet(context):
    name = context["input"]["name"]
    return {"message": f"Hello, {name}!"}
```

3. Flow 中 step `call` 指向 `plugins.my_plugin:greet`。
4. 如需自动加载可在 `pyproject.toml` 配置 entry_points（**你来写**）。

---

## 4. 策略（Policy）

```bash
tm new policy example-policy --epsilon
```

- 在 `policies/example_policy.py` 中实现策略（**你来写**）。
- 测试：

```bash
python policies/example_policy.py
tm policy lint policies/example_policy.py
```

---

## 5. Worker & 队列

启动 worker：

```bash
tm workers start \
  -n 2 \
  --queue file \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --dlq-dir data/dlq \
  --runtime tm.app.wiring_flows:_runtime
```

队列状态：

```bash
tm queue stats --queue file --queue-dir data/queue --json | jq .
```

停止:

```bash
tm workers stop --pid-file tm-workers.pid
```

---

## 6. Detached Run / Daemon

```bash
export TM_ENABLE_DAEMON=1
export TM_FILE_QUEUE_V2=1
```

启动 daemon（仅 worker）：

```bash
tm daemon start \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --dlq-dir data/dlq \
  --workers 2 \
  --runtime tm.app.wiring_flows:_runtime
```

Detached Run：

```bash
tm run flows/hello-world.yaml --detached -i '{"name":"async"}'
tm daemon ps
tm daemon ps --json | jq .
```

停止 daemon：`tm daemon stop`

---

## 7. Trigger 配置与运行

生成模板：`tm triggers init`

### 配置示例（triggers.yaml）

```yaml
version: 1
triggers:
  - id: hourly
    kind: cron
    cron: "0 * * * *"
    timezone: local
    flow_id: flows/hourly.yaml
    input:
      mode: summary

  - id: orders
    kind: webhook
    route: "/hooks/orders"
    method: POST
    bind_host: 127.0.0.1
    bind_port: 8081
    allow_cleartext: true
    secret: change-me
    flow_id: flows/order-intake.yaml
    input:
      body: "{{ body }}"

  - id: ingest
    kind: filesystem
    path: ./incoming
    pattern: "*.json"
    recursive: false
    interval_seconds: 5
    flow_id: flows/file-import.yaml
    input:
      file_path: "{{ path }}"
```

模板字段支持 `{{ }}` 占位符（详见 `docs/triggers.md`）。

### 验证 & 运行

```bash
tm triggers validate --path triggers.yaml

tm triggers run --config triggers.yaml \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --dlq-dir data/dlq
```

Webhook 测试：

```bash
curl -X POST http://127.0.0.1:8081/hooks/orders \
  -H 'Content-Type: application/json' \
  -H 'X-TraceMind-Secret: change-me' \
  -d '{"order_id":123}'
```

Filesystem：将文件写入 `incoming/` 即可触发。

### Daemon + Triggers

```bash
tm daemon start \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --dlq-dir data/dlq \
  --workers 2 \
  --runtime tm.app.wiring_flows:_runtime \
  --enable-triggers \
  --triggers-config triggers.yaml
```

---

## 8. 测试 & Lint

```bash
pytest
pytest tests/test_trigger_config.py tests/test_trigger_manager.py
ruff check
```

文档（如需）：`mkdocs serve`

---

## 9. 发布流程

1. 更新 `pyproject.toml` 版本 & `docs/CHANGELOG.md`
2. 构建与上传

```bash
python -m build
twine upload dist/*
```

或推 `v*` tag 触发 GitHub Actions (`release.yml`) 自动发布。

---

## 10. 故障排查

| 问题 | 处理 |
| --- | --- |
| Detached run 无响应 | 确认 daemon 运行、`TM_ENABLE_DAEMON=1` |
| Trigger YAML 解析失败 | `tm triggers validate` 检查；Windows 路径建议用 JSON |
| Webhook 401 | 校验 `X-TraceMind-Secret` |
| Filesystem 无反应 | 检查 `interval_seconds ≥ 0.5`，路径和 pattern 是否正确 |

---

## 11. 自定义扩展（**你来写**）

- Flow 逻辑（`flows/`）
- 插件实现（`plugins/`）
- 策略 / MCP 集成（`policies/`）
- 自定义 Trigger Adapter：使用 `tm.triggers.register_trigger_adapter`
- 部署与脚本（`scripts/` 等）

祝开发顺利！
