import type { PolicyDecisionRecord } from '../types/controllerStudio'
import { prettyValue } from '../utils/format'

type PolicyPanelProps = {
  policyDecisions: PolicyDecisionRecord[]
}

const PolicyPanel = ({ policyDecisions }: PolicyPanelProps) => {
  const allowedCount = policyDecisions.filter((entry) => entry.allowed).length
  const deniedCount = policyDecisions.length - allowedCount

  return (
    <div className="policy-panel">
      <div className="policy-panel__header">
        <h3>Policy explanation</h3>
        <p className="policy-panel__summary">
          {policyDecisions.length
            ? `${allowedCount} allowed, ${deniedCount} denied`
            : 'No policy decisions yet.'}
        </p>
      </div>
      <ul className="policy-panel__list">
        {policyDecisions.length ? (
          policyDecisions.map((decision) => (
            <li
              key={decision.effect}
              className={`policy-panel__entry ${decision.allowed ? 'allowed' : 'denied'}`}
            >
              <div className="policy-panel__entry-meta">
                <strong>{decision.effect}</strong>
                <span>{prettyValue(decision.target)}</span>
              </div>
              <p>
                <span className="policy-panel__status">
                  {decision.allowed ? 'Allowed' : 'Denied'}
                </span>{' '}
                {decision.reason}
              </p>
            </li>
          ))
        ) : (
          <li className="hint">Preview a plan to populate policy decisions.</li>
        )}
      </ul>
    </div>
  )
}

export default PolicyPanel
