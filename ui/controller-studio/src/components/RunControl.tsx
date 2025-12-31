import { useEffect, useMemo, useState } from 'react'
import { cancelRun, getRunStatus, type RunStatus } from '../api/tm'

type RunControlProps = {
  runId: string
  workspaceId: string
}

const POLL_INTERVAL_MS = 3000

const formatTimestamp = (value: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

const RunControl = ({ runId, workspaceId }: RunControlProps) => {
  const [status, setStatus] = useState<RunStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)

  const refreshStatus = async () => {
    try {
      const payload = await getRunStatus(runId, workspaceId)
      setStatus(payload)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load run status')
    }
  }

  useEffect(() => {
    let active = true
    const poll = async () => {
      if (!active) return
      await refreshStatus()
    }
    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [runId, workspaceId])

  const handleCancel = async () => {
    if (!status) return
    setIsCancelling(true)
    setError(null)
    try {
      const payload = await cancelRun(runId, workspaceId)
      setStatus(payload)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'cancel failed')
    } finally {
      setIsCancelling(false)
    }
  }

  const isCancelable = useMemo(() => {
    if (!status) return false
    if (status.canceled) return false
    return ['running', 'pending', 'cancelling'].includes(status.status)
  }, [status])

  if (!status) {
    return (
      <div className="run-control">
        <h4>Run control</h4>
        <p>Loading run status…</p>
      </div>
    )
  }

  return (
    <div className="run-control">
      <h4>Run control</h4>
      <p>
        <strong>Status:</strong> {status.status}
      </p>
      <p>
        <strong>Step:</strong> {status.current_step ?? '—'} (attempt {status.attempt})
      </p>
      <p>
        <strong>Retry count:</strong> {status.retry_count}
      </p>
      <p>
        <strong>Timeout:</strong> {status.timeout_reason ?? '—'}
      </p>
      <p>
        <strong>Started:</strong> {formatTimestamp(status.started_at)} | <strong>Ended:</strong>{' '}
        {formatTimestamp(status.ended_at)}
      </p>
      {status.errors.length > 0 && (
        <div>
          <strong>Errors:</strong>
          <ul>
            {status.errors.map((entry, index) => (
              <li key={`${entry}-${index}`}>{entry}</li>
            ))}
          </ul>
        </div>
      )}
      {error && <p className="run-control__error">{error}</p>}
      <button onClick={handleCancel} disabled={!isCancelable || isCancelling}>
        {isCancelling ? 'Cancelling…' : 'Cancel run'}
      </button>
    </div>
  )
}

export default RunControl
