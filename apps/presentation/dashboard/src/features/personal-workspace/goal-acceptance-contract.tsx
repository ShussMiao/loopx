import type { GoalAcceptanceContract } from "../../data/goal-acceptance-observation";
import type { GoalAcceptanceContractCopy } from "./delivery-review-copy";

/** Present owner-projected states without deriving acceptance or task readiness. */
export function GoalAcceptanceContractSection({ goalId, contract, copy, current }: {
  goalId: string; contract?: GoalAcceptanceContract; copy: GoalAcceptanceContractCopy; current: boolean;
}) {
  if (contract?.enabled !== true) return null;
  const inspectCommand = `loopx --format json goal-acceptance inspect --goal-id '${goalId.replace(/'/g, "'\\''")}'`;
  return <details className="delivery-acceptance-contract">
    <summary>{copy.title}</summary>
    <div className="delivery-acceptance-content">
      <p>{copy.boundary}</p>
      {!current ? <p role="status" className="delivery-notice">{copy.retained}</p> : null}
      <dl className="delivery-acceptance-source">
        <div><dt>{copy.source}</dt><dd><code>{goalId}</code></dd></div>
        <div><dt>{copy.scope}</dt><dd>{contract.scope?.kind === "selected_work" ? copy.selectedWork : copy.allWork}</dd></div>
        <div><dt>{copy.revision}</dt><dd>{contract.revision}</dd></div>
        <div><dt>{copy.digest}</dt><dd><code>{contract.digest}</code></dd></div>
      </dl>
      <h3>{copy.objective}</h3><p>{contract.objective || copy.unknown}</p>
      {contract.non_goals.length ? <><h3>{copy.nonGoals}</h3><ul>{contract.non_goals.map((item, index) => <li key={index}>{item}</li>)}</ul></> : null}
      <h3>{copy.criteria}</h3>
      {contract.criteria.length ? <ul>{contract.criteria.map(criterion => <li key={criterion.id}><code>{criterion.id}</code> · {criterion.description}</li>)}</ul> : <p>{copy.noCriteria}</p>}
      <h3>{copy.tasks}</h3>
      {contract.tasks.length ? <ul className="delivery-acceptance-tasks">{contract.tasks.map(task => <li key={task.todo_id}>
        <p><code>{task.todo_id}</code> · <strong>{copy.taskState[task.state]}</strong></p>
        <p>{copy.criteria}: {task.criterion_ids.length ? task.criterion_ids.join(", ") : copy.unknown}</p>
        {task.applicable === false ? <p>{copy.notApplicable}</p> : null}
        {task.reason ? <p>{task.reason}</p> : null}
      </li>)}</ul> : <p>{copy.noTasks}</p>}
      <h3>{copy.verification}</h3>
      <p>{copy.verificationState[contract.status]}</p>
      {contract.held_todo_ids.length ? <p>{copy.heldTasks}: {contract.held_todo_ids.join(", ")}</p> : null}
      <details><summary>{copy.receipt}</summary>
        {!contract.verification ? <p>{copy.unknown}</p> : <>
          <p>{copy.receiptNote}</p>
          <dl className="delivery-acceptance-source">
            <div><dt>{copy.operation}</dt><dd><code>{contract.verification.operation_id}</code></dd></div>
            <div><dt>{copy.revision}</dt><dd>{contract.verification.contract_revision}</dd></div>
            <div><dt>{copy.digest}</dt><dd><code>{contract.verification.contract_digest}</code></dd></div>
            <div><dt>{copy.verificationScope}</dt><dd>{contract.verification.todo_id ?? copy.allCriteria}</dd></div>
          </dl>
          <ul>{contract.verification.results.map(result => <li key={result.criterion_id}>
            <code>{result.criterion_id}</code> · {result.passed ? copy.passed : copy.failed} · {copy.exitCode}: {result.exit_code ?? copy.unknown}
          </li>)}</ul>
        </>}
      </details>
      <details><summary>{copy.help}</summary><p>{copy.guidance}</p>
        <p><code>{inspectCommand}</code></p><p><code>loopx goal-acceptance --help</code></p>
        <a href="https://github.com/huangruiteng/loopx/blob/main/docs/reference/goal-acceptance-observations.md#owner-authorized-contract-v0" target="_blank" rel="noreferrer">{copy.guide}</a>
      </details>
    </div>
  </details>;
}
