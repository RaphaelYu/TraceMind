import { useEffect, useState } from 'react'
import IntentEditor, { type IntentFormValue } from '../components/IntentEditor'
import BundleEditor, {
  type BundleFormValue,
  type AgentFormValue,
  type PlanStepFormValue,
} from '../components/BundleEditor'
import {
  listArtifacts,
  getArtifactDetail,
  createArtifact,
  updateArtifact,
  type ArtifactEntry,
  type ArtifactDetail,
} from '../api/tm'

type ArtifactsPageProps = {
  workspaceId: string | null
}

const newIntentForm = (): IntentFormValue => ({
  intentId: '',
  title: '',
  context: '',
  goal: '',
  nonGoals: [],
  actors: [],
  inputs: [],
  outputs: [],
  invariants: [],
  policies: [],
  successMetrics: [],
  risks: [],
  assumptions: [],
  parentIntent: '',
  relatedIntents: [],
})

const newBundleForm = (): BundleFormValue => ({
  bundleId: '',
  preconditions: [],
  agents: [
    {
      agentId: '',
      name: '',
      version: '0.1',
      runtimeKind: 'python',
      inputs: [],
      outputs: [],
      effectName: '',
      effectTarget: '',
    },
  ],
  plan: [
    {
      step: '',
      agentId: '',
      phase: 'run',
      inputs: [],
      outputs: [],
    },
  ],
})

const ensureList = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string')
}

const intentFromDetail = (detail: ArtifactDetail): IntentFormValue => {
  const body = detail.document.body
  const traceLinks = typeof body.trace_links === 'object' && body.trace_links !== null ? body.trace_links : {}
  return {
    intentId: String(body.intent_id ?? ''),
    title: String(body.title ?? ''),
    context: String(body.context ?? ''),
    goal: String(body.goal ?? ''),
    nonGoals: ensureList(body.non_goals),
    actors: ensureList(body.actors),
    inputs: ensureList(body.inputs),
    outputs: ensureList(body.outputs),
    invariants: ensureList(body.constraints),
    policies: [],
    successMetrics: ensureList(body.success_metrics),
    risks: ensureList(body.risks),
    assumptions: ensureList(body.assumptions),
    parentIntent: typeof traceLinks.parent_intent === 'string' ? traceLinks.parent_intent : '',
    relatedIntents: ensureList(traceLinks.related_intents),
  }
}

const bundleFromDetail = (detail: ArtifactDetail): BundleFormValue => {
  const body = detail.document.body
  const agents = Array.isArray(body.agents)
    ? body.agents.map((agent): AgentFormValue => {
        const contract = agent.contract || {}
        const inputs = Array.isArray(contract.inputs) ? contract.inputs.map((input) => String(input.ref ?? input)) : []
        const outputs = Array.isArray(contract.outputs) ? contract.outputs.map((output) => String(output.ref ?? output)) : []
        const effects = Array.isArray(contract.effects) ? contract.effects : []
        const firstEffect = effects[0] || {}
        return {
          agentId: String(agent.agent_id ?? ''),
          name: String(agent.name ?? agent.agent_id ?? ''),
          version: String(agent.version ?? ''),
          runtimeKind: String(agent.runtime?.kind ?? 'python'),
          inputs,
          outputs,
          effectName: String(firstEffect.name ?? ''),
          effectTarget: String(firstEffect.target ?? ''),
        }
      })
    : [EMPTY_BUNDLE_FORM.agents[0]]
  const plan = Array.isArray(body.plan)
    ? body.plan.map((step): PlanStepFormValue => ({
        step: String(step.step ?? ''),
        agentId: String(step.agent_id ?? ''),
        phase: String(step.phase ?? 'run'),
        inputs: ensureList(step.inputs),
        outputs: ensureList(step.outputs),
      }))
    : [EMPTY_BUNDLE_FORM.plan[0]]
  const meta = (body.meta && typeof body.meta === 'object' ? body.meta : {}) as { preconditions?: unknown }
  return {
    bundleId: String(body.bundle_id ?? ''),
    preconditions: ensureList(meta.preconditions),
    agents,
    plan,
  }
}

