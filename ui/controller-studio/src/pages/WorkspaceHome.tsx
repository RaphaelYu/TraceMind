import type { BundleEntry, WorkspaceInfo } from '../api/tm'

type WorkspaceHomeProps = {
  workspacePath: string
  onWorkspacePathChange: (value: string) => void
  onMount: () => void
  isActionInProgress: boolean
  workspaceList: WorkspaceInfo[]
  workspaceSelection: string
  onWorkspaceSelectionChange: (value: string) => void
  onWorkspaceSelect: () => void
  currentWorkspace: WorkspaceInfo | null
  bundles: BundleEntry[]
  selectedBundleId: string
  onBundleChange: (value: string) => void
  formatDate: (value: unknown) => string
}

const WorkspaceHome = ({
  workspacePath,
  onWorkspacePathChange,
  onMount,
  workspaceList,
  workspaceSelection,
  onWorkspaceSelect,
  currentWorkspace,
  bundles,
  selectedBundleId,
  onBundleChange,
  formatDate,
}: WorkspaceHomeProps) => (
  <>
    <div className="workspace-section">
      <div className="workspace-card">
        <h3>Current workspace</h3>
        {currentWorkspace ? (
          <>
            <p>
              <strong>Name:</strong> {currentWorkspace.name}
            </p>
            <p>
              <strong>ID:</strong> {currentWorkspace.workspace_id}
            </p>
            <p>
              <strong>Root:</strong> {currentWorkspace.root}
            </p>
            <p>
              <strong>Languages:</strong> {currentWorkspace.languages.join(', ')}
            </p>
          </>
        ) : (
          <p>No workspace mounted yet.</p>
        )}
      </div>
      <div className="workspace-actions">
        <label>Mount workspace (path to tracemind.workspace.yaml)</label>
        <div className="field-row">
          <input
            type="text"
            placeholder="e.g. /path/to/workspace/tracemind.workspace.yaml"
            value={workspacePath}
            onChange={(event) => onWorkspacePathChange(event.target.value)}
          />
          <button onClick={onMount} disabled={isActionInProgress || !workspacePath}>
            Mount
          </button>
        </div>
        <label>Select from mounted workspaces</label>
          <div className="field-row">
            <select value={workspaceSelection} onChange={(event) => onWorkspaceSelectionChange(event.target.value)}>
              {workspaceList.map((workspace) => (
                <option key={workspace.workspace_id} value={workspace.workspace_id}>
                  {workspace.name} ({workspace.workspace_id})
                </option>
              ))}
            </select>
            <button onClick={onWorkspaceSelect} disabled={isActionInProgress || !workspaceSelection}>
              Set active
            </button>
          </div>
      </div>
    </div>
    <div className="bundle-section">
      <label>Accepted bundles</label>
      <select value={selectedBundleId} onChange={(event) => onBundleChange(event.target.value)}>
        <option value="">— select a bundle —</option>
        {bundles.map((bundle) => (
          <option key={bundle.artifact_id} value={bundle.artifact_id}>
            {bundle.artifact_id}
          </option>
        ))}
      </select>
      {selectedBundleId && (
        <div className="bundle-details">
          {bundles
            .filter((bundle) => bundle.artifact_id === selectedBundleId)
            .map((bundle) => (
              <div key={bundle.artifact_id}>
                <p>
                  <strong>Intent:</strong> {bundle.intent_id ?? 'N/A'}
                </p>
                <p>
                  <strong>Created:</strong> {formatDate(bundle.created_at)}
                </p>
                <p>
                  <strong>Path:</strong> {bundle.path}
                </p>
                <p>
                  <strong>Status:</strong> {bundle.status}
                </p>
              </div>
            ))}
        </div>
      )}
      {!bundles.length && <p className="hint">No bundles registered yet for this workspace.</p>}
    </div>
  </>
)

export default WorkspaceHome
