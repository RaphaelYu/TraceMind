import type { ChangeEvent } from 'react'

export type IntentFormValue = {
  intentId: string
  title: string
  context: string
  goal: string
  nonGoals: string[]
  actors: string[]
  inputs: string[]
  outputs: string[]
  invariants: string[]
  policies: string[]
  successMetrics: string[]
  risks: string[]
  assumptions: string[]
  parentIntent: string
  relatedIntents: string[]
}

type IntentEditorProps = {
  value: IntentFormValue
  onChange: (value: IntentFormValue) => void
  disabled?: boolean
  errors?: string[]
}

const toTextarea = (list: string[]): string => list.join('\n')
const fromTextarea = (value: string): string[] =>
  value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

const ListField = ({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string[]
  onChange: (value: string[]) => void
  placeholder?: string
}) => (
  <label>
    {label}
    <textarea
      value={toTextarea(value)}
      onChange={(event) => onChange(fromTextarea(event.target.value))}
      placeholder={placeholder}
      rows={3}
    />
  </label>
)

const IntentEditor = ({ value, onChange, disabled, errors }: IntentEditorProps) => {
  const handleField = (field: keyof IntentFormValue) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const updated = { ...value, [field]: event.target.value }
    onChange(updated)
  }

  const handleListField =
    (field: keyof IntentFormValue) =>
    (items: string[]) => {
      onChange({ ...value, [field]: items })
    }

  return (
    <div className="intent-editor">
      <div className="intent-editor__header">
        <h4>Intent metadata</h4>
        <p>
          Fill the prompt fields below. Arrays are newline-separated; each line is treated as an individual entry.
        </p>
      </div>
      <div className="intent-editor__grid">
        <label>
          Intent ID
          <input
            type="text"
            value={value.intentId}
            onChange={handleField('intentId')}
            disabled={Boolean(disabled && value.intentId)}
          />
        </label>
        <label>
          Title
          <input type="text" value={value.title} onChange={handleField('title')} disabled={disabled} />
        </label>
        <label>
          Context
          <textarea value={value.context} onChange={handleField('context')} disabled={disabled} rows={3} />
        </label>
        <label>
          Primary goal
          <textarea value={value.goal} onChange={handleField('goal')} disabled={disabled} rows={3} />
        </label>
        <ListField label="Non-goals" value={value.nonGoals} onChange={handleListField('nonGoals')} placeholder="one per line" />
        <ListField label="Actors" value={value.actors} onChange={handleListField('actors')} placeholder="user / system / external" />
        <ListField label="Inputs" value={value.inputs} onChange={handleListField('inputs')} placeholder="state:in.foo" />
        <ListField label="Outputs" value={value.outputs} onChange={handleListField('outputs')} placeholder="artifact:out.bar" />
        <ListField label="Invariant constraints" value={value.invariants} onChange={handleListField('invariants')} placeholder="safe invariants" />
        <ListField label="Policy constraints" value={value.policies} onChange={handleListField('policies')} placeholder="GDPR, SOC2, etc." />
        <ListField label="Success metrics" value={value.successMetrics} onChange={handleListField('successMetrics')} placeholder="95% within 5s" />
        <ListField label="Risks" value={value.risks} onChange={handleListField('risks')} placeholder="alert storms" />
        <ListField label="Assumptions" value={value.assumptions} onChange={handleListField('assumptions')} placeholder="data is available" />
        <label>
          Parent intent
          <input type="text" value={value.parentIntent} onChange={handleField('parentIntent')} disabled={disabled} />
        </label>
        <ListField
          label="Related intents"
          value={value.relatedIntents}
          onChange={handleListField('relatedIntents')}
          placeholder="TM-INT-0002"
        />
      </div>
      {errors && errors.length > 0 && (
        <div className="intent-editor__errors">
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

export default IntentEditor
