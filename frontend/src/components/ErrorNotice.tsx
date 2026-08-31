interface ErrorNoticeProps {
  title: string;
  message: string;
  actionLabel?: string;
  onAction?(): void;
}

export function ErrorNotice({title, message, actionLabel, onAction}: ErrorNoticeProps) {
  return (
    <div className="error-notice" role="alert">
      <span className="error-mark" aria-hidden="true">!</span>
      <div>
        <h2>{title}</h2>
        <p>{message}</p>
        {actionLabel !== undefined && onAction !== undefined && (
          <button type="button" onClick={onAction}>{actionLabel}</button>
        )}
      </div>
    </div>
  );
}
