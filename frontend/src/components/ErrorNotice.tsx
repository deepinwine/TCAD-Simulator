interface ErrorNoticeProps {
  title: string;
  message: string;
  parameterPath?: string;
  suggestion?: string;
  rolledBack?: boolean;
  actionLabel?: string;
  onAction?(): void;
}

export function ErrorNotice({
  title,
  message,
  parameterPath,
  suggestion,
  rolledBack,
  actionLabel,
  onAction,
}: ErrorNoticeProps) {
  return (
    <div className="error-notice" role="alert">
      <span className="error-mark" aria-hidden="true">!</span>
      <div>
        <h2>{title}</h2>
        <p>{message}</p>
        {parameterPath && <p>参数路径：{parameterPath}</p>}
        {suggestion && <p>建议：{suggestion}</p>}
        {rolledBack === false && (
          <p className="rollback-warning">模型未回滚，状态可能已改变</p>
        )}
        {rolledBack === true && (
          <p className="rollback-confirmation">服务端报告：本次失败已回滚</p>
        )}
        {actionLabel !== undefined && onAction !== undefined && (
          <button type="button" onClick={onAction}>{actionLabel}</button>
        )}
      </div>
    </div>
  );
}
