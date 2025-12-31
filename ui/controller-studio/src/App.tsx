import { useEffect, useMemo, useState } from 'react'
import {
  diffArtifacts,
  getArtifactDocument,
  getCurrentWorkspace,
  listBundles,
  listLlmConfigs,
  listPromptTemplates,
  listReports,
  listWorkspaces,
  mountWorkspace,
  createLlmConfig,
  runCycle,
  selectWorkspace,
  tmServerUrl,
} from './api/tm'
import type {
  ArtifactDocument,
  ArtifactDiffResponse,
  BundleEntry,
  CycleRunResponse,
  PromptTemplateInfo,
  ReportSummary,
  WorkspaceInfo,
  LlmConfigInfo,
} from './api/tm'
import PlanReview from './components/PlanReview'
import PolicyPanel from './components/PolicyPanel'
import LlmConfig, { type LlmConfigForm } from './components/LlmConfig'
import RunControl from './components/RunControl'
import type { PolicyDecisionRecord } from './types/controllerStudio'
import { prettyValue } from './utils/format'
import './App.css'
import ArtifactsPage from './pages/Artifacts'
import WorkspaceHome from './pages/WorkspaceHome'

const STEPS = [
  { id: 1, title: 'Select bundle', summary: 'Mount or pick a workspace and choose an accepted bundle.' },
  {
    id: 2,
    title: 'Configure LLM',
    summary: 'Pick or create a recorded config so the server knows which model + prompt template to use.',
  },
  { id: 3, title: 'Run live cycle', summary: 'Generate a preview cycle to capture the proposed plan.' },
  { id: 4, title: 'Review plan diff', summary: 'Inspect hashes, policy decisions, evidence, and plan diff.' },
  { id: 5, title: 'Approve & act', summary: 'Commit the approved plan so tm-server writes artifacts + reports.' },
  { id: 6, title: 'Report timeline', summary: 'Browse recorded runs that tm-server persists.' },
  { id: 7, title: 'Replay', summary: 'Replay a past report without editing YAML or CLI.' },
]

const DEFAULT_LLM_CONFIG_FORM: LlmConfigForm = {
  model: '',
  promptTemplateVersion: '',
  promptVersion: '',
  modelId: '',
  modelVersion: '',
}

const parsePolicyDecisions = (raw: unknown): PolicyDecisionRecord[] => {
  if (!Array.isArray(raw)) return []
  return raw.map((entry) => {
    if (typeof entry !== 'object' || entry === null) {
      return { effect: 'unknown', target: 'unknown', allowed: false, reason: 'invalid payload' }
    }
    return {
      effect: 'effect' in entry && typeof entry.effect === 'string' ? entry.effect : 'unknown',
      target: 'target' in entry && typeof entry.target === 'string' ? entry.target : 'unknown',
      allowed: 'allowed' in entry && typeof entry.allowed === 'boolean' ? entry.allowed : false,
      reason: 'reason' in entry && typeof entry.reason === 'string' ? entry.reason : 'no reason provided',
    }
  })
}

const safeArtifactId = (payload: Record<string, unknown>, key: string): string | undefined => {
  const candidate = payload[key]
  return typeof candidate === 'string' && candidate.length > 0 ? candidate : undefined
}

const formatDate = (value: unknown): string => {
  if (typeof value !== 'string') return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
}

