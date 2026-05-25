import { ExternalLink, Package } from "lucide-react";
import type { SourceReference } from "@/lib/api";

interface Props { source: SourceReference }

export default function SourceCard({ source }: Props) {
  return (
    <div className="flex items-start gap-2 p-2.5 bg-gray-50 border border-gray-200 rounded-lg text-xs">
      <Package className="w-3.5 h-3.5 text-brand-500 flex-shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="font-medium text-gray-800 truncate">{source.name}</div>
        {source.part_number && (
          <div className="text-gray-400 font-mono">{source.part_number}</div>
        )}
        <div className="mt-1 flex items-center gap-2">
          <span className="text-gray-400">
            相关度 {(source.relevance * 100).toFixed(0)}%
          </span>
          {source.url && (
            <a href={source.url} target="_blank" rel="noopener noreferrer"
               className="text-brand-500 hover:underline flex items-center gap-0.5">
              查看 <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