const buildIntentBody = (value: IntentFormValue) => ({
  intent_id: value.intentId,
  title: value.title,
  context: value.context,
  goal: value.goal,
  non_goals: value.nonGoals,
  actors: value.actors,
  inputs: value.inputs,
  outputs: value.outputs,
  constraints: [...value.invariants, ...value.policies],
  success_metrics: value.successMetrics,
  risks: value.risks,
  assumptions: value.assumptions,
  trace_links: {
    parent_intent: value.parentIntent || null,
    related_intents: value.relatedIntents,
  },
})

const toIoRefs = (refs: string[], kind: 'resource' | 'artifact', mode: 'read' | 'write') =>
  refs.map((ref) => ({
    ref,
    kind,
    schema: { type: 'object' },
    required: true,
    mode,
  }))

const buildBundleBody = (value: BundleFormValue) => ({
  bundle_id: value.bundleId || `tm-bundle/${Date.now().toString(36)}`,
  agents: value.agents.map((agent) => ({
    agent_id: agent.agentId,
    name: agent.name || agent.agentId,
    version: agent.version || '0.1',
    runtime: { kind: agent.runtimeKind || 'python', config: {} },
    contract: {
      inputs: toIoRefs(agent.inputs, 'resource', 'read'),
      outputs: toIoRefs(agent.outputs, 'artifact', 'write'),
      effects: [
        {
          name: agent.effectName || `${agent.agentId}-effect`,
          kind: 'resource',
          target: agent.effectTarget || 'resource:default',
          idempotency: {
            type: 'keyed',
            key_fields: agent.effectTarget ? [agent.effectTarget] : [],
          },
          evidence: {
            type: 'hash',
            path: agent.effectTarget || 'artifact:default',
          },
        },
      ],
    },
    config_schema: {},
    evidence_outputs: [{ name: 'output', description: 'generated evidence' }],
    role: 'agent',
  })),
  plan: value.plan.map((step, index) => ({
    step: step.step || `step-${index + 1}`,
    agent_id: step.agentId,
    phase: step.phase || 'run',
    inputs: step.inputs,
    outputs: step.outputs,
  })),
  meta: {
    preconditions: value.preconditions,
  },
})

