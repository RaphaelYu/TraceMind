version: dsl/v0
workflow: plant-monitor
triggers:
  cron:
    schedule: "*/5 * * * *"
inputs:
  endpoint: string
  nodes: list<string>
steps:
  - read(opcua.read):
      endpoint: $input.endpoint
      node_ids: $input.nodes
  - decide(policy.apply):
      values: $step.read.values
  - when $step.decide.action in ["WRITE_BACK","SHUTDOWN"]:
      write(opcua.write):
        endpoint: $input.endpoint
        node_id: $step.decide.target_node
        value: $step.decide.value
outputs:
  decision: $step.decide
