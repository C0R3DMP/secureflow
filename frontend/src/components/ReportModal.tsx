import { useEffect, useRef } from 'react'
import { Download, X } from 'lucide-react'

interface ReportModalProps {
  report: string
  target: string
  onClose: () => void
  onDownload: () => void
}

/**
 * In-app preview of the generated HTML report.
 *
 * The report is rendered inside a sandboxed iframe: it is model-generated
 * markup describing a scan of an untrusted target, so it must not be able to
 * run script against the dashboard's origin (where the API token lives).
 */
export function ReportModal({ report, target, onClose, onDownload }: ReportModalProps) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`Security report for ${target}`}
      onClick={onClose}
    >
      <div
        className="panel flex h-full max-h-[88vh] w-full max-w-5xl flex-col shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="panel-header">
          <div className="min-w-0">
            <h2 className="panel-title">Assessment report</h2>
            <p className="truncate font-mono text-xs text-muted">{target}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button onClick={onDownload} className="btn btn-secondary">
              <Download className="h-4 w-4" aria-hidden="true" />
              Download
            </button>
            <button
              ref={closeRef}
              onClick={onClose}
              className="icon-btn"
              aria-label="Close report"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>

        <iframe
          title={`Security report for ${target}`}
          srcDoc={report}
          // No allow-scripts and no allow-same-origin: the report is inert.
          sandbox=""
          className="min-h-0 flex-1 rounded-b-[0.625rem] bg-white"
        />
      </div>
    </div>
  )
}