const ArtifactsPage = ({ workspaceId }: ArtifactsPageProps) => {
  const [activeTab, setActiveTab] = useState<'intents' | 'bundles'>('intents')
  const [artifacts, setArtifacts] = useState<ArtifactEntry[]>([])
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null)
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactDetail | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [intentForm, setIntentForm] = useState<IntentFormValue>(newIntentForm())
  const [bundleForm, setBundleForm] = useState<BundleFormValue>(newBundleForm())
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [validationErrors, setValidationErrors] = useState<string[] | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const artifactType = activeTab === 'intents' ? 'intent' : 'agent_bundle'

  useEffect(() => {
    if (!workspaceId) {
      setArtifacts([])
    setSelectedArtifactId(null)
    setSelectedArtifact(null)
    return
  }
    setIsLoading(true)
    setErrorMessage(null)
    listArtifacts({ artifact_type: artifactType, workspace_id: workspaceId })
      .then((data) => {
        setArtifacts(data)
        if (selectedArtifactId && !data.some((entry) => entry.artifact_id === selectedArtifactId)) {
          setSelectedArtifactId(null)
          setSelectedArtifact(null)
        }
      })
      .catch((error) => {
        setErrorMessage((error as Error).message)
      })
      .finally(() => setIsLoading(false))
  }, [workspaceId, artifactType, reloadKey, selectedArtifactId])

  useEffect(() => {
    setSelectedArtifactId(null)
    setSelectedArtifact(null)
    setValidationErrors(null)
    setSuccessMessage(null)
    setIntentForm(newIntentForm())
    setBundleForm(newBundleForm())
  }, [activeTab, workspaceId])

  const loadArtifact = async (artifactId: string) => {
    if (!workspaceId) return
    setIsLoading(true)
    setErrorMessage(null)
    try {
      const detail = await getArtifactDetail(artifactId, workspaceId)
      setSelectedArtifact(detail)
      setSelectedArtifactId(artifactId)
      setValidationErrors(null)
      if (activeTab === 'intents') {
        setIntentForm(intentFromDetail(detail))
      } else {
        setBundleForm(bundleFromDetail(detail))
      }
    } catch (error) {
      setErrorMessage((error as Error).message)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSave = async () => {
    if (!workspaceId) {
      setErrorMessage('Select a workspace before saving artifacts.')
      return
    }
    setIsSaving(true)
    setErrorMessage(null)
    setValidationErrors(null)
    const body = activeTab === 'intents' ? buildIntentBody(intentForm) : buildBundleBody(bundleForm)
    const payload = { artifact_type: artifactType, body }
    try {
      const response = selectedArtifactId
        ? await updateArtifact(selectedArtifactId, payload, workspaceId)
        : await createArtifact(payload, workspaceId)
      setSuccessMessage(`${response.entry.artifact_id} saved`)
      setSelectedArtifactId(response.entry.artifact_id)
      setSelectedArtifact(response)
      setReloadKey((prev) => prev + 1)
    } catch (error) {
      const message = (error as Error).message
      setErrorMessage(message)
      try {
        const parsed = JSON.parse(message)
        if (parsed && Array.isArray(parsed.errors)) {
          setValidationErrors(parsed.errors.map(String))
        }
      } catch {
        // ignore
      }
    } finally {
      setIsSaving(false)
    }
  }

  const handleNew = () => {
    setSelectedArtifactId(null)
    setSelectedArtifact(null)
    setValidationErrors(null)
    setSuccessMessage(null)
    setIntentForm(newIntentForm())
    setBundleForm(newBundleForm())
  }

  const rowClass = (artifactId: string) =>
    `artifact-row ${selectedArtifactId === artifactId ? 'selected' : ''}`

  return (
    <div className="artifacts-page">
      <header className="artifacts-page__header">
        <div>
          <h3>Workspace artifacts</h3>
          <p>List, edit, and persist Intent and Controller bundle artifacts directly from forms.</p>
        </div>
        <div className="artifacts-page__tabs">
          <button type="button" onClick={() => setActiveTab('intents')} className={activeTab === 'intents' ? 'active' : ''}>
            Intents
          </button>
          <button type="button" onClick={() => setActiveTab('bundles')} className={activeTab === 'bundles' ? 'active' : ''}>
            Bundles
          </button>
        </div>
      </header>
      {!workspaceId && <p className="hint">Mount and select a workspace before editing artifacts.</p>}
      {workspaceId && (
        <>
          <div className="artifacts-page__layout">
            <div className="artifacts-page__list">
              <div className="artifacts-page__list-head">
                <strong>{activeTab === 'intents' ? 'Intents' : 'Bundles'}</strong>
                <button type="button" onClick={handleNew} disabled={isLoading}>
                  New
                </button>
              </div>
              <div className="artifact-list">
                {isLoading && <p className="hint">Loading…</p>}
                {!isLoading &&
                  (artifacts.length ? (
                    artifacts.map((entry) => (
                      <button key={entry.artifact_id} type="button" className={rowClass(entry.artifact_id)} onClick={() => loadArtifact(entry.artifact_id)}>
                        <span>{entry.artifact_id}</span>
                        <small>{entry.artifact_type}</small>
                      </button>
                    ))
                  ) : (
                    <p className="hint">No artifacts yet; create one using the form.</p>
                  ))}
              </div>
            </div>
            <div className="artifacts-page__form">
              {activeTab === 'intents' ? (
                <IntentEditor value={intentForm} onChange={setIntentForm} disabled={isSaving} errors={validationErrors ?? undefined} />
              ) : (
                <BundleEditor value={bundleForm} onChange={setBundleForm} disabled={isSaving} errors={validationErrors ?? undefined} />
              )}
              <div className="artifacts-page__actions">
                <button type="button" onClick={handleSave} disabled={isSaving}>
                  {isSaving ? 'Saving…' : selectedArtifactId ? 'Save changes' : 'Create artifact'}
                </button>
                {successMessage && <span className="success-note">{successMessage}</span>}
              </div>
              {errorMessage && <p className="error-line">{errorMessage}</p>}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default ArtifactsPage
