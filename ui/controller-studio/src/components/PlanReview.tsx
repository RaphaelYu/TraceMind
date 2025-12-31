import type { ArtifactDocument, ArtifactDiffResponse } from '../api/tm'
import type { PolicyDecisionRecord } from '../types/controllerStudio'
import { prettyValue } from '../utils/format'

type PlanDecision = {
  effect_ref?: string
  target_state?: Record<string, unknown>
  idempotency_key?: string
}

type EffectMetadata = {
  target: string
  rollback?: string | null
}

type PlanReviewProps = {
  planDoc: ArtifactDocument | null
  bundleDoc: ArtifactDocument | null
  executionDoc: ArtifactDocument | null
  diffData: ArtifactDiffResponse | null
  policyDecisions: PolicyDecisionRecord[]
}

const buildEffectMetadata = (bundleDoc: ArtifactDocument | null): Map<string, EffectMetadata> => {
  const effects = new Map<string, EffectMetadata>()
  const agents = bundleDoc?.body?.agents
  if (!Array.isArray(agents)) {
    return effects
  }
  for (const agent of agents) {
    const contract = agent?.contract
    if (!contract || !Array.isArray(contract.effects)) {
      continue
    }
    for (const effect of contract.effects) {
      const target = typeof effect?.target === 'string' ? effect.target : null
      if (!target) {
        continue
      }
      effects.set(target, {
        target,
        rollback: typeof effect.rollback === 'string' ? effect.rollback : undefined,
      })
    }
  }
  return effects
}

const PlanReview = ({ planDoc, bundleDoc, executionDoc, diffData, policyDecisions }: PlanReviewProps) => {
  const decisions: PlanDecision[] = Array.isArray(planDoc?.body?.decisions)
    ? (planDoc?.body?.decisions as PlanDecision[])
    : []
  const metadata = buildEffectMetadata(bundleDoc)
  const policyByEffect = new Map(policyDecisions.map((decision) => [decision.effect, decision]))

  const effectRows =
    decisions.length > 0
      ? decisions.map((decision, index) => {
          const effectRef =
            typeof decision.effect_ref === 'string'
              ? decision.effect_ref
              : `decision-${index.toString().padStart(2, '0')}`
          const effectInfo = metadata.get(effectRef)
          const policy = policyByEffect.get(effectRef)
          return {
            key: `${effectRef}-${decision.idempotency_key ?? index}`,
            target: effectInfo?.target ?? effectRef,
            params: prettyValue(decision.target_state),
            idempotency: decision.idempotency_key ?? '—',
            rollback: effectInfo?.rollback ?? 'not provided',
            policy,
          }
        })
      : []

  return (
    <div className="plan-review-card">
      <div className="plan-review__header">
        <div>
          <h4>Plan overview</h4>
          <p>
            <strong>ID:</strong> {prettyValue(planDoc?.body?.plan_id)}
          </p>
          <p>
            <strong>Summary:</strong> {prettyValue(planDoc?.body?.summary)}
          </p>
        </div>
        <div>
          <h4>Snapshot reference</h4>
          <p>
            {prettyValue(planDoc?.body?.snapshot_id)} → {prettyValue(planDoc?.body?.plan_id)}
          </p>
        </div>
      </div>

      <section className="effect-table">
        <div className="effect-table__row effect-table__row--head">
          <span>Target</span>
          <span>Params</span>
          <span>Idempotency</span>
          <span>Rollback hint</span>
          <span>Policy</span>
        </div>
        {effectRows.length ? (
          effectRows.map((entry) => (
            <div key={entry.key} className="effect-table__row">
              <span>{entry.target}</span>
              <span>{entry.params}</span>
              <span>{entry.idempotency}</span>
              <span>{entry.rollback}</span>
              <span className="effect-table__policy">
                <span className={`policy-chip ${entry.policy?.allowed ? 'allowed' : 'denied'}`}>
                  {entry.policy?.allowed ? 'Allowed' : 'Denied'}
                </span>
                <small>{entry.policy?.reason ?? 'pending policy review'}</small>
              </span>
            </div>
          ))
        ) : (
          <p className="hint">No effect decisions available yet; run a preview cycle to generate a plan.</p>
        )}
      </section>

      <div className="evidence-summary">
        <h4>Evidence summary</h4>
        <div className="evidence-list">
          {executionDoc?.body?.artifacts ? (
            Object.entries(executionDoc.body.artifacts as Record<string, unknown>).map(
              ([agent, evidence]) => (
                <p key={agent}>
                  <strong>{agent}:</strong> {prettyValue(evidence)}
                </p>
              ),
            )
          ) : (
            <p>No execution evidence captured yet.</p>
          )}
        </div>
      </div>

      <div className="diff-table">
        <h4>Snapshot ↔ Plan diff</h4>
        {diffData && diffData.diff.length ? (
          <>
            <div className="diff-table-header">
              <span>Path</span>
              <span>Action</span>
              <span>Snapshot</span>
              <span>Plan</span>
            </div>
            {diffData.diff.map((row) => (
              <div key={`${row.path}-${row.kind}`} className="diff-row diff-row--compact">
                <span>{row.path}</span>
                <span>{row.kind}</span>
                <span>{prettyValue(row.base)}</span>
                <span>{prettyValue(row.compare)}</span>
              </div>
            ))}
          </>
        ) : (
          <p className="hint">Run a preview cycle to inspect the diff between the snapshot and proposed plan.</p>
        )}
      </div>
    </div>
  )
}

export default PlanReview