function App() {
  const [activeStep, setActiveStep] = useState(1)
  const [maxUnlockedStep, setMaxUnlockedStep] = useState(1)
  const [workspacePath, setWorkspacePath] = useState('')
  const [workspaceList, setWorkspaceList] = useState<WorkspaceInfo[]>([])
  const [currentWorkspace, setCurrentWorkspace] = useState<WorkspaceInfo | null>(null)
  const [workspaceSelection, setWorkspaceSelection] = useState<string>('')
  const [bundles, setBundles] = useState<BundleEntry[]>([])
  const [selectedBundleId, setSelectedBundleId] = useState('')
  const [activeView, setActiveView] = useState<'studio' | 'artifacts'>('studio')
  const [promptTemplates, setPromptTemplates] = useState<PromptTemplateInfo[]>([])
  const [llmConfigs, setLlmConfigs] = useState<LlmConfigInfo[]>([])
  const [selectedLlmConfigId, setSelectedLlmConfigId] = useState<string | null>(null)
  const [llmConfigForm, setLlmConfigForm] = useState<LlmConfigForm>(DEFAULT_LLM_CONFIG_FORM)
  const [isCreatingConfig, setIsCreatingConfig] = useState(false)
  const [previewCompleted, setPreviewCompleted] = useState(false)
  const [finalRun, setFinalRun] = useState<CycleRunResponse | null>(null)
  const [latestRun, setLatestRun] = useState<CycleRunResponse | null>(null)
  const [planDoc, setPlanDoc] = useState<ArtifactDocument | null>(null)
  const [executionDoc, setExecutionDoc] = useState<ArtifactDocument | null>(null)
  const [bundleDoc, setBundleDoc] = useState<ArtifactDocument | null>(null)
  const [diffData, setDiffData] = useState<ArtifactDiffResponse | null>(null)
  const [policyDecisions, setPolicyDecisions] = useState<PolicyDecisionRecord[]>([])
  const [planApproved, setPlanApproved] = useState(false)
  const [approvalToken, setApprovalToken] = useState<string | null>(null)
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [lastReplayMessage, setLastReplayMessage] = useState<string | null>(null)
  const [isActionInProgress, setIsActionInProgress] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const selectedReport = useMemo(
    () => reports.find((entry) => entry.run_id === selectedReportId) ?? null,
    [reports, selectedReportId],
  )

  const canAdvanceFromStep = (step: number): boolean => {
    switch (step) {
      case 1:
        return Boolean(currentWorkspace && selectedBundleId)
      case 2:
        return true
      case 3:
        return previewCompleted
      case 4:
        return Boolean(diffData && diffData.diff.length)
      case 5:
        return finalRun !== null
      case 6:
        return reports.length > 0
      case 7:
        return Boolean(selectedReportId)
      default:
        return false
    }
  }

  const handleActionError = (error: unknown) => {
    setErrorMessage(error instanceof Error ? error.message : String(error))
  }

  const refreshPromptTemplates = async (workspaceId: string) => {
    try {
      const entries = await listPromptTemplates(workspaceId)
      setPromptTemplates(entries)
    } catch (error) {
      handleActionError(error)
    }
  }

  const refreshLlmConfigs = async (workspaceId: string) => {
    try {
      const entries = await listLlmConfigs(workspaceId)
      setLlmConfigs(entries)
    } catch (error) {
      handleActionError(error)
    }
  }

  const handleCreateLlmConfig = async () => {
    if (!currentWorkspace?.workspace_id) {
      setErrorMessage('Select a workspace before saving a config.')
      return
    }
    setIsCreatingConfig(true)
    try {
      const entry = await createLlmConfig(
        {
          model: llmConfigForm.model,
          prompt_template_version: llmConfigForm.promptTemplateVersion,
          prompt_version: llmConfigForm.promptVersion || undefined,
          model_id: llmConfigForm.modelId || undefined,
          model_version: llmConfigForm.modelVersion || undefined,
        },
        currentWorkspace.workspace_id,
      )
      await refreshLlmConfigs(currentWorkspace.workspace_id)
      setSelectedLlmConfigId(entry.config_id)
      setLlmConfigForm({
        model: entry.model,
        promptTemplateVersion: entry.prompt_template_version,
        promptVersion: entry.prompt_version,
        modelId: entry.model_id ?? '',
        modelVersion: entry.model_version ?? '',
      })
      setErrorMessage(null)
    } catch (error) {
      handleActionError(error)
    } finally {
      setIsCreatingConfig(false)
    }
  }

  const handleLlmFormChange = (field: keyof LlmConfigForm, value: string) => {
    setLlmConfigForm((prev) => ({
      ...prev,
      [field]: value,
    }))
  }

  const refreshWorkspaces = async () => {
    try {
      const [list, current] = await Promise.all([listWorkspaces(), getCurrentWorkspace()])
      setWorkspaceList(list)
      setCurrentWorkspace(current)
      if (current) {
        setWorkspaceSelection(current.workspace_id)
      }
    } catch (error) {
      handleActionError(error)
    }
  }

  useEffect(() => {
    void refreshWorkspaces()
  }, [])

  useEffect(() => {
    if (!currentWorkspace?.workspace_id) {
      setActiveStep(1)
      setMaxUnlockedStep(1)
      setPreviewCompleted(false)
      setFinalRun(null)
      setLatestRun(null)
      setPlanDoc(null)
      setExecutionDoc(null)
      setBundleDoc(null)
      setDiffData(null)
      setPolicyDecisions([])
      setSelectedReportId(null)
      setLastReplayMessage(null)
      setReports([])
      setBundles([])
      setSelectedBundleId('')
      setPromptTemplates([])
      setLlmConfigs([])
      setSelectedLlmConfigId(null)
      setLlmConfigForm(DEFAULT_LLM_CONFIG_FORM)
      setIsCreatingConfig(false)
      setStatusMessage(null)
      setPlanApproved(false)
      setApprovalToken(null)
      return
    }
    setStatusMessage(null)
    const workspaceId = currentWorkspace.workspace_id
    void (async () => {
      try {
        const entries = await listBundles(workspaceId)
        setBundles(entries)
        if (!selectedBundleId && entries.length) {
          setSelectedBundleId(entries[0].artifact_id)
        } else if (
          selectedBundleId &&
          !entries.some((bundle) => bundle.artifact_id === selectedBundleId)
        ) {
          setSelectedBundleId(entries.length ? entries[0].artifact_id : '')
        }
      } catch (error) {
        handleActionError(error)
      }
    })()
    void (async () => {
      try {
        const timeline = await listReports(workspaceId)
        setReports(timeline)
        if (!selectedReportId && timeline.length) {
          setSelectedReportId(timeline[0].run_id)
        }
      } catch (error) {
        handleActionError(error)
      }
    })()
  }, [currentWorkspace?.workspace_id, selectedBundleId])

  useEffect(() => {
    if (!currentWorkspace?.workspace_id) {
      setPromptTemplates([])
      setLlmConfigs([])
      setSelectedLlmConfigId(null)
      setLlmConfigForm(DEFAULT_LLM_CONFIG_FORM)
      return
    }
    const workspaceId = currentWorkspace.workspace_id
    void refreshPromptTemplates(workspaceId)
    void refreshLlmConfigs(workspaceId)
  }, [currentWorkspace?.workspace_id])

  useEffect(() => {
    if (!promptTemplates.length) return
    setLlmConfigForm((prev) =>
      prev.promptTemplateVersion ? prev : { ...prev, promptTemplateVersion: promptTemplates[0].version },
    )
  }, [promptTemplates])

  useEffect(() => {
    if (!workspaceSelection && workspaceList.length) {
      setWorkspaceSelection(workspaceList[0].workspace_id)
    }
  }, [workspaceList, workspaceSelection])

  useEffect(() => {
    if (reports.length > 0) {
      setMaxUnlockedStep((prev) => Math.max(prev, 6))
    }
  }, [reports.length])

  useEffect(() => {
    if (selectedReportId) {
      setMaxUnlockedStep((prev) => Math.max(prev, 7))
    }
  }, [selectedReportId])

  const handleMount = async () => {
    if (!workspacePath) return
    setErrorMessage(null)
    setStatusMessage('Mounting workspace…')
    setIsActionInProgress(true)
    try {
      await mountWorkspace(workspacePath)
      setWorkspacePath('')
      await refreshWorkspaces()
    } catch (error) {
      handleActionError(error)
    } finally {
      setStatusMessage(null)
      setIsActionInProgress(false)
    }
  }

  const handleWorkspaceSelect = async () => {
    if (!workspaceSelection) return
    setErrorMessage(null)
    setStatusMessage('Switching workspace…')
    setIsActionInProgress(true)
    try {
      const descriptor = await selectWorkspace(workspaceSelection)
      setCurrentWorkspace(descriptor)
      await refreshWorkspaces()
    } catch (error) {
      handleActionError(error)
    } finally {
      setStatusMessage(null)
      setIsActionInProgress(false)
    }
  }

  const handlePlanApproval = () => {
    if (!latestRun) {
      setErrorMessage('Run a preview cycle before approving the plan.')
      return
    }
    setErrorMessage(null)
    const token = `approved-${Date.now()}`
    setPlanApproved(true)
    setApprovalToken(token)
    setStatusMessage('Plan marked as approved; you may now run a live cycle.')
  }

  const refreshTimeline = async (workspaceId: string) => {
    try {
      const data = await listReports(workspaceId)
      setReports(data)
      if (!selectedReportId && data.length) {
        setSelectedReportId(data[0].run_id)
      }
    } catch (error) {
      handleActionError(error)
    }
  }

  const handleRunArtifacts = async (run: CycleRunResponse) => {
    const reportPayload = run.report
    const workspaceId = currentWorkspace?.workspace_id
    const envSnapshotId = safeArtifactId(reportPayload, 'env_snapshot')
    const planId = safeArtifactId(reportPayload, 'proposed_change_plan')
    const executionId = safeArtifactId(reportPayload, 'execution_report')
    const bundleArtifactId = safeArtifactId(reportPayload, 'bundle_artifact_id')

    const planPromise = planId ? getArtifactDocument(planId, workspaceId ?? undefined) : Promise.resolve(null)
    const executionPromise = executionId
      ? getArtifactDocument(executionId, workspaceId ?? undefined)
      : Promise.resolve(null)
    const bundlePromise = bundleArtifactId
      ? getArtifactDocument(bundleArtifactId, workspaceId ?? undefined)
      : Promise.resolve(null)

    try {
      const [plan, execution, bundle] = await Promise.all([planPromise, executionPromise, bundlePromise])
      setPlanDoc(plan?.document ?? null)
      setExecutionDoc(execution?.document ?? null)
      setBundleDoc(bundle?.document ?? null)
      if (plan?.document?.body?.llm_metadata) {
        const metadata = plan.document.body.llm_metadata as Record<string, unknown>
        setSelectedLlmConfigId(
          typeof metadata.config_id === 'string' && metadata.config_id.length ? metadata.config_id : null,
        )
        setLlmConfigForm((prev) => ({
          model:
            typeof metadata.model === 'string' && metadata.model.length ? metadata.model : prev.model,
          promptTemplateVersion:
            typeof metadata.prompt_template_version === 'string' && metadata.prompt_template_version.length
              ? metadata.prompt_template_version
              : prev.promptTemplateVersion,
          promptVersion:
            typeof metadata.prompt_version === 'string' && metadata.prompt_version.length
              ? metadata.prompt_version
              : prev.promptVersion,
          modelId:
            typeof metadata.model_id === 'string' && metadata.model_id.length ? metadata.model_id : prev.modelId,
          modelVersion:
            typeof metadata.model_version === 'string' && metadata.model_version.length
              ? metadata.model_version
              : prev.modelVersion,
        }))
      }
      if (workspaceId) {
        await refreshLlmConfigs(workspaceId)
      }
    } catch (error) {
      console.warn('artifact fetch failed', error)
    }

    if (envSnapshotId && planId) {
      try {
        const diff = await diffArtifacts({
          base_id: envSnapshotId,
          compare_id: planId,
          workspace_id: workspaceId,
        })
        setDiffData(diff)
        setMaxUnlockedStep((prev) => Math.max(prev, 4))
      } catch (error) {
        console.warn('diff failed', error)
        setDiffData(null)
      }
    }

    setPolicyDecisions(parsePolicyDecisions(reportPayload.policy_decisions))
  }

  const handlePreviewRun = async () => {
    setPlanApproved(false)
    setApprovalToken(null)
    if (!currentWorkspace || !selectedBundleId) return
    setErrorMessage(null)
    setStatusMessage('Running preview cycle (dry run)…')
    setIsActionInProgress(true)
    try {
      const response = await runCycle({
        bundle_artifact_id: selectedBundleId,
        dry_run: true,
        workspace_id: currentWorkspace.workspace_id,
        llm_config_id: selectedLlmConfigId ?? undefined,
      })
      setPreviewCompleted(true)
      setLatestRun(response)
      await handleRunArtifacts(response)
      setMaxUnlockedStep((prev) => Math.max(prev, 4))
      await refreshTimeline(currentWorkspace.workspace_id)
    } catch (error) {
      handleActionError(error)
    } finally {
      setStatusMessage(null)
      setIsActionInProgress(false)
    }
  }

  const handleApproveRun = async () => {
    if (!currentWorkspace || !selectedBundleId) return
    if (!planApproved || !approvalToken) {
      setErrorMessage('Approve the latest plan before running the live cycle.')
      return
    }
    setErrorMessage(null)
    setStatusMessage('Approving plan and executing real run…')
    setIsActionInProgress(true)
    try {
      const response = await runCycle({
        bundle_artifact_id: selectedBundleId,
        dry_run: false,
        workspace_id: currentWorkspace.workspace_id,
        approval_token: approvalToken,
        llm_config_id: selectedLlmConfigId ?? undefined,
      })
      setFinalRun(response)
      setLatestRun(response)
      await handleRunArtifacts(response)
      setMaxUnlockedStep((prev) => Math.max(prev, 5))
      await refreshTimeline(currentWorkspace.workspace_id)
    } catch (error) {
      handleActionError(error)
    } finally {
      setStatusMessage(null)
      setIsActionInProgress(false)
    }
  }

  const handleReplay = async () => {
    if (!currentWorkspace || !selectedBundleId || !selectedReport) return
    if (!planApproved || !approvalToken) {
      setErrorMessage('Approve the plan before replaying the cycle.')
      return
    }
    setErrorMessage(null)
    setStatusMessage('Replaying selected report…')
    setIsActionInProgress(true)
    try {
      const response = await runCycle({
        bundle_artifact_id: selectedBundleId,
        dry_run: false,
        run_id: `replay-${selectedReport.run_id}`,
        workspace_id: currentWorkspace.workspace_id,
        approval_token: approvalToken,
        llm_config_id: selectedLlmConfigId ?? undefined,
      })
      setLatestRun(response)
      setFinalRun(response)
      await handleRunArtifacts(response)
      setLastReplayMessage(`Replayed ${selectedReport.run_id} → ${response.run_id}`)
      await refreshTimeline(currentWorkspace.workspace_id)
    } catch (error) {
      handleActionError(error)
    } finally {
      setStatusMessage(null)
      setIsActionInProgress(false)
    }
  }

  const handleNextStep = () => {
    setErrorMessage(null)
    if (!canAdvanceFromStep(activeStep)) {
      setErrorMessage('Finish the current step before continuing.')
      return
    }
    const next = Math.min(activeStep + 1, STEPS.length)
    setActiveStep(next)
    setMaxUnlockedStep((prev) => Math.max(prev, next))
  }

  const handlePrevStep = () => {
    if (activeStep > 1) {
      setActiveStep(activeStep - 1)
    }
  }

  const wizardContent = () => {
    switch (activeStep) {
      case 1:
        return (
          <WorkspaceHome
            workspacePath={workspacePath}
            onWorkspacePathChange={setWorkspacePath}
            onMount={handleMount}
            workspaceList={workspaceList}
            workspaceSelection={workspaceSelection}
            onWorkspaceSelectionChange={setWorkspaceSelection}
            onWorkspaceSelect={handleWorkspaceSelect}
          currentWorkspace={currentWorkspace}
          bundles={bundles}
          selectedBundleId={selectedBundleId}
          onBundleChange={setSelectedBundleId}
          formatDate={formatDate}
          isActionInProgress={isActionInProgress}
        />
        )
      case 2:
        return (
          <div className="config-card">
            <h3>LLM configuration</h3>
            <p>
              Pick an existing LLM config or create a new one so tm-server stores the model + prompt template
              metadata under a reproducible ID. The UI fills in recorded metadata automatically after previewing a cycle.
            </p>
            <LlmConfig
              workspaceId={currentWorkspace?.workspace_id ?? null}
              promptTemplates={promptTemplates}
              configs={llmConfigs}
              selectedConfigId={selectedLlmConfigId}
              formData={llmConfigForm}
              onFormChange={handleLlmFormChange}
              onSelectConfig={setSelectedLlmConfigId}
              onCreateConfig={handleCreateLlmConfig}
              isCreating={isCreatingConfig}
            />
          </div>
        )
      case 3:
        return (
          <div className="action-card">
            <h3>Run live cycle (preview)</h3>
            <p>This generates a proposed plan without committing any artifacts. tm-server persists everything.</p>
            <button
              onClick={handlePreviewRun}
              disabled={isActionInProgress || !selectedBundleId || !currentWorkspace}
            >
              {previewCompleted ? 'Re-run preview' : 'Run preview cycle'}
            </button>
            {latestRun && (
              <p className="run-note">
                Latest run ID: <strong>{latestRun.run_id}</strong> ({latestRun.success ? 'success' : 'failed'})
              </p>
            )}
          </div>
        )
      case 4:
        return (
          <div className="review-card">
          <PlanReview
            planDoc={planDoc}
            bundleDoc={bundleDoc}
            executionDoc={executionDoc}
            diffData={diffData}
            policyDecisions={policyDecisions}
          />
            <PolicyPanel policyDecisions={policyDecisions} />
          </div>
        )
      case 5:
        return (
          <div className="action-card">
            <h3>Approve & act</h3>
            <p>Once you approve the preview, this triggers the real controller cycle (writes artifacts + report).</p>
            <div className="approval-actions">
              <button
                onClick={handlePlanApproval}
                disabled={
                  isActionInProgress ||
                  !previewCompleted ||
                  !selectedBundleId ||
                  !currentWorkspace ||
                  planApproved
                }
              >
                {planApproved ? 'Plan approved' : 'Approve plan'}
              </button>
              {approvalToken && (
                <span className="approval-token">Token: {approvalToken}</span>
              )}
            </div>
            <button
              onClick={handleApproveRun}
              disabled={
                isActionInProgress ||
                !previewCompleted ||
                !selectedBundleId ||
                !currentWorkspace ||
                !planApproved
              }
            >
              {finalRun ? 'Re-run approved cycle' : 'Approve & run live'}
            </button>
            {finalRun && (
              <p className="run-note">
                Last live run: <strong>{finalRun.run_id}</strong> ({finalRun.success ? 'success' : 'failed'})
              </p>
            )}
          </div>
        )
      case 6:
        return (
          <div className="timeline-card">
            <h3>Report timeline</h3>
            {reports.length ? (
              <div className="timeline-list">
                {reports.map((entry) => {
                  const entryReport = entry.report
                  const startTime = formatDate(entryReport.start_time ?? entryReport.generated_at)
                  const endTime = formatDate(entryReport.end_time)
                  const success = entryReport.success ? 'success' : 'failed'
                  return (
                    <div
                      key={entry.run_id}
                      className={`timeline-row ${selectedReportId === entry.run_id ? 'selected' : ''}`}
                    >
                      <div>
                        <strong>{entry.run_id}</strong>
                        <p>
                          {prettyValue(entryReport.bundle_artifact_id, 'bundle unknown')} • {success}
                        </p>
                        <p>
                          {startTime} → {endTime} • {prettyValue(entryReport.duration_seconds)}s
                        </p>
                      </div>
                      <button type="button" onClick={() => setSelectedReportId(entry.run_id)}>
                        Select for replay
                      </button>
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="hint">No reports yet. Run a cycle to populate the timeline.</p>
            )}
          </div>
        )
      case 7:
        return (
          <div className="action-card">
            <h3>Replay a report</h3>
            {selectedReport ? (
              <>
                <p>
                  Replay target: <strong>{selectedReport.run_id}</strong>
                </p>
                <p className="hint">
                  tm-server will re-run the bundle that produced this report and store a new report under a
                  replay run ID.
                </p>
                <button
                  onClick={handleReplay}
                  disabled={isActionInProgress || !selectedReportId || !selectedBundleId || !currentWorkspace}
                >
                  Replay selected report
                </button>
              </>
            ) : (
              <p className="hint">Select a timeline entry to replay it.</p>
            )}
            {lastReplayMessage && <p className="run-note">{lastReplayMessage}</p>}
          </div>
        )
      default:
        return null
    }
  }

  return (
    <div className="app-shell">
      <header>
        <div>
          <p className="eyebrow">Controller Studio v0</p>
          <h1>Wizard for running TraceMind controller cycles</h1>
        </div>
      <p className="server-url">
        tm-server host: <strong>{tmServerUrl}</strong>
      </p>
      <div className="view-toggle">
        <button
          type="button"
          className={activeView === 'studio' ? 'active' : ''}
          onClick={() => setActiveView('studio')}
        >
          Controller Studio
        </button>
        <button
          type="button"
          className={activeView === 'artifacts' ? 'active' : ''}
          onClick={() => setActiveView('artifacts')}
        >
          Artifacts
        </button>
      </div>
    </header>
      <div className="wizard-shell">
        {activeView === 'studio' && (
          <nav className="wizard-nav">
            {STEPS.map((step) => (
              <button
                key={step.id}
                type="button"
                onClick={() => {
                  if (step.id <= maxUnlockedStep) {
                    setActiveStep(step.id)
                  }
                }}
                className={`wizard-step ${
                  step.id === activeStep
                    ? 'active'
                    : step.id < activeStep
                      ? 'completed'
                      : step.id > maxUnlockedStep
                        ? 'locked'
                        : ''
                }`}
                disabled={step.id > maxUnlockedStep}
              >
                <span className="step-index">{step.id}</span>
                <div className="step-meta">
                  <strong>{step.title}</strong>
                  <small>{step.summary}</small>
                </div>
              </button>
            ))}
          </nav>
        )}
        <section className="wizard-body">
          {activeView === 'studio' ? (
            <>
              <div className="wizard-panel">{wizardContent()}</div>
              <div className="wizard-controls">
                <button type="button" onClick={handlePrevStep} disabled={activeStep === 1}>
                  Previous
                </button>
                <button type="button" onClick={handleNextStep} disabled={activeStep === STEPS.length}>
                  Next
                </button>
              </div>
            </>
          ) : (
            <ArtifactsPage workspaceId={currentWorkspace?.workspace_id ?? null} />
          )}
        </section>
        {activeView === 'studio' && latestRun && currentWorkspace && (
          <div className="run-control-panel">
            <RunControl runId={latestRun.run_id} workspaceId={currentWorkspace.workspace_id} />
          </div>
        )}
      </div>
      {statusMessage && <p className="status-line">{statusMessage}</p>}
      {errorMessage && <p className="error-line">{errorMessage}</p>}
    </div>
  )
}

export default App
