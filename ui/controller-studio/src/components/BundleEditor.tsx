export type AgentFormValue = {
  agentId: string
  name: string
  version: string
  runtimeKind: string
  inputs: string[]
  outputs: string[]
  effectName: string
  effectTarget: string
}

export type PlanStepFormValue = {
  step: string
  agentId: string
  phase: string
  inputs: string[]
  outputs: string[]
}

export type BundleFormValue = {
  bundleId: string
  preconditions: string[]
  agents: AgentFormValue[]
  plan: PlanStepFormValue[]
}

type BundleEditorProps = {
  value: BundleFormValue
  onChange: (value: BundleFormValue) => void
  disabled?: boolean
  errors?: string[]
}

const parseList = (value: string): string[] =>
  value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

const asTextarea = (items: string[]): string => items.join('\n')

const ListTextarea = ({
  label,
  items,
  onChange,
  placeholder,
}: {
  label: string
  items: string[]
  onChange: (items: string[]) => void
  placeholder?: string
}) => (
  <label>
    {label}
    <textarea value={asTextarea(items)} onChange={(event) => onChange(parseList(event.target.value))} placeholder={placeholder} rows={3} />
  </label>
)

const defaultAgent = (): AgentFormValue => ({
  agentId: '',
  name: '',
  version: '0.1',
  runtimeKind: 'python',
  inputs: [],
  outputs: [],
  effectName: '',
  effectTarget: '',
})

const defaultStep = (): PlanStepFormValue => ({
  step: '',
  agentId: '',
  phase: 'run',
  inputs: [],
  outputs: [],
})

const BundleEditor = ({ value, onChange, disabled, errors }: BundleEditorProps) => {
  const setField = (field: keyof BundleFormValue, data: unknown) => {
    onChange({ ...value, [field]: data as never })
  }

  const updateAgent = (index: number, patch: Partial<AgentFormValue>) => {
    const updated = value.agents.map((agent, idx) => (idx === index ? { ...agent, ...patch } : agent))
    onChange({ ...value, agents: updated })
  }

  const removeAgent = (index: number) => {
    if (value.agents.length === 1) return
    const updated = value.agents.filter((_, idx) => idx !== index)
    onChange({ ...value, agents: updated })
  }

  const addAgent = () => {
    onChange({ ...value, agents: [...value.agents, defaultAgent()] })
  }

  const updateStep = (index: number, patch: Partial<PlanStepFormValue>) => {
    const updated = value.plan.map((step, idx) => (idx === index ? { ...step, ...patch } : step))
    onChange({ ...value, plan: updated })
  }

  const removeStep = (index: number) => {
    if (value.plan.length === 1) return
    const updated = value.plan.filter((_, idx) => idx !== index)
    onChange({ ...value, plan: updated })
  }

  const addStep = () => {
    onChange({ ...value, plan: [...value.plan, defaultStep()] })
  }

  return (
    <div className="bundle-editor">
      <div className="bundle-editor__grid">
        <label>
          Bundle ID
          <input type="text" value={value.bundleId} onChange={(event) => setField('bundleId', event.target.value)} disabled={disabled} />
        </label>
        <ListTextarea label="Preconditions" items={value.preconditions} onChange={(items) => setField('preconditions', items)} placeholder="one per line" />
      </div>

      <section className="bundle-editor__section">
        <div className="bundle-editor__section-head">
          <h4>Agents</h4>
          <button type="button" onClick={addAgent} disabled={disabled}>
            Add agent
          </button>
        </div>
        {value.agents.map((agent, index) => (
          <div key={`agent-${index}`} className="bundle-editor__card">
            <div className="bundle-editor__card-header">
              <strong>Agent {index + 1}</strong>
              <button type="button" onClick={() => removeAgent(index)} disabled={disabled || value.agents.length === 1}>
                Remove
              </button>
            </div>
            <div className="bundle-editor__grid">
              <label>
                Agent ID
                <input type="text" value={agent.agentId} onChange={(event) => updateAgent(index, { agentId: event.target.value })} disabled={disabled} />
              </label>
              <label>
                Name
                <input type="text" value={agent.name} onChange={(event) => updateAgent(index, { name: event.target.value })} disabled={disabled} />
              </label>
              <label>
                Version
                <input type="text" value={agent.version} onChange={(event) => updateAgent(index, { version: event.target.value })} disabled={disabled} />
              </label>
              <label>
                Runtime kind
                <input type="text" value={agent.runtimeKind} onChange={(event) => updateAgent(index, { runtimeKind: event.target.value })} disabled={disabled} />
              </label>
              <ListTextarea label="Inputs" items={agent.inputs} onChange={(items) => updateAgent(index, { inputs: items })} placeholder="state:..." />
              <ListTextarea label="Outputs" items={agent.outputs} onChange={(items) => updateAgent(index, { outputs: items })} placeholder="artifact:..." />
              <label>
                Effect name
                <input type="text" value={agent.effectName} onChange={(event) => updateAgent(index, { effectName: event.target.value })} disabled={disabled} />
              </label>
              <label>
                Effect target
                <input type="text" value={agent.effectTarget} onChange={(event) => updateAgent(index, { effectTarget: event.target.value })} disabled={disabled} />
              </label>
            </div>
          </div>
        ))}
      </section>

      <section className="bundle-editor__section">
        <div className="bundle-editor__section-head">
          <h4>Plan steps</h4>
          <button type="button" onClick={addStep} disabled={disabled}>
            Add step
          </button>
        </div>
        {value.plan.map((step, index) => (
          <div key={`step-${index}`} className="bundle-editor__card">
            <div className="bundle-editor__card-header">
              <strong>Step {index + 1}</strong>
              <button type="button" onClick={() => removeStep(index)} disabled={disabled || value.plan.length === 1}>
                Remove
              </button>
            </div>
            <div className="bundle-editor__grid">
              <label>
                Step name
                <input type="text" value={step.step} onChange={(event) => updateStep(index, { step: event.target.value })} disabled={disabled} />
              </label>
              <label>
                Agent ID
                <input type="text" value={step.agentId} onChange={(event) => updateStep(index, { agentId: event.target.value })} disabled={disabled} />
              </label>
              <label>
                Phase
                <input type="text" value={step.phase} onChange={(event) => updateStep(index, { phase: event.target.value })} disabled={disabled} />
              </label>
              <ListTextarea label="Inputs" items={step.inputs} onChange={(items) => updateStep(index, { inputs: items })} placeholder="state:foo" />
              <ListTextarea label="Outputs" items={step.outputs} onChange={(items) => updateStep(index, { outputs: items })} placeholder="artifact:bar" />
            </div>
          </div>
        ))}
      </section>

      {errors && errors.length > 0 && (
        <div className="bundle-editor__errors">
          <strong>Error</strong>
          <ul>
            {errors.map((message, index) => (
              <li key={`${message}-${index}`}>{message}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default BundleEditor
