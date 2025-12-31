import type { PromptTemplateInfo, LlmConfigInfo } from '../api/tm'

export type LlmConfigForm = {
  model: string
  promptTemplateVersion: string
  promptVersion: string
  modelId: string
  modelVersion: string
}

type LlmConfigProps = {
  workspaceId: string | null
  promptTemplates: PromptTemplateInfo[]
  configs: LlmConfigInfo[]
  selectedConfigId: string | null
  formData: LlmConfigForm
  onFormChange: (field: keyof LlmConfigForm, value: string) => void
  onSelectConfig: (configId: string | null) => void
  onCreateConfig: () => void
  isCreating: boolean
}

const formatTimestamp = (value: string): string => {
  const candidate = new Date(value)
  if (Number.isNaN(candidate.getTime())) {
    return '—'
  }
  return candidate.toLocaleString()
}

const LlmConfig = ({
  workspaceId,
  promptTemplates,
  configs,
  selectedConfigId,
  formData,
  onFormChange,
  onSelectConfig,
  onCreateConfig,
  isCreating,
}: LlmConfigProps) => {
  const selectedTemplate = promptTemplates.find(
    (template) => template.version === formData.promptTemplateVersion,
  )
  const createDisabled =
    isCreating ||
    !workspaceId ||
    !formData.model.trim() ||
    !formData.promptTemplateVersion.trim()

  const sortedConfigs = [...configs].sort((a, b) => b.created_at.localeCompare(a.created_at))
  const handleSelect = (configId: string) => {
    onSelectConfig(selectedConfigId === configId ? null : configId)
  }

  return (
    <div className="llm-config">
      <div className="llm-config__grid">
        <div className="llm-config__section">
          <div className="llm-config__section-head">
            <h4>Saved configs</h4>
            <p>Select a recorded model + prompt combo so the UI always references the same metadata.</p>
          </div>
          {sortedConfigs.length ? (
            <div className="llm-config__list">
              {sortedConfigs.map((config) => {
                const isSelected = config.config_id === selectedConfigId
                return (
                  <button
                    key={config.config_id}
                    type="button"
                    className={`llm-config-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => handleSelect(config.config_id)}
                  >
                    <div>
                      <strong>{config.model}</strong>
                      <span>
                        Prompt: {config.prompt_template_version} • {config.prompt_version}
                      </span>
                    </div>
                    <div className="llm-config-card__meta">
                      <small>{formatTimestamp(config.created_at)}</small>
                      <small>#{config.config_id}</small>
                    </div>
                  </button>
                )
              })}
            </div>
          ) : (
            <p className="hint">No saved configs yet. Create one below to persist your LLM settings.</p>
          )}
        </div>
        <div className="llm-config__section">
          <div className="llm-config__section-head">
            <h4>New config</h4>
            <p>
              Provide the model name and prompt template version you expect Decide to use. The UI pre-fills these after previewing a
              cycle and can snap back to the recorded metadata at any time.
            </p>
          </div>
          <div className="llm-config-form">
            <div className="llm-config-form__grid">
              <label>
                Model
                <input
                  type="text"
                  value={formData.model}
                  onChange={(event) => onFormChange('model', event.target.value)}
                  placeholder="e.g. gpt-4.1"
                  disabled={!workspaceId}
                />
              </label>
              <label>
                Prompt template
                <select
                  value={formData.promptTemplateVersion}
                  onChange={(event) => onFormChange('promptTemplateVersion', event.target.value)}
                  disabled={!workspaceId || !promptTemplates.length}
                >
                  <option value="">— select a template —</option>
                  {promptTemplates.map((template) => (
                    <option key={template.version} value={template.version}>
                      {template.title} ({template.version})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Prompt version
                <input
                  type="text"
                  value={formData.promptVersion}
                  onChange={(event) => onFormChange('promptVersion', event.target.value)}
                  placeholder="optional prompt hash or version label"
                  disabled={!workspaceId}
                />
              </label>
            </div>
            {selectedTemplate?.description && (
              <p className="llm-config-form__description">{selectedTemplate.description}</p>
            )}
            <div className="llm-config-form__grid llm-config-form__grid--stacked">
              <label>
                Model ID (optional)
                <input
                  type="text"
                  value={formData.modelId}
                  onChange={(event) => onFormChange('modelId', event.target.value)}
                  placeholder="provider-specific identifier"
                  disabled={!workspaceId}
                />
              </label>
              <label>
                Model version (optional)
                <input
                  type="text"
                  value={formData.modelVersion}
                  onChange={(event) => onFormChange('modelVersion', event.target.value)}
                  placeholder="provider-specific version"
                  disabled={!workspaceId}
                />
              </label>
            </div>
            <div className="llm-config-form__actions">
              <button type="button" onClick={onCreateConfig} disabled={createDisabled}>
                {isCreating ? 'Saving config…' : 'Create config'}
              </button>
              <p className="hint">
                Without a saved config, the server still records the model/prompt hash, but the UI can reload a recorded config after previewing.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default LlmConfig
