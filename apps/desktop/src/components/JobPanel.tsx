import type { JobProgressView } from "../types";
import { uiText } from "../uiText";

type JobPanelProps = {
  jobs: JobProgressView[];
  onCancel: (job: JobProgressView) => void;
  onDismiss: (jobId: string) => void;
};

function stateLabel(state: JobProgressView["state"]): string {
  switch (state) {
    case "queued":
      return "待機中";
    case "starting":
      return "開始中";
    case "running":
      return "実行中";
    case "cancelling":
      return "停止中";
    case "cancelled":
      return "中断済み";
    case "completed":
      return "完了";
    case "failed":
      return "失敗";
    default:
      return state;
  }
}

function stageLabel(stage: string): string {
  return (uiText.jobStages as Record<string, string>)[stage] ?? stage;
}

const TERMINAL_STATES: ReadonlySet<JobProgressView["state"]> = new Set([
  "completed",
  "cancelled",
  "failed",
]);

export function JobPanel(props: JobPanelProps) {
  if (!props.jobs.length) return null;

  return (
    <section className="job-panel" aria-label="Job progress panel">
      <div className="job-panel__header">
        <strong>{uiText.jobs.panelTitle}</strong>
      </div>
      <div className="job-panel__list">
        {props.jobs.map((job) => {
          const progressWidth = job.is_indeterminate ? "45%" : `${job.progress_percent ?? 0}%`;
          const isTerminal = TERMINAL_STATES.has(job.state);
          return (
            <article key={job.job_id} className={`job-card job-card--${job.state}`}>
              <div className="job-card__topline">
                <div>
                  <div className="job-card__title">{job.title}</div>
                  <div className="job-card__stage">{stageLabel(job.stage)}</div>
                </div>
                <div className="job-card__topline-right">
                  <span className={`job-card__badge job-card__badge--${job.state}`}>{stateLabel(job.state)}</span>
                  {isTerminal && (
                    <button
                      className="job-card__dismiss"
                      aria-label="通知を閉じる"
                      title="閉じる"
                      onClick={() => props.onDismiss(job.job_id)}
                    >
                      ×
                    </button>
                  )}
                </div>
              </div>
              <div className="job-card__message">{job.message}</div>
              <div className={`job-card__progress ${job.is_indeterminate ? "job-card__progress--indeterminate" : ""}`}>
                <div className="job-card__progress-fill" style={{ width: progressWidth }} />
              </div>
              <div className="job-card__footer">
                <span>{job.is_indeterminate ? uiText.jobs.indeterminate : `${job.progress_percent ?? 0}%`}</span>
                <span>{job.subtitle}</span>
                {job.can_cancel ? (
                  <button className="nle-btn nle-btn--small nle-btn--cancel" onClick={() => props.onCancel(job)}>
                    {uiText.actions.cancel}
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
