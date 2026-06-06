import { FileText, Link } from 'lucide-react'
import { SourceChunk } from '../types'

interface Props {
  chunks: SourceChunk[]
}

export default function RightPanel({ chunks }: Props) {
  if (!chunks.length) {
    return (
      <div className="w-64 bg-right-bg border-l border-sidebar-border h-full flex flex-col items-center justify-center text-center px-6">
        <Link className="w-8 h-8 text-neutral-700 mb-3" />
        <p className="text-xs text-neutral-600 leading-relaxed">
          知识来源将在这里显示。提问后，相关的教材段落会自动出现在这里。
        </p>
      </div>
    )
  }

  return (
    <div className="w-64 bg-right-bg border-l border-sidebar-border h-full flex flex-col">
      <div className="px-4 py-3 border-b border-sidebar-border">
        <h3 className="text-sm font-medium text-white flex items-center gap-2">
          <Link className="w-4 h-4 text-accent" />
          知识来源
        </h3>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {chunks.map((chunk, i) => (
          <div
            key={i}
            className="rounded-xl bg-neutral-900/80 backdrop-blur border border-neutral-800/60
              p-3 text-xs animate-fade-in"
            style={{ animationDelay: `${i * 50}ms` }}
          >
            <div className="flex items-center gap-1.5 text-neutral-500 mb-1.5">
              <FileText className="w-3 h-3 flex-shrink-0" />
              <span className="font-medium text-neutral-300 truncate">{chunk.file}</span>
            </div>
            {chunk.page && (
              <span className="inline-block px-1.5 py-0.5 rounded bg-accent/10 text-accent-hover text-xs font-mono mb-1.5">
                {chunk.page}
              </span>
            )}
            {chunk.heading && (
              <p className="text-neutral-400 leading-relaxed mt-1">{chunk.heading}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
