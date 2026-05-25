"use client";
import { useState, useEffect, useRef } from "react";
import { Upload, FileText, Trash2, RefreshCw, Loader2, CheckCircle, XCircle, Clock } from "lucide-react";
import Navbar from "@/components/ui/Navbar";
import { admin as adminApi } from "@/lib/api";
import type { AnalyticsOverview, Document } from "@/lib/api";
import clsx from "clsx";

export default function AdminPage() {
  const [overview, setOverview]   = useState<AnalyticsOverview | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadData = async () => {
    const [ov, docs] = await Promise.all([
      adminApi.overview().catch(() => null),
      adminApi.documents().catch(() => []),
    ]);
    if (ov) setOverview(ov);
    setDocuments(docs);
  };

  useEffect(() => { loadData(); }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setUploadStatus(null);
    try {
      const res = await adminApi.uploadDocument(file);
      setUploadStatus(`✅ 上传成功，正在处理... (ID: ${res.document_id.slice(0, 8)})`);
      // Poll status
      const poll = setInterval(async () => {
        const status = await adminApi.documentStatus(res.document_id).catch(() => null);
        if (status?.status === "completed") {
          setUploadStatus(`✅ 处理完成，共 ${status.chunk_count} 个文本块`);
          clearInterval(poll);
          loadData();
        } else if (status?.status === "failed") {
          setUploadStatus(`❌ 处理失败：${status.error_message}`);
          clearInterval(poll);
        }
      }, 2500);
      setTimeout(() => clearInterval(poll), 120000); // max 2min
    } catch (e) {
      setUploadStatus(`❌ 上传失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确认删除此文档及其所有内容？")) return;
    await adminApi.deleteDocument(id);
    loadData();
  };

  const statusIcon = (status: string) => {
    if (status === "completed") return <CheckCircle className="w-4 h-4 text-green-500" />;
    if (status === "failed")    return <XCircle className="w-4 h-4 text-red-500" />;
    return <Clock className="w-4 h-4 text-yellow-500 animate-pulse" />;
  };

  const MetricCard = ({ label, value, sub }: { label: string; value: string | number; sub?: string }) => (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900">管理控制台</h1>
          <button onClick={loadData} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700">
            <RefreshCw className="w-4 h-4" /> 刷新
          </button>
        </div>

        {/* Metrics */}
        {overview && (
          <div>
            <h2 className="text-sm font-medium text-gray-500 mb-3">过去 7 天概览</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="总查询次数" value={overview.total_queries} />
              <MetricCard
                label="平均置信度"
                value={overview.avg_confidence != null ? `${(overview.avg_confidence * 100).toFixed(1)}%` : "—"}
              />
              <MetricCard
                label="用户满意度"
                value={overview.feedback.satisfaction_rate != null
                  ? `${(overview.feedback.satisfaction_rate * 100).toFixed(0)}%`
                  : "—"}
                sub={`👍 ${overview.feedback.thumbs_up}  👎 ${overview.feedback.thumbs_down}`}
              />
              <MetricCard
                label="知识库"
                value={overview.knowledge_base.total_products}
                sub={`${overview.knowledge_base.documents_indexed} 份文档已索引`}
              />
            </div>
          </div>
        )}

        {/* Document upload */}
        <div>
          <h2 className="text-sm font-medium text-gray-500 mb-3">知识库文档</h2>
          <div className="bg-white border border-gray-200 rounded-xl p-4 mb-3">
            <div
              onClick={() => fileRef.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleUpload(f); }}
              className="border-2 border-dashed border-gray-200 rounded-lg p-6 text-center cursor-pointer hover:border-brand-400 hover:bg-brand-50 transition-colors"
            >
              {uploading
                ? <Loader2 className="w-6 h-6 text-brand-400 animate-spin mx-auto mb-2" />
                : <Upload className="w-6 h-6 text-gray-300 mx-auto mb-2" />
              }
              <p className="text-sm text-gray-500">
                {uploading ? "上传中..." : "点击或拖拽上传 PDF / Word 文档"}
              </p>
              <input ref={fileRef} type="file" accept=".pdf,.docx" className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f); }} />
            </div>
            {uploadStatus && (
              <div className="mt-3 text-sm text-gray-600 bg-gray-50 px-3 py-2 rounded-lg">
                {uploadStatus}
              </div>
            )}
          </div>

          {/* Document list */}
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            {documents.length === 0 ? (
              <div className="text-center py-10 text-gray-400 text-sm">
                <FileText className="w-8 h-8 mx-auto mb-2 opacity-30" />
                暂无文档，上传 PDF 或 Word 文档到知识库
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">文件名</th>
                    <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">状态</th>
                    <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">分块数</th>
                    <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">大小</th>
                    <th className="px-4 py-2.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {documents.map(doc => (
                    <tr key={doc.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-800 truncate max-w-xs">
                        {doc.filename}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          {statusIcon(doc.status)}
                          <span className={clsx(
                            "text-xs",
                            doc.status === "completed" ? "text-green-600"
                            : doc.status === "failed" ? "text-red-500"
                            : "text-yellow-600"
                          )}>
                            {doc.status === "completed" ? "已完成"
                            : doc.status === "failed" ? "失败"
                            : doc.status === "processing" ? "处理中"
                            : "等待中"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-500">{doc.chunk_count || "—"}</td>
                      <td className="px-4 py-3 text-gray-500 text-xs">
                        {(doc.size_bytes / 1024).toFixed(0)} KB
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => handleDelete(doc.id)}
                          className="text-red-400 hover:text-red-600 transition-colors p-1">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
