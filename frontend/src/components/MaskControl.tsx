import {useRef, useState} from 'react';
import {useAppState} from '../state/AppStateContext';
import {useI18n} from '../i18n/I18nContext';

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
  const {t} = useI18n();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [previewNonce, setPreviewNonce] = useState(0);
  const [previewFailed, setPreviewFailed] = useState(false);
  const hasMask = maskName !== undefined && maskName !== '';

  return (
    <div className="mask-control" role="group" aria-label={t('mask.group')}>
      <div className="mask-current">
        {t('mask.current')}<strong>{hasMask ? maskName : t('mask.unset')}</strong>
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        {t('mask.upload')}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,.png,.jpg,.jpeg,.bmp,.npy"
        aria-label={t('mask.file')}
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
          alt={t('mask.previewAlt', {step: stepIndex + 1})}
          src={`/api/mask/preview_step?step_index=${stepIndex}&t=${previewNonce}`}
          onError={() => setPreviewFailed(true)}
        />
      )}
      {hasMask && previewFailed && (
        <p className="mask-preview-error" role="status">{t('mask.previewUnavailable')}</p>
      )}
    </div>
  );
}
