"use client";
import { useState, useRef } from "react";
import { Search, Upload, X, Loader2, AlertCircle, Car } from "lucide-react";
import Navbar from "@/components/ui/Navbar";
import { search as searchApi } from "@/lib/api";
import type { SearchResult } from "@/lib/api";
import clsx from "clsx";

type Mode = "text" | "image";

export default function SearchPage() {
  const [mode, setMode]           = useState<Mode>("text");
  const [query, setQuery]         = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImgPrev]= useState<string | null>(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");
  const [results, setResults]     = useState<SearchResult[] | null>(null);
  const [identified, setIdentified] = useState<Record<string, unknown> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleImageSelect = (file: File) => {
    setImageFile(file);
    setImgPrev(URL.createObjectURL(file));
    setMode("image");
  };

  const handleSearch = async () => {
    if (mode === "text" && !query.trim()) return;
    if (mode === "image" && !imageFile) return;

    setLoading(true);
    setError("");
    setResults(null);
    setIdentified(null);

    try {
      if (mode === "image" && imageFile) {
        const res = await searchApi.byImage(imageFile);
        setResults(res.results);
        setIdentified(res.identified_part);
      } else {
        const res = await searchApi.byText(query);
        setResults(res.results);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "搜索失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">零配件智能搜索</h1>
          <p className="text-gray-500 text-sm">上传零件图片或输入描述，AI 自动匹配商品</p>
        </div>

        {/* Mode tabs */}
        <div className="flex gap-1 p-1 bg-gray-100 rounded-xl mb-4 w-fit mx-auto">
          {(["text", "image"] as Mode[]).map(m => (
            <button key={m} onClick={() => setMode(m)}
              className={clsx(
                "px-5 py-2 rounded-lg text-sm font-medium transition-all",
                mode === m ? "bg-white shadow text-gray-900" : "text-gray-500 hover:text-gray-700"
              )}>
              {m === "text" ? "🔤 文字搜索" : "📷 图片搜索"}
            </button>
          ))}
        </div>

        {/* Search box */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-4 mb-6">
          {mode === "text" ? (
            <div className="flex gap-3">
              <Search className="w-5 h-5 text-gray-400 flex-shrink-0 mt-2.5" />
              <textarea
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSearch(); } }}
                placeholder="例如：丰田凯美瑞 2020 前刹车片，陶瓷材质..."
                rows={2}
                className="flex-1 resize-none text-sm text-gray-800 placeholder-gray-400 focus:outline-none"
              />
            </div>
          ) : (
            <div
              onClick={() => fileRef.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleImageSelect(f); }}
              className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-brand-400 hover:bg-brand-50 transition-colors"
            >
              {imagePreview ? (
                <div className="relative inline-block">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={imagePreview} alt="preview" className="max-h-40 rounded-lg mx-auto" />
                  <button onClick={e => { e.stopPropagation(); setImageFile(null); setImgPrev(null); }}
                    className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-0.5">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ) : (
                <>
                  <Upload className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                  <p className="text-sm text-gray-500">点击上传或拖拽零件图片</p>
                  <p className="text-xs text-gray-400 mt-1">支持 JPG、PNG、WebP</p>
                </>
              )}
              <input ref={fileRef} type="file" accept="image/*" className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) handleImageSelect(f); }} />
            </div>
          )}

          <div className="flex justify-end mt-3">
            <button onClick={handleSearch} disabled={loading}
              className="bg-brand-500 hover:bg-brand-600 disabled:opacity-60 text-white px-6 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              {loading ? "搜索中..." : "搜索"}
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 bg-red-50 text-red-600 px-4 py-3 rounded-xl mb-4 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Vision identification result */}
        {identified && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4 text-sm">
            <div className="font-medium text-blue-800 mb-1">AI 识别结果</div>
            <div className="text-blue-700">
              零件类型：<strong>{String(identified.part_name ?? "-")}</strong>
              {identified.brand_visible && ` · 品牌：${identified.brand_visible}`}
              {identified.identification_confidence && (
                ` · 置信度：${(Number(identified.identification_confidence) * 100).toFixed(0)}%`
              )}
            </div>
            {Array.isArray(identified.search_terms) && (
              <div className="mt-1 flex flex-wrap gap-1">
                {(identified.search_terms as string[]).map(t => (
                  <span key={t} className="bg-blue-100 text-blue-600 px-2 py-0.5 rounded text-xs">{t}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Results */}
        {results !== null && (
          <div>
            <div className="text-sm text-gray-500 mb-3">
              找到 <strong>{results.length}</strong> 个匹配结果
            </div>
            {results.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <Search className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p>未找到匹配的零件，请尝试调整搜索词</p>
              </div>
            ) : (
              <div className="space-y-3">
                {results.map(r => <ProductCard key={r.id} product={r} />)}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function ProductCard({ product }: { product: SearchResult }) {
  const relevancePct = Math.round(product.relevance_score * 100);
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md transition-shadow">
      <div className="flex gap-4">
        {/* Image placeholder */}
        <div className="w-16 h-16 bg-gray-100 rounded-lg flex-shrink-0 flex items-center justify-center overflow-hidden">
          {product.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={product.image_url} alt={product.name} className="w-full h-full object-cover" />
          ) : (
            <span className="text-2xl">🔧</span>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 flex-wrap">
            <div>
              <h3 className="font-medium text-gray-900 text-sm">{product.name}</h3>
              <div className="text-xs text-gray-400 font-mono mt-0.5">{product.part_number}</div>
            </div>
            <div className="flex flex-col items-end gap-1 flex-shrink-0">
              {product.price != null && (
                <div className="text-brand-600 font-semibold text-sm">¥{product.price.toFixed(2)}</div>
              )}
              <span className={clsx(
                "text-xs px-2 py-0.5 rounded-full font-medium",
                product.in_stock ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
              )}>
                {product.in_stock ? `库存 ${product.stock}` : "暂无库存"}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3 mt-2 flex-wrap">
            {product.brand && (
              <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{product.brand}</span>
            )}
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{product.category}</span>
            <span className="text-xs text-gray-400">相关度 {relevancePct}%</span>
          </div>

          {product.compatible_vehicles.length > 0 && (
            <div className="flex items-center gap-1 mt-2 text-xs text-gray-500">
              <Car className="w-3 h-3" />
              {product.compatible_vehicles.slice(0, 2).map((v, i) => (
                <span key={i}>{v.make} {v.model} {v.year_from}-{v.year_to}</span>
              ))}
              {product.compatible_vehicles.length > 2 && <span>等 {product.compatible_vehicles.length} 款</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
