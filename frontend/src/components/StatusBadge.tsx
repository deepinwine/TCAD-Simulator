import type {RuntimeStatus} from '../api/types';

const STATUS_COPY: Record<RuntimeStatus, string> = {
  ready: '就绪 Ready',
  dirty: '已修改 Dirty',
  running: '运行中 Running',
  done: '完成 Done',
  error: '错误 Error',
};

interface StatusBadgeProps {
  status: RuntimeStatus;
}

export function StatusBadge({status}: StatusBadgeProps) {
  const copy = STATUS_COPY[status];
  return (
    <span className={`status-badge status-${status}`} aria-label={`状态：${copy}`}>
      <span className="status-dot" aria-hidden="true" />
      {copy}
    </span>
  );
}
