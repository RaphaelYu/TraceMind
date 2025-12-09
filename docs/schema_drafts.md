## PluginSpec / WorkflowSpec JSON Schema 草稿（v0）

> 用于校准字段一义性，尚未锁定为稳定 API。命名空间与 type name 需结合后续类型注册表。

### PluginSpec（draft）
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PluginSpec",
  "type": "object",
  "required": ["kind", "version", "plugin"],
  "properties": {
    "kind": {"const": "PluginSpec"},
    "version": {"type": "string"},
    "plugin": {
      "type": "object",
      "required": ["id", "name", "compute_model", "data_model"],
      "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "provider": {"type": "string"},
        "compute_model": {
          "type": "object",
          "properties": {
            "mode": {"enum": ["stateful", "stateless", "stream", "batch", "command"]},
            "invocation": {"enum": ["sync", "async", "stream"]},
            "supports_deferred": {"type": "boolean"},
            "resources": {"type": "object", "additionalProperties": {"type": "string"}}
          },
          "additionalProperties": true
        },
        "data_model": {
          "type": "object",
          "properties": {
            "inputs": {
              "type": "array",
              "items": {"$ref": "#/$defs/io"}
            },
            "outputs": {
              "type": "array",
              "items": {"$ref": "#/$defs/io"}
            }
          },
          "additionalProperties": false
        },
        "io_policies": {"$ref": "#/$defs/ioPolicies"},
        "composability": {
          "type": "object",
          "properties": {
            "role": {"enum": ["sensor", "processor", "actuator", "composite"]},
            "composition_patterns": {"type": "array", "items": {"type": "string"}}
          },
          "additionalProperties": true
        },
        "data_compatibility": {
          "type": "object",
          "properties": {
            "outputs": {"type": "object", "additionalProperties": {"$ref": "#/$defs/compat"}}
          },
          "additionalProperties": true
        },
        "collaboration_model": {
          "type": "object",
          "properties": {
            "supports_collaboration": {"type": "boolean"},
            "agent_kind": {"type": "string"},
            "pattern_refs": {"type": "array", "items": {"type": "string"}}
          },
          "additionalProperties": true
        }
      },
      "additionalProperties": false
    }
  },
  "$defs": {
    "io": {
      "type": "object",
      "required": ["name", "type"],
      "properties": {
        "name": {"type": "string"},
        "type": {"type": "string"},
        "description": {"type": "string"}
      },
      "additionalProperties": true
    },
    "ioPolicies": {
      "type": "object",
      "properties": {
        "inputs": {"type": "object", "additionalProperties": {"$ref": "#/$defs/policy"}},
        "outputs": {"type": "object", "additionalProperties": {"$ref": "#/$defs/policy"}}
      },
      "additionalProperties": false
    },
    "policy": {
      "type": "object",
      "properties": {
        "external_writable": {"type": "boolean"},
        "external_readable": {"type": "boolean"},
        "allowed_sources": {"type": "array", "items": {"type": "string"}},
        "allowed_sinks": {"type": "array", "items": {"type": "string"}}
      },
      "additionalProperties": true
    },
    "compat": {
      "type": "object",
      "properties": {
        "type": {"type": "string"},
        "convertible_to": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["target_type"],
            "properties": {
              "target_type": {"type": "string"},
              "via_plugin": {"type": "string"}
            },
            "additionalProperties": true
          }
        }
      },
      "additionalProperties": true
    }
  }
}
```

### WorkflowSpec（draft）
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "WorkflowSpec",
  "type": "object",
  "required": ["kind", "version", "flow"],
  "properties": {
    "kind": {"const": "WorkflowSpec"},
    "version": {"type": "string"},
    "flow": {
      "type": "object",
      "required": ["name", "steps", "entrypoint"],
      "properties": {
        "name": {"type": "string"},
        "flow_id": {"type": "string"},
        "entrypoint": {"type": "string"},
        "steps": {
          "type": "object",
          "additionalProperties": {"$ref": "#/$defs/step"}
        }
      },
      "additionalProperties": true
    }
  },
  "$defs": {
    "step": {
      "type": "object",
      "required": ["name", "operation"],
      "properties": {
        "name": {"type": "string"},
        "operation": {"enum": ["task", "switch", "parallel", "finish"]},
        "next_steps": {"type": "array", "items": {"type": "string"}},
        "uses": {"type": "string"},
        "config": {"type": "object"},
        "reads": {"type": "array", "items": {"type": "string"}},
        "writes": {"type": "array", "items": {"type": "string"}}
      },
      "additionalProperties": true
    }
  }
}
```
