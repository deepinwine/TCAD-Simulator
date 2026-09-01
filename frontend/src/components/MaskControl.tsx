import {useRef, useState} from 'react';
import {useAppState} from '../state/AppStateContext';

/**
 * Exposure 步骤的掩膜控件：上传（multipart）+ 服务端预览图。
 * 上传成功后嵌套 set_step 结果由状态层应用（mask_name 等参数即时更新）。
 */
export function MaskControl({
  stepIndex,
  maskName,
  disabled,
}: {
  stepIndex: number;
  maskName: string | undefined;
  disabled: boolean;
}) {
  const {actions} = useAppState();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [previewNonce, setPreviewNonce] = useState(0);
  const [previewFailed, setPreviewFailed] = useState(false);
  const hasMask = maskName !== undefined && maskName !== '';

  return (
    <div className="mask-control" role="group" aria-label="掩膜">
      <div className="mask-current">
        当前掩膜：<strong>{hasMask ? maskName : '未设置（将自动生成）'}</strong>
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        上传掩膜
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,.png,.jpg,.jpeg,.bmp,.npy"
        aria-label="掩膜文件"
        className="visually-hidden"
        onChange={event => {
          const file = event.target.files?.[0];
          if (file !== undefined) {
            void actions.uploadMask(file).then(() => {
              setPreviewNonce(value => value + 1);
              setPreviewFailed(false);
            });
          }
          event.target.value = '';
        }}
      />
      {hasMask && !previewFailed && (
        <img
          className="mask-preview"
          alt={`步骤 ${stepIndex + 1} 掩膜预览`}
          src={`/api/mask/preview_step?step_index=${stepIndex}&t=${previewNonce}`}
          onError={() => setPreviewFailed(true)}
        />
      )}
      {hasMask && previewFailed && (
        <p className="mask-preview-error" role="status">掩膜预览暂不可用</p>
      )}
    </div>
  );
}
